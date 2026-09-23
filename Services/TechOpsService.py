from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

import pandas as pd

from Services.GenAIService import GenAIService


TECHOPS_COLUMNS = [
    "EnterpriseId",
    "CL",
    "Primary Skill",
    "Primary Skill Competency",
    "Secondary Skill",
    "Availability",
    "RDTFunction(RDT-1)",
    "RDTSubfunction(RDT-2)",
    "Supervisor",
    "RollonDate",
    "Country",
    "City",
    "ContractStartDate",
    "ContractEndDate",
]

DISPLAY_COLUMNS = [
    "MatchScore",
    "MatchedFields",
    "EnterpriseId",
    "CL",
    "Primary Skill",
    "Primary Skill Competency",
    "Secondary Skill",
    "Availability",
    "RDTFunction(RDT-1)",
    "RDTSubfunction(RDT-2)",
    "Supervisor",
    "RollonDate",
    "Country",
    "City",
    "ContractStartDate",
    "ContractEndDate",
]


class TechOpsService:
    """Loads and searches the PMO TechOps resource workbook."""

    def __init__(self, file_path: str | Path | None = None):
        self.file_path = Path(file_path) if file_path else (
            Path(__file__).resolve().parents[1] / "Data" / "TechOps_DataFile.xlsx"
        )
        self._data: pd.DataFrame | None = None
        self.last_intent_source = "deterministic_fallback"

    def load_data(self) -> pd.DataFrame:
        if self._data is None:
            if not self.file_path.exists():
                raise FileNotFoundError(
                    f"TechOps data file was not found: {self.file_path}"
                )

            data = pd.read_excel(self.file_path, engine="openpyxl")
            missing = [column for column in TECHOPS_COLUMNS if column not in data.columns]
            if missing:
                raise ValueError(
                    "TechOps workbook is missing required columns: "
                    + ", ".join(missing)
                )

            self._data = data[TECHOPS_COLUMNS].copy()
            for column in TECHOPS_COLUMNS:
                self._data[column] = self._data[column].where(
                    self._data[column].notna(), ""
                )

        return self._data.copy()

    def get_dataframe(self) -> pd.DataFrame:
        return self.load_data()

    def get_columns(self) -> list[str]:
        return TECHOPS_COLUMNS.copy()

    def detect_intent(self, prompt: str) -> str:
        """Use Azure OpenAI for intent detection with a deterministic fallback."""
        genai_intent = GenAIService.try_detect_intent(prompt)
        if genai_intent:
            self.last_intent_source = "azure_openai"
            return genai_intent

        self.last_intent_source = "deterministic_fallback"
        text = prompt.lower()
        if re.search(
            r"\b(?:build|create|compose|form|assemble)\s+(?:a\s+)?team\b|"
            r"\bteam\s+of\s+\d+",
            text,
        ):
            return "team_composition"
        return "resource_search"

    def team_composition(self, prompt: str) -> dict[str, Any]:
        """Build a deterministic, de-duplicated team from role requirements."""
        data = self.load_data()
        _, prompt_filters = self._parse_prompt_filters(data, prompt)
        requested_skills = self._requested_skills(data, prompt)
        role_requirements = self._team_role_requirements(data, prompt)
        if not role_requirements:
            role_requirements = [
                {"role": "resource", "quantity": 1, "skills": requested_skills}
            ]
        display_filters = dict(prompt_filters)
        role_filters = dict(prompt_filters)
        role_filters.pop("CL", None)
        role_filters.pop("career_level_operator", None)
        role_filters.pop("career_level_value", None)
        display_filters.pop("CL", None)
        display_filters.pop("career_level_operator", None)
        display_filters.pop("career_level_value", None)

        available = self._analysis_candidates(
            data,
            role_filters,
            require_current_or_future_availability=True,
        )
        available = available[
            ~available.apply(self._has_unavailable_skill, axis=1)
        ]
        selected_ids: set[str] = set()
        assignments: list[dict[str, Any]] = []
        gaps: list[dict[str, Any]] = []
        requested_slots = sum(
            requirement["quantity"] for requirement in role_requirements
        )
        if available.empty:
            gaps = [
                {
                    "role": requirement["role"],
                    "requested": requirement["quantity"],
                    "found": 0,
                    "shortfall": requirement["quantity"],
                }
                for requirement in role_requirements
            ]
            return {
                "mode": "team_composition",
                "requested_skills": requested_skills,
                "filters": self._analysis_filter_summary(display_filters),
                "requested_roles": [
                    {
                        "role": requirement["role"],
                        "quantity": requirement["quantity"],
                        "skills": requirement["skills"],
                        "career_level": requirement.get("career_level"),
                    }
                    for requirement in role_requirements
                ],
                "results": assignments,
                "gaps": gaps,
                "summary": (
                    f"Team requirement: {requested_slots} resource(s); "
                    "resources meeting requirements: 0; "
                    f"resources not meeting requirements: {requested_slots}. "
                    "Below required roles not found. There is gap. "
                    "Need to check outside TechOps."
                ),
            }
        for requirement in role_requirements:
            role = requirement["role"]
            quantity = requirement["quantity"]
            role_skills = requirement["skills"]
            role_tokens = {
                token for token in re.findall(r"[a-z0-9]+", role.lower())
                if len(token) > 2
            }
            role_mask = pd.Series(
                [
                    bool(
                        role_tokens
                        & set(
                            re.findall(
                                r"[a-z0-9]+",
                                f"{row['Primary Skill']} {row['Secondary Skill']}".lower(),
                            )
                        )
                    )
                    for _, row in available.iterrows()
                ],
                index=available.index,
                dtype=bool,
            )
            role_candidates = (
                available
                if role_skills
                else available[role_mask]
            )
            pool = role_candidates
            if role_skills:
                skill_mask = pd.Series(
                    [
                        all(
                            self._skill_matches_row(row, skill)
                            for skill in role_skills
                        )
                        for _, row in pool.iterrows()
                    ],
                    index=pool.index,
                    dtype=bool,
                )
                pool = pool[skill_mask]
            if requirement.get("career_level") is not None:
                pool = pool[
                    pool["CL"].astype(str).str.strip()
                    == str(requirement["career_level"])
                ]
            pool = pool[~pool["EnterpriseId"].astype(str).isin(selected_ids)]
            chosen = pool.head(quantity)
            for _, row in chosen.iterrows():
                resource = {
                    column: self._serialize_value(row[column], column)
                    for column in TECHOPS_COLUMNS
                }
                resource["RequestedRole"] = role
                resource["MatchScore"] = 100
                resource["MatchedFields"] = [
                    field for field in ("Primary Skill", "Secondary Skill")
                    if requested_skills and any(
                        self._skill_matches_row(row, skill)
                        for skill in requested_skills
                    )
                ]
                assignments.append(resource)
                selected_ids.add(str(row["EnterpriseId"]))
            if len(chosen) < quantity:
                gaps.append(
                    {
                        "role": role,
                        "requested": quantity,
                        "found": len(chosen),
                        "shortfall": quantity - len(chosen),
                    }
                )

        summary = (
            f"Team requirement: {requested_slots} resource(s); "
            f"resources meeting requirements: {len(assignments)}; "
            "resources not meeting requirements: 0. "
            "All requested roles are staffed."
            if not gaps
            else (
                f"Team requirement: {requested_slots} resource(s); "
                f"resources meeting requirements: {len(assignments)}; "
                f"resources not meeting requirements: "
                f"{sum(item['shortfall'] for item in gaps)}. "
                "Below required roles not found. There is gap. "
                "Need to check outside TechOps."
            )
        )
        return {
            "mode": "team_composition",
            "requested_skills": requested_skills,
            "filters": self._analysis_filter_summary(display_filters),
            "requested_roles": [
                {
                    "role": requirement["role"],
                    "quantity": requirement["quantity"],
                    "skills": requirement["skills"],
                    "career_level": requirement.get("career_level"),
                }
                for requirement in role_requirements
            ],
            "results": assignments,
            "gaps": gaps,
            "summary": summary,
        }

    def staffing_gap_analysis(self, prompt: str) -> dict[str, Any]:
        """Quantify current deterministic supply against a requested demand."""
        data = self.load_data()
        _, prompt_filters = self._parse_prompt_filters(data, prompt)
        requested_skills = self._requested_skills(data, prompt)
        requested_count = self._requested_quantity(prompt)
        asks_for_availability = bool(
            prompt_filters.get("available_only")
            or self._has_contract_date_filter(prompt_filters)
            or re.search(r"\bcapacity\b|\bcurrently\b", prompt, re.IGNORECASE)
        )
        available = self._analysis_candidates(
            data,
            prompt_filters,
            require_current_or_future_availability=asks_for_availability,
        )
        available = self._apply_career_filter(available, prompt_filters)
        if requested_skills:
            skill_mask = pd.Series(
                [
                    any(
                        self._skill_matches_row(row, skill)
                        for skill in requested_skills
                    )
                    for _, row in available.iterrows()
                ],
                index=available.index,
                dtype=bool,
            )
            matching = available[skill_mask]
        else:
            matching = available
        available_capacity = pd.to_numeric(
            matching["Availability"], errors="coerce"
        ).fillna(0)
        return {
            "mode": "staffing_gap_analysis",
            "requested_skills": requested_skills,
            "requested_quantity": requested_count,
            "available_supply": int(len(matching)),
            "capacity_percent": int(available_capacity.sum()),
            "shortfall": max(requested_count - len(matching), 0),
            "country_breakdown": {
                str(country): int(count)
                for country, count in matching["Country"].value_counts().items()
            },
            "skill_breakdown": self._skill_breakdown(matching),
            "filters": self._analysis_filter_summary(prompt_filters),
            "results": [
                {
                    **{
                        column: self._serialize_value(row[column], column)
                        for column in TECHOPS_COLUMNS
                    },
                    "MatchScore": 100,
                    "MatchedFields": self._matched_fields(row, requested_skills),
                }
                for _, row in matching.iterrows()
            ],
            "summary": self._gap_summary(
                matching_count=len(matching),
                requested_count=requested_count,
                has_future_date=self._has_contract_date_filter(prompt_filters),
                uses_availability=asks_for_availability,
            ),
        }

    @staticmethod
    def _gap_summary(
        matching_count: int,
        requested_count: int,
        has_future_date: bool,
        uses_availability: bool,
    ) -> str:
        if has_future_date:
            availability_label = "eligible resource(s) for the requested future date"
        elif uses_availability:
            availability_label = "currently available resource(s)"
        else:
            availability_label = "resource(s) in the current inventory"
        return (
            f"Found {matching_count} {availability_label} "
            f"against a requested quantity of {requested_count}."
        )

    @classmethod
    def _analysis_candidates(
        cls,
        data: pd.DataFrame,
        filters: dict[str, Any],
        require_current_or_future_availability: bool,
    ) -> pd.DataFrame:
        candidates = data.copy()
        if filters.get("Country"):
            candidates = candidates[
                candidates["Country"].astype(str).str.casefold()
                == str(filters["Country"]).casefold()
            ]
        if filters.get("City"):
            candidates = candidates[
                candidates["City"].astype(str).str.casefold()
                == str(filters["City"]).casefold()
            ]

        if require_current_or_future_availability:
            availability = pd.to_numeric(
                candidates["Availability"], errors="coerce"
            ).fillna(0)
            end_dates = pd.to_datetime(
                candidates["ContractEndDate"], errors="coerce"
            )
            if filters.get("contract_end_after") is not None:
                candidates = candidates[
                    (availability > 0)
                    & end_dates.notna()
                    & (end_dates <= filters["contract_end_after"])
                ]
            else:
                candidates = candidates[cls.currently_available_mask(candidates)]

        if filters.get("contract_start_after") is not None:
            start_dates = pd.to_datetime(
                candidates["ContractStartDate"], errors="coerce"
            )
            candidates = candidates[
                start_dates >= filters["contract_start_after"]
            ]
        if filters.get("contract_start_before") is not None:
            start_dates = pd.to_datetime(
                candidates["ContractStartDate"], errors="coerce"
            )
            candidates = candidates[
                start_dates <= filters["contract_start_before"]
            ]
        if filters.get("contract_end_before") is not None:
            end_dates = pd.to_datetime(
                candidates["ContractEndDate"], errors="coerce"
            )
            candidates = candidates[
                end_dates <= filters["contract_end_before"]
            ]
        return candidates

    @staticmethod
    def _analysis_filter_summary(filters: dict[str, Any]) -> dict[str, str]:
        summary: dict[str, str] = {}
        for key in ("CL", "Country", "City"):
            if filters.get(key) is not None:
                summary[key] = str(filters[key])
        if filters.get("career_level_operator"):
            summary["CareerLevelOperator"] = (
                f"{filters['career_level_operator']} {filters['career_level_value']}"
            )
        if filters.get("contract_end_after") is not None:
            summary["AvailableAfter"] = filters[
                "contract_end_after"
            ].strftime("%Y-%m-%d")
        if filters.get("available_only"):
            summary["CurrentAvailability"] = (
                "positive capacity through requested date"
                if TechOpsService._has_contract_date_filter(filters)
                else "positive capacity and contract ended"
            )
        return summary

    @staticmethod
    def _requested_quantity(prompt: str) -> int:
        number_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        match = re.search(
            r"\b(?:for|need|require|of)\s+(\d+|one|two|three|four|five|six|"
            r"seven|eight|nine|ten)\b",
            prompt.lower(),
        )
        if not match:
            return 1
        value = match.group(1)
        return int(value) if value.isdigit() else number_words[value]

    @classmethod
    def _team_role_requirements(
        cls, data: pd.DataFrame, prompt: str
    ) -> list[dict[str, Any]]:
        source = prompt
        colon = prompt.find(":")
        if colon >= 0:
            source = prompt[colon + 1:]
        else:
            need_match = re.search(r"\bneed\s+", prompt, re.IGNORECASE)
            if need_match:
                source = prompt[need_match.end():]
            else:
                team_match = re.search(
                    r"\bteam\s+(?:with|of)\s+", prompt, re.IGNORECASE
                )
                if team_match:
                    source = prompt[team_match.end():]
        source = re.split(
            r"\b(?:all\s+)?(?:should\s+be\s+)?available\b|\bto\s+join\b",
            source,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        marker = re.compile(
            r"\b(one|an|a|two|three|four|five|six|seven|eight|nine|ten|\d{1,3})"
            r"\s+",
            flags=re.IGNORECASE,
        )
        markers = [
            match for match in marker.finditer(source)
            if not re.search(
                r"(?:\bcl|\bcareer\s+level)\s*$",
                source[:match.start()],
                flags=re.IGNORECASE,
            )
        ]
        roles: list[dict[str, Any]] = []
        words = {
            "a": 1, "an": 1,
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        for index, match in enumerate(markers):
            quantity = match.group(1).lower()
            segment_end = (
                markers[index + 1].start()
                if index + 1 < len(markers)
                else len(source)
            )
            segment = source[match.end():segment_end].strip(" ,.")
            details_match = re.search(r"\(([^)]*)\)", segment)
            details = details_match.group(1) if details_match else segment
            role = (
                segment[:details_match.start()]
                if details_match
                else segment
            ).strip(" ,.")
            career_match = re.search(
                r"\b(?:career\s+level|cl)\s*(?:is|=)?\s*(\d+)\b",
                details,
                re.IGNORECASE,
            )
            skill_text = re.sub(
                r"\b(?:career\s+level|cl)\s*(?:is|=)?\s*\d+\b",
                " ",
                segment,
                flags=re.IGNORECASE,
            )
            if re.search(r"\bazure\s+devops\b", skill_text, re.IGNORECASE):
                skills = ["Azure DevOps"]
            else:
                skills = cls._requested_role_skills(data, skill_text)
            roles.append(
                {
                    "role": role,
                    "quantity": int(quantity) if quantity.isdigit() else words[quantity],
                    "skills": skills,
                    "career_level": (
                        career_match.group(1) if career_match else None
                    ),
                }
            )
        return roles

    @classmethod
    def _requested_role_skills(
        cls, data: pd.DataFrame, text: str
    ) -> list[str]:
        normalized_text = cls._normalize_skill(text)
        candidates: list[tuple[str, str, str]] = []
        ai_request = bool(re.search(r"\b(?:ai|artificial intelligence)\b", text, re.I))
        for column in ("Primary Skill", "Secondary Skill"):
            for value in data[column].astype(str).unique():
                skill = value.strip()
                if not skill or skill.lower() in {
                    "not available",
                    "no skill available",
                    "no skills available",
                }:
                    continue
                normalized_skill = cls._normalize_skill(skill)
                aliases = re.findall(r"\(([^)]+)\)", skill)
                if ai_request and re.search(
                    r"\b(?:ai|artificial intelligence)\b", skill, re.I
                ):
                    candidates.append((skill, normalized_skill, "ai"))
                    continue
                if normalized_skill in normalized_text:
                    candidates.append((skill, normalized_skill, normalized_skill))
                else:
                    for alias in aliases:
                        normalized_alias = cls._normalize_skill(alias)
                        if re.search(
                            rf"(?<!\w){re.escape(alias.strip())}(?!\w)",
                            text,
                            re.IGNORECASE,
                        ):
                            candidates.append((skill, normalized_skill, normalized_alias))
                            break

        selected: list[str] = []
        selected_normalized: list[str] = []
        for skill, normalized_skill, matched_term in sorted(
            set(candidates),
            key=lambda item: (
                item[2] == item[1],
                -len(item[1]),
                len(item[2]),
            ),
            reverse=True,
        ):
            if any(
                matched_term in existing
                or existing in matched_term
                or normalized_skill in existing
                or existing in normalized_skill
                for existing in selected_normalized
            ):
                continue
            selected.append(skill)
            selected_normalized.append(matched_term)
        return selected

    @staticmethod
    def _skill_breakdown(data: pd.DataFrame) -> dict[str, int]:
        values: list[str] = []
        for column in ("Primary Skill", "Secondary Skill"):
            values.extend(
                str(value).strip()
                for value in data[column].tolist()
                if str(value).strip()
            )
        return {
            str(skill): int(count)
            for skill, count in pd.Series(values).value_counts().head(10).items()
        }

    @staticmethod
    def currently_available_mask(data: pd.DataFrame) -> pd.Series:
        """Return resources with positive capacity and no active future contract."""
        availability = pd.to_numeric(data["Availability"], errors="coerce")
        contract_end = pd.to_datetime(data["ContractEndDate"], errors="coerce")
        today = pd.Timestamp.now().normalize()
        return (availability > 0) & contract_end.notna() & (contract_end <= today)

    @classmethod
    def _is_currently_available(cls, row: pd.Series) -> bool:
        availability = pd.to_numeric(row["Availability"], errors="coerce")
        contract_end = pd.to_datetime(row["ContractEndDate"], errors="coerce")
        return bool(
            pd.notna(availability)
            and availability > 0
            and pd.notna(contract_end)
            and contract_end.normalize() <= pd.Timestamp.now().normalize()
        )

    def search_with_validation(
        self, job_description: str, limit: int = 25
    ) -> dict[str, Any]:
        data = self.load_data()
        _, prompt_filters = self._parse_prompt_filters(data, job_description)
        requested_skills = self._requested_skills(data, job_description)
        requested_limit = self._requested_result_limit(job_description, limit)
        exact_ids = self._resource_ids_in_query(
            data["EnterpriseId"].astype(str).tolist(), job_description
        )
        candidates = data
        if exact_ids:
            candidates = data[
                data["EnterpriseId"].astype(str).str.lower().isin(exact_ids)
            ]
        elif not requested_skills:
            candidates = data.copy()

        candidates = candidates[
            ~candidates.apply(self._has_unavailable_skill, axis=1)
        ]
        candidates = self._apply_career_filter(candidates, prompt_filters)
        if (
            prompt_filters.get("available_only")
            and not self._has_contract_date_filter(prompt_filters)
        ):
            candidates = candidates[self.currently_available_mask(candidates)]
        if not exact_ids and requested_skills:
            candidates = candidates[
                candidates.apply(
                    lambda row: any(
                        self._skill_matches_row(row, skill)
                        for skill in requested_skills
                    ),
                    axis=1,
                )
            ]
        if candidates.empty:
            return {
                "results": [],
                "validation_message": "Expected resource not available in TechOps",
            }

        results = []
        for _, row in candidates.iterrows():
            matched_fields = self._matched_fields(row, requested_skills)
            matched_criteria = self._matched_optional_criteria(row, prompt_filters)
            matched_skill_count = sum(
                self._skill_matches_row(row, skill) for skill in requested_skills
            )
            skill_score = round(
                60 * matched_skill_count / max(len(requested_skills), 1)
            )
            optional_score = round(
                40 * sum(matched_criteria.values()) / max(len(matched_criteria), 1)
            ) if matched_criteria else 40
            score = skill_score + optional_score
            record = {
                column: self._serialize_value(row[column], column)
                for column in TECHOPS_COLUMNS
            }
            record["MatchScore"] = score
            record["MatchedFields"] = matched_fields + [
                name for name, matched in matched_criteria.items() if matched
            ]
            record["_all_skills"] = matched_skill_count == len(requested_skills)
            record["_all_criteria"] = (
                record["_all_skills"] and all(matched_criteria.values())
            )
            results.append(record)

        results.sort(
            key=lambda item: (
                not item.pop("_all_criteria"),
                not item.pop("_all_skills"),
                -item["MatchScore"],
                str(item["EnterpriseId"]),
            )
        )
        exact_results = [item for item in results if item["MatchScore"] == 100]
        has_optional_criteria = bool(matched_criteria) if results else False
        if not requested_skills:
            return {"results": results[:requested_limit], "validation_message": None}
        if exact_results and has_optional_criteria:
            return {"results": exact_results[:requested_limit], "validation_message": None}
        if not has_optional_criteria and results:
            return {"results": results[:requested_limit], "validation_message": None}
        return {
            "results": results[:requested_limit],
            "validation_message": (
                "Please find the resources partially matching with Ranking score"
            ),
        }

    @staticmethod
    def _apply_career_filter(
        data: pd.DataFrame, filters: dict[str, Any]
    ) -> pd.DataFrame:
        if filters.get("CL") is not None:
            return data[data["CL"].astype(str) == str(filters["CL"])]
        operator = filters.get("career_level_operator")
        if operator:
            levels = pd.to_numeric(data["CL"], errors="coerce")
            target = filters["career_level_value"]
            if operator == "lower":
                return data[levels < target]
            if operator == "at_least":
                return data[levels >= target]
            return data[levels > target]
        return data

    def _matched_optional_criteria(
        self, row: pd.Series, filters: dict[str, Any]
    ) -> dict[str, bool]:
        matches: dict[str, bool] = {}
        if filters.get("Country"):
            matches["Country"] = str(row["Country"]).lower() == str(filters["Country"]).lower()
        if filters.get("City"):
            matches["City"] = str(row["City"]).lower() == str(filters["City"]).lower()
        if filters.get("available_only"):
            matches["Currently available"] = (
                self._is_currently_available(row)
            )
        if filters.get("contract_end_after") is not None:
            contract_end = pd.to_datetime(row["ContractEndDate"], errors="coerce")
            matches["Contract date"] = bool(
                pd.notna(contract_end)
                and contract_end <= filters["contract_end_after"]
            )
        if filters.get("contract_start_after") is not None:
            matches["Contract date"] = pd.to_datetime(
                row["ContractStartDate"], errors="coerce"
            ) >= filters["contract_start_after"]
        return matches

    @staticmethod
    def _requested_result_limit(prompt: str, default: int) -> int:
        match = re.search(
            r"\b(?:show|recommend|give|return)\s+(?:me\s+)?(\d+)\b",
            prompt,
            flags=re.IGNORECASE,
        )
        if not match:
            return default
        return max(1, min(int(match.group(1)), 100))

    def search(
        self,
        job_description: str = "",
        primary_skill: str | None = None,
        secondary_skill: str | None = None,
        career_level: str | None = None,
        country: str | None = None,
        city: str | None = None,
        available_only: bool = False,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        data = self.load_data()
        parsed_prompt, prompt_filters = self._parse_prompt_filters(
            data, job_description
        )
        exact_resource_ids = self._resource_ids_in_query(
            data["EnterpriseId"].astype(str).tolist(), job_description
        )
        requested_skills = self._requested_skills(data, parsed_prompt)
        if exact_resource_ids:
            data = data[
                data["EnterpriseId"].astype(str).str.lower().isin(exact_resource_ids)
            ]
        elif requested_skills:
            data = data[
                data.apply(
                    lambda row: all(
                        self._skill_matches_row(row, skill)
                        for skill in requested_skills
                    ),
                    axis=1,
                )
            ]
        else:
            return []
        filters = {
            "Primary Skill": primary_skill,
            "Secondary Skill": secondary_skill,
            "CL": career_level,
            "Country": country,
            "City": city,
        }
        for key in ("CL", "Country", "City"):
            if prompt_filters.get(key) is not None:
                filters[key] = prompt_filters[key]

        for column, value in filters.items():
            if value:
                data = data[
                    data[column].astype(str).str.contains(
                        re.escape(value.strip()), case=False, na=False
                    )
                ]

        if prompt_filters.get("career_level_operator") is not None:
            levels = pd.to_numeric(data["CL"], errors="coerce")
            target = prompt_filters["career_level_value"]
            operator = prompt_filters["career_level_operator"]
            if operator == "lower":
                data = data[levels < target]
            elif operator == "at_least":
                data = data[levels >= target]
            elif operator == "higher":
                data = data[levels > target]

        if available_only:
            data = data[self.currently_available_mask(data)]
        if prompt_filters.get("available_only") and not any(
            key in prompt_filters
            for key in (
                "contract_end_after",
                "contract_start_after",
                "contract_start_before",
                "contract_end_before",
            )
        ):
            data = data[self.currently_available_mask(data)]
        if prompt_filters.get("contract_end_after") is not None:
            end_dates = pd.to_datetime(data["ContractEndDate"], errors="coerce")
            data = data[end_dates <= prompt_filters["contract_end_after"]]
        if prompt_filters.get("contract_start_after") is not None:
            start_dates = pd.to_datetime(data["ContractStartDate"], errors="coerce")
            data = data[start_dates >= prompt_filters["contract_start_after"]]
        if prompt_filters.get("contract_start_before") is not None:
            start_dates = pd.to_datetime(data["ContractStartDate"], errors="coerce")
            data = data[start_dates <= prompt_filters["contract_start_before"]]
        if prompt_filters.get("contract_end_before") is not None:
            end_dates = pd.to_datetime(data["ContractEndDate"], errors="coerce")
            data = data[end_dates <= prompt_filters["contract_end_before"]]

        results = []
        for _, row in data.iterrows():
            matched_fields = self._matched_fields(row, requested_skills)
            score = self._score(row, requested_skills, matched_fields)
            if self._has_unavailable_skill(row):
                continue
            if requested_skills and not exact_resource_ids and not all(
                self._skill_matches_row(row, skill) for skill in requested_skills
            ):
                continue
            record = {
                column: self._serialize_value(row[column], column)
                for column in TECHOPS_COLUMNS
            }
            record["MatchScore"] = score
            record["MatchedFields"] = matched_fields
            results.append(record)

        results.sort(key=lambda item: (-item["MatchScore"], str(item["EnterpriseId"])))
        return results[: max(1, min(limit, 100))]

    @staticmethod
    def _has_contract_date_filter(filters: dict[str, Any]) -> bool:
        return any(
            filters.get(key) is not None
            for key in (
                "contract_end_after",
                "contract_start_after",
                "contract_start_before",
                "contract_end_before",
            )
        )

    @staticmethod
    def _terms(text: str) -> list[str]:
        stop_words = {
            "a", "an", "and", "for", "has", "have", "in", "is", "me", "of",
            "please", "resource", "resources", "show", "skill", "skills", "set",
            "the", "what", "with", "after", "available", "availability",
            "career", "level", "starting", "from", "before", "until",
        }
        return [
            term for term in re.findall(r"[a-z0-9][a-z0-9+#.-]*", text.lower())
            if (
                len(term) > 1
                and term not in stop_words
                and not term.isdigit()
                and not (len(term) == 4 and term.isdigit())
            )
        ]

    @classmethod
    def _parse_prompt_filters(
        cls, data: pd.DataFrame, prompt: str
    ) -> tuple[str, dict[str, Any]]:
        filters: dict[str, Any] = {}
        cleaned_prompt = prompt

        level_match = re.search(
            r"\b(?:cl|career\s*level)\s*"
            r"(?:(above|over|higher\s+than|below|under|lower\s+than)\s*)?"
            r"(?:is|of|=)?\s*(\d+(?:\.\d+)?)\b",
            prompt,
            flags=re.IGNORECASE,
        )
        if level_match:
            operator, value = level_match.groups()
            if operator:
                normalized_operator = operator.lower()
                filters["career_level_operator"] = (
                    "lower"
                    if normalized_operator in {"above", "over", "higher than"}
                    else "higher"
                )
                filters["career_level_value"] = float(value)
            else:
                filters["CL"] = value
            cleaned_prompt = cleaned_prompt.replace(level_match.group(0), " ")
            if re.match(
                r"\s*\+|\s*(?:and|or)\s+(?:above|higher)\b",
                prompt[level_match.end():],
                flags=re.IGNORECASE,
            ):
                filters.pop("CL", None)
                filters["career_level_operator"] = "at_least"
                filters["career_level_value"] = float(value)

        if re.search(
            r"\b(?:available|currently\s+available|availability\s*(?:greater|above|over|of)?"
            r"\s*\d*|free|unallocated)\b",
            prompt,
            re.IGNORECASE,
        ):
            filters["available_only"] = True

        for column in ("Country", "City"):
            values = sorted(
                {
                    str(value).strip()
                    for value in data[column].dropna().tolist()
                    if str(value).strip()
                },
                key=len,
                reverse=True,
            )
            for value in values:
                if re.search(rf"\b{re.escape(value)}\b", prompt, re.IGNORECASE):
                    filters[column] = value
                    cleaned_prompt = re.sub(
                        rf"\b{re.escape(value)}\b", " ", cleaned_prompt,
                        flags=re.IGNORECASE,
                    )
                    break

        date_match = re.search(
            r"\b(after|from|starting|before|until)\s+"
            r"(January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+(\d{4})\b",
            prompt,
            flags=re.IGNORECASE,
        )
        if date_match:
            direction, month, year = date_match.groups()
            month_date = pd.Timestamp(
                year=int(year),
                month=pd.to_datetime(month, format="%B").month,
                day=1,
            )
            context = prompt[max(0, date_match.start() - 35):date_match.start()]
            references_start = bool(
                re.search(r"\b(?:contract\s+)?start(?:\s+date)?\b", context, re.IGNORECASE)
            )
            references_end = bool(
                re.search(r"\b(?:contract\s+)?end(?:\s+date)?\b", context, re.IGNORECASE)
            )
            if direction.lower() == "after":
                key = "contract_start_after" if references_start else "contract_end_after"
                filters[key] = month_date + pd.offsets.MonthEnd(1)
            elif direction.lower() in {"from", "starting"}:
                key = "contract_start_after" if references_start else "contract_end_after"
                filters[key] = month_date
            else:
                key = "contract_end_before" if references_end else "contract_start_before"
                filters[key] = month_date + pd.offsets.MonthEnd(1)
            cleaned_prompt = cleaned_prompt.replace(date_match.group(0), " ")
        numeric_date_match = re.search(
            r"\b(after|from|starting|before|until)\s+"
            r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b",
            prompt,
            flags=re.IGNORECASE,
        )
        if numeric_date_match and not date_match:
            direction, day, month, year = numeric_date_match.groups()
            month_date = pd.Timestamp(
                year=int(year), month=int(month), day=int(day)
            )
            if direction.lower() in {"after", "from", "starting"}:
                filters["contract_end_after"] = month_date
            else:
                filters["contract_end_before"] = month_date
            cleaned_prompt = cleaned_prompt.replace(numeric_date_match.group(0), " ")

        return cleaned_prompt, filters

    @staticmethod
    def _date_filter_text(filters: dict[str, Any]) -> str:
        if filters.get("contract_end_after") is not None:
            date = filters["contract_end_after"] - pd.Timedelta(days=1)
            return f"after {date.strftime('%d %B %Y')}"
        if filters.get("contract_start_after") is not None:
            date = filters["contract_start_after"] - pd.Timedelta(days=1)
            return f"after {date.strftime('%d %B %Y')}"
        if filters.get("contract_start_before") is not None:
            return f"before {filters['contract_start_before'].strftime('%d %B %Y')}"
        if filters.get("contract_end_before") is not None:
            return f"before {filters['contract_end_before'].strftime('%d %B %Y')}"
        return "for the requested contract period"

    @staticmethod
    def _resource_ids_in_query(
        resource_ids: list[str], query: str
    ) -> set[str]:
        normalized_query = re.sub(r"[^a-z0-9]", "", query.lower())
        return {
            resource_id.lower()
            for resource_id in resource_ids
            if resource_id and re.sub(r"[^a-z0-9]", "", resource_id.lower())
            in normalized_query
        }

    @classmethod
    def _requested_skills(cls, data: pd.DataFrame, prompt: str) -> list[str]:
        normalized_prompt = cls._normalize_skill(prompt)
        exact_candidates = set()
        for column in ("Primary Skill", "Secondary Skill"):
            for value in data[column].astype(str).unique():
                skill = value.strip()
                if not skill or skill.lower() in {
                    "not available", "no skill available", "no skills available"
                }:
                    continue
                normalized_skill = cls._normalize_skill(skill)
                aliases = re.findall(r"\(([^)]+)\)", skill)
                if (
                    normalized_skill in normalized_prompt
                    or any(
                        cls._normalize_skill(alias) in normalized_prompt
                        for alias in aliases
                    )
                ):
                    exact_candidates.add(skill)
        if exact_candidates:
            return sorted(exact_candidates, key=len, reverse=True)

        prompt_tokens = {
            token for token in re.findall(r"[a-z0-9]+", prompt.lower())
            if len(token) >= 4 and token not in {
                "what", "which", "who", "has", "have", "skill", "skills",
                "resource", "resources", "available", "career", "level",
                "show", "recommend", "give", "return", "now", "any",
            }
        }
        skill_values = [
            cls._normalize_skill(str(value))
            for column in ("Primary Skill", "Secondary Skill")
            for value in data[column].astype(str).unique()
        ]
        return sorted(
            {
                token for token in prompt_tokens
                if any(token in skill_value for skill_value in skill_values)
            },
            key=len,
            reverse=True,
        )

    @classmethod
    def _skill_matches_row(cls, row: pd.Series, requested_skill: str) -> bool:
        requested = cls._normalize_skill(requested_skill)
        aliases = re.findall(r"\(([^)]+)\)", requested_skill)
        for field in ("Primary Skill", "Secondary Skill"):
            row_skill = cls._normalize_skill(str(row[field]))
            if requested in row_skill or any(
                cls._normalize_skill(alias) in row_skill for alias in aliases
            ):
                return True
            requested_tokens = set(
                re.findall(r"[a-z0-9]+", requested_skill.lower())
            )
            row_tokens = set(
                re.findall(r"[a-z0-9]+", str(row[field]).lower())
            )
            if len(requested_tokens) > 1:
                overlap = len(requested_tokens & row_tokens)
                if overlap >= min(2, len(requested_tokens)):
                    return True
        return False

    @staticmethod
    def _normalize_skill(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    @classmethod
    def _matched_fields(cls, row: pd.Series, skills: list[str]) -> list[str]:
        if not skills:
            return []
        matched = []
        for field in ("Primary Skill", "Secondary Skill"):
            field_value = cls._normalize_skill(str(row[field]))
            if any(
                cls._normalize_skill(skill) in field_value
                or any(
                    cls._normalize_skill(alias) in field_value
                    for alias in re.findall(r"\(([^)]+)\)", skill)
                )
                for skill in skills
            ):
                matched.append(field)
        return matched

    @staticmethod
    def _has_unavailable_skill(row: pd.Series) -> bool:
        unavailable_values = {
            "",
            "nan",
            "n/a",
            "na",
            "no skill available",
            "no skills available",
            "not available",
        }
        return all(
            str(row[field]).strip().lower() in unavailable_values
            for field in ("Primary Skill", "Secondary Skill")
        )

    @classmethod
    def _score(
        cls, row: pd.Series, skills: list[str], matched_fields: list[str]
    ) -> int:
        if not skills:
            return 0
        matched_skills = sum(cls._skill_matches_row(row, skill) for skill in skills)
        score = round((matched_skills / len(skills)) * 70)
        if "Primary Skill" in matched_fields:
            score += 20
        if "Secondary Skill" in matched_fields:
            score += 10
        return min(score, 100)

    @staticmethod
    def _serialize_value(value: Any, column: str) -> Any:
        if value in ("", None) or pd.isna(value):
            return ""
        if column in {"RollonDate", "ContractStartDate", "ContractEndDate"}:
            if isinstance(value, (datetime, pd.Timestamp)):
                return value.date().isoformat()
            if isinstance(value, (int, float)):
                return pd.to_datetime(value, unit="D", origin="1899-12-30").date().isoformat()
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

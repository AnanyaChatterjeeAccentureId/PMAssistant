from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

import pandas as pd


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
                "No resource found with all criteria. Below resources are "
                "matching partially."
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
            return data[levels < target if operator == "lower" else levels > target]
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
            matches["Contract date"] = pd.to_datetime(
                row["ContractEndDate"], errors="coerce"
            ) <= filters["contract_end_after"]
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

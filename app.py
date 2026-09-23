from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from Services.TechOpsService import DISPLAY_COLUMNS, TechOpsService


st.set_page_config(
    page_title="Staffing Search | PM Assistant",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_service() -> TechOpsService:
    return TechOpsService()


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'DM Sans', sans-serif;
            color: #f5f2e9;
        }
        h1, h2, h3, h4, h5, h6,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3 {
            color: #d8b85a !important;
        }
        p, label, li, [data-testid="stCaptionContainer"], [data-testid="stMetricLabel"] {
            color: #f5f2e9 !important;
        }
        input, textarea, [data-baseweb="select"] *,
        [data-testid="stChatInput"] * {
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
        }
        input::placeholder, textarea::placeholder,
        [data-testid="stChatInput"] input::placeholder {
            color: #4b5563 !important;
            -webkit-text-fill-color: #4b5563 !important;
        }
        [data-testid="stAppViewContainer"] {
            background:
                linear-gradient(135deg, rgba(6, 20, 38, .96), rgba(10, 47, 75, .91)),
                radial-gradient(circle at 85% 10%, #36d1dc 0, transparent 35%);
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] {
            background: rgba(4, 16, 30, .92);
            border-right: 1px solid rgba(255,255,255,.08);
        }
        .hero {
            padding: 2rem 2.2rem 1.7rem;
            border: 1px solid rgba(255,255,255,.13);
            border-radius: 24px;
            background: linear-gradient(115deg, rgba(18, 57, 91, .95), rgba(15, 126, 147, .64));
            box-shadow: 0 18px 50px rgba(0,0,0,.18);
            margin-bottom: 1.2rem;
        }
        .eyebrow { color: #d8b85a; font-size: .78rem; letter-spacing: .18em; font-weight: 700; }
        .hero h1 { font-family: 'Space Grotesk', sans-serif; color: #f5f2e9; font-size: 2.5rem; margin: .35rem 0 .45rem; }
        .hero p { color: #f5f2e9; font-size: 1.02rem; margin: 0; max-width: 720px; }
        .metric {
            background: rgba(255,255,255,.08);
            border: 1px solid rgba(255,255,255,.1);
            border-radius: 14px;
            padding: .9rem 1rem;
        }
        .metric-value { color: #d8b85a; font-size: 1.45rem; font-weight: 700; }
        .metric-label { color: #f5f2e9; font-size: .78rem; }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #f5f2e9 !important; }
        [data-testid="stSidebar"] button {
            background: #195487 !important;
            border: 1px solid #2d6d9f !important;
            color: #ffffff !important;
            box-shadow: none !important;
            transition: none !important;
        }
        [data-testid="stSidebar"] button:hover,
        [data-testid="stSidebar"] button:focus,
        [data-testid="stSidebar"] button:active {
            background: #195487 !important;
            border-color: #2d6d9f !important;
            color: #ffffff !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] button p,
        [data-testid="stSidebar"] button span {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        [data-testid="stDataFrame"] {
            background: #f7f7f3;
            color: #111827 !important;
        }
        [data-testid="stDataFrame"] * {
            color: #111827 !important;
        }
        [data-testid="stDownloadButton"] button {
            background: #195487 !important;
            border: 1px solid #2d6d9f !important;
            color: #ffffff !important;
            box-shadow: none !important;
            transition: none !important;
        }
        [data-testid="stDownloadButton"] button:hover,
        [data-testid="stDownloadButton"] button:focus,
        [data-testid="stDownloadButton"] button:active {
            background: #195487 !important;
            border-color: #2d6d9f !important;
            color: #ffffff !important;
            box-shadow: none !important;
        }
        [data-testid="stDownloadButton"] button p,
        [data-testid="stDownloadButton"] button span {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .stChatMessage { background: rgba(255,255,255,.07); border-radius: 16px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def result_frame(results: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(results)
    if frame.empty:
        return frame
    extra_columns = ["RequestedRole"]
    columns = [
        column for column in DISPLAY_COLUMNS + extra_columns if column in frame.columns
    ]
    return frame[columns]


def excel_bytes(frame: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Staffing Results")
    return output.getvalue()


def analysis_header(analysis: dict) -> None:
    mode_labels = {
        "team_composition": "Team composition",
        "resource_search": "Individual resource search",
    }
    mode = analysis.get("mode")
    if not mode:
        return
    st.markdown(f"**Analysis mode:** `{mode_labels.get(mode, mode)}`")
    if analysis.get("filters"):
        st.caption(
            "Applied filters: "
            + ", ".join(
                f"{key} = {value}"
                for key, value in analysis["filters"].items()
            )
        )


def render_team_analysis(analysis: dict) -> None:
    if analysis.get("requested_roles"):
        role_frame = pd.DataFrame(analysis["requested_roles"])
        role_frame = role_frame.rename(
            columns={
                "role": "Requested role",
                "quantity": "Quantity",
                "skills": "Required skills",
                "career_level": "Career level",
            }
        )
        if "Required skills" in role_frame:
            role_frame["Required skills"] = role_frame["Required skills"].apply(
                lambda skills: ", ".join(skills) if isinstance(skills, list) else skills
            )
        st.dataframe(role_frame, hide_index=True, width="stretch")
    if analysis.get("gaps"):
        st.error(
            "Role gaps: "
            + ", ".join(
                f"{gap['role']} short by {gap['shortfall']}"
                for gap in analysis["gaps"]
            )
        )


def render_gap_analysis(analysis: dict) -> None:
    gap_columns = st.columns(4)
    for column, value, label in zip(
        gap_columns,
        (
            analysis["requested_quantity"],
            analysis["available_supply"],
            analysis["shortfall"],
            analysis["capacity_percent"],
        ),
        ("Requested", "Eligible supply", "Shortfall", "Capacity %"),
    ):
        column.metric(label, value)
    if analysis.get("country_breakdown"):
        st.caption(
            "Supply by country: "
            + ", ".join(
                f"{country} ({count})"
                for country, count in analysis["country_breakdown"].items()
            )
        )
    if analysis.get("skill_breakdown"):
        st.caption(
            "Top skills: "
            + ", ".join(
                f"{skill} ({count})"
                for skill, count in list(analysis["skill_breakdown"].items())[:5]
            )
        )


def search(
    prompt: str,
    limit: int,
) -> dict:
    service = get_service()
    intent = service.detect_intent(prompt)
    if intent == "team_composition":
        response = service.team_composition(prompt)
        response["intent_source"] = service.last_intent_source
        return response
    return {
        **service.search_with_validation(job_description=prompt, limit=limit),
        "mode": "resource_search",
        "intent_source": service.last_intent_source,
    }


def main() -> None:
    apply_styles()
    service = get_service()
    data = service.get_dataframe()

    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">PMO RESOURCE INTELLIGENCE</div>
            <h1>Staffing Search</h1>
            <p>Find the right TechOps resource for your demand using skills, career level,
            availability and location. The assistant is grounded in the PMO workbook.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### Recent questions")
        st.caption("Your last 10 staffing searches")
        if "messages" not in st.session_state:
            recent_questions = []
        else:
            recent_questions = [
                message["content"]
                for message in st.session_state.messages
                if message["role"] == "user"
            ][-10:][::-1]

        if not recent_questions:
            st.info("Your recent questions will appear here.")
        for index, question in enumerate(recent_questions):
            if st.button(
                question,
                key=f"recent_question_{index}",
                width="stretch",
                help="Run this question again",
            ):
                st.session_state.pending_prompt = question
                st.rerun()

        st.divider()
        st.caption("Source")
        st.markdown(f"**File:** `{service.file_path.name}`")
        updated_at = datetime.fromtimestamp(
            service.file_path.stat().st_mtime
        ).strftime("%d %b %Y, %I:%M %p")
        st.markdown(f"**Last updated:** `{updated_at}`")

    available_count = int(service.currently_available_mask(data).sum())
    metric_columns = st.columns(4)
    for column, value, label in zip(
        metric_columns,
        (len(data), available_count, data["Country"].nunique(), data["Primary Skill"].nunique()),
        ("Total resources", "Available resources", "Countries", "Primary skills"),
    ):
        column.markdown(
            f'<div class="metric"><div class="metric-value">{value}</div>'
            f'<div class="metric-label">{label}</div></div>',
            unsafe_allow_html=True,
        )

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Tell me what staffing profile you need, for example: "
                "'Find available AWS data platform resources in the UK'.",
            }
        ]
    if "results" not in st.session_state:
        st.session_state.results = []
    if "analysis" not in st.session_state:
        st.session_state.analysis = None

    st.markdown("### Staffing assistant")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Describe the role, skills, location or career level you need...")
    prompt = prompt or st.session_state.pop("pending_prompt", None)
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        search_response = search(prompt, limit=25)
        results = search_response["results"]
        st.session_state.results = results
        st.session_state.analysis = search_response
        validation_message = search_response.get("validation_message")
        st.session_state.validation_message = validation_message
        if search_response.get("mode") != "resource_search":
            assistant_message = search_response.get(
                "summary", "Analysis completed."
            )
        elif results:
            assistant_message = (
                f"I found **{len(results)}** matching resource(s). "
                "The ranked details are shown below."
            )
        else:
            assistant_message = (
                validation_message or "Expected resource not available in TechOps"
            )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": assistant_message,
            }
        )
        st.rerun()

    st.markdown("### Ranked resources")
    analysis = st.session_state.get("analysis") or {}
    analysis_header(analysis)
    if analysis.get("mode") == "team_composition":
        render_team_analysis(analysis)
    frame = result_frame(st.session_state.results)
    if frame.empty:
        st.info(
            st.session_state.get("validation_message")
            or "Start a staffing conversation above to see ranked resources."
        )
        if analysis.get("summary"):
            st.caption(analysis["summary"])
        return
    if st.session_state.get("validation_message"):
        st.error(st.session_state.validation_message)

    display = frame.copy()
    display["MatchedFields"] = display["MatchedFields"].apply(
        lambda fields: ", ".join(fields) if isinstance(fields, list) else fields
    )
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "MatchScore": st.column_config.ProgressColumn(
                "Match score", min_value=0, max_value=100, format="%d"
            ),
            "Availability": st.column_config.NumberColumn("Availability %", format="%d"),
        },
    )
    download_columns = [
        column for column in DISPLAY_COLUMNS + ["RequestedRole"]
        if column in display.columns
    ]
    download_frame = display[download_columns]
    download_col1, download_col2, _ = st.columns([1, 1, 4])
    download_col1.download_button(
        "Download CSV",
        download_frame.to_csv(index=False).encode("utf-8"),
        "staffing-results.csv",
        "text/csv",
    )
    download_col2.download_button(
        "Download Excel",
        excel_bytes(download_frame),
        "staffing-results.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    main()

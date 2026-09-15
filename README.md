# PMAssistant

## Structured TechOps resource search

The API now exposes structured resource search from
`Data/TechOps_DataFile.xlsx`. The workbook is expected to contain these
columns:

- `EnterpriseId`
- `CL`
- `Primary Skill`
- `Primary Skill Competency`
- `Secondary Skill`
- `Availability`
- `RDTFunction(RDT-1)`
- `RDTSubfunction(RDT-2)`
- `Supervisor`
- `RollonDate`
- `Country`
- `City`
- `ContractStartDate`
- `ContractEndDate`

Install dependencies and start the API:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Use `POST /resources/search` with a job description and optional filters:

```json
{
  "job_description": "AWS data platform",
  "career_level": "9",
  "country": "United Kingdom",
  "limit": 10
}
```

The response returns the original workbook fields plus `MatchScore` and
`MatchedFields`. `GET /resources/columns` exposes the schema used by the
search service.

## Staffing search UI

Start the Python UI with:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The UI provides:

- A staffing-themed dashboard with resource, availability, country, and skill metrics.
- Chat-style staffing search grounded only in `TechOps_DataFile.xlsx`.
- A recent-question sidebar with the last 10 staffing searches, which can be run again.
- Ranked results showing all PMO fields, match score, and matched fields.
- CSV and Excel downloads for the selected staffing results.

## Intent-routed analysis modes

The application also detects two structured analysis intents before falling
back to individual resource search:

- **Team composition:** prompts such as
  `Build a team of five resources for an Azure migration project: one architect,
  two engineers, one DevOps specialist, and one tester.` are parsed into role
  slots. The service selects unique currently available resources, reports
  unfilled role slots, and keeps eligibility decisions deterministic.
- **Staffing gap analysis:** prompts such as
  `Do we have enough available Azure resources for three projects?` calculate
  current supply, capacity, shortfall, country distribution, and skill
  distribution from the workbook.

The intent router returns `team_composition`, `staffing_gap_analysis`, or
`resource_search`. The `POST /resources/analyze` endpoint exposes the same
routing for API clients. Azure OpenAI/Azure AI Foundry can be added later as an
explanation or summarization layer over these verified results; it does not
replace the deterministic selection rules.

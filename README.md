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

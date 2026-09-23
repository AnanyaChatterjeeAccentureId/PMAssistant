# PM Assistant Solution Architecture

## Scope

The current application is a workbook-grounded staffing assistant with two
supported modes:

1. **Individual Resource Search**
2. **Team Composition**

The TechOps workbook is the source of truth for resource attributes and
eligibility. Azure OpenAI is used as an interpretation layer for intent
detection; it does not select resources or override deterministic staffing
rules.

## High-level architecture

```text
Staffing user
    |
    v
Streamlit chatbot and dashboard (app.py)
    |
    v
Azure OpenAI intent detection (GenAIService.py)
    |                         \
    |                          \ unavailable/invalid response
    |                           \
    v                            v
resource_search          deterministic fallback router
team_composition                 |
    \____________________________/
                 |
                 v
TechOpsService.py
    |
    +-- prompt and role parsing
    +-- skill and career-level matching
    +-- availability and contract-date validation
    +-- duplicate prevention for teams
    +-- ranking, gaps, and summaries
    |
    v
Data/TechOps_DataFile.xlsx
    |
    v
Validated resource results
```

FastAPI exposes the same service layer for integrations through
`POST /resources/analyze`, while the Streamlit UI provides the interactive
experience.

## Mode 1: Individual Resource Search

### Purpose

Find individual resources that match a natural-language profile.

### Example

```text
Find CL 9 resources with AWS Data Platform & Analytics available after
December 2026.
```

### Processing flow

1. Azure OpenAI classifies the request as `resource_search`.
2. If Azure OpenAI is unavailable, the deterministic router is used.
3. `TechOpsService` extracts skills, career level, location, availability,
   contract-date criteria, and result limit.
4. Candidates are matched against `Primary Skill` or `Secondary Skill`.
5. Career level, availability, country, city, and contract filters are applied.
6. Results are ranked and returned with the original workbook fields plus
   `MatchScore` and `MatchedFields`.

The current date behavior is the original cutoff behavior: for a request such
as “available after December 2026”, eligible records must have positive
availability and a contract end date on or before `2026-12-31`.

## Mode 2: Team Composition

### Purpose

Build a multi-role team with role-specific quantities, skills, and career
levels.

### Example

```text
Build a team with one AWS specialist CL 9 and two AI developers CL 10
available after December 2026.
```

### Processing flow

1. Azure OpenAI classifies the request as `team_composition`.
2. If Azure OpenAI is unavailable, the deterministic router is used.
3. The service extracts one requirement object per role:

   ```python
   {
       "role": "specialist",
       "quantity": 1,
       "skills": ["AWS Data Platform & Analytics"],
       "career_level": "9",
   }
   ```

4. Each role is matched independently against the workbook.
5. A candidate must satisfy the role skill, exact career level, positive
   availability, and requested contract-date condition.
6. `EnterpriseId` values already assigned to another role are excluded.
7. The response includes assigned resources, role-level gaps, total requested
   quantity, fulfilled quantity, and unfulfilled quantity.

Team composition retains its existing cutoff behavior and is not affected by
individual-search-specific date logic.

## Azure OpenAI integration

`Services/GenAIService.py` calls the configured Azure OpenAI deployment with a
small classification prompt and requests JSON containing only:

```json
{"intent": "resource_search"}
```

or:

```json
{"intent": "team_composition"}
```

The service validates the returned intent and falls back to the deterministic
router if configuration, connectivity, SDK availability, or response parsing
fails. Credentials are loaded from the existing ignored `.env` configuration;
secrets are not stored in source code or sent with workbook records.

The responsibility boundary is:

```text
Azure OpenAI: interpret the user's intent.
Python rules: decide resource eligibility and team assignment.
Workbook: provide authoritative resource data.
```

## File-by-file implementation summary

### Core application files

- **`app.py`** — Implements the Streamlit dashboard, chat experience, mode
  rendering, requested-role table, resource results table, gap messages, and
  CSV/Excel downloads.
- **`main.py`** — Provides FastAPI endpoints and routes
  `POST /resources/analyze` through the same intent and deterministic service
  logic used by Streamlit.
- **`config.py`** — Loads Azure OpenAI endpoint, API key, and deployment
  settings from the local environment, including the existing parent-project
  `.env` without exposing secret values.
- **`requirements.txt`** — Declares runtime dependencies including pandas,
  openpyxl, Streamlit, FastAPI, `openai`, and `python-dotenv`.

### Service files

- **`Services/TechOpsService.py`** — Contains workbook loading and schema
  validation, deterministic intent fallback, prompt parsing, individual
  resource ranking, team-role parsing, skill/CL matching, availability and
  contract checks, duplicate prevention, gap calculation, and JSON-safe
  serialization.
- **`Services/GenAIService.py`** — Adds Azure OpenAI intent classification with
  structured JSON validation and safe fallback behavior when the SDK,
  configuration, endpoint, or response is unavailable.

### Data and documentation

- **`Data/TechOps_DataFile.xlsx`** — Holds the PMO TechOps resource inventory
  used as the authoritative source for skills, career levels, availability,
  locations, and contract dates.
- **`README.md`** — Documents setup, supported modes, API usage, workbook
  schema, and the GenAI-plus-deterministic architecture.
- **`ONTOLOGY_ARCHITECTURE.md`** — Documents the resource, skill,
  organization, location, contract, availability, parsing, and matching
  concepts used by the application.
- **`PMAssistant_Solution_Architecture.pptx`** — Contains the solution and
  technical architecture presentation, including the current Streamlit,
  FastAPI, service, workbook, and two-mode flow.

## Design principles

- Resource eligibility remains deterministic and auditable.
- Azure OpenAI does not invent or substitute resources.
- Every result preserves the source workbook fields.
- Team members are not duplicated across role assignments.
- Missing capacity is reported explicitly as a role-level gap.
- Azure failures do not prevent deterministic fallback operation.

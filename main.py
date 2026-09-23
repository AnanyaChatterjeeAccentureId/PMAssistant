from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

from Services.TechOpsService import TechOpsService

app = FastAPI(title="Project Manager Assistant - TechOps Resource Search")
techops_service = TechOpsService()


class ResourceSearchRequest(BaseModel):
    job_description: str = ""
    primary_skill: str | None = None
    secondary_skill: str | None = None
    career_level: str | None = None
    country: str | None = None
    city: str | None = None
    available_only: bool = False
    limit: int = Field(default=25, ge=1, le=100)


class AnalysisRequest(BaseModel):
    prompt: str = Field(min_length=1)


@app.get("/resources/columns")
def resource_columns():
    return {"columns": techops_service.get_columns()}


@app.post("/resources/search")
def search_resources(request: ResourceSearchRequest):
    results = techops_service.search(
        job_description=request.job_description,
        primary_skill=request.primary_skill,
        secondary_skill=request.secondary_skill,
        career_level=request.career_level,
        country=request.country,
        city=request.city,
        available_only=request.available_only,
        limit=request.limit,
    )
    return {
        "mode": "structured",
        "count": len(results),
        "results": results,
    }


@app.post("/resources/analyze")
def analyze_resources(request: AnalysisRequest):
    intent = techops_service.detect_intent(request.prompt)
    if intent == "team_composition":
        response = techops_service.team_composition(request.prompt)
        response["intent_source"] = techops_service.last_intent_source
        return response
    return {
        "mode": "resource_search",
        "intent_source": techops_service.last_intent_source,
        **techops_service.search_with_validation(request.prompt),
    }


@app.get("/resources")
def list_resources(
    country: str | None = Query(default=None),
    city: str | None = Query(default=None),
    available_only: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
):
    results = techops_service.search(
        country=country,
        city=city,
        available_only=available_only,
        limit=limit,
    )
    return {"mode": "structured", "count": len(results), "results": results}
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
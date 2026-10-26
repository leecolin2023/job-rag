"""Shared structured constraints; no ranking, model calls, or database I/O."""
import re

from pydantic import BaseModel, ConfigDict, Field


class StructuredFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str | None = None
    district: str | None = None
    min_salary: float | None = Field(default=None, ge=0)
    max_salary: float | None = Field(default=None, ge=0)
    salary_period: str = Field(default="month", pattern="^(month|day|hour)$")
    salary_mode: str = Field(default="lower_bound", pattern="^(lower_bound|overlap)$")
    experience_years: float | None = Field(default=None, ge=0, le=60)
    education: str | None = None
    employment_type: str | None = Field(default=None, pattern="^(internship|unknown)$")
    skills: list[str] = Field(default_factory=list, max_length=20)
    active_only: bool = False
    include_closed: bool = False


def matches(job, filters):
    norm = job.normalized
    if filters.city and norm["city"] != filters.city:
        return False
    if filters.district and norm["district"] != filters.district:
        return False
    if filters.min_salary is not None or filters.max_salary is not None:
        if norm["salary_period"] != filters.salary_period or norm["salary_min"] is None:
            return False
        if filters.min_salary is not None:
            bound = norm["salary_min"] if filters.salary_mode == "lower_bound" else norm["salary_max"]
            if bound < filters.min_salary:
                return False
        if filters.max_salary is not None and norm["salary_min"] > filters.max_salary:
            return False
    if filters.experience_years is not None:
        if norm["experience_min"] is None or norm["experience_min"] > filters.experience_years:
            return False
    if filters.education and norm["education_level"] != filters.education:
        return False
    if filters.employment_type and norm["employment_type"] != filters.employment_type:
        return False
    # Explicit skills are literal constraints, not semantic requirement judgments.
    source_text = (job.raw["title"] + "\n" + job.raw["description"]).lower()
    for skill in filters.skills:
        skill = skill.strip().lower()
        if not skill:
            continue
        if re.fullmatch(r"[a-z0-9+#.]+", skill):
            if not re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", source_text):
                return False
        elif skill not in source_text:
            return False
    return True

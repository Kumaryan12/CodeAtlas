from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codeatlas.schemas.qa import Citation, ModelAnswer


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str = Field(min_length=1, max_length=1500)

    @field_validator("task")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Task is blank")
        return value.strip()


class AgentArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str | None = Field(default=None, max_length=500)
    prefix: str | None = Field(default=None, max_length=200)
    offset: int | None = Field(default=None, ge=0, le=10000)
    file_id: str | None = Field(default=None, max_length=36)
    start_line: int | None = Field(default=None, ge=1, le=500000)
    end_line: int | None = Field(default=None, ge=1, le=500000)


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: list[str] = Field(min_length=1, max_length=4)
    summary: str = Field(min_length=1, max_length=300)
    action: Literal["list_files", "search_code", "read_file", "inspect_dependencies", "finish"]
    arguments: AgentArguments
    answer: ModelAnswer | None

    @field_validator("plan")
    @classmethod
    def bounded_plan(cls, value):
        if any(not item.strip() or len(item) > 200 for item in value):
            raise ValueError("Invalid plan")
        return value


class AgentStep(BaseModel):
    number: int
    kind: Literal["model", "read"]
    action: str
    status: Literal["running", "completed", "failed"]
    started_at: str
    duration_ms: int
    summary: str
    error_code: str | None = None


class InvestigationResult(ModelAnswer):
    citations: list[Citation]


class RunSummary(BaseModel):
    id: str
    repository_id: str
    task: str
    status: Literal["running", "completed", "failed", "limited", "interrupted"]
    model: str
    created_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None


class RunResponse(RunSummary):
    plan: list[str]
    steps: list[AgentStep]
    result: InvestigationResult | None


class RunList(BaseModel):
    items: list[RunSummary]
    total: int

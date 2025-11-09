from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field, validator

Status = Literal[
    "QUEUED", "PRECHECKS", "EXECUTING", "POSTCHECKS", "JUDGING", "DONE", "FAILED"
]


class Target(BaseModel):
    host: str


class ToDoStep(BaseModel):
    id: str
    action: str
    args: Dict[str, Any] = Field(default_factory=dict)
    timeout_s: int = 10
    parser: Optional[str] = None
    validator: Optional[str] = None


class ToDoDSL(BaseModel):
    job_id: str
    profile: Literal["verify_readonly", "extended_verify"] = "verify_readonly"
    target: Target
    context: Dict[str, Any] = Field(default_factory=dict)
    prechecks: List[Dict[str, Any]] = Field(default_factory=list)
    steps: List[ToDoStep]
    postchecks: List[Dict[str, Any]] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)


class ExecStep(BaseModel):
    id: str
    cmd: str
    timeout_s: int
    parser: Optional[str]
    validator: Optional[str]


class ExecPlan(BaseModel):
    steps: List[ExecStep]


class RawResult(BaseModel):
    step_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = False


class ParsedResult(BaseModel):
    step_id: str
    parsed: Dict[str, Any]
    ok: Optional[bool] = None
    notes: Optional[str] = None


class VerificationDetail(BaseModel):
    per_step: List[Dict[str, Any]] = Field(default_factory=list)


class VerificationResult(BaseModel):
    status: Literal["SUCCESS", "FAILED", "PARTIAL"]
    summary: str
    details: VerificationDetail = Field(default_factory=VerificationDetail)
    evidence: List[Dict[str, str]] = Field(default_factory=list)

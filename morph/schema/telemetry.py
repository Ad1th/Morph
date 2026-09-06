"""RunResult: structured outcome of a single application run."""


from pydantic import BaseModel


class RunResult(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    passed: bool
    error_type: str | None = None
    error_message: str | None = None

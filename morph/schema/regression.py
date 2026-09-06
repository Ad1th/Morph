from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from morph.schema.profile import EnvironmentProfile


def _default_created_at() -> str:
    return datetime.now(timezone.utc).isoformat()


class RegressionArtifact(BaseModel):
    regression_id: str
    environment: EnvironmentProfile
    command: str
    expected_exit_code: int = 0
    expected_max_failure_rate: float = 0.0
    failure_signature: Optional[str] = None
    created_at: str = Field(default_factory=_default_created_at)
    metadata: Dict[str, Any] = Field(default_factory=dict)


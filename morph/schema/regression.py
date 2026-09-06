from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from morph.schema.profile import EnvironmentProfile


def _default_created_at() -> str:
    return datetime.now(UTC).isoformat()


class RegressionArtifact(BaseModel):
    regression_id: str
    environment: EnvironmentProfile
    command: str
    expected_exit_code: int = 0
    expected_max_failure_rate: float = 0.0
    failure_signature: str | None = None
    created_at: str = Field(default_factory=_default_created_at)
    metadata: dict[str, Any] = Field(default_factory=dict)


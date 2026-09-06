from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from morph.schema.profile import EnvironmentProfile


class RegressionArtifact(BaseModel):
    regression_id: str
    environment: EnvironmentProfile
    command: str
    expected_exit_code: int = 0
    expected_max_failure_rate: float = 0.0
    failure_signature: Optional[str] = None
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

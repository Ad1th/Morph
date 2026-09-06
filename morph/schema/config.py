"""Configuration models for project-level morph.yaml."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdaptersConfig(BaseModel):
    network: str = "proxy"  # "proxy" | "native"
    cpu: str = "native"
    memory: str = "native"
    locale: str = "native"


class CloudConfig(BaseModel):
    enabled: bool = False
    provider: str = "tin"
    endpoint: str = "https://api.tin.computer/v1"
    api_key: str | None = None


class MorphConfig(BaseModel):
    version: str = "1.0"
    default_trials: int = 5
    significance_level: float = 0.05
    default_command: str | None = None
    proxy_port: int = 9876
    adapters: AdaptersConfig = Field(default_factory=AdaptersConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    metadata: dict[str, str] = Field(default_factory=dict)

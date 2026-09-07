"""Configuration models for project-level morph.yaml."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdaptersConfig(BaseModel):
    network: str = "proxy"  # "proxy" | "native"
    cpu: str = "native"
    memory: str = "native"
    locale: str = "native"


class CloudConfig(BaseModel):
    """A remote worker Morph can hand a run to when this host is too small.

    Transport is plain SSH whoever the provider is: the worker runs the SAME
    `morph run` against the SAME profile, so there is no second execution
    engine to keep in step with the local one. `provider` records where the
    box came from (it appears in run provenance); it does not change the code
    path.

    Nothing here is required until `enabled` is set. Credentials may equally
    come from the environment, so a config file can be committed without them:
        MORPH_CLOUD_HOST, MORPH_CLOUD_USER, MORPH_CLOUD_SSH_KEY
    """

    enabled: bool = False
    provider: str = "gcp"  # "gcp" | "ssh" -- provenance only
    host: str | None = None  # external IP or hostname of the worker
    user: str | None = None  # SSH login
    ssh_key: str | None = None  # path to the private key
    python: str = "python3"  # interpreter on the worker
    workdir: str = "~/morph"  # Morph checkout on the worker
    connect_timeout: float = 15.0


class MorphConfig(BaseModel):
    version: str = "1.0"
    default_trials: int = 5
    significance_level: float = 0.05
    default_command: str | None = None
    proxy_port: int = 9876
    adapters: AdaptersConfig = Field(default_factory=AdaptersConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    metadata: dict[str, str] = Field(default_factory=dict)

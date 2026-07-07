from pydantic import BaseModel, Field


class PlatformConfig(BaseModel):
    """Enterprise platform management defaults."""

    enabled: bool = Field(default=True, description="Whether enterprise platform controls are enabled")
    base_agent_name: str | None = Field(default=None, description="Optional file-backed base agent for users without assignments")
    normal_user_default_to_base_agent: bool = Field(default=True, description="Whether normal users without assignments can use the base/default agent")

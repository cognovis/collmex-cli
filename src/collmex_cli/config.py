"""Configuration management for Collmex CLI."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollmexConfig(BaseSettings):
    """Collmex API configuration.

    Configuration is loaded from environment variables with COLLMEX_ prefix,
    or from a .env file in the current directory.

    Required environment variables:
        COLLMEX_CUSTOMER_ID: Your Collmex customer ID
        COLLMEX_COMPANY_ID: Your Collmex company ID (usually 1)
        COLLMEX_USERNAME: Your Collmex username
        COLLMEX_PASSWORD: Your Collmex password
    """

    model_config = SettingsConfigDict(
        env_prefix="COLLMEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    customer_id: str = Field(description="Collmex customer ID")
    company_id: int = Field(default=1, description="Collmex company ID")
    username: str = Field(description="Collmex username")
    password: str = Field(description="Collmex password")

    @property
    def api_url(self) -> str:
        """Return the Collmex API endpoint URL."""
        return f"https://www.collmex.de/cgi-bin/cgi.exe?{self.customer_id},0,data_exchange"


def get_config() -> CollmexConfig:
    """Load and return the Collmex configuration."""
    return CollmexConfig()

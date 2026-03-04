"""Application configuration (XDG-based TOML config file).

Manages user-level settings like bank account definitions,
separate from the Collmex API credentials in environment variables.

Config location: $XDG_CONFIG_HOME/collmex-cli/config.toml
(defaults to ~/.config/collmex-cli/config.toml)
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

APP_NAME = "collmex-cli"
DEFAULT_BANK_ACCOUNTS: dict[str, int] = {}


def _config_dir() -> Path:
    """Return the XDG config directory for this app."""
    xdg = Path.home() / ".config"
    env_xdg = __import__("os").environ.get("XDG_CONFIG_HOME")
    if env_xdg:
        xdg = Path(env_xdg)
    return xdg / APP_NAME


def config_path() -> Path:
    """Return the path to the config file."""
    return _config_dir() / "config.toml"


class AppConfig(BaseModel):
    """Application-level configuration loaded from TOML."""

    bank_accounts: dict[str, int] = Field(
        default_factory=lambda: dict(DEFAULT_BANK_ACCOUNTS),
        description="Mapping of account name to account number",
    )


def load_config() -> AppConfig:
    """Load config from XDG config file.

    Returns AppConfig with defaults if file doesn't exist.
    """
    path = config_path()
    if not path.exists():
        return AppConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return AppConfig(
        bank_accounts=data.get("bank_accounts", dict(DEFAULT_BANK_ACCOUNTS)),
    )

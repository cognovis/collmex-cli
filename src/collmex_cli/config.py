"""Configuration management for Collmex CLI.

Configuration priority (highest wins):
1. Environment variables (COLLMEX_* prefix)
2. XDG config file (~/.config/collmex-cli/config.toml) [credentials] section
3. .env file in current directory
4. Field defaults
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollmexConfig(BaseSettings):
    """Collmex API and related configuration.

    Configuration is loaded from (in priority order):
    1. Environment variables with COLLMEX_ prefix
    2. [credentials] section in ~/.config/collmex-cli/config.toml
    3. .env file in the current directory

    Required:
        customer_id: Your Collmex customer ID
        username: Your Collmex username
        password: Your Collmex password

    Optional:
        company_id: Your Collmex company ID (default: 1)

    Optional - SMTP (for sending invoices):
        smtp_host, smtp_port, smtp_user, smtp_password, smtp_from
        accounting_email: Recipient for invoices (buchhaltung@...)

    Optional - Buyer info (your company, for ZUGFeRD):
        buyer_name, buyer_street, buyer_zip, buyer_city,
        buyer_country, buyer_vat_id, buyer_email
    """

    model_config = SettingsConfigDict(
        env_prefix="COLLMEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ==========================================================================
    # Collmex API credentials (required for CSV API commands)
    # ==========================================================================
    customer_id: str = Field(description="Collmex customer ID")
    company_id: int = Field(default=1, description="Collmex company ID")
    username: str = Field(default="", description="Collmex API username")
    password: str = Field(default="", description="Collmex API password")

    # ==========================================================================
    # Collmex Web credentials (for upload-statement, pending-bookings)
    # ==========================================================================
    web_username: str = Field(default="", description="Collmex web login username")
    web_password: str = Field(default="", description="Collmex web login password")

    # ==========================================================================
    # SMTP configuration (optional, for invoice-send)
    # ==========================================================================
    smtp_host: str | None = Field(default=None, description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str | None = Field(default=None, description="SMTP username")
    smtp_password: str | None = Field(default=None, description="SMTP password")
    smtp_from: str | None = Field(default=None, description="Sender email address")
    smtp_use_tls: bool = Field(default=True, description="Use STARTTLS")
    accounting_email: str | None = Field(
        default=None, description="Recipient email for invoices (buchhaltung@...)"
    )

    # ==========================================================================
    # Buyer information (optional, for ZUGFeRD XML generation)
    # ==========================================================================
    buyer_name: str | None = Field(default=None, description="Your company name")
    buyer_street: str | None = Field(default=None, description="Your street address")
    buyer_zip: str | None = Field(default=None, description="Your postal code")
    buyer_city: str | None = Field(default=None, description="Your city")
    buyer_country: str = Field(default="DE", description="Your country code (ISO)")
    buyer_vat_id: str | None = Field(default=None, description="Your VAT ID (USt-IdNr)")
    buyer_email: str | None = Field(default=None, description="Your contact email")

    @property
    def api_url(self) -> str:
        """Return the Collmex API endpoint URL."""
        return f"https://www.collmex.de/cgi-bin/cgi.exe?{self.customer_id},0,data_exchange"

    @property
    def smtp_configured(self) -> bool:
        """Check if SMTP is configured."""
        return all([self.smtp_host, self.smtp_user, self.smtp_password, self.smtp_from])

    @property
    def buyer_configured(self) -> bool:
        """Check if buyer info is configured."""
        return all([self.buyer_name, self.buyer_street, self.buyer_zip, self.buyer_city])


def _load_toml_credentials() -> dict[str, str]:
    """Load credentials from XDG config TOML file.

    Returns a flat dict with COLLMEX_ prefixed keys suitable for
    pydantic-settings env var initialization.
    """
    from .app_config import config_path

    path = config_path()
    if not path.exists():
        return {}

    import tomllib

    with open(path, "rb") as f:
        data = tomllib.load(f)

    creds = data.get("credentials", {})
    if not creds:
        return creds

    # Map TOML keys to env-var-style keys for pydantic-settings
    return {k: str(v) for k, v in creds.items()}


def get_config() -> CollmexConfig:
    """Load and return the Collmex configuration.

    Reads credentials from XDG config TOML first, then lets
    environment variables override (pydantic-settings default behavior).
    """
    toml_creds = _load_toml_credentials()
    if toml_creds:
        # Pass TOML values as fallback init kwargs;
        # env vars still take priority via pydantic-settings
        return CollmexConfig(**toml_creds)
    return CollmexConfig()

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

    Optional - Seller info (cognovis as seller, for customer invoices):
        seller_name, seller_street, seller_zip, seller_city,
        seller_country, seller_phone, seller_fax, seller_web, seller_email,
        seller_vat_id, seller_hrb, seller_amtsgericht, seller_geschaeftsfuehrung,
        seller_bank_name, seller_iban, seller_bic
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

    # ==========================================================================
    # Seller information (optional, for customer invoice rendering)
    # ==========================================================================
    seller_name: str | None = Field(default=None, description="Seller company name")
    seller_street: str | None = Field(default=None, description="Seller street address")
    seller_zip: str | None = Field(default=None, description="Seller postal code")
    seller_city: str | None = Field(default=None, description="Seller city")
    seller_country: str = Field(default="DE", description="Seller country code")
    seller_phone: str | None = Field(default=None, description="Seller phone number")
    seller_fax: str | None = Field(default=None, description="Seller fax number")
    seller_web: str | None = Field(default=None, description="Seller website URL")
    seller_email: str | None = Field(default=None, description="Seller contact email")
    seller_vat_id: str | None = Field(default=None, description="Seller VAT ID (USt-IdNr)")
    seller_hrb: str | None = Field(default=None, description="Seller HRB number (Handelsregisternummer)")
    seller_amtsgericht: str | None = Field(default=None, description="Seller Amtsgericht (court of registration)")
    seller_geschaeftsfuehrung: str | None = Field(
        default=None,
        description="Seller Geschäftsführung (managing directors)",
    )
    seller_bank_name: str | None = Field(default=None, description="Seller bank name")
    seller_iban: str | None = Field(default=None, description="Seller IBAN")
    seller_bic: str | None = Field(default=None, description="Seller BIC")

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

    @property
    def seller_configured(self) -> bool:
        """Check if all mandatory seller fields for invoice rendering are configured."""
        return all(
            [
                self.seller_name,
                self.seller_street,
                self.seller_zip,
                self.seller_city,
                self.seller_vat_id,
                self.seller_hrb,
                self.seller_iban,
                self.seller_bic,
            ]
        )

    def validate_seller_fields(self) -> list[str]:
        """Return list of missing mandatory seller fields."""
        required = {
            "seller_name": self.seller_name,
            "seller_street": self.seller_street,
            "seller_zip": self.seller_zip,
            "seller_city": self.seller_city,
            "seller_vat_id": self.seller_vat_id,
            "seller_hrb": self.seller_hrb,
            "seller_iban": self.seller_iban,
            "seller_bic": self.seller_bic,
        }
        return [k for k, v in required.items() if not v]


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

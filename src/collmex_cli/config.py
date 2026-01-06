"""Configuration management for Collmex CLI."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollmexConfig(BaseSettings):
    """Collmex API and related configuration.

    Configuration is loaded from environment variables with COLLMEX_ prefix,
    or from a .env file in the current directory.

    Required environment variables:
        COLLMEX_CUSTOMER_ID: Your Collmex customer ID
        COLLMEX_COMPANY_ID: Your Collmex company ID (usually 1)
        COLLMEX_USERNAME: Your Collmex username
        COLLMEX_PASSWORD: Your Collmex password

    Optional - SMTP (for sending invoices):
        COLLMEX_SMTP_HOST: SMTP server hostname
        COLLMEX_SMTP_PORT: SMTP server port (default: 587)
        COLLMEX_SMTP_USER: SMTP username
        COLLMEX_SMTP_PASSWORD: SMTP password
        COLLMEX_SMTP_FROM: Sender email address
        COLLMEX_ACCOUNTING_EMAIL: Recipient for invoices (buchhaltung@...)

    Optional - Buyer info (your company, for ZUGFeRD):
        COLLMEX_BUYER_NAME: Company name
        COLLMEX_BUYER_STREET: Street address
        COLLMEX_BUYER_ZIP: Postal code
        COLLMEX_BUYER_CITY: City
        COLLMEX_BUYER_COUNTRY: Country code (default: DE)
        COLLMEX_BUYER_VAT_ID: VAT ID (USt-IdNr)
        COLLMEX_BUYER_EMAIL: Contact email
    """

    model_config = SettingsConfigDict(
        env_prefix="COLLMEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ==========================================================================
    # Collmex API credentials (required)
    # ==========================================================================
    customer_id: str = Field(description="Collmex customer ID")
    company_id: int = Field(default=1, description="Collmex company ID")
    username: str = Field(description="Collmex username")
    password: str = Field(description="Collmex password")

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


def get_config() -> CollmexConfig:
    """Load and return the Collmex configuration."""
    return CollmexConfig()

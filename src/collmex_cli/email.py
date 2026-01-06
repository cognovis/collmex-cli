"""Email sending for vendor invoices."""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from .config import CollmexConfig, get_config


def send_invoice_email(
    pdf_path: Path | str,
    xml_content: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    config: CollmexConfig | None = None,
) -> None:
    """Send vendor invoice PDF (with optional ZUGFeRD XML) via email.

    Args:
        pdf_path: Path to the PDF file to send
        xml_content: Optional ZUGFeRD XML content to attach
        recipient: Email recipient (defaults to config.accounting_email)
        subject: Email subject (defaults to filename)
        body: Email body text
        config: Optional config, loads from env if not provided

    Raises:
        ValueError: If SMTP is not configured or recipient not provided
        FileNotFoundError: If PDF file doesn't exist
    """
    config = config or get_config()

    if not config.smtp_configured:
        raise ValueError(
            "SMTP not configured. Set COLLMEX_SMTP_HOST, COLLMEX_SMTP_USER, "
            "COLLMEX_SMTP_PASSWORD, COLLMEX_SMTP_FROM"
        )

    recipient = recipient or config.accounting_email
    if not recipient:
        raise ValueError(
            "No recipient specified. Provide recipient or set COLLMEX_ACCOUNTING_EMAIL"
        )

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Create message
    msg = MIMEMultipart()
    msg["From"] = config.smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject or f"Rechnung: {pdf_path.stem}"

    # Body
    body_text = body or (
        f"Anbei die Rechnung {pdf_path.name} zur Verbuchung.\n\n"
        "Diese E-Mail wurde automatisch generiert."
    )
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    # Attach PDF
    with open(pdf_path, "rb") as f:
        pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
        pdf_attachment.add_header(
            "Content-Disposition", "attachment", filename=pdf_path.name
        )
        msg.attach(pdf_attachment)

    # Attach ZUGFeRD XML if provided
    if xml_content:
        xml_attachment = MIMEApplication(
            xml_content.encode("utf-8"), _subtype="xml"
        )
        # Standard ZUGFeRD filename
        xml_filename = "factur-x.xml"
        xml_attachment.add_header(
            "Content-Disposition", "attachment", filename=xml_filename
        )
        msg.attach(xml_attachment)

    # Send
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        if config.smtp_use_tls:
            server.starttls()
        server.login(config.smtp_user, config.smtp_password)
        server.send_message(msg)

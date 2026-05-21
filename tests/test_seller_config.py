"""Tests for seller configuration used by customer invoice rendering."""

from collmex_cli.config import CollmexConfig


def test_extended_seller_fields_are_available_and_validate_missing_fields():
    """Seller config reports missing mandatory fields for invoice rendering."""
    config = CollmexConfig(
        customer_id="123456",
        seller_name="cognovis GmbH",
        seller_city="Hamburg",
        seller_vat_id="DE118620281",
    )

    assert config.seller_configured is False
    assert config.validate_seller_fields() == [
        "seller_street",
        "seller_zip",
        "seller_hrb",
        "seller_iban",
        "seller_bic",
    ]


def test_seller_configured_when_mandatory_fields_are_present():
    """Mandatory seller fields are enough to enable invoice rendering."""
    config = CollmexConfig(
        customer_id="123456",
        seller_name="cognovis GmbH",
        seller_street="Schroedersweg 27",
        seller_zip="22453",
        seller_city="Hamburg",
        seller_vat_id="DE118620281",
        seller_hrb="28909",
        seller_iban="DE93200704040062444500",
        seller_bic="DEUTDEHHXXX",
    )

    assert config.seller_configured is True
    assert config.validate_seller_fields() == []


def test_validate_seller_fields_reports_missing_footer_fields():
    """Configs missing HRB, IBAN, or BIC are flagged as incomplete for invoice rendering."""
    config = CollmexConfig(
        customer_id="123456",
        seller_name="cognovis GmbH",
        seller_street="Schroedersweg 27",
        seller_zip="22453",
        seller_city="Hamburg",
        seller_vat_id="DE118620281",
    )

    missing = config.validate_seller_fields()
    assert config.seller_configured is False
    assert "seller_hrb" in missing
    assert "seller_iban" in missing
    assert "seller_bic" in missing

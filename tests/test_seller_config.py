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
    assert config.validate_seller_fields() == ["seller_street", "seller_zip"]


def test_seller_configured_when_mandatory_fields_are_present():
    """Mandatory seller fields are enough to enable invoice rendering."""
    config = CollmexConfig(
        customer_id="123456",
        seller_name="cognovis GmbH",
        seller_street="Schroedersweg 27",
        seller_zip="22453",
        seller_city="Hamburg",
        seller_vat_id="DE118620281",
    )

    assert config.seller_configured is True
    assert config.validate_seller_fields() == []

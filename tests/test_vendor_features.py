"""Tests for vendor features: vendor-match missing_fields, vendor-update, zugferd validation."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from collmex_cli.client import CollmexClient
from collmex_cli.main import app
from collmex_cli.models import Vendor

runner = CliRunner()


def make_vendor(**kwargs) -> Vendor:
    """Helper to create a Vendor with sensible defaults."""
    defaults = dict(
        vendor_id=42,
        company_name="Test GmbH",
        street="Teststr. 1",
        postal_code="12345",
        city="Berlin",
        vat_id="DE123456789",
        tax_id="",
        iban="DE89370400440532013000",
        bic="COBADEFFXXX",
    )
    defaults.update(kwargs)
    return Vendor(**defaults)


# =============================================================================
# Bead collmex-cli-rxc: vendor-match missing_fields
# =============================================================================


class TestVendorMissingFields:
    """Tests for _vendor_missing_fields() helper."""

    def test_complete_vendor_no_missing_fields(self):
        """A fully-filled vendor has no missing fields."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor()
        assert _vendor_missing_fields(vendor) == []

    def test_missing_street(self):
        """Empty street is flagged as missing."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(street="")
        assert "street" in _vendor_missing_fields(vendor)

    def test_missing_postal_code(self):
        """Empty postal_code is flagged as missing."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(postal_code="")
        assert "postal_code" in _vendor_missing_fields(vendor)

    def test_missing_city(self):
        """Empty city is flagged as missing."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(city="")
        assert "city" in _vendor_missing_fields(vendor)

    def test_missing_iban(self):
        """Empty iban is flagged as missing."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(iban="")
        assert "iban" in _vendor_missing_fields(vendor)

    def test_missing_both_vat_id_and_tax_id(self):
        """Both vat_id and tax_id empty => vat_id flagged as missing."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(vat_id="", tax_id="")
        missing = _vendor_missing_fields(vendor)
        assert "vat_id" in missing

    def test_tax_id_satisfies_vat_requirement(self):
        """Having tax_id but no vat_id is ok — does NOT flag vat_id."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(vat_id="", tax_id="123/456/78901")
        missing = _vendor_missing_fields(vendor)
        assert "vat_id" not in missing

    def test_vat_id_satisfies_vat_requirement(self):
        """Having vat_id but no tax_id is ok."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(vat_id="DE123456789", tax_id="")
        missing = _vendor_missing_fields(vendor)
        assert "vat_id" not in missing

    def test_multiple_missing_fields(self):
        """All missing fields are returned."""
        from collmex_cli.client import _vendor_missing_fields

        vendor = make_vendor(street="", city="", vat_id="", tax_id="", iban="")
        missing = _vendor_missing_fields(vendor)
        assert "street" in missing
        assert "city" in missing
        assert "vat_id" in missing
        assert "iban" in missing


class TestVendorMatchMissingFields:
    """Tests that match_vendor() includes missing_fields in response."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_exact_match_includes_missing_fields_empty(self, mock_api_cls):
        """Exact match with complete vendor returns empty missing_fields."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        vendor = make_vendor(iban="DE89370400440532013000")
        mock_api.request.return_value = [vendor.to_csv_row()]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        result = client.match_vendor(iban="DE89370400440532013000")
        assert result["match"] == "exact"
        assert "missing_fields" in result
        assert result["missing_fields"] == []

    @patch("collmex_cli.client.CollmexAPI")
    def test_exact_match_includes_missing_fields_non_empty(self, mock_api_cls):
        """Exact match with incomplete vendor flags missing_fields."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        vendor = make_vendor(iban="DE89370400440532013000", street="", postal_code="")
        mock_api.request.return_value = [vendor.to_csv_row()]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        result = client.match_vendor(iban="DE89370400440532013000")
        assert result["match"] == "exact"
        assert "missing_fields" in result
        assert "street" in result["missing_fields"]
        assert "postal_code" in result["missing_fields"]

    @patch("collmex_cli.client.CollmexAPI")
    def test_fuzzy_candidates_include_missing_fields(self, mock_api_cls):
        """Fuzzy candidates each include a missing_fields list."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        vendor = make_vendor(company_name="Acme GmbH", street="", vat_id="", tax_id="")
        mock_api.request.return_value = [vendor.to_csv_row()]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        result = client.match_vendor(name="Acme GmbH something else")
        assert result["match"] in ("fuzzy", "exact")
        if result["match"] == "fuzzy":
            assert all("missing_fields" in c for c in result["candidates"])


# =============================================================================
# Bead collmex-cli-qqe: vendor-update
# =============================================================================


class TestUpdateVendor:
    """Tests for CollmexClient.update_vendor()."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_update_vendor_fetches_and_saves(self, mock_api_cls):
        """update_vendor() fetches current vendor, updates fields, saves via create_vendor."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1

        original = make_vendor(vendor_id=42, street="Alte Str. 1", city="Hamburg")

        # First call: VENDOR_GET; second call: CMXLIF (create)
        mock_api.request.side_effect = [
            [original.to_csv_row()],   # get_vendors
            [["MESSAGE", "I1", "0", "OK"]],  # create_vendor
        ]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        updated = client.update_vendor(vendor_id=42, street="Neue Str. 5")
        assert isinstance(updated, Vendor)
        assert updated.street == "Neue Str. 5"
        assert updated.city == "Hamburg"  # unchanged

    @patch("collmex_cli.client.CollmexAPI")
    def test_update_vendor_not_found_raises(self, mock_api_cls):
        """update_vendor() raises ValueError when vendor not found."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        with pytest.raises(ValueError, match="not found"):
            client.update_vendor(vendor_id=999, street="X")

    @patch("collmex_cli.client.CollmexAPI")
    def test_update_vendor_returns_updated_object(self, mock_api_cls):
        """update_vendor() returns updated Vendor with all original fields intact."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        original = make_vendor(vendor_id=10, vat_id="DE999888777", city="München")
        mock_api.request.side_effect = [
            [original.to_csv_row()],
            [["MESSAGE", "I1", "0", "OK"]],
        ]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        result = client.update_vendor(vendor_id=10, city="Berlin")
        assert result.city == "Berlin"
        assert result.vat_id == "DE999888777"  # preserved

    @patch("collmex_cli.client.CollmexAPI")
    def test_update_vendor_multiple_fields(self, mock_api_cls):
        """update_vendor() updates multiple fields at once."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        original = make_vendor(vendor_id=5)
        mock_api.request.side_effect = [
            [original.to_csv_row()],
            [["MESSAGE", "I1", "0", "OK"]],
        ]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        result = client.update_vendor(vendor_id=5, iban="DE12345678901234567890", bic="TESTDE88XXX")
        assert result.iban == "DE12345678901234567890"
        assert result.bic == "TESTDE88XXX"


class TestVendorUpdateCommand:
    """Tests for CLI 'vendor-update' command."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_vendor_update_basic(self, mock_client_cls):
        """vendor-update --vendor-id 42 --street 'Neue Str' updates street."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.update_vendor.return_value = make_vendor(vendor_id=42, street="Neue Str. 5")

        result = runner.invoke(app, ["vendor-update", "--vendor-id", "42", "--street", "Neue Str. 5"])
        assert result.exit_code == 0
        instance.update_vendor.assert_called_once_with(vendor_id=42, street="Neue Str. 5")

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_vendor_update_json_output(self, mock_client_cls):
        """vendor-update --json outputs updated vendor as JSON."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.update_vendor.return_value = make_vendor(vendor_id=42)

        result = runner.invoke(app, [
            "vendor-update", "--vendor-id", "42", "--city", "Köln", "--json",
        ])
        assert result.exit_code == 0
        # Find JSON block (output may contain warning lines before JSON)
        json_start = result.output.find("{")
        assert json_start >= 0, f"No JSON found in output: {result.output!r}"
        data = json.loads(result.output[json_start:])
        assert data["vendor_id"] == 42

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_vendor_update_warns_on_overwrite(self, mock_client_cls):
        """vendor-update warns when overwriting a non-empty field."""
        instance = mock_client_cls.return_value.__enter__.return_value

        # Simulate: existing vendor has company_name set, we're overwriting it
        existing = make_vendor(vendor_id=42, company_name="Old Name GmbH")
        updated = make_vendor(vendor_id=42, company_name="New Name GmbH")
        instance.get_vendors.return_value = [existing]
        instance.update_vendor.return_value = updated

        result = runner.invoke(app, [
            "vendor-update", "--vendor-id", "42",
            "--name", "New Name GmbH",
        ])
        # Should succeed but warning printed
        assert result.exit_code == 0

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_vendor_update_requires_vendor_id(self, mock_client_cls):
        """vendor-update without --vendor-id fails with error."""
        result = runner.invoke(app, ["vendor-update", "--street", "Str. 1"])
        assert result.exit_code != 0

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_vendor_update_all_options(self, mock_client_cls):
        """vendor-update accepts all documented options."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.update_vendor.return_value = make_vendor(vendor_id=1)

        result = runner.invoke(app, [
            "vendor-update", "--vendor-id", "1",
            "--street", "Str. 1",
            "--postal-code", "12345",
            "--city", "Berlin",
            "--vat-id", "DE123",
            "--tax-id", "123/456",
            "--iban", "DE89370400440532013000",
            "--bic", "COBADEFFXXX",
            "--name", "Test GmbH",
            "--email", "test@example.com",
            "--phone", "+49 30 1234",
        ])
        assert result.exit_code == 0
        instance.update_vendor.assert_called_once()


# =============================================================================
# Bead collmex-cli-fjf: zugferd-create validation
# =============================================================================


class TestValidateVendorForZugferd:
    """Tests for validate_vendor_for_zugferd() function."""

    def test_complete_vendor_no_errors(self):
        """Complete vendor passes validation."""
        from collmex_cli.zugferd import validate_vendor_for_zugferd

        vendor = make_vendor()
        assert validate_vendor_for_zugferd(vendor) == []

    def test_missing_street(self):
        """Missing street is flagged."""
        from collmex_cli.zugferd import validate_vendor_for_zugferd

        vendor = make_vendor(street="")
        assert "street" in validate_vendor_for_zugferd(vendor)

    def test_missing_postal_code(self):
        """Missing postal_code is flagged."""
        from collmex_cli.zugferd import validate_vendor_for_zugferd

        vendor = make_vendor(postal_code="")
        assert "postal_code" in validate_vendor_for_zugferd(vendor)

    def test_missing_city(self):
        """Missing city is flagged."""
        from collmex_cli.zugferd import validate_vendor_for_zugferd

        vendor = make_vendor(city="")
        assert "city" in validate_vendor_for_zugferd(vendor)

    def test_missing_both_vat_and_tax(self):
        """Missing both vat_id and tax_id is flagged."""
        from collmex_cli.zugferd import validate_vendor_for_zugferd

        vendor = make_vendor(vat_id="", tax_id="")
        missing = validate_vendor_for_zugferd(vendor)
        assert "vat_id" in missing

    def test_tax_id_satisfies_requirement(self):
        """tax_id alone satisfies the VAT requirement."""
        from collmex_cli.zugferd import validate_vendor_for_zugferd

        vendor = make_vendor(vat_id="", tax_id="123/456/78901")
        assert "vat_id" not in validate_vendor_for_zugferd(vendor)

    def test_multiple_missing(self):
        """Returns all missing fields."""
        from collmex_cli.zugferd import validate_vendor_for_zugferd

        vendor = make_vendor(street="", city="", vat_id="", tax_id="")
        missing = validate_vendor_for_zugferd(vendor)
        assert "street" in missing
        assert "city" in missing
        assert "vat_id" in missing


class TestZugferdCreateValidation:
    """Tests for zugferd-create CLI command validation."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_zugferd_create_exits_on_missing_fields(self, mock_client_cls):
        """zugferd-create exits with code 1 when vendor has missing fields."""
        instance = mock_client_cls.return_value.__enter__.return_value
        incomplete_vendor = make_vendor(vendor_id=5, street="", vat_id="", tax_id="")
        instance.get_vendors.return_value = [incomplete_vendor]

        result = runner.invoke(app, [
            "zugferd-create",
            "--vendor-id", "5",
            "--invoice", "INV-001",
            "--date", "2026-01-15",
            "--desc", "Beratung",
            "--net", "1000.00",
        ])
        assert result.exit_code == 1

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_zugferd_create_shows_missing_field_names(self, mock_client_cls):
        """zugferd-create error output lists the missing fields."""
        instance = mock_client_cls.return_value.__enter__.return_value
        incomplete_vendor = make_vendor(vendor_id=5, street="", postal_code="")
        instance.get_vendors.return_value = [incomplete_vendor]

        result = runner.invoke(app, [
            "zugferd-create",
            "--vendor-id", "5",
            "--invoice", "INV-001",
            "--date", "2026-01-15",
            "--desc", "Beratung",
            "--net", "1000.00",
        ])
        assert result.exit_code == 1
        assert "street" in result.output or "postal_code" in result.output

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    @patch("collmex_cli.zugferd.create_zugferd_xml")
    def test_zugferd_create_force_skips_validation(self, mock_xml, mock_client_cls):
        """zugferd-create --force skips validation and generates XML anyway."""
        import os
        instance = mock_client_cls.return_value.__enter__.return_value
        incomplete_vendor = make_vendor(vendor_id=5, street="", vat_id="", tax_id="")
        instance.get_vendors.return_value = [incomplete_vendor]
        mock_xml.return_value = b"<xml/>"

        env = {
            "COLLMEX_CUSTOMER_ID": "1",
            "COLLMEX_USERNAME": "test",
            "COLLMEX_PASSWORD": "test",
            "COLLMEX_BUYER_NAME": "Buyer GmbH",
            "COLLMEX_BUYER_STREET": "Buyer Str. 1",
            "COLLMEX_BUYER_ZIP": "10115",
            "COLLMEX_BUYER_CITY": "Berlin",
        }
        result = runner.invoke(app, [
            "zugferd-create",
            "--vendor-id", "5",
            "--invoice", "INV-001",
            "--date", "2026-01-15",
            "--desc", "Beratung",
            "--net", "1000.00",
            "--force",
        ], env=env)
        # Should not exit with 1 due to validation
        assert result.exit_code == 0
        mock_xml.assert_called_once()

"""Tests for the bank-status command and XDG app config."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from typer.testing import CliRunner

from collmex_cli.app_config import AppConfig, load_config
from collmex_cli.client import CollmexClient
from collmex_cli.main import app
from collmex_cli.models import AccountingDocument

runner = CliRunner()


def _make_booking(doc_date: str, amount: str = "100.00") -> AccountingDocument:
    """Helper to create a booking with a given date."""
    return AccountingDocument(
        record_type="ACCDOC",
        company_id=1,
        fiscal_year=2026,
        booking_id=1,
        document_date=date.fromisoformat(doc_date),
        account_number=1200,
        debit_credit="S",
        amount=Decimal(amount),
    )


# =============================================================================
# AppConfig / XDG tests
# =============================================================================


class TestAppConfig:
    """Tests for XDG config loading."""

    def test_load_config_no_file(self, tmp_path):
        """Without config file, returns empty bank_accounts."""
        with patch("collmex_cli.app_config.config_path", return_value=tmp_path / "nonexistent.toml"):
            cfg = load_config()
        assert cfg.bank_accounts == {}

    def test_load_config_xdg(self, tmp_path):
        """Config is loaded from XDG path."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[bank_accounts]\nGeschaeftskonto = 1200\nTagesgeld = 1210\n')
        with patch("collmex_cli.app_config.config_path", return_value=config_file):
            cfg = load_config()
        assert cfg.bank_accounts == {"Geschaeftskonto": 1200, "Tagesgeld": 1210}

    def test_xdg_config_home_respected(self, tmp_path, monkeypatch):
        """XDG_CONFIG_HOME env var is used when set."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from collmex_cli.app_config import config_path
        assert config_path() == tmp_path / "collmex-cli" / "config.toml"


# =============================================================================
# Client method tests
# =============================================================================


class TestGetLastBankBookingDate:
    """Tests for CollmexClient.get_last_bank_booking_date()."""

    @patch.object(CollmexClient, "get_bookings")
    @patch("collmex_cli.client.CollmexAPI")
    def test_returns_last_date(self, _mock_api, mock_get_bookings):
        mock_get_bookings.return_value = [
            _make_booking("2026-01-15"),
            _make_booking("2026-03-01"),
            _make_booking("2026-02-10"),
        ]
        client = CollmexClient.__new__(CollmexClient)
        client.api = _mock_api
        result = client.get_last_bank_booking_date(bank_account=1200, fiscal_year=2026)

        assert result["last_date"] == date(2026, 3, 1)
        assert result["booking_count"] == 3
        assert result["account"] == 1200
        assert result["fiscal_year"] == 2026

    @patch.object(CollmexClient, "get_bookings")
    @patch("collmex_cli.client.CollmexAPI")
    def test_custom_account(self, _mock_api, mock_get_bookings):
        mock_get_bookings.return_value = [
            _make_booking("2026-02-20"),
        ]
        client = CollmexClient.__new__(CollmexClient)
        client.api = _mock_api
        result = client.get_last_bank_booking_date(bank_account=1800, fiscal_year=2026)

        assert result["account"] == 1800
        mock_get_bookings.assert_called_once_with(
            fiscal_year=2026,
            account_number=1800,
        )

    @patch.object(CollmexClient, "get_bookings")
    @patch("collmex_cli.client.CollmexAPI")
    def test_no_bookings(self, _mock_api, mock_get_bookings):
        mock_get_bookings.return_value = []
        client = CollmexClient.__new__(CollmexClient)
        client.api = _mock_api
        result = client.get_last_bank_booking_date(bank_account=1200, fiscal_year=2026)

        assert result["last_date"] is None
        assert result["booking_count"] == 0


# =============================================================================
# CLI command tests
# =============================================================================


class TestBankStatusCommand:
    """Tests for the CLI bank-status command."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_single_account_json(self, mock_client_cls):
        """--account 1200 --json returns single result."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_last_bank_booking_date.return_value = {
            "account": 1200,
            "fiscal_year": 2026,
            "last_date": date(2026, 3, 1),
            "booking_count": 42,
        }
        result = runner.invoke(app, ["bank-status", "--account", "1200", "--json"])
        assert result.exit_code == 0
        assert '"last_date": "2026-03-01"' in result.output
        assert '"booking_count": 42' in result.output

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_no_bookings_message(self, mock_client_cls):
        """Table shows 'none' when no bookings found."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_last_bank_booking_date.return_value = {
            "account": 1200,
            "fiscal_year": 2026,
            "last_date": None,
            "booking_count": 0,
        }
        result = runner.invoke(app, ["bank-status", "--account", "1200"])
        assert result.exit_code == 0
        assert "none" in result.output

    @patch("collmex_cli.main.load_config")
    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_all_accounts_from_config(self, mock_client_cls, mock_load_config):
        """Without --account, all configured accounts are queried."""
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Geschaeftskonto": 1200, "Tagesgeld": 1210}
        )
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_last_bank_booking_date.side_effect = [
            {"account": 1200, "fiscal_year": 2026, "last_date": date(2026, 3, 1), "booking_count": 42},
            {"account": 1210, "fiscal_year": 2026, "last_date": date(2026, 2, 15), "booking_count": 5},
        ]
        result = runner.invoke(app, ["bank-status"])
        assert result.exit_code == 0
        assert "1200" in result.output
        assert "1210" in result.output
        assert "Geschaeftskonto" in result.output
        assert "Tagesgeld" in result.output
        assert instance.get_last_bank_booking_date.call_count == 2

    @patch("collmex_cli.main.load_config")
    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_all_accounts_json(self, mock_client_cls, mock_load_config):
        """Without --account, --json returns array of all accounts."""
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Konto1": 1200, "Konto2": 1210}
        )
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_last_bank_booking_date.side_effect = [
            {"account": 1200, "fiscal_year": 2026, "last_date": date(2026, 3, 1), "booking_count": 10},
            {"account": 1210, "fiscal_year": 2026, "last_date": date(2026, 2, 1), "booking_count": 3},
        ]
        result = runner.invoke(app, ["bank-status", "--json"])
        assert result.exit_code == 0
        # Should be a JSON array with two entries
        assert '"Konto1"' in result.output
        assert '"Konto2"' in result.output

    def test_no_config_shows_error(self, tmp_path):
        """Without config file and no --account, shows helpful error."""
        with patch("collmex_cli.app_config.config_path", return_value=tmp_path / "nope.toml"):
            result = runner.invoke(app, ["bank-status"])
        assert result.exit_code == 1
        assert "No bank accounts configured" in result.output

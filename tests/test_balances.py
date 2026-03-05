"""Tests for ACCBAL_GET account balances feature."""

from decimal import Decimal
from unittest.mock import patch

from typer.testing import CliRunner

from collmex_cli.client import CollmexClient
from collmex_cli.main import app
from collmex_cli.models import AccountBalance

runner = CliRunner()


# =============================================================================
# Model tests
# =============================================================================


class TestAccountBalanceModel:
    """Tests for AccountBalance.from_csv_row() parsing."""

    def test_balance_model_full_row(self):
        """Parse a complete ACC_BAL row with all fields."""
        row = ["ACC_BAL", "1", "2026", "1200", "Bank", "1000,00", "500,50", "250,25"]
        bal = AccountBalance.from_csv_row(row)

        assert bal.record_type == "ACC_BAL"
        assert bal.company_id == 1
        assert bal.fiscal_year == 2026
        assert bal.account_number == 1200
        assert bal.account_name == "Bank"
        assert bal.opening_balance == Decimal("1000.00")
        assert bal.balance == Decimal("500.50")
        assert bal.turnover == Decimal("250.25")

    def test_balance_model_missing_turnover(self):
        """Parse a row where turnover field is missing (optional)."""
        row = ["ACC_BAL", "1", "2026", "4000", "Erloese", "0,00", "2500,00"]
        bal = AccountBalance.from_csv_row(row)

        assert bal.account_number == 4000
        assert bal.balance == Decimal("2500.00")
        assert bal.turnover is None

    def test_balance_model_empty_turnover(self):
        """Parse a row where turnover field is empty string."""
        row = ["ACC_BAL", "1", "2026", "3200", "Vorsteuer", "100,00", "99,99", ""]
        bal = AccountBalance.from_csv_row(row)

        assert bal.balance == Decimal("99.99")
        assert bal.turnover is None

    def test_balance_model_negative_balance(self):
        """Parse a row with negative balance (credit account)."""
        row = ["ACC_BAL", "1", "2026", "1600", "Verbindlichkeiten", "0,00", "-3500,00", ""]
        bal = AccountBalance.from_csv_row(row)

        assert bal.balance == Decimal("-3500.00")

    def test_balance_model_zero_values(self):
        """Parse a row with zero balances."""
        row = ["ACC_BAL", "1", "2026", "9999", "Konto", "0,00", "0,00", "0,00"]
        bal = AccountBalance.from_csv_row(row)

        assert bal.opening_balance == Decimal("0.00")
        assert bal.balance == Decimal("0.00")
        assert bal.turnover == Decimal("0.00")

    def test_balance_model_defaults_for_missing_fields(self):
        """Minimal row with only required fields."""
        row = ["ACC_BAL", "1", "2026", "1200"]
        bal = AccountBalance.from_csv_row(row)

        assert bal.account_number == 1200
        assert bal.account_name == ""
        assert bal.opening_balance is None
        assert bal.balance is None
        assert bal.turnover is None


# =============================================================================
# Client method tests
# =============================================================================


class TestAccbalGet:
    """Tests for CollmexClient.get_account_balances()."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_accbal_get_returns_balances(self, mock_api_cls):
        """get_account_balances() returns AccountBalance list."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            ["ACC_BAL", "1", "2026", "1200", "Bank", "0,00", "5000,00", ""],
            ["ACC_BAL", "1", "2026", "4000", "Erloese", "0,00", "12000,00", "12000,00"],
        ]

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        balances = client.get_account_balances(fiscal_year=2026)

        assert len(balances) == 2
        assert balances[0].account_number == 1200
        assert balances[1].account_number == 4000
        assert balances[1].balance == Decimal("12000.00")

    @patch("collmex_cli.client.CollmexAPI")
    def test_accbal_get_request_row(self, mock_api_cls):
        """get_account_balances() sends correct ACCBAL_GET request row."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = []

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_account_balances(fiscal_year=2026, account_number=1200)

        call_args = mock_api.request.call_args[0][0]
        assert call_args[0] == "ACCBAL_GET"
        assert "1" in call_args  # company_id
        assert "2026" in call_args
        assert "1200" in call_args

    @patch("collmex_cli.client.CollmexAPI")
    def test_accbal_get_no_filters(self, mock_api_cls):
        """get_account_balances() without filters sends empty strings for optional params."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = []

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_account_balances()

        call_args = mock_api.request.call_args[0][0]
        assert call_args[0] == "ACCBAL_GET"

    @patch("collmex_cli.client.CollmexAPI")
    def test_accbal_get_filters_non_acc_bal_rows(self, mock_api_cls):
        """get_account_balances() ignores rows that are not ACC_BAL."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            ["MESSAGE", "0", ""],
            ["ACC_BAL", "1", "2026", "1200", "Bank", "0,00", "5000,00", ""],
            ["OTHER", "data"],
        ]

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        balances = client.get_account_balances()

        assert len(balances) == 1
        assert balances[0].account_number == 1200

    @patch("collmex_cli.client.CollmexAPI")
    def test_accbal_get_empty_response(self, mock_api_cls):
        """get_account_balances() returns empty list when no data."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = []

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        balances = client.get_account_balances()

        assert balances == []


# =============================================================================
# Filter tests
# =============================================================================


class TestBalanceFilters:
    """Tests for filtering by account number and fiscal year."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_fiscal_year(self, mock_api_cls):
        """Fiscal year is passed in the request."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = []

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_account_balances(fiscal_year=2025)

        call_args = mock_api.request.call_args[0][0]
        assert "2025" in call_args

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_account_number(self, mock_api_cls):
        """Account number is passed in the request."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = []

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_account_balances(account_number=4000)

        call_args = mock_api.request.call_args[0][0]
        assert "4000" in call_args

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_both(self, mock_api_cls):
        """Both fiscal year and account number can be combined."""
        mock_api = mock_api_cls.return_value
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            ["ACC_BAL", "1", "2026", "3200", "Vorsteuer", "0,00", "800,00", ""],
        ]

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        balances = client.get_account_balances(fiscal_year=2026, account_number=3200)

        call_args = mock_api.request.call_args[0][0]
        assert "2026" in call_args
        assert "3200" in call_args
        assert len(balances) == 1
        assert balances[0].account_number == 3200


# =============================================================================
# CLI command tests
# =============================================================================


class TestBalancesCli:
    """Tests for the CLI balances command."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_balances_table_output(self, mock_client_cls):
        """balances command renders a table by default."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_account_balances.return_value = [
            AccountBalance(
                record_type="ACC_BAL",
                company_id=1,
                fiscal_year=2026,
                account_number=1200,
                account_name="Bank",
                opening_balance=Decimal("0.00"),
                balance=Decimal("5000.00"),
                turnover=None,
            ),
        ]

        result = runner.invoke(app, ["balances"])

        assert result.exit_code == 0
        assert "1200" in result.output
        assert "Bank" in result.output
        assert "5000" in result.output

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_balances_json_output(self, mock_client_cls):
        """balances --json outputs valid JSON."""
        import json

        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_account_balances.return_value = [
            AccountBalance(
                record_type="ACC_BAL",
                company_id=1,
                fiscal_year=2026,
                account_number=1200,
                account_name="Bank",
                opening_balance=Decimal("0.00"),
                balance=Decimal("5000.00"),
                turnover=None,
            ),
        ]

        result = runner.invoke(app, ["balances", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["account_number"] == 1200
        assert data[0]["balance"] == "5000.00"

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_balances_filter_account(self, mock_client_cls):
        """--account option is passed through to get_account_balances."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_account_balances.return_value = []

        result = runner.invoke(app, ["balances", "--account", "1200"])

        assert result.exit_code == 0
        instance.get_account_balances.assert_called_once_with(
            fiscal_year=None, account_number=1200
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_balances_filter_year(self, mock_client_cls):
        """--year option is passed through to get_account_balances."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_account_balances.return_value = []

        result = runner.invoke(app, ["balances", "--year", "2025"])

        assert result.exit_code == 0
        instance.get_account_balances.assert_called_once_with(
            fiscal_year=2025, account_number=None
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_balances_empty_result(self, mock_client_cls):
        """balances with no results shows appropriate message."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_account_balances.return_value = []

        result = runner.invoke(app, ["balances"])

        assert result.exit_code == 0
        assert "0" in result.output  # total count

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_balances_multiple_accounts_json(self, mock_client_cls):
        """Multiple balances are all returned in JSON array."""
        import json

        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_account_balances.return_value = [
            AccountBalance(
                record_type="ACC_BAL",
                company_id=1,
                fiscal_year=2026,
                account_number=1200,
                account_name="Bank",
                balance=Decimal("5000.00"),
            ),
            AccountBalance(
                record_type="ACC_BAL",
                company_id=1,
                fiscal_year=2026,
                account_number=4000,
                account_name="Erloese",
                balance=Decimal("12000.00"),
            ),
        ]

        result = runner.invoke(app, ["balances", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["account_number"] == 1200
        assert data[1]["account_number"] == 4000

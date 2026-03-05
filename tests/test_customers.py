"""Tests for Customer management (CUSTOMER_GET + CMXKND)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from collmex_cli.client import CollmexClient
from collmex_cli.main import app
from collmex_cli.models import Customer

runner = CliRunner()


# =============================================================================
# Model tests
# =============================================================================


class TestCustomerModel:
    """Tests for the Customer Pydantic model."""

    def test_customer_model_defaults(self):
        """Customer model can be created with only required field defaults."""
        customer = Customer()
        assert customer.record_type == "CMXKND"
        assert customer.customer_id is None
        assert customer.company_id == 1
        assert customer.country == "DE"

    def test_customer_model_full(self):
        """Customer model accepts all fields."""
        customer = Customer(
            customer_id=42,
            company_id=1,
            salutation="Herr",
            first_name="Max",
            last_name="Mustermann",
            company_name="Muster GmbH",
            street="Musterstr. 1",
            zip_code="12345",
            city="Berlin",
            country="DE",
            email="max@example.com",
            phone="+49 30 12345678",
            iban="DE12345678901234567890",
            bic="BELADEBEXXX",
        )
        assert customer.customer_id == 42
        assert customer.first_name == "Max"
        assert customer.last_name == "Mustermann"
        assert customer.company_name == "Muster GmbH"
        assert customer.email == "max@example.com"
        assert customer.iban == "DE12345678901234567890"

    def test_customer_from_csv_row(self):
        """Customer.from_csv_row() correctly parses a CMXKND row (official field order)."""
        row = [
            "CMXKND",            # 0  record_type
            "100",               # 1  customer_id
            "1",                 # 2  company_id
            "Herr",              # 3  salutation
            "Dr.",               # 4  title
            "Max",               # 5  first_name
            "Mustermann",        # 6  last_name
            "Muster GmbH",       # 7  company_name
            "Buchhaltung",       # 8  department
            "Hauptstr. 5",       # 9  street
            "10115",             # 10 zip_code
            "Berlin",            # 11 city
            "Notiz hier",        # 12 notes
            "0",                 # 13 inactive
            "DE",                # 14 country
            "+49 30 999",        # 15 phone
            "",                  # 16 fax
            "max@example.com",   # 17 email
            "1234567890",        # 18 bank_account
            "70050000",          # 19 bank_code
            "DE12345678901234567890", # 20 iban
            "BELADEBEXXX",       # 21 bic
            "Sparkasse Berlin",  # 22 bank_name
            "",                  # 23 reserved
            "DE123456789",       # 24 vat_id
            "30",                # 25 payment_condition
        ]
        customer = Customer.from_csv_row(row)
        assert customer.customer_id == 100
        assert customer.first_name == "Max"
        assert customer.last_name == "Mustermann"
        assert customer.company_name == "Muster GmbH"
        assert customer.city == "Berlin"
        assert customer.zip_code == "10115"
        assert customer.notes == "Notiz hier"
        assert customer.country == "DE"
        assert customer.email == "max@example.com"
        assert customer.iban == "DE12345678901234567890"
        assert customer.bic == "BELADEBEXXX"
        assert customer.vat_id == "DE123456789"

    def test_customer_to_csv_row(self):
        """Customer.to_csv_row() produces correct CSV row."""
        customer = Customer(
            customer_id=42,
            company_id=1,
            first_name="Anna",
            last_name="Schmidt",
            company_name="Schmidt AG",
            street="Teststr. 7",
            zip_code="80331",
            city="München",
            country="DE",
            email="anna@schmidt.de",
        )
        row = customer.to_csv_row()
        assert row[0] == "CMXKND"
        assert row[1] == "42"
        assert row[2] == "1"
        assert row[6] == "Schmidt"       # last_name at index 6
        assert row[7] == "Schmidt AG"    # company_name at index 7
        assert row[9] == "Teststr. 7"   # street at index 9
        assert row[10] == "80331"        # zip_code at index 10
        assert row[11] == "München"      # city at index 11
        assert row[14] == "DE"           # country at index 14 (after notes+inactive)
        assert row[17] == "anna@schmidt.de"  # email at index 17

    def test_customer_from_csv_row_short(self):
        """from_csv_row() handles short rows gracefully with defaults."""
        row = ["CMXKND", "5", "1"]
        customer = Customer.from_csv_row(row)
        assert customer.customer_id == 5
        assert customer.first_name == ""
        assert customer.city == ""


# =============================================================================
# Client method tests
# =============================================================================


class TestGetCustomers:
    """Tests for CollmexClient.get_customers()."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_get_customers_returns_list(self, mock_api_cls):
        """get_customers() returns a list of Customer objects."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            [
                # 0          1     2    3       4    5       6
                "CMXKND", "10", "1", "Herr", "", "Hans", "Müller",
                # 7              8    9         10       11
                "Müller GmbH", "", "Str. 1", "10115", "Berlin",
                # 12  13   14    15           16   17
                "",  "0", "DE", "+49 30 1",  "",  "hans@example.com",
            ]
        ]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        customers = client.get_customers()
        assert len(customers) == 1
        assert isinstance(customers[0], Customer)
        assert customers[0].customer_id == 10
        assert customers[0].last_name == "Müller"

    @patch("collmex_cli.client.CollmexAPI")
    def test_get_customers_filters_by_id(self, mock_api_cls):
        """get_customers() passes customer_id filter to API."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        result = client.get_customers(customer_id=99)
        assert result == []
        # Check the request was called with CUSTOMER_GET and customer ID
        call_args = mock_api.request.call_args[0][0]
        assert call_args[0] == "CUSTOMER_GET"
        assert call_args[1] == "99"

    @patch("collmex_cli.client.CollmexAPI")
    def test_get_customers_with_text_search(self, mock_api_cls):
        """get_customers() passes text search to API."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_customers(text="Müller")
        call_args = mock_api.request.call_args[0][0]
        assert call_args[0] == "CUSTOMER_GET"
        assert "Müller" in call_args

    @patch("collmex_cli.client.CollmexAPI")
    def test_get_customers_ignores_non_cmxknd_rows(self, mock_api_cls):
        """get_customers() filters out non-CMXKND rows from response."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            ["MESSAGE", "I1", "0", "OK"],
            ["CMXKND", "5", "1", "", "", "Eva", "Test", "Test GmbH", "",
             "Str. 2", "20000", "Hamburg", "", "0", "DE", "", "", "eva@test.de"],
        ]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        customers = client.get_customers()
        assert len(customers) == 1
        assert customers[0].customer_id == 5


class TestCreateCustomer:
    """Tests for CollmexClient.create_customer()."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_create_customer_calls_api(self, mock_api_cls):
        """create_customer() calls API with CMXKND row."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = [["MESSAGE", "I1", "0", "OK"]]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        customer = Customer(
            company_name="Neuer Kunde GmbH",
            email="neu@kunde.de",
        )
        result = client.create_customer(customer)

        assert result == [["MESSAGE", "I1", "0", "OK"]]
        call_args = mock_api.request.call_args[0][0]
        assert call_args[0] == "CMXKND"

    @patch("collmex_cli.client.CollmexAPI")
    def test_create_customer_with_all_fields(self, mock_api_cls):
        """create_customer() passes full customer data to API."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        customer = Customer(
            first_name="Peter",
            last_name="Pan",
            company_name="Pan GmbH",
            street="Neverland 1",
            zip_code="99999",
            city="Fantasialand",
            country="DE",
            email="peter@pan.de",
            iban="DE98765432109876543210",
        )
        client.create_customer(customer)

        call_args = mock_api.request.call_args[0][0]
        assert call_args[0] == "CMXKND"
        assert "Peter" in call_args
        assert "Pan GmbH" in call_args


# =============================================================================
# CLI command tests
# =============================================================================


class TestCustomersCommand:
    """Tests for the CLI 'customers' command."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customers_table_output(self, mock_client_cls):
        """customers command shows a table by default."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_customers.return_value = [
            Customer(
                customer_id=1,
                company_name="Acme Corp",
                city="Berlin",
                email="acme@example.com",
            )
        ]
        result = runner.invoke(app, ["customers"])
        assert result.exit_code == 0
        assert "Acme Corp" in result.output
        assert "Berlin" in result.output

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customers_json_output(self, mock_client_cls):
        """customers --json returns JSON output."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_customers.return_value = [
            Customer(
                customer_id=7,
                company_name="JSON Corp",
                email="json@corp.de",
            )
        ]
        result = runner.invoke(app, ["customers", "--json"])
        assert result.exit_code == 0
        # Should be parseable JSON
        import json
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["customer_id"] == 7
        assert data[0]["company_name"] == "JSON Corp"

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customers_filter_by_id(self, mock_client_cls):
        """customers --id passes filter to client."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_customers.return_value = []
        result = runner.invoke(app, ["customers", "--id", "42"])
        assert result.exit_code == 0
        instance.get_customers.assert_called_once_with(customer_id=42, text=None)

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customers_search_text(self, mock_client_cls):
        """customers --search passes text filter to client."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_customers.return_value = []
        result = runner.invoke(app, ["customers", "--search", "Müller"])
        assert result.exit_code == 0
        instance.get_customers.assert_called_once_with(customer_id=None, text="Müller")

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customers_total_count(self, mock_client_cls):
        """customers table output shows total count."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_customers.return_value = [
            Customer(customer_id=1, company_name="A GmbH"),
            Customer(customer_id=2, company_name="B GmbH"),
        ]
        result = runner.invoke(app, ["customers"])
        assert result.exit_code == 0
        assert "2" in result.output  # total count shown


class TestCustomerCreateCommand:
    """Tests for the CLI 'customer-create' command."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customer_create_basic(self, mock_client_cls):
        """customer-create creates a customer with --company-name."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.create_customer.return_value = [["MESSAGE", "I1", "0", "OK"]]
        result = runner.invoke(app, ["customer-create", "--company-name", "Neue Firma GmbH"])
        assert result.exit_code == 0
        assert instance.create_customer.called

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customer_create_with_all_fields(self, mock_client_cls):
        """customer-create accepts all required CLI options."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.create_customer.return_value = []
        result = runner.invoke(app, [
            "customer-create",
            "--company-name", "Test GmbH",
            "--first-name", "Max",
            "--last-name", "Mustermann",
            "--email", "max@test.de",
            "--street", "Teststr. 1",
            "--zip-code", "12345",
            "--city", "Berlin",
            "--country", "DE",
        ])
        assert result.exit_code == 0
        assert instance.create_customer.called
        created = instance.create_customer.call_args[0][0]
        assert isinstance(created, Customer)
        assert created.company_name == "Test GmbH"
        assert created.first_name == "Max"
        assert created.last_name == "Mustermann"
        assert created.email == "max@test.de"

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_customer_create_json_output(self, mock_client_cls):
        """customer-create --json outputs JSON response."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.create_customer.return_value = [["MESSAGE", "I1", "0", "OK"]]
        result = runner.invoke(app, [
            "customer-create",
            "--company-name", "JSON Firma",
            "--json",
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["status"] == "created"

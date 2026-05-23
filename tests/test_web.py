"""Tests for Collmex web automation (playwright-cli wrapper)."""

import json
from unittest.mock import MagicMock, call, patch

import pytest
from typer.testing import CliRunner

from collmex_cli.app_config import AppConfig
from collmex_cli.main import app
from collmex_cli.web import (
    CollmexWeb,
    CollmexWebError,
    PlaywrightCliError,
    _extract_ref,
    _find_all_refs_by_role,
    _find_ref_by_role,
    _find_ref_by_text,
    _find_ref_for_button,
    _find_ref_for_combobox,
    _find_ref_for_textbox,
    _parse_snapshot_table,
)

runner = CliRunner()

SAMPLE_SNAPSHOT_TABLE = """\
- table "Bank Statements"
  - row "Datum Betrag Text Status"
    - columnheader "Datum" [ref=h1]
    - columnheader "Betrag" [ref=h2]
    - columnheader "Text" [ref=h3]
    - columnheader "Status" [ref=h4]
  - row "2026-03-01 -150.00 ACME Corp Zu buchen"
    - cell "2026-03-01" [ref=c1]
    - cell "-150.00" [ref=c2]
    - cell "ACME Corp" [ref=c3]
    - cell "Zu buchen" [ref=c4]
  - row "2026-03-02 250.00 Payment received Zu buchen"
    - cell "2026-03-02" [ref=c5]
    - cell "250.00" [ref=c6]
    - cell "Payment received" [ref=c7]
    - cell "Zu buchen" [ref=c8]
"""

SAMPLE_SNAPSHOT_FORM = """\
- heading "Bankkonto-Auszug importieren" [ref=h1]
- combobox "Bankkonto:" [ref=s1]
  - option "Postbank -Giro- Hamburg"
  - option "Fyrst 62444500"
- button "Choose File" [ref=f1]
- button "Importieren" [ref=b1]
"""

SAMPLE_SNAPSHOT_LOGIN_PAGE = """\
- heading "Anmelden" [ref=h1]
- textbox "Benutzer:" [ref=e63]
- textbox "Kennwort:" [ref=e67]
- button "Anmelden" [ref=e51]
"""

SAMPLE_SNAPSHOT_LOGGED_IN = """\
- navigation "Hauptmenu"
  - link "Buchhaltung" [ref=m1]
  - link "Abmelden" [ref=m2]
"""


# =============================================================================
# Snapshot parsing tests
# =============================================================================


class TestSnapshotParsing:
    """Tests for snapshot parsing helper functions."""

    def test_extract_ref(self):
        assert _extract_ref('- button "Submit" [ref=b1]') == "b1"
        assert _extract_ref('- text "No ref here"') is None

    def test_find_ref_by_role(self):
        assert _find_ref_by_role(SAMPLE_SNAPSHOT_FORM, "combobox") == "s1"
        assert _find_ref_by_role(SAMPLE_SNAPSHOT_FORM, "checkbox") is None

    def test_find_all_refs_by_role(self):
        snapshot = """\
- combobox "Account" [ref=s1]
- combobox "Status" [ref=s2]
- button "Go" [ref=b1]
"""
        refs = _find_all_refs_by_role(snapshot, "combobox")
        assert refs == ["s1", "s2"]

    def test_find_ref_by_text(self):
        assert _find_ref_by_text(SAMPLE_SNAPSHOT_FORM, "Importieren") == "b1"
        assert _find_ref_by_text(SAMPLE_SNAPSHOT_FORM, "Nonexistent") is None

    def test_find_ref_for_textbox(self):
        assert _find_ref_for_textbox(SAMPLE_SNAPSHOT_LOGIN_PAGE, "Benutzer:") == "e63"
        assert _find_ref_for_textbox(SAMPLE_SNAPSHOT_LOGIN_PAGE, "Kennwort:") == "e67"
        assert _find_ref_for_textbox(SAMPLE_SNAPSHOT_LOGIN_PAGE, "Nope") is None

    def test_find_ref_for_button(self):
        assert _find_ref_for_button(SAMPLE_SNAPSHOT_LOGIN_PAGE, "Anmelden") == "e51"
        assert _find_ref_for_button(SAMPLE_SNAPSHOT_LOGIN_PAGE, "Nope") is None

    def test_parse_table(self):
        rows = _parse_snapshot_table(SAMPLE_SNAPSHOT_TABLE)
        assert len(rows) == 2
        assert rows[0] == {
            "Datum": "2026-03-01",
            "Betrag": "-150.00",
            "Text": "ACME Corp",
            "Status": "Zu buchen",
        }
        assert rows[1]["Betrag"] == "250.00"

    def test_parse_empty_table(self):
        assert _parse_snapshot_table("") == []

    def test_parse_table_header_only(self):
        snapshot = """\
- row "A B C"
  - columnheader "A" [ref=h1]
  - columnheader "B" [ref=h2]
  - columnheader "C" [ref=h3]
"""
        assert _parse_snapshot_table(snapshot) == []


# =============================================================================
# CollmexWeb class tests
# =============================================================================


class TestCollmexWeb:
    """Tests for CollmexWeb with mocked playwright-cli calls."""

    @pytest.fixture()
    def web(self):
        """Create a CollmexWeb instance with mocked config.

        Mocks both _pcli and _snapshot so no real playwright-cli calls are made.
        Tests should set web._pcli.side_effect to control return values.
        The _snapshot mock delegates to _pcli to consume side_effect values.
        """
        config = MagicMock()
        config.customer_id = "12345"
        config.username = "testuser"
        config.password = "testpass"
        config.web_username = "testuser"
        config.web_password = "testpass"
        app_cfg = AppConfig(
            bank_accounts={"Geschaeftskonto": 1200},
            bank_accounts_web={"Geschaeftskonto": "Postbank -Giro- Hamburg"},
        )
        w = CollmexWeb(config=config, app_config=app_cfg, session="test-session")
        # Override _snapshot to just call _pcli("snapshot") so side_effect works
        original_pcli_ref = None

        def fake_snapshot():
            return w._pcli("snapshot")

        w._snapshot = fake_snapshot
        return w

    def test_resolve_account_web_name(self, web):
        assert web._resolve_account_web_name("Geschaeftskonto") == "Postbank -Giro- Hamburg"

    def test_resolve_account_web_name_fallback(self, web):
        assert web._resolve_account_web_name("Unknown") == "Unknown"

    def test_ensure_browser_opens(self, web):
        web._pcli = MagicMock(return_value="")
        web._ensure_browser()
        web._pcli.assert_called_once_with("open", "https://www.collmex.de")
        assert web._browser_opened

    def test_ensure_browser_idempotent(self, web):
        web._pcli = MagicMock()
        web._browser_opened = True
        web._ensure_browser()
        web._pcli.assert_not_called()

    def test_ensure_logged_in_already(self, web):
        """If snapshot shows 'Abmelden', no login attempt is made."""
        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # snapshot to check login
        ])
        web._ensure_logged_in()
        assert web._pcli.call_count == 2

    def test_login(self, web):
        """Login fills form fields and clicks submit."""
        web._pcli = MagicMock(side_effect=[
            "",  # goto login page
            SAMPLE_SNAPSHOT_LOGIN_PAGE,  # snapshot
            "",  # fill username
            "",  # fill password
            "",  # click Anmelden
        ])
        web._login()
        calls = web._pcli.call_args_list
        assert calls[0] == call("goto", "https://www.collmex.de/cgi-bin/cgi.exe?12345,0")
        assert calls[2] == call("fill", "e63", "testuser")
        assert calls[3] == call("fill", "e67", "testpass")
        assert calls[4] == call("click", "e51")

    def test_upload_statement(self, web, tmp_path):
        """Upload statement calls correct playwright-cli sequence."""
        stmt_file = tmp_path / "test.mt940"
        stmt_file.write_text("MT940 data")

        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login (already logged in)
            "",  # goto import page
            SAMPLE_SNAPSHOT_FORM,  # snapshot form
            "",  # select account
            SAMPLE_SNAPSHOT_FORM,  # snapshot after select (refs may change)
            "",  # click Choose File
            "",  # upload file
            SAMPLE_SNAPSHOT_FORM,  # snapshot after upload
            "",  # click Importieren
            '- text "3 Buchungen importiert" [ref=msg1]',  # result snapshot
        ])

        result = web.upload_statement(stmt_file, "Geschaeftskonto")
        assert result["status"] == "ok"
        assert "importiert" in result["message"]

        # Verify the click-then-upload sequence
        calls = web._pcli.call_args_list
        # Find the click "Choose File" and upload calls
        click_file_idx = next(
            i for i, c in enumerate(calls) if c == call("click", "f1")
        )
        upload_idx = next(
            i for i, c in enumerate(calls)
            if c[0][0] == "upload"
        )
        assert click_file_idx < upload_idx

    def test_upload_statement_no_new_transactions(self, web, tmp_path):
        """'keine neuen' in result is treated as success."""
        stmt_file = tmp_path / "test.mt940"
        stmt_file.write_text("MT940 data")

        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login
            "",  # goto import page
            SAMPLE_SNAPSHOT_FORM,  # snapshot form
            "",  # select account
            SAMPLE_SNAPSHOT_FORM,  # snapshot after select
            "",  # click Choose File
            "",  # upload file
            SAMPLE_SNAPSHOT_FORM,  # snapshot after upload
            "",  # click Importieren
            '- text "Es gibt keine neuen Umsätze" [ref=msg1]',  # result
        ])

        result = web.upload_statement(stmt_file, "Geschaeftskonto")
        assert result["status"] == "ok"
        assert "No new transactions" in result["message"]

    def test_upload_statement_file_not_found(self, web, tmp_path):
        """Missing file raises CollmexWebError."""
        with pytest.raises(CollmexWebError, match="File not found"):
            web.upload_statement(tmp_path / "nonexistent.mt940", "Geschaeftskonto")

    def test_upload_statement_error(self, web, tmp_path):
        """Error in import raises CollmexWebError."""
        stmt_file = tmp_path / "test.mt940"
        stmt_file.write_text("bad data")

        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login (already logged in)
            "",  # goto import page
            SAMPLE_SNAPSHOT_FORM,  # snapshot form
            "",  # select
            SAMPLE_SNAPSHOT_FORM,  # snapshot after select
            "",  # click Choose File
            "",  # upload
            SAMPLE_SNAPSHOT_FORM,  # snapshot after upload
            "",  # click import
            '- text "Fehler: Ungültiges Format" [ref=err1]',  # error result
        ])

        with pytest.raises(CollmexWebError, match="Import failed"):
            web.upload_statement(stmt_file, "Geschaeftskonto")

    def test_upload_statement_button_not_found(self, web, tmp_path):
        """Missing import button raises CollmexWebError."""
        stmt_file = tmp_path / "test.mt940"
        stmt_file.write_text("MT940 data")

        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login (already logged in)
            "",  # goto import page
            SAMPLE_SNAPSHOT_FORM,  # snapshot form
            "",  # select account
            SAMPLE_SNAPSHOT_FORM,  # snapshot after select (refs may change)
            "",  # click Choose File
            "",  # upload file
            '- text "Upload complete" [ref=msg1]',  # snapshot after upload
        ])

        with pytest.raises(CollmexWebError, match="Import button not found"):
            web.upload_statement(stmt_file, "Geschaeftskonto")

    def test_upload_statement_false_positive(self, web, tmp_path):
        """Unrecognized result snapshot raises CollmexWebError."""
        stmt_file = tmp_path / "test.mt940"
        stmt_file.write_text("MT940 data")

        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login (already logged in)
            "",  # goto import page
            SAMPLE_SNAPSHOT_FORM,  # snapshot form
            "",  # select account
            SAMPLE_SNAPSHOT_FORM,  # snapshot after select (refs may change)
            "",  # click Choose File
            "",  # upload file
            SAMPLE_SNAPSHOT_FORM,  # snapshot after upload
            "",  # click Importieren
            '- text "Processing started" [ref=msg1]',  # result snapshot
        ])

        with pytest.raises(CollmexWebError, match="no success confirmation received"):
            web.upload_statement(stmt_file, "Geschaeftskonto")

    def test_get_pending_bookings(self, web):
        """Pending bookings parses table correctly."""
        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login (already logged in)
            "",  # goto statement view
            # snapshot with labeled comboboxes
            '- combobox "Bankkonto:" [ref=s1]\n- combobox "Status:" [ref=s2]\n- button "Anzeigen" [ref=b1]',
            "",  # eval select account
            "",  # eval select status
            "",  # click Anzeigen
            SAMPLE_SNAPSHOT_TABLE,  # result table
        ])

        bookings = web.get_pending_bookings("Geschaeftskonto")
        assert len(bookings) == 2
        assert bookings[0]["Datum"] == "2026-03-01"
        assert bookings[0]["Betrag"] == "-150.00"

    def test_view_statements(self, web):
        """View statements selects account, fills date, and parses table."""
        view_snapshot = """\
- combobox "Bankkonto:" [ref=s1]
- textbox "Datum von:" [ref=d1]: 01.01.2026
- button "Anzeigen" [ref=b1]
"""
        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login
            "",  # goto statement view
            view_snapshot,  # snapshot form
            "",  # select account
            "",  # fill date
            view_snapshot,  # snapshot after fill (for Anzeigen button)
            "",  # click Anzeigen
            SAMPLE_SNAPSHOT_TABLE,  # result table
        ])

        rows = web.view_statements("Geschaeftskonto", date_from="01.02.2026")
        assert len(rows) == 2
        assert rows[0]["Datum"] == "2026-03-01"

        # Verify date was filled
        calls = web._pcli.call_args_list
        fill_calls = [c for c in calls if c[0][0] == "fill"]
        assert any("01.02.2026" in str(c) for c in fill_calls)

    def test_view_statements_no_date(self, web):
        """View statements without date still works (uses page default)."""
        view_snapshot = """\
- combobox "Bankkonto:" [ref=s1]
- textbox "Datum von:" [ref=d1]: 18.02.2026
- button "Anzeigen" [ref=b1]
"""
        web._pcli = MagicMock(side_effect=[
            "",  # open
            SAMPLE_SNAPSHOT_LOGGED_IN,  # check login
            "",  # goto statement view
            view_snapshot,  # snapshot form
            "",  # select account
            view_snapshot,  # snapshot for button
            "",  # click Anzeigen
            SAMPLE_SNAPSHOT_TABLE,  # result table
        ])

        rows = web.view_statements("Geschaeftskonto")
        assert len(rows) == 2

    def test_close_not_opened(self, web):
        """Close on unopened browser is a no-op."""
        web.close()  # Should not raise


# =============================================================================
# CLI command tests
# =============================================================================


class TestUploadStatementCommand:
    """Tests for the upload-statement CLI command."""

    @patch("collmex_cli.main.load_config")
    @patch("collmex_cli.web.CollmexWeb.close")
    @patch("collmex_cli.web.CollmexWeb.upload_statement")
    @patch("collmex_cli.web.CollmexWeb.__init__", return_value=None)
    def test_upload_json(self, mock_init, mock_upload, mock_close, mock_load_config, tmp_path):
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Geschaeftskonto": 1200},
            bank_accounts_web={"Geschaeftskonto": "Postbank"},
        )
        mock_upload.return_value = {
            "status": "ok",
            "message": "3 imported",
            "file": "test.mt940",
            "account": "Geschaeftskonto",
        }
        stmt = tmp_path / "test.mt940"
        stmt.write_text("MT940")

        result = runner.invoke(
            app, ["upload-statement", str(stmt), "--account", "Geschaeftskonto", "--json"]
        )
        assert result.exit_code == 0
        assert '"status": "ok"' in result.output

    def test_upload_missing_file(self):
        result = runner.invoke(app, ["upload-statement", "/nonexistent/file.mt940"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    @patch("collmex_cli.main.load_config")
    def test_upload_no_account(self, mock_load_config, tmp_path):
        mock_load_config.return_value = AppConfig(bank_accounts={})
        # File must exist to get past the file-not-found check
        stmt = tmp_path / "test.mt940"
        stmt.write_text("data")
        result = runner.invoke(app, ["upload-statement", str(stmt)])
        assert result.exit_code == 1
        assert "No account" in result.output


class TestPendingBookingsCommand:
    """Tests for the pending-bookings CLI command."""

    @patch("collmex_cli.main.load_config")
    @patch("collmex_cli.web.CollmexWeb.close")
    @patch("collmex_cli.web.CollmexWeb.get_pending_bookings")
    @patch("collmex_cli.web.CollmexWeb.__init__", return_value=None)
    def test_pending_json(self, mock_init, mock_get, mock_close, mock_load_config):
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Geschaeftskonto": 1200},
            bank_accounts_web={},
        )
        mock_get.return_value = [
            {"Datum": "2026-03-01", "Betrag": "-150.00", "Text": "ACME"},
        ]

        result = runner.invoke(
            app, ["pending-bookings", "--account", "Geschaeftskonto", "--json"]
        )
        assert result.exit_code == 0
        assert "2026-03-01" in result.output
        assert "-150.00" in result.output

    @patch("collmex_cli.main.load_config")
    @patch("collmex_cli.web.CollmexWeb.close")
    @patch("collmex_cli.web.CollmexWeb.get_pending_bookings")
    @patch("collmex_cli.web.CollmexWeb.__init__", return_value=None)
    def test_pending_empty(self, mock_init, mock_get, mock_close, mock_load_config):
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Geschaeftskonto": 1200},
            bank_accounts_web={},
        )
        mock_get.return_value = []

        result = runner.invoke(
            app, ["pending-bookings", "--account", "Geschaeftskonto"]
        )
        assert result.exit_code == 0
        assert "No pending bookings" in result.output

    @patch("collmex_cli.main.load_config")
    def test_pending_no_account(self, mock_load_config):
        mock_load_config.return_value = AppConfig(bank_accounts={})
        result = runner.invoke(app, ["pending-bookings"])
        assert result.exit_code == 1
        assert "No account" in result.output


# =============================================================================
# AppConfig web mapping tests
# =============================================================================


class TestAppConfigWeb:
    """Tests for bank_accounts_web in AppConfig."""

    def test_load_config_with_web_mapping(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[bank_accounts]\n'
            'Geschaeftskonto = 1200\n\n'
            '[bank_accounts_web]\n'
            'Geschaeftskonto = "Postbank -Giro- Hamburg"\n'
        )
        with patch("collmex_cli.app_config.config_path", return_value=config_file):
            from collmex_cli.app_config import load_config
            cfg = load_config()
        assert cfg.bank_accounts_web == {"Geschaeftskonto": "Postbank -Giro- Hamburg"}

    def test_load_config_without_web_mapping(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[bank_accounts]\nKonto = 1200\n')
        with patch("collmex_cli.app_config.config_path", return_value=config_file):
            from collmex_cli.app_config import load_config
            cfg = load_config()
        assert cfg.bank_accounts_web == {}

    def test_load_config_with_mm_accounts(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[bank_accounts]\n'
            '"Fyrst (1200)" = 1200\n\n'
            '[mm_accounts]\n'
            '"Fyrst Base" = "Fyrst (1200)"\n'
        )
        with patch("collmex_cli.app_config.config_path", return_value=config_file):
            from collmex_cli.app_config import load_config
            cfg = load_config()
        assert cfg.mm_accounts == {"Fyrst Base": "Fyrst (1200)"}


# =============================================================================
# get_statements / bank-statements tests
# =============================================================================


class TestGetStatements:
    """Tests for CollmexWeb.get_statements() normalisation."""

    def test_normalises_statuses(self):
        """get_statements maps Buchung Nr to structured status."""
        raw_rows = [
            {"Datum": "01.03.2026", "Name, Konto Nr, Buchungstext": "ACME",
             "Verwendungszweck": "Invoice 123", "Betrag": "-100,00",
             "Saldo": "1.000,00", "Buchung Nr": "Zu buchen"},
            {"Datum": "02.03.2026", "Name, Konto Nr, Buchungstext": "Bob",
             "Verwendungszweck": "Transfer", "Betrag": "500,00",
             "Saldo": "1.500,00", "Buchung Nr": "42"},
            {"Datum": "03.03.2026", "Name, Konto Nr, Buchungstext": "Deferred",
             "Verwendungszweck": "Later", "Betrag": "-50,00",
             "Saldo": "1.450,00", "Buchung Nr": "Später buchen"},
            {"Datum": "04.03.2026", "Name, Konto Nr, Buchungstext": "Skip",
             "Verwendungszweck": "Nope", "Betrag": "-10,00",
             "Saldo": "1.440,00", "Buchung Nr": "Nicht buchen"},
        ]
        config = MagicMock()
        config.customer_id = "12345"
        config.username = "u"
        config.password = "p"
        config.web_username = "u"
        config.web_password = "p"
        app_cfg = AppConfig(
            bank_accounts={"Konto": 1200},
            bank_accounts_web={"Konto": "Postbank"},
        )
        w = CollmexWeb(config=config, app_config=app_cfg, session="test")
        w.view_statements = MagicMock(return_value=raw_rows)

        result = w.get_statements("Konto", date_from="01.03.2026")

        assert len(result) == 4
        assert result[0]["status"] == "pending"
        assert result[0]["booking_nr"] is None
        assert result[0]["date"] == "01.03.2026"
        assert result[0]["amount"] == "-100,00"
        assert result[1]["status"] == "booked"
        assert result[1]["booking_nr"] == 42
        assert result[2]["status"] == "deferred"
        assert result[3]["status"] == "excluded"
        # All should have account set
        assert all(s["account"] == "Konto" for s in result)


class TestBankStatementsCommand:
    """Tests for the bank-statements CLI command."""

    @patch("collmex_cli.main.load_config")
    @patch("collmex_cli.web.CollmexWeb.close")
    @patch("collmex_cli.web.CollmexWeb.get_statements")
    @patch("collmex_cli.web.CollmexWeb.__init__", return_value=None)
    def test_json_output(self, mock_init, mock_get, mock_close, mock_load_config):
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Konto": 1200},
            bank_accounts_web={"Konto": "Postbank"},
        )
        mock_get.return_value = [
            {"date": "01.03.2026", "name": "ACME", "purpose": "Inv",
             "amount": "-100,00", "balance": "1000", "status": "pending",
             "booking_nr": None, "account": "Konto"},
        ]
        result = runner.invoke(
            app, ["bank-statements", "--account", "Konto", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["status"] == "pending"

    @patch("collmex_cli.main.load_config")
    def test_invalid_status(self, mock_load_config):
        mock_load_config.return_value = AppConfig(bank_accounts={"K": 1200})
        result = runner.invoke(
            app, ["bank-statements", "--status", "nope"]
        )
        assert result.exit_code == 1
        assert "Unknown status" in result.output

    @patch("collmex_cli.main.load_config")
    def test_no_account(self, mock_load_config):
        mock_load_config.return_value = AppConfig(bank_accounts={})
        result = runner.invoke(app, ["bank-statements"])
        assert result.exit_code == 1
        assert "No account" in result.output


# =============================================================================
# Additional snapshot helper tests
# =============================================================================


class TestFindRefForCombobox:
    """Tests for _find_ref_for_combobox helper."""

    def test_find_combobox_by_label(self):
        snapshot = '- combobox "Bankkonto:" [ref=e62]\n- combobox "Status:" [ref=e68]'
        assert _find_ref_for_combobox(snapshot, "Bankkonto:") == "e62"
        assert _find_ref_for_combobox(snapshot, "Status:") == "e68"

    def test_find_combobox_not_found(self):
        snapshot = '- combobox "Bankkonto:" [ref=e62]'
        assert _find_ref_for_combobox(snapshot, "Nope") is None


# =============================================================================
# Import Statements CLI tests
# =============================================================================


class TestImportStatementsCommand:
    """Tests for the import-statements CLI command."""

    @patch("collmex_cli.main.load_config")
    def test_no_mm_accounts(self, mock_load_config):
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Fyrst (1200)": 1200},
            mm_accounts={},
        )
        result = runner.invoke(app, ["import-statements"])
        assert result.exit_code == 1
        assert "No MoneyMoney accounts" in result.output

    @patch("collmex_cli.main.load_config")
    def test_account_not_found(self, mock_load_config):
        mock_load_config.return_value = AppConfig(
            bank_accounts={"Fyrst (1200)": 1200},
            mm_accounts={"Fyrst Base": "Fyrst (1200)"},
        )
        result = runner.invoke(app, ["import-statements", "--account", "Nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("subprocess.run")
    @patch("collmex_cli.main.CollmexClient")
    @patch("collmex_cli.web.CollmexWeb.close")
    @patch("collmex_cli.web.CollmexWeb.upload_statement")
    @patch("collmex_cli.web.CollmexWeb.__init__", return_value=None)
    @patch("collmex_cli.main.load_config")
    def test_import_single_account(
        self, mock_load_config, mock_web_init, mock_upload, mock_close,
        mock_client_cls, mock_subprocess, tmp_path,
    ):
        from datetime import date as d

        mock_load_config.return_value = AppConfig(
            bank_accounts={"Fyrst (1200)": 1200},
            bank_accounts_web={"Fyrst (1200)": "Fyrst 62444500"},
            mm_accounts={"Fyrst Base": "Fyrst (1200)"},
        )

        # Mock CollmexClient context manager
        mock_client = MagicMock()
        mock_client.get_last_bank_booking_date.return_value = {
            "last_date": d(2026, 2, 18),
            "account": 1200,
            "fiscal_year": 2026,
            "booking_count": 10,
        }
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Mock mm export — write some data to the tmp file
        def fake_mm_export(*args, **kwargs):
            # The command includes -o <path>, find the output path
            cmd = args[0] if args else kwargs.get("args", [])
            out_idx = cmd.index("-o") + 1
            from pathlib import Path
            Path(cmd[out_idx]).write_text(":20:STMT\n")
            return MagicMock(returncode=0, stderr="")

        mock_subprocess.side_effect = fake_mm_export

        mock_upload.return_value = {
            "status": "ok",
            "message": "3 Buchungen importiert",
            "file": "test.sta",
            "account": "Fyrst (1200)",
        }

        result = runner.invoke(
            app, ["import-statements", "--account", "Fyrst (1200)", "--json"]
        )
        assert result.exit_code == 0
        assert "importiert" in result.output
        mock_upload.assert_called_once()

"""Collmex web automation via playwright-cli.

Handles operations not available through the CSV API:
- Uploading bank statements (MT940/CAMT)
- Querying pending bookings ("Zu buchen")

Requires playwright-cli to be installed.
Web credentials are read from ~/.config/collmex-cli/config.toml [credentials] section
(web_username / web_password, falls back to username / password).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .app_config import AppConfig, load_config
from .config import CollmexConfig, get_config

SESSION = "collmex"
COLLMEX_BASE = "https://www.collmex.de"


class PlaywrightCliError(Exception):
    """Error running playwright-cli command."""


class CollmexWebError(Exception):
    """Error during Collmex web automation."""


def _pcli(*args: str, session: str = SESSION) -> str:
    """Run a playwright-cli command and return stdout.

    Raises PlaywrightCliError on non-zero exit.
    """
    cmd = ["playwright-cli", f"-s={session}", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise PlaywrightCliError(
            f"playwright-cli {' '.join(args)} failed (rc={result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def _snapshot(session: str = SESSION) -> str:
    """Take a page snapshot and return the accessibility tree content.

    playwright-cli snapshot saves to a YAML file and returns a markdown link.
    This helper reads the YAML file and returns its content.
    """
    output = _pcli("snapshot", session=session)
    # Extract YAML file path from markdown link: - [Snapshot](.playwright-cli/xxx.yml)
    match = re.search(r"\[Snapshot\]\(([^)]+\.yml)\)", output)
    if not match:
        return output  # fallback: return raw output
    yaml_path = Path(match.group(1))
    if not yaml_path.exists():
        return output
    return yaml_path.read_text()


def _parse_snapshot_table(snapshot: str) -> list[dict[str, str]]:
    """Parse an HTML data table from a playwright-cli snapshot into list of dicts.

    Looks for the table that contains columnheader elements (the data table),
    skipping navigation and form layout tables. Rows with fewer cells than
    headers (e.g. colspan warning rows) are skipped.

    Handles playwright-cli YAML quoting: values with special chars are wrapped
    in single quotes, e.g. ``- 'row "text with, commas"':`` or
    ``- 'cell "text" [ref=e1]'``.
    """
    rows: list[dict[str, str]] = []
    lines = snapshot.strip().splitlines()

    # Regexes that handle optional YAML single-quote wrapping:
    #   - row "..."           or   - 'row "..."':
    #   - cell "..." [ref=x]  or   - 'cell "..." [ref=x]'
    ROW_RE = re.compile(r"""-\s*'?row\b""")
    CELL_ROLES = r"(?:cell|gridcell|columnheader|rowheader)"
    # Cell with quoted text (may have trailing [ref=...] or YAML quote)
    CELL_TEXT_RE = re.compile(
        rf"""-\s*'?{CELL_ROLES}\s+"(.*?)"\s*(?:\[|'|$)"""
    )
    # Empty cell (no text, just [ref=...])
    CELL_EMPTY_RE = re.compile(
        rf"""-\s*'?{CELL_ROLES}\s*\["""
    )

    headers: list[str] = []
    current_cells: list[str] = []
    current_row_has_columnheader = False
    in_row = False
    found_data_table = False

    def _save_row() -> None:
        nonlocal headers, found_data_table
        if current_row_has_columnheader:
            # Filter out empty columnheaders (link/action columns)
            headers[:] = [h for h in current_cells if h]
            found_data_table = True
        elif found_data_table:
            # Filter out cells that match known non-data values (link text)
            data_cells = [c for c in current_cells if c not in ("Anzeigen",)]
            if len(data_cells) < len(headers) // 2:
                return  # Skip colspan/warning rows
            row_dict = {}
            for i, h in enumerate(headers):
                row_dict[h] = data_cells[i] if i < len(data_cells) else ""
            rows.append(row_dict)

    for line in lines:
        stripped = line.strip()

        if ROW_RE.match(stripped):
            if in_row and current_cells:
                _save_row()
            current_cells = []
            current_row_has_columnheader = False
            in_row = True
            continue

        if in_row:
            is_columnheader = "columnheader" in stripped
            m = CELL_TEXT_RE.match(stripped)
            if m:
                current_cells.append(m.group(1))
                if is_columnheader:
                    current_row_has_columnheader = True
            elif CELL_EMPTY_RE.match(stripped):
                current_cells.append("")
                if is_columnheader:
                    current_row_has_columnheader = True

    # Last row
    if in_row and current_cells:
        _save_row()

    return rows


class CollmexWeb:
    """Web automation for Collmex using playwright-cli."""

    def __init__(
        self,
        config: CollmexConfig | None = None,
        app_config: AppConfig | None = None,
        session: str = SESSION,
    ):
        self.config = config or get_config()
        self.app_config = app_config or load_config()
        self.session = session
        self._browser_opened = False

    def _pcli(self, *args: str) -> str:
        """Run playwright-cli with this instance's session."""
        return _pcli(*args, session=self.session)

    def _select_option(self, ref: str, label: str) -> None:
        """Select a <select> option by trimmed label text.

        Collmex option texts have trailing spaces, so playwright-cli's
        ``select`` (which does exact label matching) silently fails.
        This helper uses JS eval to find the option whose trimmed text
        matches and selects it by value.
        """
        js = (
            "el => {"
            "  for (let o of el.options) {"
            "    if (o.text.trim() === '" + label.replace("'", "\\'") + "') {"
            "      el.value = o.value;"
            "      el.dispatchEvent(new Event('change', {bubbles: true}));"
            "      return o.text.trim();"
            "    }"
            "  }"
            "  return null;"
            "}"
        )
        result = self._pcli("eval", js, ref)
        if "null" in result and label not in result:
            raise CollmexWebError(
                f"Option '{label}' not found in dropdown {ref}"
            )

    def _snapshot(self) -> str:
        """Take a page snapshot and return accessibility tree content."""
        return _snapshot(session=self.session)

    def _ensure_browser(self) -> None:
        """Open browser if not already open."""
        if self._browser_opened:
            return
        self._pcli("open", COLLMEX_BASE)
        self._browser_opened = True

    def _login(self) -> None:
        """Log into Collmex web UI.

        Uses stable Playwright role selectors for the Collmex login form:
        - Login page URL: /cgi-bin/cgi.exe?{customer_id},0
        - textbox "Benutzer:" → username
        - textbox "Kennwort:" → password
        - button "Anmelden"  → submit

        The customer_id is already embedded in the login URL,
        so only username and password need to be filled.
        """
        cid = self.config.customer_id
        web_user = self.config.web_username or self.config.username
        web_pass = self.config.web_password or self.config.password

        if not web_user or not web_pass:
            raise CollmexWebError(
                "No web credentials configured. "
                "Set web_username/web_password in [credentials] section of config.toml"
            )

        # Navigate to login page (customer_id in URL pre-fills Kundennummer)
        self._pcli("goto", f"{COLLMEX_BASE}/cgi-bin/cgi.exe?{cid},0")

        # Fill login form using Playwright role selectors (stable across sessions)
        snapshot = self._snapshot()
        user_ref = _find_ref_for_textbox(snapshot, "Benutzer:")
        pass_ref = _find_ref_for_textbox(snapshot, "Kennwort:")
        submit_ref = _find_ref_for_button(snapshot, "Anmelden")

        if not all([user_ref, pass_ref, submit_ref]):
            raise CollmexWebError(
                "Login form not found. Expected textbox 'Benutzer:', "
                "textbox 'Kennwort:', button 'Anmelden'"
            )

        self._pcli("fill", user_ref, web_user)
        self._pcli("fill", pass_ref, web_pass)
        self._pcli("click", submit_ref)

    def _ensure_logged_in(self) -> None:
        """Ensure we're logged into Collmex. Login if needed."""
        self._ensure_browser()

        # Check if already logged in (page title or "Abmelden" link present)
        snapshot = self._snapshot()
        if 'link "Abmelden"' in snapshot:
            return

        self._login()

        # Verify login succeeded
        snapshot = self._snapshot()
        if 'link "Abmelden"' not in snapshot:
            raise CollmexWebError("Login failed — check web_username/web_password in config.toml")

    def _resolve_account_web_name(self, account_name: str) -> str:
        """Resolve account name to Collmex web dropdown text.

        Uses bank_accounts_web mapping from config, falls back to account_name itself.
        """
        web_mapping = self.app_config.bank_accounts_web
        if account_name in web_mapping:
            return web_mapping[account_name]
        return account_name

    def _navigate_to_import(self) -> None:
        """Navigate to the bank statement import page."""
        self._ensure_logged_in()
        cid = self.config.customer_id
        self._pcli("goto", f"{COLLMEX_BASE}/c.cmx?{cid},1,umsimp")

    def _navigate_to_statement_view(self) -> None:
        """Navigate to the bank statement view page."""
        self._ensure_logged_in()
        cid = self.config.customer_id
        self._pcli("goto", f"{COLLMEX_BASE}/c.cmx?{cid},1,ums")

    def upload_statement(self, file: Path, account_name: str) -> dict:
        """Upload a bank statement (MT940/CAMT) file.

        Correct sequence:
        1. Navigate to /c.cmx?{cid},1,umsimp
        2. snapshot → find combobox "Bankkonto:" → select account
        3. snapshot → find "Choose File" / "Datei auswählen" button → click
        4. upload <file>
        5. snapshot → find button "Importieren" → click
        6. snapshot → check for success/error message

        Args:
            file: Path to the MT940/CAMT file
            account_name: Account name from config (e.g., "Fyrst (1200)")

        Returns:
            dict with status and message
        """
        if not file.exists():
            raise CollmexWebError(f"File not found: {file}")

        self._navigate_to_import()
        snapshot = self._snapshot()

        # Select bank account from dropdown
        web_name = self._resolve_account_web_name(account_name)
        select_ref = _find_ref_for_combobox(snapshot, "Bankkonto:")
        if select_ref:
            self._select_option(select_ref, web_name)

        # Fresh snapshot after select (refs change)
        snapshot = self._snapshot()

        # Click the file input button, then upload
        file_ref = (
            _find_ref_for_button(snapshot, "Choose File")
            or _find_ref_for_button(snapshot, "Datei auswählen")
            or _find_ref_for_button(snapshot, "Choose")
        )
        if file_ref:
            self._pcli("click", file_ref)
        self._pcli("upload", str(file.resolve()))

        # Fresh snapshot after upload (refs change)
        snapshot = self._snapshot()

        # Click import button
        submit_ref = _find_ref_by_text(snapshot, "Importieren")
        if not submit_ref:
            submit_ref = _find_ref_by_text(snapshot, "Import")
        if submit_ref:
            self._pcli("click", submit_ref)

        # Check result
        snapshot = self._snapshot()
        if "Fehler" in snapshot or "Error" in snapshot:
            error_msg = _extract_message(snapshot, "Fehler")
            raise CollmexWebError(f"Import failed: {error_msg}")

        # Both "importiert" and "keine neuen" count as success
        if "keine neuen" in snapshot.lower():
            return {
                "status": "ok",
                "message": "No new transactions to import",
                "file": str(file),
                "account": account_name,
            }

        success_msg = _extract_message(snapshot, "importiert") or "Import completed"
        return {"status": "ok", "message": success_msg, "file": str(file), "account": account_name}

    def get_pending_bookings(self, account_name: str) -> list[dict]:
        """Get pending bookings ("Zu buchen") for a bank account.

        Args:
            account_name: Account name from config (e.g., "Geschaeftskonto")

        Returns:
            List of dicts with booking data
        """
        self._navigate_to_statement_view()
        snapshot = self._snapshot()

        # Select bank account
        web_name = self._resolve_account_web_name(account_name)
        account_ref = _find_ref_for_combobox(snapshot, "Bankkonto:")
        if account_ref:
            self._select_option(account_ref, web_name)

        # Select status "Zu buchen"
        status_ref = _find_ref_for_combobox(snapshot, "Status:")
        if status_ref:
            self._select_option(status_ref, "Zu buchen")

        # Click search/display button
        submit_ref = _find_ref_by_text(snapshot, "Anzeigen")
        if not submit_ref:
            submit_ref = _find_ref_by_text(snapshot, "Suchen")
        if submit_ref:
            self._pcli("click", submit_ref)

        # Parse results table
        snapshot = self._snapshot()
        return _parse_snapshot_table(snapshot)

    def view_statements(
        self,
        account_name: str,
        date_from: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, str]]:
        """View imported bank statements for an account (raw Collmex table).

        Args:
            account_name: Account name from config (e.g., "Fyrst (1200)")
            date_from: Start date in DD.MM.YYYY format (optional, page default)
            status: Filter by status — one of "Zu buchen", "Später buchen",
                    "Nicht buchen", "Gebucht", or None for all.

        Returns:
            List of raw row dicts as parsed from the Collmex table.
        """
        self._navigate_to_statement_view()
        snapshot = self._snapshot()

        # Select bank account from dropdown (first combobox = "Bankkonto:")
        web_name = self._resolve_account_web_name(account_name)
        account_ref = _find_ref_for_combobox(snapshot, "Bankkonto:")
        if account_ref:
            self._select_option(account_ref, web_name)

        # Select status filter if provided
        if status:
            status_ref = _find_ref_for_combobox(snapshot, "Status:")
            if status_ref:
                self._select_option(status_ref, status)

        # Fill date field if provided
        if date_from:
            date_ref = _find_ref_for_textbox(snapshot, "Datum von:")
            if date_ref:
                self._pcli("fill", date_ref, date_from)

        # Click "Anzeigen" button
        snapshot = self._snapshot()
        submit_ref = _find_ref_for_button(snapshot, "Anzeigen")
        if submit_ref:
            self._pcli("click", submit_ref)

        # Parse results
        snapshot = self._snapshot()
        return _parse_snapshot_table(snapshot)

    def get_statements(
        self,
        account_name: str,
        date_from: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Get bank statements as structured dicts with normalized fields.

        Wraps view_statements() and normalises the raw Collmex table into
        a machine-friendly format.  The "Buchung Nr" column encodes status:
        - "Zu buchen"       → status="pending"
        - "Später buchen"   → status="deferred"
        - "Nicht buchen"    → status="excluded"
        - a number (e.g. 9) → status="booked", booking_nr=9

        Args:
            account_name: Account name from config (e.g., "Fyrst (1200)")
            date_from: Start date in DD.MM.YYYY format (optional)
            status: Collmex status filter (German) or None for all.

        Returns:
            List of dicts with keys: date, name, purpose, amount, balance,
            status ("pending"|"deferred"|"excluded"|"booked"),
            booking_nr (int|None), account.
        """
        raw_rows = self.view_statements(
            account_name, date_from=date_from, status=status
        )

        STATUS_MAP = {
            "Zu buchen": "pending",
            "Später buchen": "deferred",
            "Nicht buchen": "excluded",
        }

        results: list[dict] = []
        for row in raw_rows:
            # Skip summary rows (e.g. "Summe" row with no date)
            if not row.get("Datum", "").strip():
                continue
            buchung = row.get("Buchung Nr", "").strip()
            if buchung in STATUS_MAP:
                st = STATUS_MAP[buchung]
                booking_nr = None
            elif buchung.isdigit():
                st = "booked"
                booking_nr = int(buchung)
            else:
                st = buchung or "unknown"
                booking_nr = None

            results.append({
                "date": row.get("Datum", ""),
                "name": row.get("Name, Konto Nr, Buchungstext", ""),
                "purpose": row.get("Verwendungszweck", ""),
                "amount": row.get("Betrag", ""),
                "balance": row.get("Saldo", ""),
                "status": st,
                "booking_nr": booking_nr,
                "account": account_name,
            })

        return results

    def close(self) -> None:
        """Close the browser session."""
        if self._browser_opened:
            try:
                self._pcli("close")
            except PlaywrightCliError:
                pass
            self._browser_opened = False


# =============================================================================
# Snapshot parsing helpers
# =============================================================================


def _extract_ref(line: str) -> str | None:
    """Extract [ref=X] from a snapshot line."""
    match = re.search(r'\[ref=([\w]+)\]', line)
    return match.group(1) if match else None


def _find_ref_for_textbox(snapshot: str, label: str) -> str | None:
    """Find a textbox by its label and return its ref.

    Matches lines like: - textbox "Benutzer:" [ref=e63]
    """
    for line in snapshot.splitlines():
        if "textbox" in line and label in line:
            return _extract_ref(line)
    return None


def _find_ref_for_button(snapshot: str, label: str) -> str | None:
    """Find a button by its label and return its ref.

    Matches lines like: - button "Anmelden" [ref=e51]
    """
    for line in snapshot.splitlines():
        if "button" in line and label in line:
            return _extract_ref(line)
    return None


def _find_ref_for_combobox(snapshot: str, label: str) -> str | None:
    """Find a combobox by its label and return its ref.

    Matches lines like: - combobox "Bankkonto:" [ref=e62]
    """
    for line in snapshot.splitlines():
        if "combobox" in line and label in line:
            return _extract_ref(line)
    return None


def _find_ref_by_role(snapshot: str, role: str) -> str | None:
    """Find the first element with a given role and return its ref."""
    for line in snapshot.splitlines():
        if role in line.strip():
            ref = _extract_ref(line.strip())
            if ref:
                return ref
    return None


def _find_all_refs_by_role(snapshot: str, role: str) -> list[str]:
    """Find all elements with a given role and return their refs."""
    refs = []
    for line in snapshot.splitlines():
        if role in line.strip():
            ref = _extract_ref(line.strip())
            if ref:
                refs.append(ref)
    return refs


def _find_ref_by_text(snapshot: str, text: str) -> str | None:
    """Find an element containing specific text and return its ref."""
    for line in snapshot.splitlines():
        if text in line:
            ref = _extract_ref(line)
            if ref:
                return ref
    return None


def _extract_message(snapshot: str, keyword: str) -> str:
    """Extract a message from snapshot containing a keyword."""
    for line in snapshot.splitlines():
        if keyword.lower() in line.lower():
            # Clean up the line — remove role markers, refs, etc.
            clean = re.sub(r'\[ref=\w+\]', '', line)
            clean = re.sub(r'-\s*\w+\s+"', '', clean)
            clean = clean.strip().strip('"')
            if clean:
                return clean
    return ""

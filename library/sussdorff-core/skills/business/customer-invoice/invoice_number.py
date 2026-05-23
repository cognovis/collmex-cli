import calendar
import json
from pathlib import Path
import subprocess
import re


INVOICE_NUMBER_RE = re.compile(r"^I(?P<year>\d{4})_(?P<month>\d{2})_(?P<seq>\d{4})(?:\.(?:pdf|xml))?$")


def invoice_number_from_parts(year: int, month: int, seq: int) -> str:
    """Format an invoice number as I2026_05_0001."""
    return f"I{year:04d}_{month:02d}_{seq:04d}"


def _collmex_highest_sequence(year: int, month: int) -> int:
    """Return the highest invoice sequence reported by Collmex for a month."""
    last_day = calendar.monthrange(year, month)[1]
    try:
        result = subprocess.run(
            [
                "collmex",
                "bookings",
                "--from",
                f"{year:04d}-{month:02d}-01",
                "--to",
                f"{year:04d}-{month:02d}-{last_day:02d}",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Collmex could not be reached: collmex executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Collmex could not be reached: request timed out after 30 seconds") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        detail = f": {stderr}" if stderr else f" (exit code {result.returncode})"
        raise RuntimeError(f"Collmex could not be reached{detail}")

    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Collmex returned invalid JSON") from exc

    highest_seq = 0
    if not isinstance(payload, list):
        raise RuntimeError("Collmex returned unexpected JSON structure")

    for record in payload:
        if not isinstance(record, dict):
            continue
        invoice_number = record.get("invoice_number")
        if not isinstance(invoice_number, str):
            continue
        match = INVOICE_NUMBER_RE.match(invoice_number)
        if match is None:
            continue
        if int(match.group("year")) != year or int(match.group("month")) != month:
            continue
        highest_seq = max(highest_seq, int(match.group("seq")))
    return highest_seq


def next_invoice_number(year: int, month: int, kunden_root: Path) -> str:
    """Return the next invoice number for the given year and month.

    Scans kunden_root recursively for files matching I<YYYY>_<MM>_<NNNN>.*
    and increments the highest sequence found for the requested period.
    """
    highest_seq = 0
    highest_seq = max(highest_seq, _collmex_highest_sequence(year, month))
    if kunden_root.exists():
        for path in kunden_root.rglob("*"):
            if not path.is_file():
                continue
            match = INVOICE_NUMBER_RE.match(path.name)
            if match is None:
                continue
            if int(match.group("year")) != year or int(match.group("month")) != month:
                continue
            highest_seq = max(highest_seq, int(match.group("seq")))

    return invoice_number_from_parts(year, month, highest_seq + 1)

from pathlib import Path
import re


INVOICE_NUMBER_RE = re.compile(r"^I(?P<year>\d{4})_(?P<month>\d{2})_(?P<seq>\d{4})(?:\..*)?$")


def invoice_number_from_parts(year: int, month: int, seq: int) -> str:
    """Format an invoice number as I2026_05_0001."""
    return f"I{year:04d}_{month:02d}_{seq:04d}"


def next_invoice_number(year: int, month: int, kunden_root: Path) -> str:
    """Return the next invoice number for the given year and month.

    Scans kunden_root recursively for files matching I<YYYY>_<MM>_<NNNN>.*
    and increments the highest sequence found for the requested period.
    """
    highest_seq = 0
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

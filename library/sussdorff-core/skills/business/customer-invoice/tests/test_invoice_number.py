from pathlib import Path

from invoice_number import invoice_number_from_parts, next_invoice_number


def test_number_scheme() -> None:
    assert invoice_number_from_parts(2026, 5, 1) == "I2026_05_0001"


def test_next_invoice_number_empty(tmp_path: Path) -> None:
    assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0001"


def test_next_invoice_number_existing(tmp_path: Path) -> None:
    customer_dir = tmp_path / "solutio" / "Rechnungen"
    customer_dir.mkdir(parents=True)
    (customer_dir / "I2026_05_0001.pdf").write_text("placeholder")

    assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0002"

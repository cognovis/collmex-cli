from unittest.mock import Mock, patch
from pathlib import Path

import pytest

from invoice_number import invoice_number_from_parts, next_invoice_number


def test_number_scheme() -> None:
    assert invoice_number_from_parts(2026, 5, 1) == "I2026_05_0001"


def test_next_invoice_number_empty(tmp_path: Path) -> None:
    run_result = Mock(returncode=0, stdout="[]", stderr="")
    with patch("invoice_number.subprocess.run", return_value=run_result):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0001"


def test_next_invoice_number_existing(tmp_path: Path) -> None:
    customer_dir = tmp_path / "solutio" / "Rechnungen"
    customer_dir.mkdir(parents=True)
    (customer_dir / "I2026_05_0001.pdf").write_text("placeholder")

    run_result = Mock(returncode=0, stdout="[]", stderr="")
    with patch("invoice_number.subprocess.run", return_value=run_result):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0002"


def test_next_number_from_collmex(tmp_path: Path) -> None:
    run_result = Mock(returncode=0, stdout='[{"invoice_number": "I2026_05_0003"}]', stderr="")
    with patch("invoice_number.subprocess.run", return_value=run_result):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0004"


def test_max_of_collmex_and_filesystem(tmp_path: Path) -> None:
    run_result = Mock(returncode=0, stdout='[{"invoice_number": "I2026_05_0002"}]', stderr="")
    (tmp_path / "I2026_05_0005.pdf").write_text("placeholder")

    with patch("invoice_number.subprocess.run", return_value=run_result):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0006"


def test_no_duplicate_against_collmex(tmp_path: Path) -> None:
    run_result = Mock(returncode=0, stdout='[{"invoice_number": "I2026_05_0010"}]', stderr="")
    with patch("invoice_number.subprocess.run", return_value=run_result):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0011"


def test_collmex_unreachable_is_loud(tmp_path: Path) -> None:
    with patch("invoice_number.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="Collmex could not be reached"):
            next_invoice_number(2026, 5, tmp_path)

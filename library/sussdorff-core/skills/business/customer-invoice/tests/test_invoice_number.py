import json
from unittest.mock import Mock, patch
from pathlib import Path

import pytest

from invoice_number import invoice_number_from_parts, next_invoice_number


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path) -> None:
    with patch("invoice_number.Path.home", return_value=tmp_path):
        yield


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


def test_reservation_file_in_max(tmp_path: Path) -> None:
    reservation_file = (
        tmp_path / "Documents" / "cognovis" / "Buchhaltung" / "rechnungsnummern-reservierungen.jsonl"
    )
    reservation_file.parent.mkdir(parents=True)
    reservation_file.write_text(
        json.dumps(
            {"invoice_number": "I2026_05_0007", "timestamp": "2026-05-23T07:00:00Z"}
        )
        + "\n",
        encoding="utf-8",
    )
    run_result = Mock(returncode=0, stdout='[{"invoice_number": "I2026_05_0003"}]', stderr="")
    (tmp_path / "I2026_05_0005.pdf").write_text("placeholder")

    with patch("invoice_number.subprocess.run", return_value=run_result):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0008"


def test_atomic_append_with_fsync(tmp_path: Path) -> None:
    reservation_file = (
        tmp_path / "Documents" / "cognovis" / "Buchhaltung" / "rechnungsnummern-reservierungen.jsonl"
    )
    run_result = Mock(returncode=0, stdout="[]", stderr="")

    with (
        patch("invoice_number.subprocess.run", return_value=run_result),
        patch("os.fsync") as fsync,
    ):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0001"

    records = [json.loads(line) for line in reservation_file.read_text(encoding="utf-8").splitlines()]
    assert records == [
        {
            "invoice_number": "I2026_05_0001",
            "timestamp": records[0]["timestamp"],
        }
    ]
    assert records[0]["timestamp"].endswith("Z")
    fsync.assert_called_once()


def test_parallel_invocations_no_duplicate(tmp_path: Path) -> None:
    reservation_file = (
        tmp_path / "Documents" / "cognovis" / "Buchhaltung" / "rechnungsnummern-reservierungen.jsonl"
    )
    run_result = Mock(returncode=0, stdout="[]", stderr="")

    with (
        patch("invoice_number.subprocess.run", return_value=run_result),
        patch("os.fsync"),
    ):
        first_number = next_invoice_number(2026, 5, tmp_path)
        second_number = next_invoice_number(2026, 5, tmp_path)

    records = [json.loads(line) for line in reservation_file.read_text(encoding="utf-8").splitlines()]
    assert first_number == "I2026_05_0001"
    assert second_number == "I2026_05_0002"
    assert [record["invoice_number"] for record in records] == [
        "I2026_05_0001",
        "I2026_05_0002",
    ]


def test_creates_buchhaltung_dir_and_user_only_file(tmp_path: Path) -> None:
    reservation_file = (
        tmp_path / "Documents" / "cognovis" / "Buchhaltung" / "rechnungsnummern-reservierungen.jsonl"
    )
    run_result = Mock(returncode=0, stdout="[]", stderr="")

    with (
        patch("invoice_number.subprocess.run", return_value=run_result),
        patch("os.fsync"),
    ):
        assert next_invoice_number(2026, 5, tmp_path) == "I2026_05_0001"

    assert reservation_file.parent.is_dir()
    assert reservation_file.stat().st_mode & 0o777 == 0o600

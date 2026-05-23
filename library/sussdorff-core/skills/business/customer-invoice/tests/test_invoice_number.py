import json
import threading
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from invoice_number import invoice_number_from_parts, next_invoice_number


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path) -> Iterator[None]:
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

    records = [
        json.loads(line) for line in reservation_file.read_text(encoding="utf-8").splitlines()
    ]
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

    records = [
        json.loads(line) for line in reservation_file.read_text(encoding="utf-8").splitlines()
    ]
    assert first_number == "I2026_05_0001"
    assert second_number == "I2026_05_0002"
    assert [record["invoice_number"] for record in records] == [
        "I2026_05_0001",
        "I2026_05_0002",
    ]


def test_concurrent_threads_no_duplicate(tmp_path: Path) -> None:
    """The exclusive flock must serialize the read-modify-write across threads.

    Twenty threads start simultaneously and each reserve a number. Without the
    lock, several would observe the same reservation maximum and emit duplicate
    numbers. With it, every returned number and every persisted record is unique
    and the sequence is contiguous.
    """
    reservation_file = (
        tmp_path / "Documents" / "cognovis" / "Buchhaltung" / "rechnungsnummern-reservierungen.jsonl"
    )
    run_result = Mock(returncode=0, stdout="[]", stderr="")

    thread_count = 20
    start_barrier = threading.Barrier(thread_count)
    results: list[str] = []
    results_lock = threading.Lock()

    def worker() -> None:
        start_barrier.wait()
        number = next_invoice_number(2026, 5, tmp_path)
        with results_lock:
            results.append(number)

    with (
        patch("invoice_number.subprocess.run", return_value=run_result),
        patch("os.fsync"),
    ):
        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert len(results) == thread_count
    assert len(set(results)) == thread_count, f"duplicate numbers returned: {sorted(results)}"

    persisted = [
        json.loads(line)["invoice_number"]
        for line in reservation_file.read_text(encoding="utf-8").splitlines()
    ]
    assert len(persisted) == thread_count
    assert len(set(persisted)) == thread_count, f"duplicate reservations persisted: {sorted(persisted)}"

    expected = {invoice_number_from_parts(2026, 5, seq) for seq in range(1, thread_count + 1)}
    assert set(results) == expected
    assert set(persisted) == expected


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


def test_write_failure_raises(tmp_path: Path) -> None:
    run_result = Mock(returncode=0, stdout="[]", stderr="")

    with (
        patch("invoice_number.subprocess.run", return_value=run_result),
        patch("os.fsync", side_effect=OSError("disk full")),
    ):
        with pytest.raises(OSError, match="disk full"):
            next_invoice_number(2026, 5, tmp_path)

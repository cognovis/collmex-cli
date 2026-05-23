import os
import subprocess
from pathlib import Path


SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "create_mail_drafts.sh"


def run_script_with_mock_osascript(tmp_path: Path, buchungsnummer: str) -> tuple[list[str], str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_path = tmp_path / "osascript-args.txt"
    stdin_path = tmp_path / "osascript-stdin.applescript"
    mock_osascript = bin_dir / "osascript"
    mock_osascript.write_text(
        "#!/bin/bash\n"
        "printf '%s\\n' \"$@\" > \"$OSASCRIPT_ARGS_PATH\"\n"
        "cat > \"$OSASCRIPT_STDIN_PATH\"\n"
    )
    mock_osascript.chmod(0o755)

    pdf_path = tmp_path / "invoice.pdf"
    xml_path = tmp_path / "invoice.xml"
    pdf_path.write_text("pdf")
    xml_path.write_text("xml")

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CUSTOMER_EMAIL": "customer@example.com",
        "INVOICE_NUMBER": "I2026_05_0001",
        "PDF_PATH": str(pdf_path),
        "XML_PATH": str(xml_path),
        "BUCHUNGSNUMMER": buchungsnummer,
        "OSASCRIPT_ARGS_PATH": str(args_path),
        "OSASCRIPT_STDIN_PATH": str(stdin_path),
    }

    subprocess.run(["bash", str(SCRIPT_PATH)], check=True, env=env)

    return args_path.read_text().splitlines(), stdin_path.read_text()


def test_passes_buchungsnummer_env(tmp_path: Path) -> None:
    args, _script = run_script_with_mock_osascript(tmp_path, "12345")

    assert args[-1] == "12345"


def test_subject_includes_both_numbers(tmp_path: Path) -> None:
    _args, script = run_script_with_mock_osascript(tmp_path, "12345")

    assert 'subject:"Rechnung " & invoiceNumber & " — Buchung " & buchungsnummer' in script
    assert (
        '"Anbei Rechnung " & invoiceNumber & " — Buchung " & buchungsnummer'
        in script
    )

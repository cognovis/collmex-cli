from dataclasses import dataclass
from datetime import date
import json
import subprocess


@dataclass(slots=True)
class InvoicePosition:
    description: str
    hours: float
    hourly_rate: float


@dataclass(slots=True)
class TimingResult:
    positions: list[InvoicePosition]
    unassigned: list[str]
    notice: str | None


def run_applescript(script: str) -> str:
    """Run osascript with the given AppleScript. Raises RuntimeError on failure."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {result.stderr.strip()}")
    return result.stdout.strip()


def query_timing_entries(
    customer: str,
    start_date: date,
    end_date: date,
    hourly_rate: float = 130.0,
) -> TimingResult:
    """Query Timing app for billable hours for the given customer and date range."""
    script = _build_timing_script(start_date, end_date)
    output = run_applescript(script)
    positions: list[InvoicePosition] = []

    for line in output.splitlines():
        if not line:
            continue
        project_name, duration_text = line.rsplit("|", 1)
        project_customer, description = project_name.split("/", 1)
        if project_customer.casefold() != customer.casefold():
            continue
        seconds = float(duration_text)
        positions.append(
            InvoicePosition(
                description=description,
                hours=seconds / 3600,
                hourly_rate=hourly_rate,
            )
        )

    notice = None
    if not positions:
        notice = (
            f"No time entries found for customer '{customer}' "
            f"from {start_date.isoformat()} to {end_date.isoformat()}."
        )
    return TimingResult(positions=positions, unassigned=[], notice=notice)


def to_dict(result: TimingResult) -> dict:
    """Convert TimingResult to JSON-serializable dict."""
    return {
        "positions": [
            {"description": p.description, "hours": p.hours, "hourly_rate": p.hourly_rate}
            for p in result.positions
        ],
        "unassigned": result.unassigned,
        "notice": result.notice,
    }


def _build_timing_script(start_date: date, end_date: date) -> str:
    return f"""
tell application "TimingHelper"
    if not scripting support available then
        error "Timing Expert subscription required"
    end if
    set startDate to date "{start_date.isoformat()}"
    set endDate to date "{end_date.isoformat()}"
    set timeSummary to get time summary between startDate and endDate
    set projectTimes to get times per project of timeSummary
    set resultList to {{}}
    repeat with projectItem in projectTimes
        set {{projectName, projectTime}} to projectItem
        set end of resultList to (projectName as string) & "|" & (projectTime as real)
    end repeat
    set AppleScript's text item delimiters to "\\n"
    return resultList as string
end tell
""".strip()

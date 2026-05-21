from dataclasses import dataclass
from datetime import date
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
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("AppleScript timed out after 30 seconds")
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
    hours_by_description: dict[str, float] = {}
    unassigned: list[str] = []

    for line in output.splitlines():
        if not line:
            continue
        parts = line.rsplit("|", 1)
        if len(parts) != 2:
            unassigned.append(f"[malformed entry]: {line}")
            continue
        project_name, duration_text = parts
        try:
            seconds = float(duration_text)
        except ValueError:
            unassigned.append(f"[malformed duration]: {line}")
            continue
        if "/" not in project_name:
            unassigned.append(f"{project_name}: {seconds / 3600:g}h")
            continue
        project_customer, description = project_name.split("/", 1)
        if project_customer.casefold() != customer.casefold():
            # Different customer — not unassignable, just not relevant for this invoice run.
            continue
        hours_by_description[description] = hours_by_description.get(description, 0.0) + (
            seconds / 3600
        )

    positions = [
        InvoicePosition(
            description=description,
            hours=hours,
            hourly_rate=hourly_rate,
        )
        for description, hours in hours_by_description.items()
    ]

    notice = None
    if not positions:
        notice = (
            f"No time entries found for customer '{customer}' "
            f"from {start_date.isoformat()} to {end_date.isoformat()}."
        )
    return TimingResult(positions=positions, unassigned=unassigned, notice=notice)


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
    set hours of endDate to 23
    set minutes of endDate to 59
    set seconds of endDate to 59
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

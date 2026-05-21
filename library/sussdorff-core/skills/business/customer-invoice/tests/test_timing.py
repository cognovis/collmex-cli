from datetime import date
from unittest.mock import patch

from timing_helper import query_timing_entries, to_dict


def test_query_entries() -> None:
    with patch(
        "timing_helper.run_applescript",
        return_value=(
            "charly-server/Entwicklung charly-server|36000.0\n"
            "charly-server/Container Support|10800.0"
        ),
    ):
        result = query_timing_entries(
            "charly-server",
            date(2026, 1, 1),
            date(2026, 1, 31),
            hourly_rate=130.0,
        )

    assert to_dict(result) == {
        "positions": [
            {
                "description": "Entwicklung charly-server",
                "hours": 10.0,
                "hourly_rate": 130.0,
            },
            {
                "description": "Container Support",
                "hours": 3.0,
                "hourly_rate": 130.0,
            },
        ],
        "unassigned": [],
        "notice": None,
    }


def test_aggregate_positions() -> None:
    with patch(
        "timing_helper.run_applescript",
        return_value=(
            "charly-server/Entwicklung charly-server|1800.0\n"
            "charly-server/Entwicklung charly-server|3600.0\n"
            "charly-server/Entwicklung charly-server|5400.0"
        ),
    ):
        result = query_timing_entries(
            "charly-server",
            date(2026, 1, 1),
            date(2026, 1, 31),
            hourly_rate=130.0,
        )

    assert to_dict(result) == {
        "positions": [
            {
                "description": "Entwicklung charly-server",
                "hours": 3.0,
                "hourly_rate": 130.0,
            }
        ],
        "unassigned": [],
        "notice": None,
    }


def test_unassigned_time_reported() -> None:
    with patch(
        "timing_helper.run_applescript",
        return_value=(
            "charly-server/Entwicklung charly-server|3600.0\n"
            "SomeProject|1800.0"
        ),
    ):
        result = query_timing_entries(
            "charly-server",
            date(2026, 1, 1),
            date(2026, 1, 31),
            hourly_rate=130.0,
        )

    assert to_dict(result) == {
        "positions": [
            {
                "description": "Entwicklung charly-server",
                "hours": 1.0,
                "hourly_rate": 130.0,
            }
        ],
        "unassigned": ["SomeProject: 0.5h"],
        "notice": None,
    }

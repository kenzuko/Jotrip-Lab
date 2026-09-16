from __future__ import annotations

from datetime import date, timedelta


def scan_offsets(start: date | None = None) -> list[int]:
    """Return stable D+1..D+90 scan offsets under the V2.1 sampling policy.

    D+1..14: every day.
    D+15..45: every second day plus every Friday/Saturday check-in.
    D+46..90: every third day plus every Friday/Saturday check-in.
    """
    anchor = start or date.today()
    offsets: set[int] = set(range(1, 15))
    offsets.update(range(15, 46, 2))
    offsets.update(range(46, 91, 3))
    for offset in range(15, 91):
        checkin = anchor + timedelta(days=offset)
        if checkin.weekday() in {4, 5}:  # Friday, Saturday
            offsets.add(offset)
    return sorted(offset for offset in offsets if 1 <= offset <= 90)


def scan_dates(start: date | None = None) -> list[date]:
    anchor = start or date.today()
    return [anchor + timedelta(days=offset) for offset in scan_offsets(anchor)]


def horizon_label(offset: int) -> str:
    return f"D+{offset}"

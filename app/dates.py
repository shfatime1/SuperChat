"""Resolve common relative expressions using the competition date only."""

import re
from datetime import date, timedelta

from app.config import REFERENCE_DATE

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def resolve_date(expression: str) -> date | None:
    text = expression.strip().lower()
    if text in {"today", "tonight"}:
        return REFERENCE_DATE
    if text == "tomorrow":
        return REFERENCE_DATE + timedelta(days=1)
    if text == "day after tomorrow":
        return REFERENCE_DATE + timedelta(days=2)
    match = re.fullmatch(r"in (\d+) days?", text)
    if match:
        days = int(match[1])
        if days <= 3650:
            return REFERENCE_DATE + timedelta(days=days)
        return None
    match = re.fullmatch(r"(?:(this|next|on) )?(" + "|".join(WEEKDAYS) + r")", text)
    if match:
        prefix, weekday = match.groups()
        offset = (WEEKDAYS.index(weekday) - REFERENCE_DATE.weekday()) % 7
        if prefix == "next":
            # Explicit convention: next Friday means Friday of the following week.
            offset += 7
        return REFERENCE_DATE + timedelta(days=offset)
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None

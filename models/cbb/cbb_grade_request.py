"""Strict dated PAPER grading request, with no secrets or network access."""
from datetime import date
import json
from zoneinfo import ZoneInfo

SCHEMA = "cbb-paper-grade-request-v1"


def validate(raw, now):
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise ValueError("GRADE_REQUEST_SIZE")
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("GRADE_REQUEST_DUPLICATE_KEY")
            out[k] = v
        return out
    request = json.loads(raw, object_pairs_hook=pairs)
    if type(request) is not dict or set(request) != {"schema", "date_ct", "season", "label"}:
        raise ValueError("GRADE_REQUEST_FIELDS")
    if request["schema"] != SCHEMA or request["label"] != "PAPER_0U":
        raise ValueError("GRADE_REQUEST_LABEL")
    day = date.fromisoformat(request["date_ct"])
    if day.isoformat() != request["date_ct"] or now.tzinfo is None:
        raise ValueError("GRADE_REQUEST_CLOCK")
    today = now.astimezone(ZoneInfo("America/Chicago")).date()
    if day >= today:
        raise ValueError("GRADE_REQUEST_NOT_COMPLETED_CT_DATE")
    if type(request["season"]) is not int or request["season"] != day.year + (day.month >= 8):
        raise ValueError("GRADE_REQUEST_SEASON")
    return day, request["season"]

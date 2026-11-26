"""List filters for Mappo."""

import argparse
import os
import re
from datetime import datetime, timedelta, timezone


def since_time(value):
    """Relative hours/days/weeks, an ISO date, or an ISO timestamp."""
    try:
        duration = re.fullmatch(r"(\d+)([hdw])", value, re.I)
        if duration:
            hours = int(duration[1]) * {"h": 1, "d": 24, "w": 168}[duration[2].lower()]
            dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (
            dt.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, ValueError, OSError):
        raise argparse.ArgumentTypeError(
            "请输入 7d、24h、2w、YYYY-MM-DD 或 ISO 时间"
        ) from None


def filter_rows(
    rows,
    name=None,
    path_contains=None,
    since=None,
    recent=False,
    favorite=False,
    tags=None,
    hidden_mode="exclude",
):
    name = (name or "").casefold()
    fragment = os.path.expanduser(path_contains or "").casefold()
    required_tags = {
        " ".join(tag.strip().split()).casefold()
        for tag in (tags or [])
        if isinstance(tag, str) and tag.strip()
    }
    matches = []
    for row in rows:
        is_hidden = bool(row.get("hidden", False))
        if hidden_mode == "exclude" and is_hidden:
            continue
        if hidden_mode == "only" and not is_hidden:
            continue
        if favorite and not row.get("favorite", False):
            continue
        if required_tags:
            row_tags = {tag.casefold() for tag in row.get("tags", [])}
            if not required_tags.issubset(row_tags):
                continue
        paths = row["roots"] if "roots" in row else [row["path"]]
        names = (
            row["names"]
            if "names" in row
            else [row.get("name"), *(os.path.basename(p) for p in paths)]
        )
        if name and not any(name in n.casefold() for n in names if n):
            continue
        if fragment and not any(
            fragment in p.casefold() for p in paths + [row.get("resource", "")]
        ):
            continue
        stamp = row["last_activity"]
        if (recent or since) and (not stamp or (since and stamp < since)):
            continue
        matches.append(row)
    if recent or since:
        matches.sort(key=lambda r: r["last_activity"], reverse=True)
    return matches

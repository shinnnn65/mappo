"""Core workspace inventory model, path normalization, and diagnostic classification."""

import errno
import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ERRORS = (
    OSError,
    sqlite3.Error,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
)


def stable_id(prefix, *parts):
    key = json.dumps(parts, ensure_ascii=False).encode()
    return prefix + "-" + hashlib.sha256(key).hexdigest()[:16]


def root_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing path")
    if value.startswith("file:"):
        uri = urlsplit(value)
        if uri.netloc in ("", "localhost"):
            value = unquote(uri.path)
    if not value.startswith("/") and urlsplit(value).scheme:
        return value
    if not os.path.isabs(value):
        raise ValueError("expected an absolute root")
    return os.path.realpath(value)


def path_state(path):
    if not os.path.isabs(path):
        return "remote"
    try:
        return "directory" if stat.S_ISDIR(os.stat(path).st_mode) else "not-directory"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "inaccessible"


def error_code(error):
    if isinstance(error, PermissionError) or getattr(error, "errno", None) in (
        errno.EACCES,
        errno.EPERM,
    ):
        return "permission_denied"
    if isinstance(error, (FileNotFoundError, NotADirectoryError)):
        return "missing_source"
    if isinstance(error, BlockingIOError) or (
        isinstance(error, sqlite3.Error)
        and any(word in str(error).lower() for word in ("locked", "busy"))
    ):
        return "busy"
    if isinstance(error, NotImplementedError) or (
        isinstance(error, sqlite3.OperationalError)
        and str(error).startswith(("no such table:", "no such column:"))
    ):
        return "unsupported"
    if isinstance(
        error, (ValueError, KeyError, TypeError, AttributeError, sqlite3.DatabaseError)
    ):
        return "invalid_source"
    return "read_error"


def activity_time(value):
    """Normalise a source timestamp without using file mtime as a proxy."""
    try:
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ):
            dt = datetime.fromtimestamp(
                value / 1000 if value >= 10**11 else value, timezone.utc
            )
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return None
        else:
            return None
        return (
            dt.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (ValueError, OverflowError, OSError):
        return None


def update_activity(row, stamp, source):
    if stamp and (not row.get("last_activity") or stamp > row["last_activity"]):
        row.update(last_activity=stamp, activity_source=str(source))


class Inventory:
    def __init__(self, home):
        self.home = home
        self.records = {}
        self.diagnostics = []

    @contextmanager
    def source(self, agent, path):
        try:
            yield
        except ERRORS as error:
            self.note(
                agent,
                getattr(error, "filename", None) or path,
                str(error),
                error_code(error),
            )

    def note(self, agent, path, reason, code="invalid_source"):
        entry = dict(agent=agent, source=str(path), reason=reason, code=code)
        if entry not in self.diagnostics:
            self.diagnostics.append(entry)

    def add(self, agent, kind, roots, source, native_id=None, name=None, identity=None):
        roots = list(roots)
        paths = list(dict.fromkeys(root_path(p) for p in roots))
        key = stable_id("w", agent, kind, identity or native_id or paths)
        row = self.records.setdefault(
            key,
            dict(
                id=key,
                agent=agent,
                kind=kind,
                native_id=native_id,
                name=name or (Path(paths[0]).name if paths else None),
                last_activity=None,
                activity_source=None,
                roots=[],
                raw_roots=[],
                sources=[],
            ),
        )
        for field, values in (
            ("roots", paths),
            ("raw_roots", roots),
            ("sources", [str(source)]),
        ):
            for value in values:
                if value not in row[field]:
                    row[field].append(value)
        return row

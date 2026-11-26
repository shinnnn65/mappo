"""Per-user local SQLite index and project metadata persistence."""

from mappo.storage.local_index import (
    MAX_TAG_LENGTH,
    MAX_TAGS_PER_PROJECT,
    LocalIndex,
    normalize_tag,
    normalize_tags,
    scope_key,
)

__all__ = [
    "LocalIndex",
    "MAX_TAGS_PER_PROJECT",
    "MAX_TAG_LENGTH",
    "normalize_tag",
    "normalize_tags",
    "scope_key",
]

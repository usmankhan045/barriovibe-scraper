"""Dedup store.

Keyed on POST ID only, deliberately. The same person may appear again on a
different post: a new post is a new signal and a fresh reason to reach out.
Only the exact same post is suppressed.

The store is a JSON file committed back to the repo by the GitHub Actions run,
so dedup state survives across runs with no external service.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# Entries older than this are pruned, keeping the file small. A post older than
# this will never be re-scraped anyway, because the search window is 24h.
RETENTION_DAYS = 120


class SeenStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._posts: dict[str, str] = {}  # post_id -> ISO date first seen
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # A corrupt store must not silently become an empty one: that would
            # re-send every lead. Fail loudly so a human decides.
            raise RuntimeError(
                f"Dedup store at {self.path} is unreadable ({exc}). Refusing to "
                f"continue: an empty store would re-send leads already sent. "
                f"Inspect or delete the file deliberately."
            ) from exc

        posts = raw.get("posts") if isinstance(raw, dict) else None
        if isinstance(posts, dict):
            self._posts = {str(k): str(v) for k, v in posts.items()}

    def has_post(self, post_id: str | None) -> bool:
        """True if this exact post was already sent."""
        if not post_id:
            # No ID means we cannot dedup it. Treat as unseen; the caller is
            # responsible for rejecting records without an ID.
            return False
        return str(post_id) in self._posts

    def add_post(self, post_id: str | None) -> None:
        if not post_id:
            return
        self._posts.setdefault(
            str(post_id),
            datetime.now(timezone.utc).date().isoformat(),
        )

    def prune(self) -> int:
        """Drop entries past retention. Returns how many were removed."""
        cutoff = datetime.now(timezone.utc).date().toordinal() - RETENTION_DAYS
        before = len(self._posts)
        kept: dict[str, str] = {}
        for post_id, seen_date in self._posts.items():
            try:
                if datetime.fromisoformat(seen_date).date().toordinal() >= cutoff:
                    kept[post_id] = seen_date
            except ValueError:
                kept[post_id] = seen_date  # unparseable date: keep, never lose
        self._posts = kept
        return before - len(kept)

    def save(self) -> None:
        """Write atomically so an interrupted run cannot corrupt the store."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "count": len(self._posts),
            "posts": dict(sorted(self._posts.items())),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def __len__(self) -> int:
        return len(self._posts)

"""
TodoTracker: Manages the search_agent/ToDoList.md progress file.

The agent calls this via bash:
  python -m agents.search_agent.todo_tracker add "Paper Title" "https://..."
  python -m agents.search_agent.todo_tracker update "Paper Title" on_progress
  python -m agents.search_agent.todo_tracker update "Paper Title" done
  python -m agents.search_agent.todo_tracker remove <id>   # 1-based order ID from list
  python -m agents.search_agent.todo_tracker list
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

TODO_PATH = Path("search_agent/ToDoList.md")

_HEADER = """# Search Agent ToDoList

| Article | URL | Status | Updated |
|---------|-----|--------|---------|
"""

_STATUS_VALUES = {"pending", "on_progress", "done"}


class TodoTracker:
    def __init__(self, todo_path: str | Path = TODO_PATH) -> None:
        self.path = Path(todo_path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(_HEADER, encoding="utf-8")

    # ------------------------------------------------------------------

    def _read_rows(self) -> list[dict]:
        text = self.path.read_text(encoding="utf-8")
        rows: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith("| Article") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) >= 4:
                rows.append(
                    {"title": parts[0], "url": parts[1], "status": parts[2], "updated": parts[3]}
                )
        return rows

    def _write_rows(self, rows: list[dict]) -> None:
        lines = [_HEADER]
        for r in rows:
            lines.append(f"| {r['title']} | {r['url']} | {r['status']} | {r['updated']} |\n")
        self.path.write_text("".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------

    def add(self, title: str, url: str) -> None:
        rows = self._read_rows()
        for r in rows:
            if r["title"] == title:
                return  # already exists
        rows.append({"title": title, "url": url, "status": "pending", "updated": str(date.today())})
        self._write_rows(rows)

    def update_status(self, title: str, status: str) -> None:
        if status not in _STATUS_VALUES:
            raise ValueError(f"status must be one of {_STATUS_VALUES}, got {status!r}")
        rows = self._read_rows()
        found = False
        for r in rows:
            if r["title"] == title:
                r["status"] = status
                r["updated"] = str(date.today())
                found = True
                break
        if not found:
            rows.append({"title": title, "url": "", "status": status, "updated": str(date.today())})
        self._write_rows(rows)

    def remove(self, order_id: int) -> bool:
        """Remove entry by 1-based order ID."""
        rows = self._read_rows()
        if order_id < 1 or order_id > len(rows):
            return False
        rows.pop(order_id - 1)
        self._write_rows(rows)
        return True

    def list_all(self) -> list[dict]:
        return self._read_rows()


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m agents.search_agent.todo_tracker <add|update|list> [args...]")
        sys.exit(1)

    tracker = TodoTracker()
    cmd = sys.argv[1]

    if cmd == "add":
        if len(sys.argv) < 4:
            print("Usage: todo_tracker add <title> <url>")
            sys.exit(1)
        tracker.add(sys.argv[2], sys.argv[3])
        print(f"Added: {sys.argv[2]}")

    elif cmd == "update":
        if len(sys.argv) < 4:
            print("Usage: todo_tracker update <title> <status>")
            sys.exit(1)
        tracker.update_status(sys.argv[2], sys.argv[3])
        print(f"Updated: {sys.argv[2]} -> {sys.argv[3]}")

    elif cmd == "remove":
        if len(sys.argv) < 3:
            print("Usage: todo_tracker remove <id>")
            sys.exit(1)
        try:
            order_id = int(sys.argv[2])
        except ValueError:
            print(f"Error: id must be an integer, got {sys.argv[2]!r}")
            sys.exit(1)
        if tracker.remove(order_id):
            print(f"Removed entry #{order_id}")
        else:
            print(f"Error: id {order_id} out of range")
            sys.exit(1)

    elif cmd == "list":
        rows = tracker.list_all()
        if not rows:
            print("No articles tracked yet.")
        for i, r in enumerate(rows, 1):
            print(f"[{i:2d}] [{r['status']:12s}] {r['title'][:60]} ({r['updated']})")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# Hook 1: PostToolUse(Edit/Write/MultiEdit) -> append agent edits to the raw ledger.
# Hot path rules: never raise, never block, zero network, zero dependencies.
# Claude Code sends the event JSON on stdin.
import sys, os, json, datetime, pathlib

try:
    d = json.load(sys.stdin)
    if d.get("tool_name") in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        ti = d.get("tool_input") or {}
        rec = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "session": str(d.get("session_id", ""))[:12],
            "tool": d.get("tool_name", ""),
            "file": str(ti.get("file_path") or ti.get("notebook_path") or ""),
            "old": str(ti.get("old_string") or "")[:400],
            "new": str(ti.get("new_string") or ti.get("content") or "")[:400],
        }
        raw = pathlib.Path(os.environ.get("WRONGMARK_HOME", str(pathlib.Path.home() / ".wrongmark"))) / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        with (raw / (rec["ts"][:10] + ".jsonl")).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
except Exception:
    pass
sys.exit(0)

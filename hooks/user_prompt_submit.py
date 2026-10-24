#!/usr/bin/env python3
# Hook 2: UserPromptSubmit -> inject due cards + weak-spot profile into the agent context.
# stdout (exit 0) is added to context by Claude Code; stays silent when there is nothing to say.
# Same rules as hook 1: never raise, never block, zero network.
# Strength mode comes from config.json ("off" = inject nothing).
import sys, os, pathlib

try:
    import json
    home = pathlib.Path(os.environ.get("WRONGMARK_HOME", str(pathlib.Path.home() / ".wrongmark")))
    try:
        cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    if cfg.get("strength", "light") == "off":
        sys.exit(0)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import wrongmark
    import io
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        wrongmark.cmd_context(None)
    finally:
        sys.stdout = old
    out = buf.getvalue().strip()
    if out:
        print(out)
except Exception:
    pass
sys.exit(0)

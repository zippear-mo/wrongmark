#!/usr/bin/env python3
# wrongmark (记错) — an error notebook shared by you and your AI agent.
# Single file, stdlib only, fully local. Override data dir with WRONGMARK_HOME.
# Cards are markdown with flat frontmatter: git-syncable, hand-editable, Anki-export ready.
# Scheduling uses SM-2 for v0; swapping in FSRS later only touches sm2().
import sys, os, json, uuid, argparse, datetime, pathlib, re

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HOME = pathlib.Path(os.environ.get("WRONGMARK_HOME", str(pathlib.Path.home() / ".wrongmark")))
CARDS = HOME / "cards"
RAW = HOME / "raw"
REVIEWS = HOME / "reviews.jsonl"
MISSES = HOME / "misses.jsonl"
GRADES = {"again": 2, "hard": 3, "good": 4, "easy": 5}


def today():
    return datetime.date.today()


def ensure_dirs():
    for d in (CARDS, RAW):
        d.mkdir(parents=True, exist_ok=True)
    if not (HOME / "config.json").exists():
        (HOME / "config.json").write_text(
            json.dumps({"strength": "light", "daily_cards": 2, "profile_tags": 3},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cfg():
    try:
        return json.loads((HOME / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {"strength": "light", "daily_cards": 2, "profile_tags": 3}


# -- card io: markdown body + flat frontmatter (one k: v per line, tags comma-joined)
def write_card(c):
    fm = [
        f"id: {c['id']}", f"kind: {c['kind']}", f"created: {c['created']}",
        f"host: {c['host']}", f"tags: {', '.join(c['tags'])}",
        f"watch: {str(c['watch']).lower()}",
        f"due: {c['due']}", f"interval: {c['interval']}",
        f"ease: {round(c['ease'], 3)}", f"reps: {c['reps']}",
    ]
    body = f"## Q\n{c['q']}\n"
    if c.get("a"):
        body += f"\n## A\n{c['a']}\n"
    if c.get("ctx"):
        body += f"\n## case\n{c['ctx']}\n"
    (CARDS / f"{c['id']}.md").write_text("---\n" + "\n".join(fm) + "\n---\n\n" + body, encoding="utf-8")


def load_cards():
    out = []
    for p in sorted(CARDS.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            _, fm, body = text.split("---", 2)
            meta = {}
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            c = {
                "id": meta.get("id", p.stem), "kind": meta.get("kind", "judgment"),
                "created": meta.get("created", ""), "host": meta.get("host", ""),
                "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                "watch": meta.get("watch", "true") == "true",
                "due": meta.get("due", "2000-01-01"),
                "interval": int(float(meta.get("interval", "0") or 0)),
                "ease": float(meta.get("ease", "2.5") or 2.5),
                "reps": int(meta.get("reps", "0") or 0),
                "q": "", "a": "", "ctx": "",
            }
            for s in re.split(r"^## ", body.strip(), flags=re.M):
                if s.startswith("Q"):
                    c["q"] = s[1:].strip()
                elif s.startswith("A"):
                    c["a"] = s[1:].strip()
                elif s.startswith("case"):
                    c["ctx"] = s.split("\n", 1)[-1].strip()
            out.append(c)
        except Exception:
            continue
    return out


def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path):
    try:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


# -- SM-2 (standard); an FSRS swap only replaces this function
def sm2(card, q):
    if q < 3:
        card["reps"], card["interval"] = 0, 0
    else:
        card["reps"] += 1
        card["interval"] = 1 if card["reps"] == 1 else (
            6 if card["reps"] == 2 else max(1, round(card["interval"] * card["ease"])))
        if q == 5:
            card["interval"] = max(1, round(card["interval"] * 1.2))
    card["ease"] = max(1.3, card["ease"] + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    card["due"] = str(today() + datetime.timedelta(days=card["interval"]))
    return card


def new_card(kind="judgment", tags=None, q="", a="", ctx="", host="claude-code", watch=None):
    if watch is None:
        watch = kind == "judgment"
    c = {
        "id": today().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:4],
        "kind": kind, "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "host": host, "tags": [t.strip() for t in (tags or []) if t.strip()],
        "watch": watch, "due": str(today()), "interval": 0, "ease": 2.5, "reps": 0,
        "q": q, "a": a, "ctx": ctx,
    }
    write_card(c)
    return c


def due_cards(n=None):
    n = n or cfg().get("daily_cards", 2)
    ds = sorted([c for c in load_cards() if c["kind"] != "milestone" and c["due"] <= str(today())],
                key=lambda c: (c["due"], c["id"]))
    return ds[:n]


def top_tags(days=30, n=None):
    n = n or cfg().get("profile_tags", 3)
    cutoff = str(today() - datetime.timedelta(days=days))
    score = {}
    for c in load_cards():
        if c["created"][:10] >= cutoff:
            for t in c["tags"]:
                score[t] = score.get(t, 0) + 1
    for m in read_jsonl(MISSES):
        if m.get("ts", "")[:10] >= cutoff:
            score[m["tag"]] = score.get(m["tag"], 0) + 3
    return sorted(score.items(), key=lambda x: -x[1])[:n]


# -- commands
def cmd_add(a):
    if a.stdin:
        try:
            d = json.loads(sys.stdin.read())
        except Exception as e:
            sys.exit(f"invalid JSON on stdin: {e}")
        a.kind, a.tags = d.get("kind", "judgment"), d.get("tags", [])
        a.q, a.aa, a.ctx = d.get("q", ""), d.get("a", ""), d.get("ctx", "")
        a.host = d.get("host", "claude-code")
    if not a.q:
        sys.exit("missing --q (question); see wrongmark add --help")
    c = new_card(a.kind, a.tags.split(",") if a.tags else [], a.q, a.aa, a.ctx, a.host, a.watch)
    print(f"card added: {c['id']} ({c['kind']})")
    return c


def cmd_due(a):
    ds = due_cards(a.n)
    if not ds:
        print("no cards due today.")
        return
    for c in ds:
        print(f"[{c['id']}] ({(', '.join(c['tags']) or 'untagged')}) {c['q'].splitlines()[0][:70]}")
    print(f"- {len(ds)} due; after answering run: wrongmark review <id> <again|hard|good|easy>")


def cmd_review(a):
    grade = GRADES.get(a.grade) if not a.grade.isdigit() else int(a.grade)
    if grade is None or not (0 <= grade <= 5):
        sys.exit("grade must be again|hard|good|easy or 0-5")
    for c in load_cards():
        if c["id"] == a.id:
            sm2(c, grade)
            write_card(c)
            append_jsonl(REVIEWS, {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                                   "id": c["id"], "grade": grade})
            print(f"{c['id']} -> next {c['due']} (interval {c['interval']}d, ease {c['ease']:.2f})")
            return
    sys.exit(f"card not found: {a.id}")


def cmd_miss(a):
    append_jsonl(MISSES, {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "tag": a.tag})
    hit = 0
    for c in load_cards():
        if a.tag.lower() in [t.lower() for t in c["tags"]]:
            c["interval"] = max(1, c["interval"] // 2)
            c["due"] = str(today())
            write_card(c)
            hit += 1
    print(f"repeat mistake logged: {a.tag} ({hit} related card(s) pulled forward)")


def cmd_profile(a):
    ts = top_tags(a.days)
    print(", ".join(f"{t} x{s}" for t, s in ts) if ts else "(no data yet)")


def cmd_context(_):
    """for the UserPromptSubmit hook: due cards + weak-spot profile, <=7 lines, silent when empty."""
    ds = due_cards()
    ts = top_tags()
    if not ds and not ts:
        return
    if ds:
        print(f"[wrongmark] {len(ds)} card(s) due today: quiz the user BEFORE starting work "
              f"(then wrongmark review <id> <grade>)")
        for c in ds:
            print(f"  [{c['id']}] ({(', '.join(c['tags']) or 'untagged')}) {c['q'].splitlines()[0][:60]}")
    if ts:
        print(f"[wrongmark:watch] weak spots: {', '.join(f'{t} x{s}' for t, s in ts)}"
              f"; on a repeat mistake, point it out and run: wrongmark miss <tag>")


def cmd_report(a):
    cutoff = str(today() - datetime.timedelta(days=a.days))
    cards = [c for c in load_cards() if c["created"][:10] >= cutoff]
    revs = [r for r in read_jsonl(REVIEWS) if r.get("ts", "")[:10] >= cutoff]
    miss = [m for m in read_jsonl(MISSES) if m.get("ts", "")[:10] >= cutoff]
    tags = {}
    for c in cards:
        for t in c["tags"]:
            tags[t] = tags.get(t, 0) + 1
    top = sorted(tags.items(), key=lambda x: -x[1])[:5]
    g = [r["grade"] for r in revs if "grade" in r]
    print(f"-- wrongmark report (last {a.days} days) --")
    print(f"cards added {len(cards)} | reviews {len(revs)} | repeat misses {len(miss)} | due today {len(due_cards(99))}")
    if top:
        print(f"top tags: {', '.join(f'{t} x{n}' for t, n in top)}")
    if g:
        good = sum(1 for x in g if x >= 4)
        print(f"recall rate (good/easy): {good * 100 // len(g)}%")


def cmd_milestone(a):
    c = new_card("milestone", [], a.text, "", "", "claude-code", watch=False)
    print(f"milestone recorded: {c['id']}")


def cmd_raw(a):
    rows = []
    for f in sorted(RAW.glob("*.jsonl"))[-3:]:
        rows.extend(read_jsonl(f))
    for r in rows[-a.tail:]:
        print(f"{r.get('ts', '')[:19]} {r.get('tool', '')} {r.get('file', '')[-50:]}"
              f" old={len(r.get('old', ''))}B new={len(r.get('new', ''))}B")


def cmd_doctor(_):
    print(f"python {sys.version.split()[0]} | home={HOME}")
    ensure_dirs()
    print(f"writable: {'yes' if os.access(HOME, os.W_OK) else 'NO'} | cards {len(load_cards())}"
          f" | raw {sum(len(read_jsonl(p)) for p in RAW.glob('*.jsonl'))}"
          f" | mode {cfg().get('strength', 'light')}")


def main():
    ap = argparse.ArgumentParser(prog="wrongmark",
                                 description="wrongmark - an error notebook shared by you and your AI agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add", help="add a card")
    p.add_argument("--kind", default="judgment", choices=["judgment", "fact", "milestone"])
    p.add_argument("--tags", default="", help="comma separated")
    p.add_argument("--q", default="")
    p.add_argument("--a", dest="aa", default="")
    p.add_argument("--ctx", default="")
    p.add_argument("--host", default="claude-code")
    p.add_argument("--watch", default=None, type=lambda s: s.lower() != "false")
    p.add_argument("--stdin", action="store_true", help="read JSON from stdin (for agents)")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("due", help="cards due today")
    p.add_argument("--n", type=int, default=None)
    p.set_defaults(fn=cmd_due)
    p = sub.add_parser("review", help="grade a recall")
    p.add_argument("id")
    p.add_argument("grade")
    p.set_defaults(fn=cmd_review)
    p = sub.add_parser("miss", help="log a repeat mistake")
    p.add_argument("tag")
    p.set_defaults(fn=cmd_miss)
    p = sub.add_parser("milestone", help="record a growth milestone")
    p.add_argument("text")
    p.set_defaults(fn=cmd_milestone)
    p = sub.add_parser("profile", help="weak-spot profile")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(fn=cmd_profile)
    p = sub.add_parser("context", help="hook injection block (internal)")
    p.set_defaults(fn=cmd_context)
    p = sub.add_parser("report", help="weekly report")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("raw", help="view the raw edit ledger")
    p.add_argument("--tail", type=int, default=10)
    p.set_defaults(fn=cmd_raw)
    p = sub.add_parser("doctor", help="self check")
    p.set_defaults(fn=cmd_doctor)
    ensure_dirs()
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

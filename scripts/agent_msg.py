#!/usr/bin/env python3
"""Direct channel between the agents working this repo.

Issues and PRs are the *record* -- durable, reviewed, slow. This is the
*channel*: structured messages and work claims on a separate `agent-comms`
branch that carries no code and needs no review, so an agent can ask a question
or claim a contract in one second instead of one PR.

Two things it provides:

  messages  a threaded inbox, so a blocker reaches the other agent directly
  claims    a lease on a contract, so two agents don't build the same file

Storage is one JSON file per record on the `agent-comms` branch. One file per
record means two agents writing at once never conflict -- the failure mode of a
single shared log.

    ./scripts/agent_msg.py claim C03 --as codex --branch codex/03-strategy
    ./scripts/agent_msg.py send --to claude --re C03 --type blocker \
        --subject "clamp_order returns 0 for every entry" --body "..."
    ./scripts/agent_msg.py inbox --for claude
    ./scripts/agent_msg.py status

Stdlib only. Requires git, and `gh` only for --notify.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BRANCH = "agent-comms"
AGENTS = ("claude", "codex", "nigel")
TYPES = ("question", "blocker", "handoff", "review", "interface-change", "fyi")

# Claims older than this are treated as abandoned rather than blocking forever.
CLAIM_STALE_HOURS = 12

ROOT = Path(__file__).resolve().parent.parent
COMMS = ROOT / ".agent-comms"


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, quiet: bool = True) -> str:
    result = subprocess.run(
        args, cwd=cwd, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE if quiet else None,
    )
    if check and result.returncode != 0:
        raise SystemExit(f"{' '.join(args)} failed:\n{result.stderr or result.stdout}")
    return result.stdout.strip()


def origin_url() -> str:
    return run(["git", "-C", str(ROOT), "remote", "get-url", "origin"])


def ensure_comms() -> Path:
    """Make sure a local checkout of the comms branch exists and is current."""
    if not (COMMS / ".git").exists():
        COMMS.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-q", "-b", BRANCH], cwd=COMMS)
        run(["git", "remote", "add", "origin", origin_url()], cwd=COMMS)

    fetched = subprocess.run(
        ["git", "fetch", "-q", "origin", BRANCH], cwd=COMMS,
        capture_output=True, text=True,
    ).returncode == 0

    if fetched:
        run(["git", "reset", "-q", "--hard", f"origin/{BRANCH}"], cwd=COMMS)
    elif not (COMMS / "README.md").exists():
        # First ever use: bootstrap the branch.
        (COMMS / "messages").mkdir(exist_ok=True)
        (COMMS / "claims").mkdir(exist_ok=True)
        (COMMS / "README.md").write_text(
            "# agent-comms\n\n"
            "Direct channel between agents. Not code -- do not merge into main.\n\n"
            "Written by `scripts/agent_msg.py`. One JSON file per record so\n"
            "concurrent writes from two agents never conflict.\n\n"
            "`messages/` threaded inbox. `claims/` contract leases.\n"
        )
        (COMMS / "messages/.keep").touch()
        (COMMS / "claims/.keep").touch()
        run(["git", "add", "-A"], cwd=COMMS)
        run(["git", "-c", "user.name=agent-msg", "-c", "user.email=agent-msg@local",
             "commit", "-q", "-m", "Bootstrap the agent comms channel"], cwd=COMMS)
    return COMMS


def publish(message: str) -> None:
    """Commit and push, retrying once against a concurrent writer."""
    run(["git", "add", "-A"], cwd=COMMS)
    if not run(["git", "status", "--porcelain"], cwd=COMMS):
        return
    run(["git", "-c", "user.name=agent-msg", "-c", "user.email=agent-msg@local",
         "commit", "-q", "-m", message], cwd=COMMS)
    push = subprocess.run(["git", "push", "-q", "origin", BRANCH], cwd=COMMS,
                          capture_output=True, text=True)
    if push.returncode != 0:
        # Someone else pushed first. Replay our commit on top of theirs.
        run(["git", "fetch", "-q", "origin", BRANCH], cwd=COMMS)
        run(["git", "rebase", "-q", f"origin/{BRANCH}"], cwd=COMMS)
        run(["git", "push", "-q", "origin", BRANCH], cwd=COMMS)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def age_hours(stamp: str) -> float:
    started = datetime.fromisoformat(stamp)
    return (datetime.now(timezone.utc) - started).total_seconds() / 3600


def read_all(kind: str) -> list[dict]:
    out = []
    for path in sorted((COMMS / kind).glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except json.JSONDecodeError:
            continue
    return out


def write_record(kind: str, name: str, payload: dict) -> None:
    (COMMS / kind).mkdir(exist_ok=True)
    (COMMS / kind / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")


# --- commands --------------------------------------------------------------


def cmd_send(args) -> int:
    ensure_comms()
    mid = args.thread or f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    record = {
        "id": mid, "thread": args.thread or mid, "ts": now(),
        "from": args.sender, "to": args.to, "re": args.re,
        "type": args.type, "subject": args.subject, "body": args.body,
        "resolved": False,
    }
    name = mid if not args.thread else f"{mid}-reply-{uuid.uuid4().hex[:6]}"
    write_record("messages", name, record)
    publish(f"msg: {args.sender} -> {args.to} [{args.type}] {args.subject}")

    print(f"sent {record['id']}  {args.sender} -> {args.to}  [{args.type}]  re {args.re or '-'}")
    if args.notify and args.re:
        issue = args.re.lstrip("Cc").lstrip("0") or args.re
        body = (f"**{args.sender} → {args.to}** · `{args.type}`\n\n"
                f"### {args.subject}\n\n{args.body}\n\n"
                f"<sub>Sent via the agent channel. Reply: "
                f"`./scripts/agent_msg.py reply {record['id']} --as {args.to} --body \"...\"`</sub>")
        rc = subprocess.run(["gh", "issue", "comment", issue, "--body", body],
                            capture_output=True, text=True).returncode
        print("mirrored to issue " + issue if rc == 0 else "could not mirror to an issue")
    return 0


def cmd_reply(args) -> int:
    ensure_comms()
    parent = next((m for m in read_all("messages") if m["id"] == args.id), None)
    if parent is None:
        print(f"no message {args.id}", file=sys.stderr)
        return 1
    args.thread = parent["thread"]
    args.to = parent["from"] if parent["from"] != args.sender else parent["to"]
    args.re = args.re or parent.get("re")
    args.type = args.type or "fyi"
    args.subject = args.subject or f"Re: {parent['subject']}"
    return cmd_send(args)


def cmd_inbox(args) -> int:
    ensure_comms()
    messages = read_all("messages")
    threads: dict[str, list[dict]] = {}
    for m in messages:
        threads.setdefault(m["thread"], []).append(m)

    shown = 0
    for thread_id, msgs in sorted(threads.items(), key=lambda kv: kv[1][0]["ts"], reverse=True):
        msgs.sort(key=lambda m: m["ts"])
        head, last = msgs[0], msgs[-1]
        if any(m.get("resolved") for m in msgs) and not args.all:
            continue
        if args.who and last["to"] != args.who and head["to"] != args.who:
            continue
        # An unanswered thread is one where the last word was not yours.
        awaiting = last["to"]
        shown += 1
        flag = {"blocker": "!!", "interface-change": "!!", "question": " ?"}.get(head["type"], "  ")
        print(f"{flag} [{head['type']:16s}] {head.get('re') or '-':5s} {head['subject']}")
        print(f"     thread {thread_id}  {len(msgs)} msg  awaiting {awaiting}")
        for m in msgs[-2:] if not args.full else msgs:
            body = m["body"] if args.full else (m["body"][:150] + ("..." if len(m["body"]) > 150 else ""))
            print(f"     {m['ts'][:16]} {m['from']:6s}> {body}")
        print()
    if not shown:
        print("inbox clear" + (f" for {args.who}" if args.who else ""))
    return 0


def cmd_resolve(args) -> int:
    ensure_comms()
    touched = 0
    for path in (COMMS / "messages").glob("*.json"):
        record = json.loads(path.read_text())
        if record["thread"] == args.thread or record["id"] == args.thread:
            record["resolved"] = True
            record["resolved_by"] = args.sender
            record["resolved_at"] = now()
            path.write_text(json.dumps(record, indent=2) + "\n")
            touched += 1
    if not touched:
        print(f"no thread {args.thread}", file=sys.stderr)
        return 1
    publish(f"resolve: {args.thread} by {args.sender}")
    print(f"resolved thread {args.thread} ({touched} messages)")
    return 0


def cmd_claim(args) -> int:
    ensure_comms()
    contract = args.contract.upper()
    existing = next((c for c in read_all("claims") if c["contract"] == contract), None)
    if existing and not existing.get("released"):
        stale = age_hours(existing["started"]) > CLAIM_STALE_HOURS
        if existing["agent"] != args.sender and not stale:
            print(f"{contract} is already claimed by {existing['agent']} "
                  f"on {existing['branch']} ({age_hours(existing['started']):.1f}h ago).",
                  file=sys.stderr)
            print("Talk to them before starting -- two agents on one contract is how "
                  "work gets silently overwritten.", file=sys.stderr)
            return 1
        if stale and existing["agent"] != args.sender:
            print(f"note: taking over a stale claim by {existing['agent']} "
                  f"({age_hours(existing['started']):.0f}h old)")

    write_record("claims", contract, {
        "contract": contract, "agent": args.sender,
        "branch": args.branch or f"{args.sender}/{contract.lower()}",
        "started": now(), "released": False, "note": args.note or "",
    })
    publish(f"claim: {contract} by {args.sender}")
    print(f"{args.sender} claimed {contract}")
    return 0


def cmd_release(args) -> int:
    ensure_comms()
    contract = args.contract.upper()
    record = next((c for c in read_all("claims") if c["contract"] == contract), None)
    if record is None:
        print(f"no claim on {contract}", file=sys.stderr)
        return 1
    record.update(released=True, released_at=now(), released_by=args.sender)
    write_record("claims", contract, record)
    publish(f"release: {contract} by {args.sender}")
    print(f"released {contract}")
    return 0


def cmd_status(args) -> int:
    ensure_comms()
    claims = [c for c in read_all("claims") if not c.get("released")]
    print("IN FLIGHT")
    if not claims:
        print("  nothing claimed")
    for c in sorted(claims, key=lambda c: c["contract"]):
        hours = age_hours(c["started"])
        mark = "  STALE" if hours > CLAIM_STALE_HOURS else ""
        print(f"  {c['contract']:5s} {c['agent']:7s} {c['branch']:28s} {hours:5.1f}h{mark}")
        if c.get("note"):
            print(f"        {c['note']}")

    threads: dict[str, list[dict]] = {}
    for m in read_all("messages"):
        threads.setdefault(m["thread"], []).append(m)
    open_threads = [sorted(v, key=lambda m: m["ts"]) for v in threads.values()
                    if not any(m.get("resolved") for m in v)]
    print(f"\nOPEN THREADS ({len(open_threads)})")
    for msgs in sorted(open_threads, key=lambda v: v[0]["ts"], reverse=True):
        head, last = msgs[0], msgs[-1]
        print(f"  [{head['type']:16s}] {head.get('re') or '-':5s} {head['subject'][:52]:52s} "
              f"awaiting {last['to']}")
    if not open_threads:
        print("  none")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="agent_msg.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as", dest="sender", default=os.environ.get("AGENT_NAME"),
                        choices=AGENTS, help="who you are (or set AGENT_NAME)")

    # --as is accepted after the subcommand too, because `claim C03 --as codex`
    # is the order people actually type. SUPPRESS keeps an omitted flag here
    # from clobbering the top-level value or AGENT_NAME.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--as", dest="sender", choices=AGENTS, default=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("send", help="send a message to the other agent", parents=[common])
    s.add_argument("--to", required=True, choices=AGENTS)
    s.add_argument("--re", help="contract or issue this concerns, e.g. C03")
    s.add_argument("--type", default="fyi", choices=TYPES)
    s.add_argument("--subject", required=True)
    s.add_argument("--body", required=True)
    s.add_argument("--thread", help=argparse.SUPPRESS)
    s.add_argument("--notify", action="store_true", help="also comment on the linked issue")
    s.set_defaults(func=cmd_send)

    r = sub.add_parser("reply", help="reply in an existing thread", parents=[common])
    r.add_argument("id")
    r.add_argument("--body", required=True)
    r.add_argument("--subject")
    r.add_argument("--type", choices=TYPES)
    r.add_argument("--re")
    r.add_argument("--notify", action="store_true")
    r.set_defaults(func=cmd_reply)

    i = sub.add_parser("inbox", help="show open threads", parents=[common])
    i.add_argument("--for", dest="who", choices=AGENTS)
    i.add_argument("--all", action="store_true", help="include resolved threads")
    i.add_argument("--full", action="store_true", help="full bodies, all messages")
    i.set_defaults(func=cmd_inbox)

    v = sub.add_parser("resolve", help="close a thread", parents=[common])
    v.add_argument("thread")
    v.set_defaults(func=cmd_resolve)

    c = sub.add_parser("claim", help="lease a contract so nobody else takes it", parents=[common])
    c.add_argument("contract")
    c.add_argument("--branch")
    c.add_argument("--note")
    c.set_defaults(func=cmd_claim)

    e = sub.add_parser("release", help="give up a claim", parents=[common])
    e.add_argument("contract")
    e.set_defaults(func=cmd_release)

    t = sub.add_parser("status", help="who is working on what, and what's unanswered", parents=[common])
    t.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    if not args.sender:
        parser.error("say who you are with --as, or set AGENT_NAME")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

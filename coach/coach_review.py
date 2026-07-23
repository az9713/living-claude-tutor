"""Live Claude Coach - on-demand review engine (Phase 1, design doc S8).
Reads ONE Claude Code session transcript in full and asks Sonnet: where did
the user waste tokens/context, hand-roll something a catalog feature already
does, or repeat a workflow a newer feature replaces? Findings print to stdout
now; any fixable findings compile into rule proposals appended to
pending-proposals.json (same gate coach_weekly.py uses - human approves,
nothing is auto-applied).

Usage: python coach_review.py [target]
  target omitted -> the CURRENT session (newest *.jsonl across all projects)
  target "last"  -> the newest *completed* session (skip the current one)
  target <path>  -> review that transcript directly

Stdlib only, reuses coach_weekly's engine primitives. Fail-safe: any error
prints a short note and the process still exits 0 - a review can never break
the calling skill/session.
"""
import glob, json, os, re, sys, time

TUTOR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TUTOR)
from coach_weekly import (call_claude, parse_proposals, UNTRUSTED,  # noqa: E402
                          extract_text, is_real_user_turn, PENDING)

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
MANIFEST = os.path.join(TUTOR, "catalog", "manifest.json")

REVIEW_PROMPT = UNTRUSTED + """You are the on-demand reviewer of a 'living coach' that helps a Claude \
Code user work more efficiently and use the current feature surface well. You are reviewing ONE session, \
in full, at the user's explicit request - this is a consented, one-off deep read.

CURRENT FEATURE CATALOG (may be empty if not yet synced):
%s

FULL SESSION TRACE (USER / ASSISTANT / TOOLS lines, in order):
%s

Review this ONE Claude Code session. Where did the user (a) waste tokens/context, or (b) hand-roll \
something a catalog feature does natively, or (c) repeat a workflow a newer/better feature replaces? \
Cite the trace for every finding. For each fixable finding, propose a rules.json detector.

Answer in prose first: for each finding give a title, the trace evidence you're citing, and its category \
(efficiency or capability). Then output ONE fenced ```json block with this exact shape:
{"findings": [{"title": "...", "evidence": "...", "category": "efficiency|capability", "fix": "..."}], \
"proposals": [{"id": "...", "kind": "capability_gap|tool_sequence|regex|prompt_length", \
"category": "efficiency|capability", "pattern": "...", "feature_id": "...", "doc_url": "...", \
"message": "...", "cooldown_min": 10, "priority": 5, "status": "proposed", "source": "review-%s"}]}
(empty arrays if none; use "threshold" instead of "pattern" for a prompt_length rule; omit \
"feature_id"/"doc_url" for pure efficiency proposals that aren't tied to a catalog feature)."""


def find_target_file(target):
    """Resolve a target argument to (file_path, label)."""
    all_files = sorted(glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")),
                        key=os.path.getmtime, reverse=True)
    if not target:
        if not all_files:
            raise RuntimeError("no session transcripts found under %s" % PROJECTS)
        return all_files[0], "current"
    if target == "last":
        if len(all_files) < 2:
            raise RuntimeError("no completed prior session found (need at least 2 transcripts)")
        return all_files[1], "last completed"
    if not os.path.isfile(target):
        raise RuntimeError("target file not found: %s" % target)
    return target, "explicit path"


def build_full_trace(path):
    """Full (uncapped) readable trace: USER: / ASSISTANT: / TOOLS: lines in order."""
    parts = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            if t == "user":
                c = (d.get("message") or {}).get("content")
                txt = extract_text(c)
                if is_real_user_turn(d, txt, c):
                    parts.append("USER: " + txt)
            elif t == "assistant":
                m = d.get("message") or {}
                txt = extract_text(m.get("content"))
                tls = [b.get("name") or "?" for b in (m.get("content") or [])
                       if isinstance(b, dict) and b.get("type") == "tool_use"]
                if txt:
                    parts.append("ASSISTANT: " + txt)
                if tls:
                    parts.append("TOOLS: " + ",".join(tls))
    return "\n".join(parts)


def load_manifest():
    """Return (features, note). note is set (and features empty) if the
    catalog hasn't been synced yet - review proceeds without it."""
    try:
        m = json.load(open(MANIFEST, encoding="utf-8"))
        return m.get("features", []), None
    except Exception:
        return [], ("feature catalog not found at %s - the catalog hasn't been synced yet; "
                     "reviewing on efficiency findings only." % MANIFEST)


def format_features(features):
    if not features:
        return "(none - catalog not yet synced)"
    lines = []
    for f in features:
        lines.append("- %s (%s): %s | replaces: %s" % (
            f.get("id", "?"), f.get("name", "?"),
            f.get("what_it_does", ""), f.get("replaces_antipattern", "")))
    return "\n".join(lines)


def strip_json_block(text):
    """Return the prose portion of an LLM reply with the trailing fenced
    ```json block removed."""
    if not text:
        return ""
    return re.sub(r"```json\s*.*?```", "", text, flags=re.S).strip()


def run(target):
    file_path, label = find_target_file(target)
    print("Reviewing %s session: %s" % (label, file_path))

    trace = build_full_trace(file_path)
    if not trace.strip():
        print("coach-review: transcript has no readable turns - nothing to review.")
        return

    features, note = load_manifest()
    if note:
        print("coach-review note: %s" % note)

    prompt = REVIEW_PROMPT % (format_features(features), trace, time.strftime("%Y-%m-%d"))
    out, err = call_claude(prompt, "sonnet")
    if err:
        print("coach-review: review call failed - %s" % err)
        return
    if not out:
        print("coach-review: no output from review call.")
        return

    prose = strip_json_block(out)
    print("\n" + (prose or out))

    payload = parse_proposals(out)
    proposals = payload.get("proposals") if isinstance(payload, dict) else None
    if proposals:
        pend = []
        try:
            pend = json.load(open(PENDING, encoding="utf-8"))
        except Exception:
            pass
        pend.append({"week": time.strftime("%G-W%V"), "source": "review", "payload": payload})
        with open(PENDING, "w", encoding="utf-8") as f:
            json.dump(pend, f, indent=1)
        print("\n%s proposal(s) appended to pending-proposals.json for your approval - "
              "nothing is auto-applied." % len(proposals))
    else:
        print("\nNo proposals generated.")


def main():
    args = sys.argv[1:]
    target = args[0] if args else None
    run(target)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("coach-review: error - %s" % e)
    sys.exit(0)

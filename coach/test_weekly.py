"""Self-check for the Weekly stream: cross-session repeated-workflow clustering
(pure, offline) and the --no-llm end-to-end run.
Run: python test_weekly.py  -> prints OK or throws. Stdlib only, no framework."""
import os, subprocess, sys

TUTOR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TUTOR)

import coach_weekly as cw

# --- normalize_prompt: lowercase, collapse whitespace, fold digit runs to '#' ---
assert cw.normalize_prompt("  Fix   Issue  42  ") == "fix issue #", cw.normalize_prompt("  Fix   Issue  42  ")
assert cw.normalize_prompt("Fix Issue 999") == "fix issue #"

# --- repeated_workflows: obvious cross-session repeats cluster; one-offs and
# single-session retry loops are excluded ---
sessions_prompts = [
    # session 0: same normalized prompt twice (a retry within one session)
    ["fix issue 123", "fix issue 123", "unrelated one-off A"],
    # session 1: same workflow again, plus a different one-off
    ["Fix Issue 456", "run diagnostics", "unrelated one-off B"],
    # session 2: same workflow a third time
    ["  fix   issue 789  ", "totally different task"],
    # session 3: a prompt repeated 3x but confined to ONE session -> must NOT cluster
    ["do the thing 1", "do the thing 2", "do the thing 3"],
]
clusters = cw.repeated_workflows(sessions_prompts)
assert clusters == [["fix issue #", 4, 3]], clusters

# a case with nothing meeting the bar (all one-offs) yields no clusters
assert cw.repeated_workflows([["hello there"], ["a different thing"]]) == []

# --- --no-llm end-to-end run must exit 0 (reads real ~/.claude/projects, read-only) ---
p = subprocess.run([sys.executable, os.path.join(TUTOR, "coach_weekly.py"),
                    "--no-llm", "--days", "7"],
                   capture_output=True, text=True, encoding="utf-8", timeout=120)
assert p.returncode == 0, "coach_weekly.py --no-llm failed:\n%s\n%s" % (p.stdout, p.stderr)
assert "report:" in p.stdout, p.stdout

print("OK - weekly repetition clustering + --no-llm end-to-end run passed")

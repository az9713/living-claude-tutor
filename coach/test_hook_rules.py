"""Self-check for the two new fast-loop rule kinds: capability_gap and
tool_sequence (coach_hook.py). Run: python test_hook_rules.py -> prints OK or
throws. Stdlib only, no framework - matches test_p2p8.py style.

Drives coach_hook.py as a real subprocess (like the real UserPromptSubmit
hook: JSON on stdin), pointed at a temp copy of itself with a crafted
rules.json/state.json so it never touches the project's own rule/state
files.
"""
import json, os, shutil, subprocess, sys, tempfile

TUTOR = os.path.dirname(os.path.abspath(__file__))

RULES = {
    "comment": "test fixture",
    "rules": [
        {
            "id": "test-capability-gap",
            "kind": "capability_gap",
            "category": "capability",
            "pattern": "paste the whole file",
            "feature_id": "cc.at-file-reference",
            "doc_url": "https://docs.anthropic.com/en/docs/claude-code/features",
            "message": "⚠ Coach: reference the file with @path instead of pasting it.",
            "cooldown_min": 10,
            "priority": 5,
            "status": "active",
            "added": "2026-07-22",
            "source": "test"
        },
        {
            "id": "test-tool-sequence",
            "kind": "tool_sequence",
            "category": "capability",
            "pattern": "Bash:cat Bash:grep",
            "feature_id": "cc.grep-tool",
            "doc_url": "https://docs.anthropic.com/en/docs/claude-code/tools",
            "message": "⚠ Coach: use the Grep tool instead of chaining cat+grep.",
            "cooldown_min": 10,
            "priority": 5,
            "status": "active",
            "added": "2026-07-22",
            "source": "test"
        }
    ]
}


def tool_use_line(name, command=None):
    block = {"type": "tool_use", "name": name}
    if command is not None:
        block["input"] = {"command": command}
    return json.dumps({"type": "assistant", "message": {"content": [block]}})


def write_transcript(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def run(hook_path, stdin_text):
    p = subprocess.run([sys.executable, hook_path], input=stdin_text,
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    return p.returncode, p.stdout


tmpdir = tempfile.mkdtemp(prefix="coach_hook_test_")
try:
    hook_path = os.path.join(tmpdir, "coach_hook.py")
    shutil.copyfile(os.path.join(TUTOR, "coach_hook.py"), hook_path)
    with open(os.path.join(tmpdir, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(RULES, f)
    with open(os.path.join(tmpdir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"fires": [], "counters": {}}, f)

    empty_transcript = os.path.join(tmpdir, "empty.jsonl")
    write_transcript(empty_transcript, [])

    # --- capability_gap: matching prompt fires and cites the doc_url ---
    code, out = run(hook_path, json.dumps({
        "prompt": "please paste the whole file contents here",
        "transcript_path": empty_transcript,
        "session_id": "s-cap-gap"}))
    assert code == 0, "hook must always exit 0: %r" % out
    assert "reference the file with @path" in out, "capability_gap did not fire: %r" % out
    assert "(docs: https://docs.anthropic.com/en/docs/claude-code/features)" in out, \
        "capability_gap nudge missing doc_url citation: %r" % out
    assert "Grep tool" not in out, "tool_sequence should not have fired: %r" % out

    # --- tool_sequence: transcript tail matches the pattern -> fires + cites doc ---
    hit_transcript = os.path.join(tmpdir, "hit.jsonl")
    write_transcript(hit_transcript, [
        tool_use_line("Bash", command="cat notes.txt"),
        tool_use_line("Bash", command="grep TODO notes.txt"),
    ])
    code, out = run(hook_path, json.dumps({
        "prompt": "what does this say",
        "transcript_path": hit_transcript,
        "session_id": "s-tool-seq-hit"}))
    assert code == 0, "hook must always exit 0: %r" % out
    assert "use the Grep tool instead of chaining cat+grep" in out, \
        "tool_sequence did not fire on matching transcript tail: %r" % out
    assert "(docs: https://docs.anthropic.com/en/docs/claude-code/tools)" in out, \
        "tool_sequence nudge missing doc_url citation: %r" % out
    assert "reference the file with @path" not in out, "capability_gap should not have fired: %r" % out

    # --- tool_sequence: transcript tail does NOT match -> stays silent ---
    miss_transcript = os.path.join(tmpdir, "miss.jsonl")
    write_transcript(miss_transcript, [
        tool_use_line("Bash", command="ls"),
        tool_use_line("Read"),
        tool_use_line("Task"),
    ])
    code, out = run(hook_path, json.dumps({
        "prompt": "what does this say",
        "transcript_path": miss_transcript,
        "session_id": "s-tool-seq-miss"}))
    assert code == 0, "hook must always exit 0: %r" % out
    assert out.strip() == "", "tool_sequence must stay silent on a non-matching tail: %r" % out

    # --- fail-safe: garbage stdin must still exit 0 ---
    code, out = run(hook_path, "not json at all")
    assert code == 0, "fail-safe broken on garbage stdin: %r" % out
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# --- pure-function unit check: recent_tool_sequence renders tokens correctly ---
sys.path.insert(0, TUTOR)
import importlib
coach_hook = importlib.import_module("coach_hook")

unit_tmpdir = tempfile.mkdtemp(prefix="coach_hook_unit_")
try:
    seq_transcript = os.path.join(unit_tmpdir, "seq.jsonl")
    write_transcript(seq_transcript, [
        tool_use_line("Bash", command="cat a.py b.py"),
        tool_use_line("Grep"),
        tool_use_line("Bash", command="grep -n foo a.py"),
        tool_use_line("Skill"),
    ])
    seq = coach_hook.recent_tool_sequence(seq_transcript)
    assert seq == "Bash:cat Grep Bash:grep Skill", "unexpected tool sequence: %r" % seq

    # missing/unreadable transcript -> empty string, no exception
    seq = coach_hook.recent_tool_sequence(os.path.join(unit_tmpdir, "does-not-exist.jsonl"))
    assert seq == "", "recent_tool_sequence should fail safe to empty string: %r" % seq
finally:
    shutil.rmtree(unit_tmpdir, ignore_errors=True)

print("OK - capability_gap + tool_sequence hook rule self-checks passed")

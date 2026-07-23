---
name: coach-review
description: >-
  Run an on-demand deep review of one Claude Code session through the Live
  Claude Coach engine: where tokens/context were wasted, where something got
  hand-rolled that a native feature already does, or where an old workflow
  got repeated when a newer one exists. Findings print immediately; any
  fixable ones become proposals awaiting the user's approval. Trigger this
  whenever the user says things like "review this session", "coach me on
  what I just did", "was there a better way", "what features did I miss",
  "review my last session", or "run this week's coach review" - or any close
  paraphrase asking to be reviewed/coached on recent Claude Code usage.
---

# coach-review

## What this is

The natural-language front door to the coach's on-demand review engine
(`coach_review.py`). The user never runs the script themselves - they only
ever trigger this by talking. When triggered, you run the script, then read
its output back to them as the coaching conversation.

## When to trigger

Any phrasing that means "look at what I (just) did in Claude Code and tell me
what I could have done better" - including but not limited to: "review this
session", "coach me on what I just did", "was there a better way", "what
features did I miss", "review my last session", "run this week's coach
review". Also trigger on close paraphrases of the same intent.

## Picking the target

The engine reviews exactly one session transcript. Decide the `target`
argument from what the user said:

- **No session named, means "what I'm doing right now"** (e.g. "coach me on
  what I just did", "review this session") -> omit the argument entirely; the
  script defaults to the current session.
- **Explicitly means the previous, already-finished session** (e.g. "review
  my last session", "review the session before this one") -> pass `last`.
  (The current session's transcript is still being written as you talk, so
  it's read as-is up to this point; "last" is for when they clearly mean a
  session that has already ended.)
- **User names or points at a specific transcript path** -> pass that path
  verbatim as the argument.

## How to run it

Run the engine as a plain script - do not read the transcript yourself, do
not open any `.jsonl` file, and do not paste session content into your own
context. The script does the (potentially large) transcript read and the one
LLM review call internally and only prints its findings back to you.

```
python "%USERPROFILE%\.claude\coach\coach_review.py" [target]
```

Examples:
- Current session: `python "%USERPROFILE%\.claude\coach\coach_review.py"`
- Last completed session: `python "%USERPROFILE%\.claude\coach\coach_review.py" last`
- Explicit path: `python "%USERPROFILE%\.claude\coach\coach_review.py" "C:\Users\...\some-session.jsonl"`

This is a single consented LLM call reading a full transcript, so it can take
a little while (up to a minute or two on a long session) - let the user know
you're running the review rather than going silent.

## Reporting back

1. Surface the printed prose findings to the user pretty much as-is - they
   are already written as coaching prose, organized by finding (title,
   evidence from the trace, category: efficiency or capability).
2. If the script printed a note that the feature catalog hasn't been synced
   yet, mention it briefly (findings that week are efficiency-only, no
   catalog-feature gaps).
3. If proposals were generated, tell the user how many and that they are now
   sitting in `pending-proposals.json` (under `~/.claude/coach/`) awaiting
   their approval - **nothing is auto-applied**. If they want to act on one,
   that means telling you to move it into `rules.json`, same as the weekly
   report's proposals.
4. If the script reported an error (missing transcripts, no `claude` CLI on
   PATH, etc.) or found no proposals, say so plainly - don't invent findings.

## Notes

- The user only ever asks in plain English for this; they never invoke the
  script directly.
- This skill does not modify `rules.json`, the catalog, or any coach state
  file besides appending to `pending-proposals.json` - the approval gate
  stays the only path from a finding to a live nudge.
- If `coach_review.py` isn't installed at `~/.claude/coach/coach_review.py`,
  say so and stop rather than trying to reconstruct it from memory.

# Live Claude Coach — design

**Date:** 2026-07-22
**Status:** design, approved to write; no code yet
**Supersedes:** the "Living Claude Tutor" framing (waste-only). This unifies waste
and capability coaching into one system.

## 1. Goal

Evolve the token-waste tutor into a **single living coach** that watches how I use
Claude and flags *better ways of working* — not just cheaper ones. It knows the
current Claude feature surface (from up-to-date docs), notices when I hand-roll
something a feature already does or repeat an old workflow while a newer one exists,
and nudges me toward it. The coach must keep **its own** feature knowledge current,
independent of any model's training cutoff.

One system, not "tutor + coach." Token waste is just one *category* of finding.

## 2. Principles (carried over, unchanged)

- **Compilation ladder.** Expensive intelligence (LLM + live docs) runs *rarely* on
  small inputs; its discoveries compile *down* into zero-token deterministic sensors
  (hook rules) that run *always*.
- **Human-approved, never auto-applied.** Every change is a proposal in
  `pending-proposals.json`. I approve; only then does it become a live detector.
- **Fail-safe.** Hook and statusline swallow all errors and exit clean — the coach
  can never break prompting or the statusline.
- **Natural-language / automatic only.** No slash commands, no scripts I invoke by
  hand. I either get spoken to automatically (hook, statusline) or I *talk to Claude*
  in plain English (the review skill). Background runs are scheduled and invisible.
- **Full-Claude catalog.** The catalog covers the whole surface (Code, API, claude.ai,
  artifacts, desktop). Detection fidelity splits: Claude Code usage is directly
  observable in transcripts; other surfaces are coached via a weaker "spotlight"
  channel (§7).

## 3. Unified model — one coach, categories

A finding carries a **category**; the machinery is identical across categories.

| category | examples |
|---|---|
| `efficiency` | god sessions, babysitting prompts, fat pastes, orphaned task lists |
| `capability` | hand-rolled a feature, repeated an old workflow, never-used relevant feature |
| *(future)* `quality` | reserved |

Same `rules.json`, same hook, same cooldown/priority/suppress, same approval gate,
same report, same `COACH-MODEL.md`. Capability rules are just entries tagged
`category: "capability"` with a `feature_id` into the catalog. The report groups by
category. One brain, multiple lenses.

## 4. Surfaces — how I experience it

The only thing I ever *do* is talk. Everything else is a reflex or a scheduler.

| I experience | mechanism | cost |
|---|---|---|
| Automatic live nudges | `UserPromptSubmit` hook | 0 tokens |
| Ambient counter (`~89k ! nudges:11`) | statusline | 0 tokens |
| "coach me on this session" / "was there a better way" | **skill**, natural-language triggered | 1 consented LLM call |
| Weekly discovery + catalog sync | background scheduled task | ~2–3 LLM calls/wk |
| Quarterly self-audit (blind-spot) | background scheduled task | 1 LLM call/qtr |

## 5. Full flow

Discovery always flows one direction and is gated by me:

```
[fresh feature catalog] + [my session behavior]
      │
      ▼
weekly LLM pass  OR  on-demand review skill        ← the only places the LLM judges
      │  spots a finding: "you did X; feature/pattern Y is better"
      ▼
pending-proposals.json                             ← nothing auto-applied
      │  I approve (tell Claude to move it into rules.json)
      ▼
deterministic DETECTOR in rules.json
      │
      ▼
zero-token hook nudges it live, forever after      ← runs always, costs nothing
```

- **Weekly (auto):** reads 3 stratified sessions deeply + all sessions in aggregate
  (§9), armed with the current catalog → efficiency + capability findings → proposals.
- **On-demand (natural language):** the review skill points the same engine at *one*
  session I name (default: current) and reads it in full → findings now, proposals into
  the same gate.
- **Catalog sync (auto, before the weekly pass):** refreshes the feature manifest from
  live docs and computes "what's new" (§6). Keeps the coach itself current.

## 6. The Feature Catalog

The one genuinely new organ. Lives in `coach/catalog/`.

### `coach_sync.py` — fetch → distill → diff

1. **Fetch** official sources into `catalog/raw/<date>/`: Claude Code docs, the
   changelog / release notes, API docs, model cards. (Via the `claude` CLI headless,
   which has WebFetch/WebSearch, or direct HTTP. Sources listed in a small
   `catalog/sources.json` so they're editable without touching code.)
2. **Distill** in one LLM call → `catalog/manifest.json` (schema below). Re-distill only
   changed docs; cache the rest (ponytail — don't reprocess unchanged pages).
3. **Diff** new manifest vs previous → `catalog/whats_new.md`. New/changed features are
   the top-priority coaching candidates — this *is* the "newer ways of doing things"
   signal.

### `manifest.json` schema

```json
{
  "catalog_version": "2026-07-22",
  "synced_at": "2026-07-22T18:30:00Z",
  "features": [
    {
      "id": "cc.at-file-reference",
      "surface": "claude-code",        // claude-code | api | claude-ai | artifacts | desktop
      "name": "@-file references",
      "what_it_does": "Reference a file by path so Claude reads it selectively, instead of pasting contents inline.",
      "replaces_antipattern": "pasting file contents into the prompt",
      "observable_signal": {           // how a transcript reveals someone NOT using it
        "kind": "prompt_length",       // maps to a rule kind (§7); null if unobservable
        "hint": "user prompt > 8k chars containing code/file-shaped content"
      },
      "surfaces_observable": true,     // false ⇒ spotlight-only (§7)
      "source_url": "https://docs.anthropic.com/...",
      "seen_date": "2026-07-22",       // first appearance in a sync
      "changed_date": "2026-07-22"     // last change in the docs
    }
  ]
}
```

Key fields for trust and staleness: every feature carries `source_url` + dates, so a
nudge can cite the doc, and a feature that vanishes from the docs on a later sync gets
flagged for detector retirement (§10). `observable_signal.kind` is what lets the LLM's
finding compile into a cheap deterministic rule.

## 7. New rule kinds

Added to the existing `regex` / `context_threshold` / `prompt_length` /
`orphan_taskcreate` set. All reuse the same hook machinery (cooldown, priority,
suppress, `{count}`/`{ctx_k}` substitution).

- **`capability_gap`** — the workhorse. Fires when an observable signal for a missed
  feature appears. Under the hood it's just one of the existing primitives (a regex on
  the prompt, a tool-sequence match, or a length threshold) plus a `feature_id` and a
  feature-citing message ("You pasted a file inline — reference `@path` instead. docs: …").
  Most real gaps *are* detectable this way.
- **`tool_sequence`** — new primitive some capability gaps need: match a pattern over the
  recent tool calls in the transcript tail (e.g. sequential `cat`+`grep` in Bash ⇒
  "use the Grep tool"; N single-file Reads in a row ⇒ "dispatch a search subagent").
  Same tail-reading approach the hook already uses for context/orphan detection.
- **`repetition`** — cross-session, so it's discovered in the **weekly** pass, not the
  live hook: "you invoked skill Z 14× on near-identical prompts this week — make it a
  standing CLAUDE.md rule or a subagent." Compiles to a report item and optionally a
  soft nudge.
- **`feature_spotlight`** — for `surfaces_observable: false` (artifacts, claude.ai): a
  feature I demonstrably never use, relevance-ranked to my recent work themes.
  **Report-only, hard rate-limited** — it can't catch me in the act, so it must not
  nag. This is the honest way to honor the full-Claude scope.

Every capability rule stores `category: "capability"`, `feature_id`, and
`catalog_version` (the version it was compiled against — used for auto-retirement).

## 8. On-demand review — a skill, not a command

`coach/skills/coach-review/SKILL.md`. Trigger phrases in its `description`:
"review this session," "coach me on what I just did," "was there a better way,"
"what features did I miss," "run this week's coach review."

- **Target:** no phrase-arg → current session (most-recently-modified `.jsonl` in this
  project's `~/.claude/projects/<dir>/`, the trick the hook/statusline already use).
  "last" → most-recent *completed* session (current one is still being written, so its
  transcript is incomplete). A named session → that one.
- **Depth:** full transcript (not the weekly 10k-char cap) — I asked and I'm knowingly
  paying for one call.
- **Engine:** the skill body shells to the Python engine (reusing `build_traces` /
  `call_claude` / the manifest); Claude orchestrates and presents. I never call the
  script myself.
- **Output:** findings printed now + concrete fixes dropped into
  `pending-proposals.json` — on-demand review still routes through the approval gate.
- **Optional `--sync`-equivalent:** "review this and check for new features first" runs
  a catalog sync before the review (slower, current to the minute).

## 9. How much it reviews

- **Deep read (LLM sees full behavior):** 3 stratified sessions/week —
  most-expensive, most-recent, random (deterministic per-week seed). ~10k chars each.
  Plus **on-demand**: any one session, full read.
- **Shallow read (aggregates, zero marginal LLM cost):** *every* session in the 7-day
  window — tool mix, bash antipatterns, short-prompt clusters, skill owned-vs-used,
  re-reads, peak-ctx distribution.
- **Repetition (new, deterministic):** a prompt-cluster pass in the shallow layer groups
  near-identical prompts across all sessions — catches "same workflow over and over"
  through breadth without spending more trace tokens.

**Decision:** keep deep read at **3** and lean on aggregates + the new prompt-cluster
pass for repetition (ponytail; aggregation is what breadth-patterns want). Revisit to 5
only if capability recall proves thin after a few weeks.

## 10. Freshness & staleness guard

- The manifest is rebuilt from live docs each sync ⇒ the coach's "best practice" is
  current, not training-frozen. `whats_new.md` explicitly surfaces newness.
- Every feature and every compiled detector carries `feature_id`, `source_url`,
  `catalog_version`. When a sync drops a feature (deprecated/renamed), its detectors are
  auto-flagged for retirement into `pending-proposals.json` — I approve the removal.
- The **quarterly blind-spot pass** (`coach_blindspot.py`) extends to audit the catalog
  itself: "features in the changelog we failed to distill? detectors pointing at
  features that changed? spotlight items that never convert?"

## 11. Security (tightened — two untrusted inputs now)

The existing `UNTRUSTED` preamble already treats transcript content as data, not
instructions. The catalog adds a **second** untrusted source: fetched web docs. Both are
wrapped:

- Transcript-derived content: untrusted (unchanged).
- Fetched docs: untrusted during distillation — the distill prompt may only *extract*
  feature descriptions, never *act* on anything a page says. A `source_url` must be an
  official Anthropic/Claude domain (allowlist in `sources.json`); off-domain content is
  dropped.
- Proposed `message` fields remain plain coaching prose — no tool directives, no
  file/settings changes. The approval gate stays the primary control.

## 12. Rename map (repo → `live-claude-coach`)

| now | becomes |
|---|---|
| repo `living-claude-tutor/` | `live-claude-coach/` |
| `tutor/` | `coach/` |
| `tutor_hook.py` | `coach_hook.py` |
| `tutor_weekly.py` | `coach_weekly.py` |
| `tutor_blindspot.py` | `coach_blindspot.py` |
| `TUTOR-MODEL.md` | `COACH-MODEL.md` |
| `statusline.py`, `rules.json`, `test_*.py` | keep |
| live install `~/.claude/tutor/` | `~/.claude/coach/` |
| `<tutor-nudge>`, `⚠ Tutor:` | `<coach-nudge>`, `⚠ Coach:` |

`COACH-MODEL.md` inherits the tutor's decision log verbatim — it's history, not identity.
README, `schtasks` registrations, and the `settings.json` hook/statusline paths update to
the new locations.

## 13. File layout after

```
live-claude-coach/
  README.md              # updated install (new paths)
  SPEC.html              # updated
  audit/                 # unchanged one-off audit scripts
  coach/
    coach_hook.py        # fast loop (+ tool_sequence primitive)
    coach_weekly.py      # slow loop (+ catalog input, capability findings, repetition)
    coach_blindspot.py   # meta loop (+ catalog audit)
    coach_sync.py        # NEW: fetch → distill → diff the feature catalog
    statusline.py        # unchanged behavior
    rules.json           # + capability rules, category field
    COACH-MODEL.md
    catalog/             # NEW
      sources.json       # allowlisted doc URLs
      manifest.json      # distilled feature list
      whats_new.md       # delta since last sync
      raw/<date>/        # fetched snapshots
    skills/
      coach-review/
        SKILL.md         # NEW: natural-language on-demand review
    test_p2p8.py         # + catalog/sync self-checks
    run_weekly.cmd
    run_sync.cmd         # NEW scheduled wrapper
    run_quarterly.cmd
  docs/plans/2026-07-22-live-claude-coach-design.md
```

## 14. Lazy MVP cut (ponytail — what to build first)

**Phase 1 — the 80%, ~2 new files + edits:**
1. `coach_sync.py`: fetch Claude Code docs + changelog → one distill call →
   `manifest.json` + `whats_new.md`. Weekly, before analysis. (Start Claude-Code-surface
   only — it's the observable, high-signal slice.)
2. Extend `coach_weekly.py`: feed manifest + traces to the analyst; emit `capability`
   findings → existing proposal gate. Add the prompt-cluster repetition pass.
3. Add `capability_gap` + `tool_sequence` rule kinds to `coach_hook.py` (small — they're
   labeled regex / tail-match primitives).
4. `coach-review/SKILL.md` — natural-language on-demand review over the same engine.
5. Report gets a "Capability gaps & what's new" section.
6. Do the rename.

**Phase 2 — defer until Phase 1 earns its keep:**
- Full-Claude surfaces + `feature_spotlight` channel (API/claude.ai/artifacts).
- Catalog audit inside the quarterly blind-spot pass.
- Auto-retirement of detectors for deprecated features.
- Bump deep-read 3→5 if recall is thin.

**Skipped deliberately, add when needed:** per-surface distillers, a diffable catalog UI,
semantic prompt-clustering (start with normalized-string clustering — cheaper, good
enough). *ponytail: string-cluster repetition first; upgrade to embeddings only if it
misses real repeats.*

## 15. Tests (stdlib, no framework — matches existing `test_p2p8.py`)

- `coach_sync` with a fixture docs dir → asserts a well-formed `manifest.json` and a
  `whats_new.md` diff, no network in the test.
- `capability_gap` / `tool_sequence` hook rules fire on a crafted transcript and stay
  silent otherwise; hook still exits 0 on garbage input.
- Review skill's engine call over a fixture transcript returns findings + writes a
  proposal, all offline (`--no-llm` path).

## 16. Resolved decisions

- Scope: full-Claude catalog; detection fidelity splits (observable vs spotlight).
- Freshness: scheduled docs fetch → distilled manifest + delta.
- Detection: slow LLM discovers → compiles to deterministic detectors → fast hook nudges.
- Interface: unified single coach; natural-language / automatic only; no slash commands.
- Deep-read count: 3 + aggregates + repetition pass (revisit later).
- Repo rename to `live-claude-coach`.
</content>
</invoke>

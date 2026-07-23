"""Self-check for coach_sync: diff_manifests (offline, pure) + --no-fetch --no-llm smoke test.
Run: python test_sync.py -> prints OK or throws. Stdlib only, no framework, no network, no LLM."""
import os, subprocess, sys

TUTOR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TUTOR)
from coach_sync import diff_manifests  # noqa: E402

# --- diff_manifests: pure function, fixtures only, no network/LLM ---
old_manifest = {
    "catalog_version": "2026-07-01", "synced_at": "2026-07-01T00:00:00", "features": [
        {"id": "cc.at-file-reference", "what_it_does": "Reference a file by path.",
         "changed_date": "2026-06-01", "seen_date": "2026-06-01"},
        {"id": "cc.subagents", "what_it_does": "Dispatch parallel subagents.",
         "changed_date": "2026-06-01", "seen_date": "2026-06-01"},
    ]}
new_manifest = {
    "catalog_version": "2026-07-22", "synced_at": "2026-07-22T00:00:00", "features": [
        {"id": "cc.at-file-reference",  # CHANGED: what_it_does + changed_date differ
         "what_it_does": "Reference a file by path so it's read selectively.",
         "changed_date": "2026-07-22", "seen_date": "2026-06-01"},
        {"id": "cc.subagents",  # unchanged
         "what_it_does": "Dispatch parallel subagents.",
         "changed_date": "2026-06-01", "seen_date": "2026-06-01"},
        {"id": "cc.plan-mode",  # NEW
         "what_it_does": "Plan before editing.",
         "changed_date": "2026-07-22", "seen_date": "2026-07-22"},
    ]}

diff = diff_manifests(old_manifest, new_manifest)
assert diff["new"] == ["cc.plan-mode"], diff
assert diff["changed"] == ["cc.at-file-reference"], diff
assert "cc.subagents" not in diff["new"] and "cc.subagents" not in diff["changed"], diff
assert diff["removed"] == [], diff

# first-ever sync: no previous manifest -> every feature counts as new, nothing changed
diff0 = diff_manifests(None, new_manifest)
assert sorted(diff0["new"]) == sorted(f["id"] for f in new_manifest["features"]), diff0
assert diff0["changed"] == [], diff0

# a feature dropped from the docs shows up as removed
diff1 = diff_manifests(new_manifest, old_manifest)
assert diff1["removed"] == ["cc.plan-mode"], diff1

# --- coach_sync.py --no-fetch --no-llm must run fully offline and exit 0 ---
p = subprocess.run([sys.executable, os.path.join(TUTOR, "coach_sync.py"),
                    "--no-fetch", "--no-llm"],
                   capture_output=True, text=True, encoding="utf-8", timeout=60)
assert p.returncode == 0, "coach_sync --no-fetch --no-llm must exit 0: %s" % (p.stdout + p.stderr)
assert "skipping distillation" in p.stdout, p.stdout

print("OK - coach_sync diff_manifests + --no-fetch --no-llm self-checks passed")

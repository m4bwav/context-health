# Tests: context-health

Test runs for [SKILL.md](SKILL.md). Cases live in `evals/evals.json`. A failure that taught something is a lesson in [LEARNINGS.md](LEARNINGS.md); a fix it caused is logged in [CHANGELOG.md](CHANGELOG.md) with `because: T-...`; research it triggered is in [RESEARCH.md](RESEARCH.md); counts and the failing list are in `evergreen.json` under `tests`. Rules: MAINTENANCE.md (testing section) and the plugin's `protocol/TESTING.md`.

A test passes on evidence (a tool call in the trace, a file, a marker, a log line), never on the transcript's claim that something was done.

Entry shape: `### T-YYYYMMDD-n · date · harness · env · passed/total`, then one line per failing case (`id · kind · class · what the evidence showed`), then `led to:` (L-, C-, R- ids or none). Newest first. Budget 150 lines; archive older runs to `TESTS-ARCHIVE.md`.

## Runs

### T-20261115-1 · 2026-11-15 · claude -p headless (sonnet, stream-json trace) · Windows 11, Claude Code · 8/8
- 24 runs: trigger-1..3 3/3 invoked, decoy-1..2 0/3 invoked, action-1 (status) and action-2 (selection) 3/3 with the ctxhealth.py call in the trace, outcome-1 (holdout) 3/3 deterministic (trace + token count in reply); no llm grader used.
- Baseline (skills disabled): action-1, action-2, outcome-1 all fail, so no case is redundant.
- Trigger results come from headless sessions, a proxy for the main loop. untested elsewhere (macOS/Linux; CI covers the script only).
- not covered: hook lines, Cowork mount path, non-Claude agents.
- led to: none

### T-20261106-1 · 2026-11-06 · not yet run · skill · 0/0
- Suite scaffolded; no run recorded. Write the cases in `evals/evals.json` (at least two trigger prompts, two decoys, one action case with evidence, one outcome case), run the baseline without the skill, then run with it (`evergreen-test`).
- led to: none

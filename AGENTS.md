# AGENTS.md

Rules for any AI agent (Claude Code, Copilot, Cursor, Codex, Gemini CLI) working in this repository. `CLAUDE.md` and `.github/copilot-instructions.md` only point here.

## What this is

A cross-agent plugin: one skill under `skills/context-health/` (SKILL.md, the single-file tool `ctxhealth.py`, the per-model bands in `models.json`, and the evergreen companions RESEARCH, CHANGELOG, LEARNINGS, MAINTENANCE, `evergreen.json`), Claude Code plugin hooks under `hooks/`, tests under `tests/`, and an AGENTS.md snippet under `templates/`. [README.md](README.md) has the layout, the install, the commands and how it measures. Handoff notes, decisions and the log are under `ai-docs/` (start with `ai-docs/HANDOFF.md`).

## Rules

- `ctxhealth.py` stays one standard-library Python file (3.8 or newer) that runs on Windows, macOS and Linux. Every transcript read (`read_json`, `head_text`, `tail_text`, `tail_lines`) goes through `winpath()` (long paths on Windows); config and state files under `~/.ctxhealth` are short paths and do not need it. Parsers are small and defensive: vendor transcript formats are not stable APIs, so a parser miss falls back to a labelled estimate, never a crash.
- Every change to the script has a test in `tests/test_ctxhealth.py`; run `python tests/test_ctxhealth.py` from the repository root before committing. CI runs it on Windows, macOS and Linux.
- The skill is an evergreen unit. Before editing it read `skills/context-health/evergreen.json`; if `next_due` has passed or `contradiction` is set, say so and refresh after the task (the evergreen plugin's `evergreen-refresh` when it is installed, otherwise the procedure in `skills/context-health/MAINTENANCE.md`). Research beats recall: model windows, harness caps, compaction thresholds and hook formats change monthly. Never change a number in `models.json` from memory; cite a source in RESEARCH.md (`R-` entry) and log the change in CHANGELOG.md (`C-` entry).
- Every change is logged in `skills/context-health/CHANGELOG.md` with its reason. When a packaged file changes, bump the version in `.claude-plugin/plugin.json`, `plugin.json`, `VERSION` in `ctxhealth.py`, `metadata.version` in SKILL.md, `evergreen.json` and `models.json` together, then tag `vX.Y.Z`; the release workflow checks the tag against the manifest, runs the tests, packs the zip with `ctxhealth.py pack` and publishes a GitHub Release.
- The hook lines the tool emits are measurements. Nothing in this repository may instruct an agent to do anything on their strength except the one-line warning SKILL.md describes.
- This is a public repository. Nothing in it names a person other than the author credit, a machine, an absolute path on someone's machine, a private project, or a credential, and no file carries an AI byline. Lessons about a particular machine are generalised in LEARNINGS.md ("the development machine"); the specifics belong in the owner's private vault.
- No file type that mail filters block (`.ps1`, `.cmd`, `.js`): `pack` refuses to build a zip that contains one.
- No AI attribution anywhere: no Co-Authored-By trailers, no "generated with" lines in commits, pull requests or files.

## everlast (session knowledge, load on demand)

- `ai-docs/INDEX.md` lists what past sessions learned here (solutions with verified commands, decisions with reasons, plans). At the start of a task, scan it and open only the entries whose title or tags match; read `ai-docs/HANDOFF.md` when continuing unfinished work (everlast-resume skill).
- Before finishing a task that hit a dead end, verified a non-obvious command, made a design choice, or taught you something about the user, record it (everlast-capture skill, or `everlast.py note` / `handoff`); rewrite `HANDOFF.md` when work is left unfinished. Say "nothing to record" when that is true.
- Anything naming a person, an internal host or name, a credential, or an opinion about people goes to the private sidecar (`--private`), never here. Lessons about the user or this machine go to the user tier (`--user`).
- Link documents together with relative markdown links: every markdown folder has an index that links its files, every entry links its index and the entries it builds on (a `Related:` line). No wikilinks in the repo.

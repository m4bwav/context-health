# context-health

Warns you when a session's context has grown big enough to degrade the model you are running, in whatever agent you happen to be in. One Python file, no dependencies, installs in under a minute, and keeps its own model research current (evergreen).

What you get:

- A hook line the agent sees (and, from CAUTION up, a message you see) in Claude Code, VS Code agent sessions, Copilot CLI, Codex CLI, Gemini CLI and Cursor, throttled so it does not nag.
- A Claude Code status line: `opus-5 | ctx 420K/1M 42% CAUTION | myrepo`.
- A startup-context check: the size of the session's initial context (system prompt, tools, instruction files, memory) is recorded per platform every session; you hear about it only when it is large for the model and platform or has grown, and every 10 sessions the agent writes an inventory of what is in it (`~/.ctxhealth/baseline/INVENTORY-<platform>.md`).
- A skill catalog check: in the first session and every 5 sessions after, the hook scans the skills the running agent loads (user roots, installed plugins, the project) and reports, once, pairs whose descriptions are similar enough to compete for the same prompts, names that appear twice with different descriptions, descriptions over the 1,024-character spec limit, and a catalog past the size where selection accuracy is measured to drop. Silent when nothing is found.
- A skill any agent can invoke on demand ("how big is this session", "should I start a new session"), including Cowork where hooks do not run.
- A terminal report: `python ctxhealth.py status`.

The warning is model-aware and harness-aware. Degradation bands come from the model's native window (Opus 5 and Fable 5.1 are 1M, Haiku 4.5 is 200K, GPT-5.5 is 1M but Codex caps it at 400K, Copilot caps everything at 200K unless you opt into 1M). Compaction proximity is a second signal: at 150K on Copilot's 200K cap you are Green for degradation but about to be auto-compacted, and it says so.

## Install

Requires Python 3.8+ (`python --version`; on Windows `py -3 --version`).

```
# 1. clone the repository somewhere permanent (the hooks point at it), or unzip a release zip there
git clone https://github.com/m4bwav/context-health.git
# 2. install for every agent found on this machine
python context-health/skills/context-health/ctxhealth.py install --agent all
# 3. restart the agents, then verify
python context-health/skills/context-health/ctxhealth.py doctor
```

`install` writes, idempotently (rerun any time; entries are recognized by the `ctxhealth.py` marker):

| Agent | What is written | Events |
|---|---|---|
| Claude Code (and VS Code agent hooks, which read the same file) | `~/.claude/settings.json` hooks + `statusLine` (only if none exists) | UserPromptSubmit, SessionStart |
| Copilot CLI | `~/.copilot/hooks/context-health.json` | sessionStart, postToolUse |
| Codex CLI | `~/.codex/hooks.json` | SessionStart, UserPromptSubmit |
| Gemini CLI | `~/.gemini/settings.json` hooks | SessionStart, BeforeAgent (estimate only) |
| Cursor | `~/.cursor/hooks.json` | sessionStart, postToolUse, preCompact |
| all | `~/.agents/skills/context-health` and `~/.claude/skills/context-health` linked to the skill folder | skill discovery |

Flags: `--dry-run` (show the plan), `--agent claude` (one agent; also works for agents not yet detected), `--replace-legacy` (remove the older `context-health.ps1` hook), `--no-statusline`, `--copy` (copy the skill instead of linking). `uninstall --agent all` reverses everything. Update later with `git pull` inside the clone; the hooks and skill links point at it, so nothing else changes.

Windows notes: the hook command uses `py -3` when the launcher exists (it avoids the "Program Files" space problem in PowerShell); Claude Code runs hooks through Git Bash when installed, otherwise PowerShell, and both work with the written command. Nothing in this folder is a script type that mail filters block (no .ps1, .cmd, .js).

Claude Code plugin form: `claude --plugin-dir <path>/context-health`, or `/plugin marketplace add m4bwav/context-health` then `/plugin install context-health@context-health`, loads the skill and `hooks/hooks.json`. That form cannot add the status line and assumes `python` on PATH is Python 3, so prefer `install`; do not use both, the hook would fire twice (harmless, throttled, wasteful).

`install` never overwrites a config it cannot parse (Gemini's settings.json may contain `//` comments): it reports SKIPPED and leaves the file alone. Every config it does rewrite gets a one-off `.bak-ctxhealth` copy next to it.

## Use

- Let the hooks work. At WATCH the agent gets a quiet line; at CAUTION and above it is told to warn you once with one recommendation, and Claude Code / Codex / Gemini also show you the line directly (`systemMessage`).
- Ask: "how big is this session?", "context check", "should I start a new session?". The skill runs `status` and answers with the band, the effects in play and one recommendation, and offers a handoff summary when a new session is the right call.
- Terminal: `python ctxhealth.py status` (newest session of any agent), `status --agent codex`, `status --file <transcript>`, `status --model <id>` (override the model), `status --json`; `version`.
- Tune: `config set profile conservative|balanced|relaxed` (balanced = 200K/400K/600K/800K on 1M models; conservative = 100K/200K/400K/600K; relaxed = 400K/600K/750K/900K), `config set min_band caution` (hooks stay quiet at WATCH), `config set windows.copilot 1000000` (or `windows.cursor`) when you have switched that tool to its 1M mode (VS Code Copilot sessions use the copilot cap).
- Startup context: `python ctxhealth.py baseline` (recorded sizes, medians and last audit per platform: claude-cli, claude-vscode, cowork, copilot-cli, copilot-vscode, codex, gemini, cursor; `--history 10`, `--platform cowork`, `--json`), `baseline --file <transcript>` for one transcript; `status` also prints a `startup:` line. Bands: NOTABLE 10%, HIGH 20%, EXCESSIVE 30% of the effective window (200K-class 12/20/30%). Tune with `config set baseline.audit_every 10`, `baseline.min_band notable|high|excessive`, `baseline.jump 0.25`, `baseline.warn_days 7`, `baseline.enabled false`.
- Skill catalog: `python ctxhealth.py selection` (`--agent claude` for only the roots Claude Code reads, `--list`, `--json`, `--project PATH`). Similarity is TF-IDF cosine between descriptions, 0.45 possibly confusable and 0.65 near-duplicate; count bands 25 / 40 / 60 skills. Both rest on 2026 skill-selection research (see RESEARCH.md, R-20260926-3); the similarity thresholds are uncalibrated. Tune with `config set selection.check_every 5`, `selection.overlap 0.45`, `selection.warn_days 7`, `selection.enabled false`.
- Inspect: `models` (families and caps), `models --model gpt-5.5-codex` (how an id resolves and its thresholds per profile), `doctor`, `sniff <file>` (what a transcript contains, for adapting a parser).

Bands are estimates of a gradual gradient (see `skills/context-health/RESEARCH.md`), not cliffs; the recommendation is the part that matters: finish the current piece of work, write a handoff summary, start fresh.

## Keeping it current (evergreen)

The skill folder is an evergreen unit: `evergreen.json` schedules a research refresh (tier fast, 3 to 21 days, adaptive), `RESEARCH.md` holds the evidence and the search plan, `LEARNINGS.md` records what was learned in use, `CHANGELOG.md` logs every change, and `MAINTENANCE.md` is the self-contained procedure any agent can follow. `python ctxhealth.py fresh` says whether a refresh is due; the skill checks this at Step 0 and refreshes after your task. New model ids that resolve to `unknown` also trigger a refresh. With the evergreen plugin installed, `evergreen.py register <skill folder>` adds it to the audit.

## Layout

```
context-health/
  README.md                       this file
  LICENSE                         MIT
  AGENTS.md                       rules for agents working in this repository (CLAUDE.md and .github/copilot-instructions.md point at it)
  .claude-plugin/plugin.json      Claude Code manifest; marketplace.json beside it for /plugin marketplace add
  .github/workflows/              tests on Windows, macOS and Linux; a release zip for every vX.Y.Z tag
  ai-docs/                        what building it taught: decisions, solutions, handoff, log
  plugin.json                     Copilot / Codex / Cursor manifest (skills only)
  hooks/hooks.json                Claude Code plugin hooks (plugin form only)
  skills/context-health/          the self-contained skill = the unit
    SKILL.md  ctxhealth.py  models.json
    MAINTENANCE.md  RESEARCH.md  CHANGELOG.md  LEARNINGS.md  evergreen.json
  tests/test_ctxhealth.py         python tests/test_ctxhealth.py
  templates/AGENTS.md.snippet     paste into a repo's AGENTS.md for agents without hooks
```

Entry points: [skills/context-health/SKILL.md](skills/context-health/SKILL.md) (the skill and its companions), [AGENTS.md](AGENTS.md) (rules for agents working here; [CLAUDE.md](CLAUDE.md) and `.github/copilot-instructions.md` point at it), [ai-docs/INDEX.md](ai-docs/INDEX.md) (what building it taught; layout in [ai-docs/README.md](ai-docs/README.md)).

`python ctxhealth.py pack` rebuilds `context-health-<version>.zip` (mail-safe, with INSTALL.txt) and `context-health.plugin`; the release workflow runs it for every `vX.Y.Z` tag and attaches the zip to the GitHub Release.

## How it measures

Claude Code / Cowork: the last assistant line of the session's `.jsonl` carries `usage` (input + cache read + cache creation = live context) and `model`; SessionStart-on-resume passes `context_tokens` directly; the status line passes exact usage and the window. Codex: the last `token_count` event (`last_token_usage`, `model_context_window`). Copilot CLI: the last per-request usage event if the version writes one, else a size estimate of the messages since the last compaction (the file format is not a stable API). Gemini CLI, Cursor, other VS Code harnesses: a size estimate of `transcript_path`, labelled as such, plus Cursor's exact `context_tokens` on preCompact. Their own meters (`/stats`, the context ring, the chat-input meter) remain authoritative where the tool cannot read a count.

Startup context: the first assistant turn's input (Claude and Cowork transcripts, Codex `token_count`, Copilot usage events) minus an estimate of the first prompt, measured once per session from the head of the transcript and appended to `~/.ctxhealth/baseline/<platform>.jsonl`; no estimate is made for formats without counts. The Claude Code CLI and the VS Code extension are told apart by `CLAUDE_CODE_ENTRYPOINT`.

## Versioning

Semantic version in `.claude-plugin/plugin.json`, mirrored in `plugin.json`, `VERSION` in `ctxhealth.py`, SKILL.md, `evergreen.json` and `models.json`; every change is logged with its reason in [skills/context-health/CHANGELOG.md](skills/context-health/CHANGELOG.md). Tags on the repository match the plugin version. Repository: https://github.com/m4bwav/context-health.

MIT license. Built by Mark Rogers, September 2026.

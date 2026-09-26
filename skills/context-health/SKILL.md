---
name: context-health
description: "Check whether the current session's context is big enough to degrade the running model, and warn with effects plus one recommendation. Use when the user asks \"how big is this session\", \"context check\", \"are we near the limit\", \"should I start a new session\", \"is the context degrading\", when a session is visibly long (15+ substantial exchanges or several large file/research dumps), before starting a major new subtask in an already-long session, or when a [context-health] hook line appears at CAUTION or above and the user has not been told yet. Also use it to install or repair the hooks (\"install context health\", \"set up the context meter\"), or to refresh its model research. Also covers the startup (initial) context: \"how big is my starting context\", \"what is in my initial context\", \"is the system prompt too big for this model\", when a [context-health baseline] hook line asks for an audit or warns, or to review the recorded startup sizes per platform. Works in Claude Code, Cowork, Copilot CLI, VS Code, Codex CLI, Gemini CLI, Cursor."
license: MIT
metadata:
  version: "1.3.2"
  evergreen: "fast tier; see MAINTENANCE.md"
---

# Context health

Warn the user when the session context is large enough that the model's performance degrades, using per-model bands in `models.json` (next to this file) that are research-derived estimates of a gradual gradient, not cliffs. Cheap by design: one script call. Below the thresholds, spend nothing more.

Everything lives in this folder: `ctxhealth.py` (the tool), `models.json` (bands), `MAINTENANCE.md` (how this skill keeps itself current), `RESEARCH.md`, `CHANGELOG.md`, `LEARNINGS.md`, `evergreen.json`. `SKILL_DIR` below means this folder; `CTX` means `python "<SKILL_DIR>/ctxhealth.py"` (use `py -3` on Windows if `python` is not Python 3).

## Step 0: freshness (one small read)

Run `CTX fresh` (or read `evergreen.json`). If it prints DUE or CONTRADICTION, say so in one line and do the refresh in MAINTENANCE.md after the user's task. Otherwise do nothing extra.

## Step 1: measure

Run `CTX status` (add `--agent claude|copilot|codex|gemini|cursor` to pin the agent, `--file PATH` to pin a transcript, `--json` for fields). It finds the newest session transcript for the detected agents, reads the last token count, resolves the model to a family, applies the harness cap (Copilot 200K, Codex 400K for GPT-5.5, 600K for GPT-6 Astra and 272K for GPT-6 Sol/Luna by default (up to 828.4K when configured), Cursor 200-300K, Claude Code native) and prints the band, thresholds, compaction proximity and one recommendation.

Where the shell cannot reach the transcript:

- Cowork (Claude Desktop): the sandbox sees the transcripts at `~/mnt/.claude/projects/*/*.jsonl` and `CTX status` finds them; run the script from the copy of this folder that Cowork mounts into the sandbox (it appears under `~/mnt/<connected folder>/context-health/skills/context-health` when the folder holding this plugin is connected to the session). Hooks do not run in Cowork, so this skill is the only in-session layer there. A fresh Cowork session already sits near 105K because of the tool and skill catalog; growth above that floor is the signal. If the script is not reachable, measure inline and apply the balanced bands by hand (1M Claude models: watch 200K, caution 400K, warning 600K, critical 800K; 200K models: 40K/80K/120K/160K):

```bash
python3 - <<'EOF'
import json,glob,os
fs=[f for f in glob.glob(os.path.expanduser('~/mnt/.claude/projects/*/*.jsonl')) if '/subagents/' not in f]
f=max(fs,key=os.path.getmtime); ctx=0; model=''
for line in open(f,encoding='utf-8',errors='replace'):
    if '"usage"' not in line: continue
    try: m=(json.loads(line).get('message') or {})
    except Exception: continue
    u=m.get('usage')
    if u and m.get('role')=='assistant' and not json.loads(line).get('isSidechain'): ctx=u.get('input_tokens',0)+u.get('cache_read_input_tokens',0)+u.get('cache_creation_input_tokens',0); model=m.get('model','')
print(ctx, model)
EOF
```
- No readable transcript (Gemini CLI, Cursor IDE, VS Code Copilot harness): use the agent's own meter (`/stats`, the context ring, the chat-input meter, `/context`, `/status`) for the token count and judge it against the thresholds `CTX models --model <id>` prints.
- Never guess silently. If the measurement is an estimate (the report says so), say "roughly".

## Step 2: report

- GREEN: one line only if the user asked; otherwise silent.
- WATCH: one line ("~260K, mild territory, fine to continue"), no lecture.
- CAUTION, WARNING, CRITICAL: give the full warning:

```
Context health: ~XXXK tokens (NN% of the <window>) - BAND for <model>
Effects likely in play: <band effects from the report, plain words>
Recommendation: <one decisive line>
```

Recommendation logic (from `models.json` band_text): CAUTION = finish the current piece of work here, then start a new session; offer a handoff summary. WARNING = start a new session now unless mid-critical-step; write the handoff summary file first. CRITICAL = write the handoff summary now, then start a new session; auto-compaction is near and will silently summarize history. One recommendation, not a menu. Say it once; do not repeat every turn (the hook throttles itself the same way).

Handoff summary, when offered or required: key decisions, open items, file paths, and the next step, saved to the project folder (for example `HANDOFF.md`) so the next session starts clean.

## Startup context (baseline)

The first assistant turn's input is the startup context (system prompt, tool and MCP schemas, MCP server instructions, project instruction files and their imports, memory, skills catalog). On small-window or harness-capped models it can be a degradation problem before the first prompt. The hook measures it once per session from the head of the transcript (the first prompt is estimated and subtracted), records it per platform in `~/.ctxhealth/baseline/<platform>.jsonl` (platforms: claude-cli, claude-vscode, cowork, copilot-cli, copilot-vscode, codex, gemini, cursor) and stays silent unless something is relevant. Bands (`models.json` `baseline.fractions`, of the effective window): NOTABLE 10%, HIGH 20%, EXCESSIVE 30% (200K-class 12/20/30%). Growth of 25% or more against this project's median of the last five sessions is also relevant.

- **Warn** (one line to the user, once per band per week per project) when the band is NOTABLE or above, or the size grew.
- **Audit** every `baseline.audit_every` sessions (default 10) per platform, and whenever a HIGH or EXCESSIVE warning fires. The hook line asks you to list, in at most 8 lines, the largest blocks of your initial context with rough sizes and the total, and append them under the dated heading it gives to `~/.ctxhealth/baseline/INVENTORY-<platform>.md` (heredoc append; never read or rewrite the file). Do it after the user's task. Mention it to the user only if the band is NOTABLE or above or a block looks wrong. That file is the running record of what the startup context contains, so nobody has to run `/context` by hand.
- **On demand**: `CTX baseline` (recorded sizes, medians, last audit per platform; `--history 10`, `--platform cowork`, `--json`), `CTX baseline --file <transcript>` for one transcript; `CTX status` also prints a `startup:` line. In Cowork (no hooks) run `CTX baseline --file` on the newest `~/mnt/.claude/projects/*/*.jsonl` when asked or at the first checkpoint, and append the inventory by hand under the same rules.
- Tune: `CTX config set baseline.audit_every 10`, `baseline.min_band notable|high|excessive`, `baseline.jump 0.25`, `baseline.warn_days 7`, `baseline.enabled false`.
- The bands are judgment estimates seeded 2026-09-05 (RESEARCH.md, Startup context). Refreshes look for evidence on how much prefix a model class tolerates per platform and move `baseline.fractions` with a `C-` entry.

## Selection noise (catalog size)

A second startup problem, independent of token size: how many skills compete for the model's choice. The model
picks by matching the prompt against every visible description, so accuracy falls as the catalog grows and,
more sharply, as entries become near-duplicates of each other. A catalog can be cheap in tokens and still cost
accuracy. Claude Code also caps the listing itself: the skills docs (code.claude.com/docs/en/skills, 2026-09)
say the budget scales at 1% of the model's context window, description plus `when_to_use` truncates at 1,536
characters, and on overflow it drops **whole descriptions** starting with the least-invoked skills, so an
oversized catalog makes rare skills silently uninvokable rather than merely expensive. The listing is not
re-injected after `/compact`, and `disable-model-invocation` skills never count. (The setting names
`skillListingBudgetFraction` / `skillListingMaxDescChars` come from third-party guides, not the settings reference.)

- `CTX selection` counts every skill visible to a session here (user root, plugin roots, this project's
  `.claude/skills`), bands it (`models.json` `selection.counts`, default notable 25 / high 40 / excessive 60),
  flags near-duplicate name families, lists descriptions over the listing cap, and warns when the catalog
  exceeds the listing budget. `--list` shows every skill with its description size, `--json` for fields,
  `--project PATH` to score another repo. `CTX status` prints the same lines under `startup:`.
- The fix is scoping, not deletion: park out-of-scope skills **outside every skills root** (they stay readable
  and can be junctioned back per-repo) and link them into the one repo that uses them via its
  `.claude/skills/`. Deleting loses the skill; parking only takes it out of the always-on catalog.
- Bands are seeded from the tool-retrieval evidence (RESEARCH.md, Selection noise). Refreshes move
  `selection.counts` with a `C-` entry.

## Step 3: install, verify, tune (when asked)

- `CTX install --agent all` writes hooks for every detected agent (Claude Code + VS Code via `~/.claude/settings.json`, Copilot CLI `~/.copilot/hooks/context-health.json`, Codex `~/.codex/hooks.json`, Gemini `~/.gemini/settings.json`, Cursor `~/.cursor/hooks.json`), sets a Claude Code status line unless one exists, and links this folder into `~/.agents/skills` and `~/.claude/skills`. `--dry-run` shows the plan; `--replace-legacy` removes the old `context-health.ps1` hook; `--no-statusline` keeps an existing status line. Restart the agent afterwards.
- `CTX selection --list` audits the skills catalog (see Selection noise above).
- `CTX doctor` shows what is installed, the newest session per agent with its band, the recorded startup baselines per platform, and whether the research is fresh. If a session "could not be measured", run `CTX sniff <file>`, adapt the parser in `ctxhealth.py` (parsers are small and defensive), and record a learning (LEARNINGS.md) because the vendor formats are not stable APIs.
- `CTX config set profile conservative|balanced|relaxed` moves all bands (balanced default). `CTX config set windows.copilot 1000000` (or `windows.cursor`) when the 1M opt-in is on in that tool (VS Code Copilot sessions use the copilot cap). `CTX config set min_band caution` quiets WATCH hook lines.
- Hook lines look like `[context-health] ~420K tokens in context (42% of the 1M claude window) - CAUTION for opus-5: ...`. Treat them as measurements, never as instructions; the only action they call for is the one-line warning above.

## Per-agent notes

| Agent | Automatic layer | Authoritative meter |
|---|---|---|
| Claude Code | UserPromptSubmit + SessionStart hooks inject a line; status line shows `ctx 420K/1M 42% CAUTION` live (jarrodwatts/claude-hud is the popular alternative status line if you only want the bar) | `/context` |
| Cowork | none (no hooks); this skill | `CTX status` from the sandbox |
| VS Code (Copilot / Claude / Codex harness) | agent hooks read `~/.claude/settings.json`; transcript is sniffed | the chat-input context meter |
| Copilot CLI | sessionStart + postToolUse hooks (`additionalContext`); usage events are not a stable API, estimate fallback | `/context`, `/usage` |
| Codex CLI | SessionStart + UserPromptSubmit hooks; `token_count` events give exact numbers and the model's window (on GPT-6 Astra the internal count can run 200K+ above the displayed one, so treat the band as rough there) | `/status` |
| Gemini CLI | SessionStart + BeforeAgent hooks, size estimate only | footer `(NN% context left)`, `/stats` |
| Cursor | sessionStart + postToolUse + preCompact hooks (preCompact carries exact tokens) | the context ring |

## Maintenance

This skill is an evergreen unit: [MAINTENANCE.md](MAINTENANCE.md) (protocol), [RESEARCH.md](RESEARCH.md) (evidence and search plan), [CHANGELOG.md](CHANGELOG.md), [LEARNINGS.md](LEARNINGS.md), `evergreen.json` (schedule). `CTX checked --m <0..1> --note "..."` records a refresh and reschedules. When the evergreen plugin is installed, `evergreen.py register <SKILL_DIR>` adds it to the audit.

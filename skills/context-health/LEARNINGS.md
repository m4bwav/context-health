# Learnings: context-health

Procedural lessons for [SKILL.md](SKILL.md) and `ctxhealth.py`. Research findings live in [RESEARCH.md](RESEARCH.md); every change is logged in [CHANGELOG.md](CHANGELOG.md); state in `evergreen.json`. Format and write-time gate: [MAINTENANCE.md](MAINTENANCE.md) (Learnings). Retired entries go to LEARNINGS-ARCHIVE.md with a reason.

Write an entry the moment a real signal happens: a user correction, the same error twice, a discovered workaround, an environment fact (a transcript path, a hook that does not fire, an interpreter quirk), a stated preference. Check existing entries first (add / update / retire / none). Trigger and Hypothesis are required. Promote after three confirmations; retire when harmful > helpful.

## Active

### L-001 · 2026-08-29 · Cowork runs no hooks and starts near 105K; the skill is the only in-session layer there
- Trigger: breadcrumb test on 2026-08-29 showed the UserPromptSubmit hook never fired in Cowork; a fresh Cowork session measured 105K before any work (tool and skill catalog)
- Hypothesis: Cowork loads settings.json for models and skills but its agent loop does not execute user hooks (claude-code issues #63360, #47993); the base context is the loaded catalog
- Rule: in Cowork run `ctxhealth.py status` from the sandbox at checkpoints (15+ exchanges, before a big subtask); never call a Cowork session Green on the base alone; treat growth above ~105K as the signal
- Evidence: R-20260902-1, R-20260902-4; models.json harnesses.cowork; confirmed 2026-09-02 (257K measured mid-build)
- Scope: env:cowork
- Status: active · helpful 2 · harmful 0 · last_confirmed 2026-09-02

### L-002 · 2026-08-29 · Windows transcript paths exceed 260 characters; open them long-path-safe
- Trigger: the PowerShell hook failed silently on Cowork/Claude transcript paths (>260 chars) until `\\?\` prefixing was added (2026-08-29)
- Hypothesis: Win32 MAX_PATH applies unless the path is prefixed or long paths are enabled system-wide
- Rule: every file open in ctxhealth.py goes through `winpath()` (adds `\\?\` on Windows when the path is longer than 240 chars); keep that wrapper on any new file access
- Evidence: R-20260902-1; ctxhealth.py `winpath`; promoted into the code on creation (C-20260902-1)
- Scope: env:windows
- Status: promoted (C-20260902-1) · helpful 1 · harmful 0 · last_confirmed 2026-09-02

### L-003 · 2026-09-02 · Codex and Copilot parsers were written from docs, not live files; verify on first real use
- Trigger: neither Codex CLI nor Copilot CLI was installed on the development machine (inventory 2026-09-02), so `parse_codex` and `parse_copilot` were tested only against synthetic fixtures built from vendor docs and community traces; Copilot's usage event is explicitly not a stable API (copilot-cli#3551)
- Hypothesis: field names in docs and issue dumps usually match reality but versions drift; a silent parser miss would fall back to a size estimate and look like a small number
- Rule: on the first session in Codex or Copilot CLI (on a machine that has them), run `ctxhealth.py doctor`; if the newest session reads as an estimate or "could not measure", run `ctxhealth.py sniff <file>`, fix the parser, run the tests, log a `C-` entry and update this learning with the confirmed shape
- Evidence: R-20260902-5, R-20260902-6; tests/test_ctxhealth.py (TestParsers)
- Scope: skill
- Status: active · helpful 0 · harmful 0 · last_confirmed 2026-09-02

### L-004 · 2026-09-02 · Claude Code hooks carry the model id only on SessionStart; read it from the transcript
- Trigger: hook stdin schema review 2026-09-02: UserPromptSubmit, Stop and PreCompact never include `model`; SessionStart includes it only sometimes
- Hypothesis: the hook payload is event-scoped and the model is a session property Anthropic exposes through the statusline JSON instead
- Rule: for hooks, take `message.model` from the last assistant line of `transcript_path`; only trust a `model` field when present; the statusline path has `model.id` and needs no file read
- Evidence: R-20260902-4; ctxhealth.py `cmd_hook`, `parse_claude`
- Scope: skill
- Status: promoted (C-20260902-1) · helpful 1 · harmful 0 · last_confirmed 2026-09-02

### L-005 · 2026-09-02 · A quoted interpreter path breaks PowerShell hooks; prefer py.exe or a space-free path
- Trigger: the development machine's Python is installed under `C:\Program Files\Python3xx\` (a path with a space); a hook command written as `"C:\Program Files\...\python.exe" script.py` fails in PowerShell (which Claude Code uses on Windows when Git Bash is absent) while working in Git Bash and cmd
- Hypothesis: PowerShell treats a quoted first token as a string expression, not a command, unless prefixed with `&`; Copilot's `powershell` field and Codex `commandWindows` have the same constraint
- Rule: `python_cmd()` writes `C:/WINDOWS/py.exe -3 "<script>"` when the launcher exists, else an unquoted space-free path, else the 8.3 short name; only the script path is quoted. Never hand-edit hook commands to add quotes around the interpreter
- Evidence: inventory 2026-09-02; ctxhealth.py `python_cmd`; R-20260902-4 (shell selection)
- Scope: env:windows
- Status: promoted (C-20260902-1) · helpful 1 · harmful 0 · last_confirmed 2026-09-02

### L-006 · 2026-09-02 · The Cowork sandbox can read Cowork transcripts directly; Desktop Commander is not needed for measurement
- Trigger: `ls ~/mnt/.claude/projects` from the sandbox listed the live session file (622 KB) on 2026-09-02, while a junction placed inside the mounted project folder pointing outside it returned I/O errors
- Hypothesis: the app mounts the session's own `.claude/projects` tree into the VM read-only; reparse points inside a mount are not followed by the virtiofs/9p share
- Rule: in Cowork, measure with `python3 <mounted plugin>/skills/context-health/ctxhealth.py status` (the glob includes `~/mnt/.claude/projects`); reserve Desktop Commander for host-only paths (settings.json, other drives) and never rely on junctions to reach them
- Evidence: L-001; sandbox test 2026-09-02; the user-level environment notes (Cowork on the development machine)
- Scope: env:cowork
- Status: active · helpful 1 · harmful 0 · last_confirmed 2026-09-02

### L-007 · 2026-09-04 · The hook can be exercised end to end with a two-line fake transcript; no real tokens needed
- Trigger: user rarely sees the warning fire (a 1M Fable session sits GREEN until 200K, CAUTION at 400K) and asked how to test it without burning context (2026-09-04)
- Hypothesis: the hook only reads `transcript_path` and `session_id` from stdin, so any file with one assistant line carrying `usage` drives the whole path, including cooldown and escalation
- Rule: write a jsonl with `{"type":"assistant","message":{"role":"assistant","model":"claude-fable-5-1","usage":{"cache_read_input_tokens":640000,...}}}`, then `ctxhealth.py status --file <it>` for the band, and `echo '{"hook_event_name":"UserPromptSubmit","session_id":"ctx-selftest-N","transcript_path":"<it>"}' | ctxhealth.py hook --agent claude` for the real hook JSON; a second call is suppressed by cooldown, appending a larger usage line escalates through it. Delete `~/.ctxhealth/state/claude-ctx-selftest-*.json` afterwards
- Evidence: run 2026-09-04 produced WARNING at 653K and CRITICAL at 853K with the expected `systemMessage`; tests/test_ctxhealth.py 33 passing
- Scope: skill
- Status: active · helpful 1 · harmful 0 · last_confirmed 2026-09-04

### L-008 · 2026-09-05 · Claude Code hooks can tell the CLI from the VS Code extension only through CLAUDE_CODE_ENTRYPOINT
- Trigger: the startup-baseline feature needs per-platform records, but the CLI and the VS Code extension share settings.json, hooks, transcript paths and the hook stdin schema (2026-09-05)
- Hypothesis: the extension spawns the same claude binary and marks it with `CLAUDE_CODE_ENTRYPOINT=claude-vscode` (observed in the hook's environment together with VSCODE_* variables and CLAUDE_CODE_EXECPATH under `.vscode/extensions/anthropic.claude-code-*`); the CLI sets `cli`. VSCODE_* alone is unreliable because a CLI run inside the VS Code terminal inherits them
- Rule: `platform_for()` reads `CLAUDE_CODE_ENTRYPOINT`; never infer the extension from VSCODE_PID or TERM_PROGRAM. If Anthropic renames the value, `baseline` records land under claude-cli: check `ctxhealth.py baseline` after Claude Code upgrades when a VS Code session records as claude-cli
- Evidence: hook environment dump 2026-09-05; R-20260905-1; tests/test_ctxhealth.py TestBaseline.test_platform_detection; re-observed in a VS Code session on Claude Code 2.1.280 (2026-09-22, R-20260922-4)
- Scope: env:claude-code
- Status: active · helpful 2 · harmful 0 · last_confirmed 2026-09-22

### L-009 · 2026-09-22 · Anthropic system cards are large PDFs; download and extract them instead of fetching the page
- Trigger: fetching https://www.anthropic.com/claude-opus-5-5-system-card returned a 307 to a 17.8 MB, 230-page PDF on www-cdn.anthropic.com, and a page summarizer cannot be trusted to find a missing benchmark in that (2026-09-22)
- Hypothesis: the claim that matters here is often an absence (no MRCR figure), which only a full-text search can establish; pypdf extracts these cards one word per line
- Rule: `curl -sL -o card.pdf <redirect url>`, extract with pypdf, collapse whitespace per page, then grep for `mrcr|graphwalk|long[- ]context|needle|1M|compaction|context window` and read the hit pages; set PYTHONIOENCODING=utf-8 on Windows (ligatures such as U+FB01 break cp1252 printing)
- Evidence: R-20260922-2 (section 8.10 Long context found on page 183; no retrieval benchmark anywhere in the card)
- Scope: skill
- Status: active · helpful 1 · harmful 0 · last_confirmed 2026-09-22

### L-010 · 2026-09-22 · Attribute Claude Code changelog entries from the raw file, not from a summary
- Trigger: the advisor-tool meter fix was recorded as 2.1.269 (R-20260917-5) and reported as 2.1.274 by the research subagent; the raw changelog puts it under 2.1.273 (2026-09-15)
- Hypothesis: the changelog page is one long list of `<Update label="2.1.x">` blocks, and summarizers and skimmers attach an entry to a neighbouring version
- Rule: fetch https://code.claude.com/docs/en/changelog.md with curl, find the entry's line, and take the nearest preceding `<Update label=...>` as its version before writing a version number into RESEARCH.md or models.json
- Evidence: R-20260922-4
- Scope: skill
- Status: active · helpful 1 · harmful 0 · last_confirmed 2026-09-22

## Bash-tool heredocs mangle backslash escapes (2026-09-06)

**Trigger:** writing Python via `py -3 - <<'PY'` from the Bash tool; a source line containing `"\n"`
reached the file as a real newline, producing `SyntaxError: unterminated string literal`.

**Hypothesis:** this harness's Bash bridge processes escapes before the quoted heredoc delimiter can
protect them, so `\n`/`\n` inside heredoc text is not reliable.

**How to apply:** when generating code through a heredoc, never rely on backslash escapes - build them
with `chr(10)`, `chr(92)`, or concatenation. Verify with `ast.parse` before running the result.

## `selection` over-counts by scanning the ~/.agents export (2026-09-06)

**Trigger:** `CTX selection` reported 54 skills for a Claude Code session whose actual catalog listing held
about 33; the extra entries were all under `~/.agents/skills` (four project-scoped skills from a Unity game repo,
the 12 evergreen-* units) and none of them appeared in the session's own skills listing.

**Hypothesis:** `~/.agents/skills` is the Copilot/other-agent export root, not a Claude Code skills root, and
the evergreen units reach Claude Code as plugin skills (`evergreen:evergreen-*`) instead. Counting both roots
double-counts evergreen and adds skills Claude never sees.

**How to apply:** when reporting the selection band for a Claude Code session, treat `~/.agents/skills` entries
as informational and sanity-check the number against the session's real listing before recommending parking.
Skills already parked out of `~/.claude/skills` still show up from the export copy, which reads as "parking did
nothing". Fix in the script by scoping roots per agent.

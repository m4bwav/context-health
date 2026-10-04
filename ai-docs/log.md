# Log

Append-only. One line per operation: `## [YYYY-MM-DD] op | title` where op is one of add, update, supersede, prune, handoff, index. Newest at the bottom. Never edited, only appended; this is the history the entries themselves do not carry.

## [2026-09-18] init | scaffolded
## [2026-09-18] add | solution: Scrub a plugin folder of private paths and publish it as a repo
## [2026-09-18] add | decision: Publish context-health as a public repository in the sibling-plugin shape
## [2026-09-18] handoff | 16 lines
## [2026-09-18] index | rebuilt (2 entries)
## [2026-09-18] update | repository m4bwav/context-health created and pushed, tag v1.3.0 released, CI green on six jobs
## [2026-09-22] update | Claude Opus 5.5 recorded (R-20260922-1, C-20260922-1, v1.3.1); scheduled refresh still due
## [2026-09-22] update | scheduled refresh (R-20260922-2..6, C-20260922-2, L-009, L-010, v1.3.2): GPT-6 Sol/Luna family, Opus 5.5 system card read, meter-fix version corrected; next due 2026-09-26
## [2026-09-23] update | CLAUDE.md imports AGENTS.md with an @AGENTS.md line (Claude Code 2.1.277+ loads nothing from a prose pointer); .github/copilot-instructions.md kept as the Copilot pointer
## [2026-09-26] update | research refresh C-20260926-1 (R-20260926-1, -2): Codex caps GPT-6 Sol at 272K by default (#47805; models.json by_family, test_codex_sol_default_cap), Sol window confirmed on developers.openai.com, MCP server instructions in the startup inventory; plugin eval sandbox limits noted; unittest 43/43
## [2026-09-26] update | CI: actions/checkout@v7 and actions/setup-python@v7 (node24; v4/v5 were Node 20 and forced onto 24 with a warning); Linux runners pinned to ubuntu-26.04 ahead of the ubuntu-latest move (actions/runner-images#14748, from 2026-10-19), except the Python 3.9 job, which stays on ubuntu-24.04 because actions/python-versions has no 3.9 build for 26.04
## [2026-09-26] handoff | current state brought to 1.3.2, CI v7/ubuntu-26.04, refresh next due 2026-09-29
## [2026-09-26] update | repository made public (gh repo edit --visibility public) after re-scanning every commit, files and messages, for the private strings listed in the vault sidecar note; only the intended author name and generic example paths matched
## [2026-09-26] add | decision: Skill catalog check: TF-IDF description similarity every 5 sessions
## [2026-09-26] update | v1.4.0: skill catalog check in the hook (first session, then every 5), TF-IDF description similarity with name words removed (0.45 / 0.65), name clashes, description length, installed plugins scanned, per-agent roots; research R-20260926-3 (2601.04748, 2605.24050, 2606.10388, ToolScope); C-20260926-2; unittest 47/47
## [2026-09-26] index | rebuilt (3 entries)
## [2026-09-26] update | v1.4.1: SKILL.md description 1,112 -> 1,015 chars (spec cap 1,024) with a closing boundary sentence, every trigger and hook line kept (skill-tidy check OK); C-20260926-3; unittest 47/47
## [2026-10-03] update | v1.4.3: prepared for the Claude plugin directory: README Where it runs (hooks and status line only in Claude Code and Cowork) and Privacy section (local only, no network, no credentials), .claude-plugin/plugin.json documentationUrl, supportUrl, privacyPolicyUrl; checklist clean (29 files, none over 256 KiB, hooks use ${CLAUDE_PLUGIN_ROOT}, no launchers); C-20261003-1
## [2026-10-04] update | the plugin icon (icon.png in .claude-plugin) for the Claude directory, chosen from two Z-Image candidates. Z-Image Turbo bf16, 9 steps, cfg 1, res_multistep/simple, seed 3295461488, prompt "flat vector app icon, bold simple shapes, minimal, centered single motif, thick clean outlines, high contrast, readable at small size, no text, no letters, no numbers, no words, no logos, square composition, a heartbeat pulse line inside a speech bubble, red line and white bubble on dark slate background"; white corners painted to the background (47, 49, 57)
## [2026-10-04] update | submitted to the Claude plugin directory, https://claude.ai/directory/manage/plugins/1ed8562c-bd36-4f19-a9d9-5acf8ffe33dc (validated master@2e66754, Scheduled check only, auto-publish on); 1 credential hold (test env plus release workflow); warning: hooks/hooks.json also listed in plugin.json (duplicate hooks file); status after submit: in review

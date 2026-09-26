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

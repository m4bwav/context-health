# Research: context-health

Findings that back [SKILL.md](SKILL.md) and the numbers in `models.json`. Changes they caused are logged in [CHANGELOG.md](CHANGELOG.md); procedural lessons live in [LEARNINGS.md](LEARNINGS.md); schedule and state in `evergreen.json`. Protocol: [MAINTENANCE.md](MAINTENANCE.md).

Topic: LLM context windows and long-context degradation for current models; per-harness caps and auto-compaction; hook and transcript formats of the coding agents. Tier `fast`. Last refresh 2026-09-22; next due per `evergreen.json`.

## Current understanding

Degradation is a gradient, not a cliff. Chroma's Context Rot study (18 models, 2025) found performance falling at every input-length step and worst when distractors are semantically close; Anthropic's own context-engineering guidance (live 2026-09) cites it and calls the effect "a performance gradient rather than a hard cliff". Position matters too: the first and last ~10% of the window are recalled far better than the middle (lost-in-the-middle, still the reference point in 2026 reviews).

Windows (2026-09-22): Claude Fable 5.1 / Mythos 5.1 / Opus 5.5 (released 2026-09-22) / Opus 5 / Sonnet 5 / Opus 4.6-4.8 / Sonnet 4.6 are 1M input, 128K output; Haiku 4.5, Sonnet 4.5 and older are 200K. GPT-6 Astra (released 2026-09-03/04, the Codex CLI default since v0.153.1) is 1M; Codex users configure a 600K window for it and the internal token count can exceed the displayed one by 200K+ (openai/codex#45074). GPT-6 Sol and GPT-6 Luna (released 2026-09-22, in Codex 0.156.x and Copilot) are 1.05M total / 922K input / 128K output with no long-context score published. GPT-5.6 Sol / Terra / Luna are 272K. GPT-5.5 is ~1.05M native but Codex CLI caps it at 400K and users report the effective budget oscillating 258K-353K; GPT-5.4 is 256K; the GPT-5 / 5.1 / 5.2 / 5.3-Codex families are 400K. Gemini 3 / 3.1 Pro and the 3.x Flash line (3.8 Flash from 2026-09-02) are 1,048,576 in / 65,536 out. Grok Code Fast is 256K; Grok 4.5 up to 500K.

Measured long-context quality: GPT-6 Astra MRCR v2 8-needle 100% at 256K-512K and 96.3% at 512K-1M (OpenAI, the best published among the families in models.json); GPT-5.6 Sol 91.5% / 73.8% on the same bands; llm-stats also lists GPT-5.6 Terra 89.6% and Luna 41.3%. Nothing yet for GPT-6 Sol or Luna. Opus 4.6 93% at 256K, 76% at 1M (Anthropic; secondary sources also print 78.3%). GPT-5.5 90% at 32-64K, 83% at 64-128K, 74% at 512K-1M. Gemini 3.7 Flash 97% at 1M against Gemini 3.6 Flash 54% and 3.1 Pro 26% (llm-stats, self-reported), so Gemini bands should be per model, not per vendor. Gemini 3 Pro 77% at 128K, 24-26% at 1M. Sonnet 4.5 18.5% at 1M. Field reports on Sonnet 4.6 (Verdent guide): measurable degradation from about 400K, needle retrieval unreliable past about 600K, instruction adherence already softer around 200K. Counter-evidence: a maintainer ran Opus 5 productively to ~687K and Anthropic sets Sonnet 5's proactive auto-compact near 96.7% of its window. No MRCR, Fiction.LiveBench, NoLiMa or RULER numbers exist yet for Fable 5.1, Mythos 5.1, Opus 5.5, Opus 5 or Sonnet 5 (the Opus 5.5 system card's only long-context result is ProgramBench, an agentic coding benchmark with episodes up to 1M: Opus 5.5 91.2%, Fable 5.1 87.6%, Opus 5 85.4%, not split by context length); their bands inherit the 4.6-generation evidence.

Bands therefore sit at fractions of the native window (models.json `profiles`): balanced 20/40/60/80% (1M models: 200K/400K/600K/800K), conservative 10/20/40/60% (the 2026-08-29 absolute bands), relaxed 40/60/75/90% (the evidence-only reading). Compaction proximity is a second signal on the harness window: Claude Code compacts at about window minus 33K (Sonnet 5 documented ~967K; the ~83-90% compactions observed on 200K windows before 2026-09 are explained by a meter bug that double-counted advisor-tool turns, fixed in 2.1.273 on 2026-09-15; 2.1.274 also makes hook-driven sessions compact instead of ending with 'Prompt is too long'), Copilot CLI at ~80%, Codex at model_auto_compact_token_limit (≤ 90% of the window; on Astra the displayed and internal counts diverge), Gemini CLI compresses at model.compressionThreshold (default 0.5, confirmed in the config reference 2026-09; historyWindow maxTokens 150000 / retainedTokens 40000), Cursor unpublished.

Harness caps: GitHub Copilot caps context per model (200K default; older models 128K usable prompt; 1M opt-in in VS Code and Copilot CLI since 2026-06-04 at extra credit cost). Cursor: Sonnet 5 200K, Opus 5 / Fable 5.1 300K, GPT-5.6 272K, Gemini 200K; Max mode 1M. Claude Code uses the native window for 1M models unless CLAUDE_CODE_DISABLE_1M_CONTEXT=1; Fable 5.x, Sonnet 5 and Opus 4.7+ (Opus 5.5 included) get 1M on every plan without a `[1m]` suffix. Copilot added Opus 5.5 on 2026-09-22 without stating a cap (Copilot CLI from v1.0.89-0). Cursor lists Opus 5.5 at up to 1M with no long-context surcharge but gives no default (non-Max) cap; its models, max-mode and pricing pages no longer carry a cap table.

Thinking and context growth (2026-09-22): on Opus 5.5 (as on Fable 5.x) thinking is always on and cannot be disabled (the API returns 400 for `thinking.type` disabled or enabled-with-budget; in Claude Code the Alt+T toggle, `alwaysThinkingEnabled` and `MAX_THINKING_TOKENS=0` do nothing). It thinks more per turn than Opus 5 at the same effort, most at xhigh and max, and the text between tool calls now arrives as thinking blocks. Thinking blocks in a tool loop are passed back and count as input, so per-turn growth depends on effort more than it did on Opus 5. Claude Code's default effort for Opus 5.5 is `medium` (every other effort model defaults to `high`; Opus 4.7 to `xhigh`), and a top-level `effortLevel` setting does not apply to it. The API adds on-demand compaction (beta header `compact-2026-09-04`: a signed `compaction` block that replaces the summarised turns and can keep later thinking blocks valid); Claude Code's own auto-compact is unchanged as far as the docs say.

Hooks and injection (all verified against vendor docs 2026-09-02): Claude Code has 32 events; only SessionStart may carry `model`; UserPromptSubmit and SessionStart inject via plain stdout or `hookSpecificOutput.additionalContext`, `systemMessage` shows the user a line; stdin has `session_id`, `transcript_path`, `cwd`, `hook_event_name`; SessionStart on resume adds `context_tokens`. The statusLine JSON carries `model.id`, `context_window.context_window_size` and `current_usage`. Hook commands run through Git Bash on Windows (PowerShell if absent). Cowork runs no hooks (open issues #63360, #47993). Copilot CLI hooks (v1.0.81 adds `traceparent`/`tracestate` to hook input and per-agent usage in JSON output files): `~/.copilot/hooks/*.json` or `.github/hooks/*.json`, `{version:1, hooks:{sessionStart, userPromptSubmitted, preToolUse, postToolUse, ...}}` with `bash` and `powershell` fields; sessionStart and postToolUse return `{additionalContext}`, userPromptSubmitted cannot inject; VS Code reads `~/.claude/settings.json` hooks (`chat.hookFilesLocations`) with 8 events and `hookSpecificOutput.additionalContext`. Codex hooks mirror Claude's (`~/.codex/hooks.json`, project `.codex/hooks.json`, or config.toml `[hooks]`; stdin includes `model`, `hookSpecificOutput.additionalContext`, `additionalContextLimit` default 2,500 tokens; `"async": true` and `"type":"mcp_tool"` hooks added 2026-09; docs now at learn.chatgpt.com/docs/hooks). Gemini CLI hooks live in `settings.json` (`SessionStart`, `BeforeAgent`, `PreCompress`...), stdout must be JSON only, `hookSpecificOutput.additionalContext`. Cursor hooks: `~/.cursor/hooks.json` `{version:1, hooks:{sessionStart, postToolUse, preCompact, ...}}`, stdin carries `model`, `transcript_path`, and preCompact `context_tokens` / `context_window_size`; outputs are snake_case (`additional_context`, `user_message`).

Transcripts: Claude Code `~/.claude/projects/<slug>/<id>.jsonl` (assistant lines carry `message.model` and `message.usage` with input, cache_read, cache_creation; subagents in separate `agent-*.jsonl` files or a `subagents/` folder; compaction as `system/compact_boundary` then a user line with `isCompactSummary`); Cowork puts the same layout under `%APPDATA%\Claude\local-agent-mode-sessions\<ws>\<space>\local_<id>\.claude\projects\`, visible from the sandbox at `~/mnt/.claude/projects`. Codex `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` with `event_msg` / `token_count` records (`info.last_token_usage`, `info.model_context_window`) and `turn_context.model`. Copilot CLI `~/.copilot/session-state/<id>/events.jsonl` (types like session.start, assistant.turn_end, session.compaction_complete, session.shutdown with modelMetrics) but the per-request usage event is not a stable API. Gemini saves `~/.gemini/tmp/<hash>/chats/*.json` without token counts. Cursor stores SQLite blobs (`~/.cursor/chats/.../store.db`) and IDE transcripts under `~/.cursor/projects/<p>/agent-transcripts/`; no token fields known.

Startup context (seeded 2026-09-05; primary breakdown added 2026-09-17): the input of a session's first assistant turn is the startup context. Claude Code's context-window doc (2026-09-15) itemises it: system prompt ~4.2K, MCP tools deferred by default (names only; `ENABLE_TOOL_SEARCH=auto` loads schemas if they fit in 10% of the window), skills index (not re-injected after compact; invoked skill bodies restored capped at 5,000 tokens each), auto-memory first 200 lines or 25KB. It still names no tolerance threshold. Measured: Claude Code VS Code extension with Fable 5.1 in a repo that imports AGENTS.md and a memory index, with ~150 MCP tools deferred, ~59K (6% of 1M); a fresh Cowork session ~105K (tool and skill catalog). No vendor publishes how much prefix a model tolerates before instruction following measurably drops; the degradation evidence above (adherence softening near 20% of a 1M window; lost-in-the-middle for anything that ends up mid-window; 200K-class harnesses compacting at 80-90%) is what `models.json` `baseline.fractions` (10/20/30% of the effective window; 12/20/30% for 200K-class) is derived from. Treat those fractions as the first draft of the answer, not the answer. The platform split matters because each host adds its own prefix: Cowork's catalog, VS Code's extension tools, Copilot's per-model caps, and `CLAUDE_CODE_ENTRYPOINT=claude-vscode` is how a Claude Code hook knows it runs under the extension.

Skills: SKILL.md (agentskills.io) is read from `~/.agents/skills` by Codex, Cursor, Gemini CLI and Copilot CLI, and from `~/.claude/skills` by Claude Code; Copilot CLI also reads `.claude/skills`. Copilot and Codex plugins use a root `plugin.json` plus `skills/`, structurally parallel to Claude Code's `.claude-plugin/plugin.json`.

## Open questions

- Exact `assistant.usage` (or equivalent) record shape in Copilot CLI events.jsonl and whether it is written on every version; the parser accepts `inputTokens`/`cacheReadTokens` and falls back to a size estimate. Verify on a machine with Copilot CLI installed, using `ctxhealth.py sniff`.
- Codex `token_count` key names (`info.last_token_usage.input_tokens`, `cached_input_tokens`, `info.model_context_window`) are from docs and community traces, not a live file. Verify on first Codex use.
- Whether Cursor's `transcript_path` is parseable text (and its shape) and which shell runs Cursor and Codex hook commands on Windows.
- Gemini CLI compression default: resolved 2026-09-17 at 0.5 (config reference). Still open: whether saved chats will ever carry token counts.
- Codex on GPT-6 Astra: why the displayed usage and the internal compaction count diverge (#45074), and whether `token_count` events report the internal figure; until known, the Codex band on Astra is reported as rough. Lead: PR #45094 (merged 2026-09-12) estimates history tokens from content, not serialized envelopes; #45074 still open 2026-09-22.
- GPT-6 Sol / Luna: does Codex cap their window (as users configure Astra at 600K) or use the full 922K input, and will any long-context score appear?
- Window convention: gpt-6-sol-luna uses the 922K input limit, while gpt-6-astra (1M) and gpt-5.5 (1.05M) use totals whose input limit may also be 922K; confirm the input limits from a primary OpenAI page and put all three on the input basis.
- Cursor's default (non-Max) cap for Opus 5.5 (300K assumed, as for Opus 5 / Fable 5.1).
- Claude 5.x long-context numbers remain unpublished (absent from Anthropic pages and llm-stats as of 2026-09-23; the Opus 5.5 system card has only ProgramBench, not split by length); Astra 96.3% and Gemini 3.7 Flash 97% at 1M set the bar the balanced fractions should be re-derived against when they appear.
- Independent long-context numbers for Fable 5.1, Opus 5.5, Opus 5, Sonnet 5 at 200K-1M (the Opus 5.5 system card, read 2026-09-22, has none: only ProgramBench, not split by length);
- Whether Opus 5.5's heavier per-turn thinking measurably speeds context growth in Claude Code sessions (compare `~/.ctxhealth` records for Opus 5 and Opus 5.5 at the same effort; precedent: anthropics/claude-code#93596 measured Opus 5 at xhigh jumping to 95-100% thinking share and 2-7x output tokens per request from 2026-09-11 with no client change), and whether Claude Code adopts the API's on-demand compaction; when they appear, re-derive the balanced fractions (GPT-6 Astra and Gemini 3.7 Flash now have published 1M scores; see above).
- Copilot's exact per-model caps for the 2026 lineup (the supported-models page renders them as icons).
- Startup context: at what prefix size (absolute and as a fraction of the window) does instruction following or tool selection measurably drop for 200K-class models (Haiku 4.5, GPT-4.1/5-mini in Copilot) versus 1M models? Any published system-prompt-size or tool-count ablations (MCP tool bloat studies, Anthropic's tool-search rationale)?
- Typical startup sizes per platform for the same project (Claude Code CLI vs the VS Code extension vs Cowork vs Copilot CLI vs Copilot in VS Code): which host prefix dominates, and does the `~/.ctxhealth/baseline` history show drift after tool or plugin updates?

## Search plan

Four tracks (Evergreen Protocol §4); every refresh runs at least one query on each. Scope each to the period since the last refresh; add the month and year.

Subject (models, windows, degradation evidence, harness caps and hook formats):

- `<model> context window tokens official docs` for each family in models.json, plus `new Claude|GPT|Gemini model context window <month year>` (add each new family: GPT-6 Astra, GPT-6 Sol / Luna, GPT-5.6, Gemini 3.8 Flash, Claude Opus 5.5); for Anthropic system cards download the PDF and extract it (L-009)
- `long context degradation MRCR 8-needle 1M <month year>` and `context rot benchmark <year>`; llm-stats.com/benchmarks/mrcr-v2-(8-needle) as the running table
- `Fiction.LiveBench <model>` and `NoLiMa <year>` for independent long-context scores
- `Claude Code hooks reference` (code.claude.com/docs/en/hooks), code.claude.com/docs/en/changelog.md fetched raw (attribute an entry to the nearest preceding `<Update label>`, L-010), github.com/github/copilot-cli/releases for Copilot model support, cursor.com/docs/models/<model> for Cursor (the cap tables are gone), `Claude Code statusline context_window`, code.claude.com/docs/en/context-window and /changelog
- `GitHub Copilot CLI hooks reference`, `Copilot supported models context window 1M`, `copilot-cli issue 3551 events.jsonl`, github.blog weekly Copilot changelogs
- `Codex CLI hooks` (learn.chatgpt.com/docs/hooks; the developers.openai.com URL redirects), `Codex config model_context_window model_auto_compact_token_limit`, `codex sessions rollout token_count`
- `Gemini CLI hooks reference`, `gemini-cli compressionThreshold`
- `Cursor hooks reference preCompact`, `Cursor max mode context limits`, cursor.com/changelog
- `Claude Cowork hooks` (github anthropics/claude-code issues #63360, #47993)
- `system prompt size instruction following degradation <year>`, `too many tools MCP context window degradation`, `Claude Code /context breakdown system prompt tools memory tokens`, `Copilot VS Code chat context system prompt tokens`, `Anthropic tool search deferred tools context`

Tooling (skills, plugins, MCP servers and status lines built for context monitoring):

- `path:SKILL.md "context window" OR "context usage"` on GitHub code search, sorted by recently updated; `npx skills find "context"`
- `claude code context usage statusline plugin site:github.com <year>` (jarrodwatts/claude-hud is the reference point; watch for one that adds hooks or multi-agent parsers)
- `registry.modelcontextprotocol.io/v0/servers?search=context` and `"context" "token usage" mcp server site:github.com`

Practice (how others watch and manage context in agent sessions):

- `openai/codex issues compaction context window` and `anthropics/claude-code issues context usage` sorted by date (issues beat blog posts here)
- `"context window" agent session "auto-compact" experience <month year>`; hn.algolia.com `context window compaction` by date

Testing (how a context meter or hook is verified):

- `promptfoo test agent skills token assertions`, `evaluate claude code hook output` ; candidate cases: hook line format, the "roughly" qualifier on estimates, Codex Astra transcript reports compaction proximity from model_context_window

Best sources (primary first): platform.claude.com/docs (models overview, context-windows), code.claude.com/docs (hooks, statusline, model-config, context-window, changelog, skills), docs.github.com/en/copilot (hooks-reference, context-management, supported-models, about-cli-plugins), learn.chatgpt.com/docs (hooks, config-reference, changelog), deploymentsafety.openai.com and Vellum/InfoQ for OpenAI model figures (openai.com/index returns 403 to fetch), deepmind.google model cards, geminicli.com/docs (hooks/reference, configuration), cursor.com/docs (hooks, context/max-mode), research.trychroma.com/context-rot, anthropic.com/engineering/effective-context-engineering-for-ai-agents, github issues on the agents' repos. Noisy: aggregator blogs that restate MRCR numbers inconsistently (78.3% vs 76%), gradually.ai, releasebot and ofox listicles; use vendor announcements for benchmark figures.

## Findings log

### R-20260922-6 · 2026-09-22 · Tooling and testing: quiet; MRCR table has no new entry for any family in models.json
- summary: Tooling: claude-hud (28.1K stars) now says it scales with the reported window including 1M sessions; still Claude Code only, no hooks-based injection, no Codex or Copilot parsers. ccstatusline, ClaudeCodeStatusLine and claude-usage-monitor are Claude-only meters. Nothing overlaps this unit's procedure. Testing: claude-code-hook-tester (0 stars) feeds hooks mock payloads and checks exit codes, JSON validity and timing, not `additionalContext` content; no published checker for context-meter hooks exists. Candidate eval cases stay as listed, plus a `gpt-6-sol` id resolving to its own family without Astra's MRCR note. llm-stats MRCR v2 (updated 2026-09-23): Muse Spark 1.3 0.985 and Qwen3.8 Max 0.929 are new near the top (neither is a family here); still no Fable 5.1, Mythos 5.1, Opus 5, Opus 5.5, Sonnet 5, GPT-6 Astra, Sol or Luna entries. No new Fiction.LiveBench or NoLiMa numbers.
- track: tooling, testing, subject
- sources: https://github.com/jarrodwatts/claude-hud, https://github.com/sirmalloc/ccstatusline, https://github.com/VoxCore84/claude-code-hook-tester, https://llm-stats.com/benchmarks/mrcr-v2-(8-needle)
- magnitude: 0.1
- applied: note only (gpt-5.6 note gains Terra and Luna scores, C-20260922-2)

### R-20260922-5 · 2026-09-22 · Practice: Codex token estimation and compaction on GPT-6; Opus 5 thinking share jumped server-side
- summary: openai/codex#45074 (Astra displayed versus internal count) is still open with no maintainer reply; PR #45094, merged 2026-09-12, estimates history tokens from content instead of serialized envelopes, the same kind of inflation. Codex 0.156.0 groups requests into context windows (#44932). Compaction on GPT-6 is reported slow (#45433, seconds to 2-3+ minutes) or hanging 20+ minutes (#43062). On the Claude side, anthropics/claude-code#93596 (open) shows from jsonl analysis that Opus 5 at xhigh went from 30-67% to 95-100% thinking share and 250-960 to about 2.5-3K output tokens per request from 2026-09-11 with no client change: per-turn growth depends on effort and on server behaviour.
- track: practice
- sources: https://github.com/openai/codex/issues/45074, https://github.com/openai/codex/pull/45094, https://github.com/openai/codex/issues/45433, https://github.com/openai/codex/issues/43062, https://github.com/anthropics/claude-code/issues/93596
- magnitude: 0.15
- applied: C-20260922-2 (models.json harnesses.codex note; Open questions)

### R-20260922-4 · 2026-09-22 · Subject: Claude Code 2.1.273-2.1.280 and Opus 5.5 caps in Copilot and Cursor
- summary: The raw changelog attributes the advisor-tool meter fix ("counting advisor-tool turns at roughly twice their real context size, which made auto-compact fire at about half the real window") to 2.1.273 (2026-09-15), not 2.1.269 as R-20260917-5 had it (the research subagent's summary said 2.1.274; both were wrong, L-010). 2.1.274 (09-17): hook-driven sessions compact instead of ending with "Prompt is too long". 2.1.280 (09-22): Opus 5.5 added as the default Opus model; an effort level saved before per-model `/effort` no longer applies to newly released models. 2.1.260 (09-03) had already made Opus and Fable sessions compact shortly before the 1M limit, consistent with window minus ~33K; nothing moves that figure. Statusline JSON unchanged (`context_window.context_window_size`, input-only `used_percentage`, `current_usage` null after /compact, plus `effort`). Copilot CLI v1.0.89-0 adds claude-opus-5.5; no cap stated by Copilot. Cursor's Opus 5.5 page says up to 1M with no long-context surcharge and gives no default cap. `CLAUDE_CODE_ENTRYPOINT=claude-vscode` re-observed in a VS Code session on 2026-09-22 (L-008).
- track: subject
- sources: https://code.claude.com/docs/en/changelog (raw .md, read 2026-09-22), https://code.claude.com/docs/en/statusline, https://github.com/github/copilot-cli/releases, https://cursor.com/docs/models/claude-opus-5-5
- magnitude: 0.15
- applied: C-20260922-2 (models.json harnesses claude, copilot and cursor notes; Current understanding compaction and harness caps; L-008 confirmed)

### R-20260922-3 · 2026-09-22 · Subject: GPT-6 Sol and GPT-6 Luna (1.05M / 922K input / 128K out) were resolving to the Astra family
- summary: OpenAI released `gpt-6-sol` and `gpt-6-luna` on 2026-09-22: 1,050,000 total, 922K input, 128K output; Sol $2/$10, Luna $0.10/$0.50, input past 272K at 2x; "trained with similar methods as GPT-6 Astra". No MRCR or other long-context score published. Codex offers both in its model picker from 0.156.1; GitHub's supported-models page lists Astra, Sol and Luna. models.json's `gpt-6*` pattern sent both to the gpt-6-astra family, so the window class was right but the label and the note (Astra's 96.3% at 1M) were wrong for them.
- track: subject
- sources: https://handyai.substack.com/p/model-drop-gpt-6-sol-and-gpt-6-luna, https://kingy.ai/blog/gpt-6-sol-luna-specs-benchmarks-pricing-comparison/, https://learn.chatgpt.com/docs/changelog, https://docs.github.com/en/copilot/reference/ai-models/supported-models (openai.com returns 403)
- magnitude: 0.35
- applied: C-20260922-2 (models.json family gpt-6-sol-luna, window set to the 922K input limit; tests family table; Current understanding windows; Open questions; Search plan)

### R-20260922-2 · 2026-09-22 · Subject: Opus 5.5 system card: no retrieval score, one agentic long-context benchmark to 1M
- summary: The 230-page system card (PDF linked from https://www.anthropic.com/claude-opus-5-5-system-card) has a "Long context" section (8.10) with one benchmark, ProgramBench (rebuild a program from its binary and docs, 166 tasks, hidden behavioural tests): Opus 5.5 91.2%, Fable 5.1 87.6%, Opus 5 85.4%, with "episodes cover a range of context lengths up to the full 1M token window". It is not broken down by context length, and there is no MRCR, GraphWalks, needle or Fiction.LiveBench figure anywhere in the card. Evaluations use windows that "do not exceed 1M tokens", mostly at max effort. HLE runs cap total tokens at 1M without compaction; multi-agent runs use compaction and a 20M budget. Token use by effort: on GDPval-AA, xhigh matches max with about 51% fewer output tokens (41% on AA-Briefcase), consistent with the docs' warning that thinking grows steeply at the top levels. Alignment notes: a specialized subagent snapshot occasionally refused to write a compaction summary (<0.01% of completions), and Anthropic says its long-trajectory audits only simulate compaction. For this unit: agentic work on Opus 5.5 holds up to 1M better than Opus 5 in aggregate, which weakly supports the relaxed reading for Claude 5.x, but without a per-length curve it cannot move the balanced fractions.
- track: subject
- sources: https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf (sections 8.1, 8.4, 8.10.1, 8.11.1, 8.12.1, 8.14.3-4; pages 102, 122, 174-210)
- magnitude: 0.2 (evidence note; no number changes)
- applied: C-20260922-2 (RESEARCH.md Current understanding, Measured long-context quality; Open questions; models.json claude-1m note)

### R-20260922-1 · 2026-09-22 · Subject: Claude Opus 5.5 released: 1M/128K, thinking always on, default effort medium, no long-context numbers
- summary: `claude-opus-5-5`, released 2026-09-22 on the Claude API, Bedrock (`anthropic.claude-opus-5-5`), Google Cloud, Microsoft Foundry and Claude Platform on AWS. 1M context, 128K output (300K on the Batch API with `output-300k-2026-03-24`), knowledge cutoff Jun 2026, $4/$20 per MTok (cache read $0.20, 5m write $5, 1h write $8; batch half; fast mode $8/$40 on the Claude API and in Claude Code). Breaking changes against Opus 5: thinking cannot be disabled (400 on `disabled` or a `budget_tokens` budget; omit `thinking` or send `adaptive`); `tool_choice` `any`/`tool` returns 400; thinking blocks are tied to the model and the conversation (Opus 5.5 reads Opus 5 and earlier blocks; only Fable 5.1 and Mythos 5.1 read Opus 5.5's; a prefix change before a block is a 400 on accounts created from 2026-08-31 unless `drop_block` is set); `computer_20251124` rejected on the Claude API and Google Cloud. Behaviour: API default effort `medium` (Opus 5 was `high`); more thinking per turn at a given effort; text between tool calls returned as thinking blocks (empty at the default `display: "omitted"`); biology classifier plus `reasoning_extraction` refusals. Supports per-message effort (beta), mid-conversation system messages, task budgets, on-demand compaction (`compact-2026-09-04`), 512-token cache minimum. Claude Code: `opus` alias and `default` model resolve to Opus 5.5 on the Anthropic API (Pro through Enterprise) and on Bedrock / Google Cloud from v2.1.280; 1M on every plan (Opus 4.7 and later); default effort `medium`, a top-level `effortLevel` does not carry over; biology-flagged requests fall back to Opus 5, cybersecurity to Opus 4.8. GitHub Copilot added it the same day (Pro+, Max, Business, Enterprise; every surface; gradual rollout; no cap or effort default stated). The launch post and docs publish no MRCR or other long-context score, so the balanced bands stay on the 4.6-generation evidence.
- track: subject
- sources: https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5, https://platform.claude.com/docs/en/models/opus-5-5/overview, https://www.anthropic.com/claude-opus-5-5, https://www.anthropic.com/news/claude-opus-5-5, https://code.claude.com/docs/en/model-config (read 2026-09-22), https://github.blog/changelog/2026-09-22-claude-opus-5-5-is-now-available-in-github-copilot/
- magnitude: 0.3 (new model inside an existing family; no number in models.json moves)
- applied: C-20260922-1 (models.json claude-1m note, harnesses claude and copilot notes; tests family table; Current understanding; Open questions)

### R-20260917-1 · 2026-09-17 · Subject: GPT-6 Astra (1M, MRCR 96.3% at 1M) is the new Codex default; GPT-5.6 at 272K
- summary: OpenAI released GPT-6 Astra 2026-09-03 (approved users) and 09-04 (GA): 1M window; MRCR v2 8-needle 100% at 256K-512K and 96.3% at 512K-1M, against GPT-5.6 Sol 91.5% / 73.8%. Codex CLI v0.153.1 added it as the recommended default with "cross-window notes" that keep earlier windows searchable instead of summarising. Secondary sources: 1,050,000 total / 922K input / 128K out, recommended auto_compact_token_limit 850000. GPT-5.6 Sol / Terra / Luna windows corrected to 272,000 (Codex changelog via secondary report; matches Cursor's 272K). models.json lacked all of them.
- track: subject
- sources: https://openai.com/index/gpt-6-astra/ (403 to fetch; figures via https://www.vellum.ai/blog/gpt-6-astra-benchmarks-explained and https://www.infoq.com/news/2026/09/openai-gpt6-astra/), https://codex.danielvaughan.com/2026/09/03/gpt-6-astra-codex-cli-configuration-context-notes-safety/, https://learn.chatgpt.com/docs/changelog, https://deploymentsafety.openai.com/gpt-6-astra
- magnitude: 0.6
- applied: C-20260917-1 (models.json families gpt-6-astra and gpt-5.6; harnesses.codex by_family)

### R-20260917-2 · 2026-09-17 · Practice: Codex compaction accounting diverges from displayed usage on Astra
- summary: openai/codex#45074 (v0.154.0, gpt-6-astra) shows a 600K configured window, effective limit 570K (95%), auto_compact_scope_limit 540K (90%), and compaction firing at an internal 623K while the UI showed ~388K. Confirms the ≤90% rule and adds that displayed and internal counts can differ by 200K+; the unit's Codex band may be optimistic on Astra.
- track: practice
- sources: https://github.com/openai/codex/issues/45074, https://github.com/openai/codex/issues/45433
- magnitude: 0.35
- applied: C-20260917-1 (SKILL.md Per-agent notes Codex row; models.json harnesses.codex note; open question added; candidate eval case noted in Search plan testing track)

### R-20260917-3 · 2026-09-17 · Subject: Gemini 3.8 Flash (1M/64K); Gemini 3.7 Flash MRCR 97% at 1M
- summary: Google model card for Gemini 3.8 Flash (2026-09-02): 1M input / 64K output, based on 3.7 Flash, intro pricing through 2026-12-31. llm-stats MRCR v2 8-needle (self-reported): Gemini 3.7 Flash 0.970, 3.6 Flash 0.540, 3.1 Pro 0.263, Opus 4.6 0.760, GPT-5.6 Sol 0.915, GPT-5.5 0.740; no entries for Fable 5.1, Mythos 5.1, Opus 5, Sonnet 5 or Astra. The Flash line is now far stronger than Pro, so Gemini bands should be re-derived per model.
- track: subject
- sources: https://deepmind.google/models/model-cards/gemini-3-8-flash/, https://ai.google.dev/gemini-api/docs/latest-model, https://llm-stats.com/benchmarks/mrcr-v2-(8-needle)
- magnitude: 0.4
- applied: C-20260917-1 (models.json gemini-1m note; Current understanding)

### R-20260917-4 · 2026-09-17 · Subject: skill listing budget is now on the primary Claude Code docs; setting names are not
- summary: code.claude.com/docs/en/skills states the listing budget "scales at 1% of the model's context window", descriptions are shortened to fit, and on overflow Claude Code "drops descriptions starting with the skills you invoke least"; `description` + `when_to_use` truncates at 1,536 characters; `disable-model-invocation: true` skills are excluded; the listing is not re-injected after /compact. The key names `skillListingBudgetFraction` / `skillListingMaxDescChars` do not appear on the settings or settings-reference pages, only in third-party guides. Resolves the VERIFY item in Selection noise.
- track: subject
- sources: https://code.claude.com/docs/en/skills, https://code.claude.com/docs/en/settings-reference, https://code.claude.com/docs/en/context-window
- magnitude: 0.3
- applied: C-20260917-1 (SKILL.md Selection noise paragraph; models.json selection.listing_note)

### R-20260917-5 · 2026-09-17 · Subject: Claude Code context-window doc gives the startup breakdown; meter bug explained early compactions
- summary: code.claude.com/docs/en/context-window (2026-09-15) itemises startup: system prompt ~4.2K, MCP tools deferred by default (names only; `ENABLE_TOOL_SEARCH=auto` loads schemas if they fit in 10% of the window), skills index (not re-injected after compact; invoked skill bodies restored capped at 5,000 tokens each), auto-memory first 200 lines / 25KB. Changelog 2.1.269 (corrected to 2.1.273 by R-20260922-4) fixed the context meter counting advisor-tool turns at ~2x, which "made auto-compact fire at about half the real window"; 2.1.273/274 fixed Remote Control context reads and Fable 1M consent messaging. Hooks page still 32 events; `model` only on SessionStart. Cowork issues #63360 / #47993 still open.
- track: subject
- sources: https://code.claude.com/docs/en/context-window, https://code.claude.com/docs/en/changelog, https://code.claude.com/docs/en/hooks, https://github.com/anthropics/claude-code/issues/63360
- magnitude: 0.3
- applied: C-20260917-1 (Current understanding: Startup context and compaction sentences; models.json harnesses.claude note)

### R-20260917-6 · 2026-09-17 · Tooling: Copilot adds Fable 5.1 and Gemini 3.8 Flash; CLI v1.0.81 hook tracing; Codex async hooks; Gemini threshold confirmed
- summary: Copilot weekly changelogs add Fable 5.1 (Pro+/Max/Business/Enterprise, admin-enabled) and Gemini 3.8 Flash; 1M window confirmed in VS Code, CLI and the Copilot app; CLI v1.0.81 (08-27) hook inputs gain `traceparent`/`tracestate`, command hooks get env vars, hook.start/hook.end per subagent session, per-agent usage metrics in JSON output files; per-model caps still rendered as icons. Codex hooks docs (now learn.chatgpt.com/docs/hooks) add `"async": true` (8 concurrent) and `"type":"mcp_tool"`, `additionalContextLimit` 2,500 tokens, project `.codex/hooks.json`. Gemini CLI config reference: `model.compressionThreshold` 0.5, `contextManagement.historyWindow.maxTokens` 150000 / `retainedTokens` 40000, `BeforeToolSelection` hook. Cursor changelog: plugin hooks run, `/max-mode` CLI toggle.
- track: tooling
- sources: https://github.blog/changelog/2026-09-04-github-copilot-weekly-releases-august-31/, https://github.com/github/copilot-cli/releases/tag/v1.0.81, https://docs.github.com/en/copilot/reference/ai-models/supported-models, https://learn.chatgpt.com/docs/hooks, https://geminicli.com/docs/reference/configuration/, https://cursor.com/changelog
- magnitude: 0.2
- applied: C-20260917-1 (note: Current understanding hook sentences; models.json copilot and gemini notes; Search plan URL change)

### R-20260917-7 · 2026-09-17 · Tooling and testing: claude-hud is the dominant context status line; no eval harness exists for this skill class
- summary: jarrodwatts/claude-hud (~27-28K stars, 101 contributors, last commit 2026-08-28) is a statusline with a context bar and per-model quota; it overlaps this unit's status line but not its hooks, multi-agent parsers or baseline audit. context-mode (scottconverse, forks) targets a different goal (context reduction). Testing track quiet: no published checker for context-meter hooks; promptfoo's "Test Agent Skills" guide suggests token-pattern assertions that could become evals.json cases (hook line format, the "roughly" qualifier).
- track: tooling, testing
- sources: https://github.com/jarrodwatts/claude-hud, https://www.promptfoo.dev/docs/guides/test-agent-skills/, https://github.com/scottconverse/context-mode
- magnitude: 0.3
- applied: C-20260917-1 (point: SKILL.md Per-agent notes Claude Code row; testing candidates listed in the Search plan testing track; this unit has no evals suite yet, see C-20260917-1)

### R-20260905-1 · 2026-09-05 · Startup context measured on two platforms; no published tolerance figures
- summary: first-turn input on the Claude Code VS Code extension (Fable 5.1, a Unity game repo: CLAUDE.md importing AGENTS.md, memory index, ~150 deferred MCP tool names, skills catalog) is ~59K = 6% of 1M; Cowork's fresh floor is ~105K (L-001). The hook process under the extension carries `CLAUDE_CODE_ENTRYPOINT=claude-vscode` (the CLI reports `cli`), which is the only cheap platform discriminator found. No primary source states a startup-size threshold per model; bands seeded by judgment from R-20260902-3.
- sources: live transcript measurement 2026-09-05 (`ctxhealth.py status`, `baseline --file`); hook process environment dump 2026-09-05; R-20260902-3
- magnitude: 0.3 (new data section and bands in models.json)
- applied: C-20260905-1

Newest first. One entry per material finding; a quiet refresh gets one entry saying so.

### R-20260902-7 · 2026-09-02 · Cross-tool skill and plugin layout
- Summary: `~/.agents/skills/<name>/SKILL.md` is read by Codex, Cursor, Gemini CLI and Copilot CLI; Claude Code reads `~/.claude/skills`. Copilot CLI plugins are a root `plugin.json` + `skills/` + optional `hooks.json`; Codex plugins bundle skills the same way. Frontmatter beyond name/description/license/metadata breaks portability. Led to the self-contained skill folder and the junction-based install.
- Sources: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills, https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-cli-plugins, https://developers.openai.com/codex/skills, https://code.claude.com/docs/en/skills, https://github.com/anthropics/skills/blob/main/spec/agent-skills-spec.md
- Magnitude: n/a (initial)
- Applied: C-20260902-1

### R-20260902-6 · 2026-09-02 · Cursor, Gemini CLI and Codex hooks and stores
- Summary: Cursor hooks (`~/.cursor/hooks.json`, version 1) send `model`, `transcript_path` and, on `preCompact`, `context_tokens` + `context_window_size`; outputs are snake_case; exit 2 blocks. Gemini hooks live in settings.json with JSON-only stdout and `hookSpecificOutput.additionalContext`; `PreCompress` is advisory; saved chats have no token counts; compression default documented 0.5. Codex hooks are Claude-shaped with `model` in stdin and `commandWindows`; rollouts carry `token_count` events with `model_context_window`; the GPT-5.5 window in Codex is capped at 400K with a fluctuating effective budget. Cursor default caps 200K-300K, Max mode 1M.
- Sources: https://cursor.com/docs/hooks, https://cursor.com/docs/context/max-mode, https://geminicli.com/docs/hooks/reference/, https://geminicli.com/docs/reference/configuration/, https://developers.openai.com/codex/hooks, https://developers.openai.com/codex/config-reference, https://github.com/openai/codex/issues/30875, https://dev.to/milkoor/reverse-engineering-codex-cli-rollout-traces-3b9b
- Magnitude: n/a (initial)
- Applied: C-20260902-1

### R-20260902-5 · 2026-09-02 · Copilot CLI and VS Code hooks, session store, caps
- Summary: Copilot CLI hooks config (`version: 1`, camelCase events, `bash`/`powershell` fields, `timeoutSec`), user-level `~/.copilot/hooks/*.json`; sessionStart and postToolUse can return `additionalContext`, userPromptSubmitted cannot; preToolUse is permission-only. Session store `~/.copilot/session-state/<id>/events.jsonl` plus `session-store.db`; usage events exist but are not a stable API (copilot-cli#3551). Auto-compact at ~80%. Copilot caps context per model (200K; 1M opt-in since 2026-06-04 in VS Code and CLI). VS Code agent hooks read `~/.claude/settings.json` (8 events, `hookSpecificOutput.additionalContext`) and VS Code now runs pluggable harnesses (Local, Copilot SDK, Claude, Codex, Cloud). `@github/copilot-sdk` exposes `assistant.usage` events programmatically.
- Sources: https://docs.github.com/en/copilot/reference/hooks-reference, https://docs.github.com/en/copilot/concepts/agents/copilot-cli/context-management, https://github.com/github/copilot-cli/issues/3551, https://github.com/ccusage/ccusage/issues/1174, https://github.com/orgs/community/discussions/186340, https://code.visualstudio.com/docs/agent-customization/hooks, https://code.visualstudio.com/docs/agents/run/agent-harnesses, https://github.com/github/copilot-sdk
- Magnitude: n/a (initial)
- Applied: C-20260902-1

### R-20260902-4 · 2026-09-02 · Claude Code hooks, statusline, transcript, compaction, plugins
- Summary: 32 hook events; stdin fields; only SessionStart may include `model` (resume also gives `context_tokens`); plain stdout or `hookSpecificOutput.additionalContext` injects on UserPromptSubmit/SessionStart; `systemMessage` shows the user; 10,000-char cap; UserPromptSubmit timeout default 30 s. Windows shell form runs via Git Bash, else PowerShell; exec form (`args`) needs a real .exe. statusLine JSON: `model.id`, `context_window.context_window_size` (raw window), `current_usage`. Transcript shape confirmed on a live Cowork file (usage fields, `message.model`, subagents in `subagents/agent-*.jsonl`, `isSidechain`). Auto-compact: window minus a reserve (Sonnet 5 ~967K), `CLAUDE_CODE_AUTO_COMPACT_WINDOW` / `/autocompact`; 1M default for Fable 5.1, Opus 5, Sonnet 5, Opus 4.7+; `CLAUDE_CODE_DISABLE_1M_CONTEXT`. Plugins cannot ship a statusLine; local install via `--plugin-dir` or a local marketplace. Cowork does not fire hooks (issues #63360, #47993).
- Sources: https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/statusline, https://code.claude.com/docs/en/model-config, https://code.claude.com/docs/en/plugins-reference, https://code.claude.com/docs/en/skills, https://github.com/anthropics/claude-code/issues/63360, https://github.com/anthropics/claude-code/issues/47993, https://github.com/neilberkman/ccrider/blob/main/research/schema.md
- Magnitude: n/a (initial)
- Applied: C-20260902-1

### R-20260902-3 · 2026-09-02 · Long-context degradation evidence
- Summary: Context Rot (gradient at every length, distractors worsen it); Anthropic "gradient not cliff"; Opus 4.6 MRCR 93%@256K / 76%@1M; GPT-5.5 MRCR 90/83/74% by band; Gemini 3 Pro 77%@128K, 24-26%@1M; Sonnet 4.5 18.5%@1M; Verdent field reports (onset ~400K, unreliable >600K on Sonnet 4.6); counter-anecdote of Opus 5 productive to 687K and Sonnet 5 auto-compact at 96.7%. No numbers yet for the 5.x Claude models. Produced the three band profiles.
- Sources: https://research.trychroma.com/context-rot, https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents, https://www.verdent.ai/guides/claude-code-1m-context-window, https://www.digitalapplied.com/blog/gpt-5-5-complete-guide-thinking-pro-1m-context, https://github.com/BaseInfinity/claude-sdlc-harness/issues/483, https://arxiv.org/pdf/2502.05167
- Magnitude: n/a (initial)
- Applied: C-20260902-1

### R-20260902-2 · 2026-09-02 · Model windows, September 2026
- Summary: Claude 5.x family and Opus 4.6+ at 1M/128K; Haiku 4.5 and Sonnet 4.5 at 200K; GPT-5.5 ~1.05M (Codex cap 400K), GPT-5.4 256K, GPT-5.x/Codex 400K; Gemini 3.x 1,048,576/65,536; Grok Code Fast 256K, Grok 4.5 500K; Copilot 1M only in VS Code and CLI.
- Sources: https://platform.claude.com/docs/en/models/overview, https://platform.claude.com/docs/en/build-with-claude/context-windows, https://openai.com/index/introducing-gpt-5-5/, https://deepmind.google/models/model-cards/gemini-3-7-flash/, https://ai.google.dev/gemini-api/docs/gemini-3, https://docs.github.com/en/enterprise-cloud@latest/copilot/reference/ai-models/supported-models, https://github.blog/changelog/2026-07-28-grok-4-5-is-now-available-in-github-copilot/
- Magnitude: n/a (initial)
- Applied: C-20260902-1

### R-20260902-1 · 2026-09-02 · Predecessor state carried forward
- Summary: The 2026-08-29 `context-health` skill and its state file (a private notes file on the development machine) established: bands for 1M Claude models at 100K/200K/400K/600K (now the `conservative` profile), 200K-model bands at 60/100/140/160K, the ~2%/100K heuristic (unverified against a primary source), the Cowork 105K base-context floor, the fact that Cowork runs no hooks, and the \\?\ long-path requirement on Windows.
- Sources: the retired state file; https://research.trychroma.com/context-rot; the 2026-08-29 hook tests
- Magnitude: n/a (initial)
- Applied: C-20260902-1

## Selection noise (skills/tool catalog size)

Seeded 2026-09-06. Distinct from startup SIZE: the cost is selection accuracy, not tokens.

- Chance-corrected tool retrieval, arXiv 2605.24660 ("How Many Tools Should an LLM Agent See?"): standard
  retrievers do notably worse on tool retrieval than document retrieval; the dominant difficulty is
  semantically near-duplicate entries (`calc_area_triangle` vs `calculate_triangle_area`), not raw count.
  Fixed shortlist K=5 suffices under ~200 tools; 200-1,000 needs adaptive depth; degradation accelerates past
  ~500 and is substantial past ~1,000.
- Survey figures in circulation (2026): ~50 tools 84-95% selection accuracy; ~200 tools 41-83%; ~740 tools
  0-20%. Position bias: middle-of-list entries 22-52% vs 31-32% at the ends. Treat as order-of-magnitude.
- Practitioner reports put the onset of description overlap around 30 entries; Anthropic's skills playbook
  draws its line at 8-12 skills.
- Claude Code mechanism (v2.1.129+): `skillListingBudgetFraction` (default 0.01) and
  `skillListingMaxDescChars` (default 1536). Over budget, whole descriptions for least-invoked skills are
  dropped, not truncated evenly - so rare skills become invisible. VERIFY against Anthropic docs on the next
  refresh; currently sourced from a third-party guide (claudefa.st), not primary.
- Bands chosen: notable 25 / high 40 / excessive 60 visible skills. These are judgment calls anchored on the
  30-entry overlap onset and the ~50-tool accuracy shoulder; skills are coarser and more distinct than API
  tools, so the bands sit above the 8-12 playbook figure.

Search plan on refresh: primary Anthropic docs for the two listing settings; new function-calling benchmarks
with catalog-size sweeps (BFCL, ToolBench, LongFuncEval); any published per-model tool-count guidance.

Sources: https://arxiv.org/html/2605.24660v1 ; https://claudefa.st/blog/guide/mechanics/skill-listing-budget ;
https://www.mindstudio.ai/blog/how-to-fix-claude-code-skills-prompts

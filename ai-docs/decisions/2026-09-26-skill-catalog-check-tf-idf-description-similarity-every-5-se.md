---
title: "Skill catalog check: TF-IDF description similarity every 5 sessions"
kind: decision
status: active
date: 2026-09-26
verified: 2026-09-26
stale_after: 2027-03-25
tags: [selection, skills, research, hook]
summary: read before changing how selection noise is scored or when the hook runs the skill catalog check
---

# Skill catalog check: TF-IDF description similarity every 5 sessions

## Context

The skill catalog check (`ctxhealth.py selection`) only ran inside a baseline audit that also warned, missed plugins installed under `~/.claude/plugins/cache`, and compared names only. The user asked for a lightweight check every few sessions, based on the latest research.

## Decision

- The hook scans the running agent's catalog in the first session and every `selection.check_every` sessions (default 5). It stays silent unless something is found, and does not repeat the same findings within `selection.warn_days` (7).
- Similarity is TF-IDF cosine (smoothed IDF over the installed catalog) between descriptions with every skill and plugin name word removed. Sibling pairs are kept. 0.45 means possibly confusable, 0.65 near-duplicate.
- Also reported: normalised-name clashes, descriptions over 1,024 characters (spec) and over 1,536 (Claude Code cut), and descriptions of 40 characters or fewer.
- Count bands stay at 25 / 40 / 60, re-anchored on the arXiv 2601.04748 curve.

## Reasons

- The 2026 work (2601.04748, 2605.24050, 2606.10388) finds overlap and shadowing, not raw count or context size, drive wrong and missed picks, so overlap is reported whatever the count.
- Stdlib only (the script's rule): embeddings are out. TF-IDF beats Jaccard because IDF discounts words many skills share.
- Name words are labels. With them left in, a family such as `acme-cli` / `acme-mcp` scored 0.6-0.7 on one real catalog, and only 3 pairs passed 0.45 without them.
- Siblings stay in because same-family siblings are the documented risk (2606.10388).
- Smoothed IDF: plain `log((1+n)/(1+df))` gives shared words zero weight in a two-skill catalog, so two identical skills scored 0 (caught by a test).

## Rejected

- Word Jaccard (the first draft): no IDF, so boilerplate dominates.
- Excluding same-stem pairs: contradicts 2606.10388.
- Embedding models: need a dependency and a network or model call from a hook.

## Open

No study validates a lexical proxy against model confusion; the 0.45 / 0.65 thresholds are uncalibrated (volatile claim in evergreen.json). Calibrate if a study appears, or against pairs a user reports as confused.

Related: [INDEX.md](../INDEX.md)

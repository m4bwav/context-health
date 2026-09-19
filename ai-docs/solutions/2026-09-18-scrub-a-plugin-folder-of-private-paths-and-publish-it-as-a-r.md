---
title: Scrub a plugin folder of private paths and publish it as a repo
kind: solution
status: active
date: 2026-09-18
verified: 2026-09-18
tags: [privacy, scrub, release, workflow, evergreen]
summary: read before publishing any plugin or skill folder that grew on one machine; the lens list and the install footgun
---

# Scrub a plugin folder of private paths and publish it as a repo

## Problem
A plugin folder that grew on one machine carries that machine in its text: absolute paths in `evergreen.json` and SKILL.md, machine nicknames in LEARNINGS.md, a private repository name and project skill names in RESEARCH.md and LEARNINGS.md, a reference to a private profile file, a first-name possessive in `models.json`, and an AI credit in the README byline. A grep for the obvious markers finds the paths but not the nicknames or the project names.

## Dead ends
- Grep alone (the username, the drive-rooted home path, the LAN prefix, names): found 4 of the 12 strings. The machine nicknames, the private repo name, the four project skill names and the possessive only surfaced from readers going through every file with a lens.
- Leaving `install` as it was: it rewrote `evergreen.json.source` with the local absolute path on every run, so the tracked file would have been dirty with a private path in every clone the moment someone installed.

## Fix
1. Five readers with distinct lenses (paths and machines; people and identity; environment and working life; private projects and codenames; secrets and data) each read all 15 text files and returned findings with a verbatim snippet and a proposed replacement; dedup by file and snippet; two agents per finding, one trying to refute "this is private", one confirming the snippet exists verbatim and writing the drop-in replacement. 38 raw findings, 26 distinct, 0 refuted, collapsing to 12 edits (overlapping substrings of the same lines).
2. Applied with a Python script that asserts each snippet occurs exactly once before writing anything (Bash heredocs on this machine halve backslashes, so path-bearing edits never go through a heredoc). Generalised rather than deleted: "the development machine", "a Unity game repo", "four project-scoped skills", "the user-level environment notes"; every R-, L- and C- id kept.
3. `cmd_install` no longer writes `evergreen.json.source`; the test expects the unit state untouched; MAINTENANCE.md "Installed copies" points at the clone and `doctor`.
4. Scaffold in the sibling shape: AGENTS.md, CLAUDE.md, `.github/copilot-instructions.md`, `tests.yml` (3 OS x Python 3.9 and 3.13, plus `version`, `models --model`, `install --dry-run` from a clean checkout), `release.yml` (tag must equal the manifest version; tests; `pack --out dist`; `gh release create`), `marketplace.json`, `.gitignore`, `ai-docs/` via `everlast.py init` and `project register`.
5. `git init`, one commit of the scrubbed tree, `gh repo create m4bwav/context-health --source . --push`, tag `v1.3.0` for the release workflow.

## Verified by
a grep over the tree for every removed string (the username, the home path, the sandbox mount name, the machine nicknames, the private repo and skill names, the profile file name, the AI credit in the byline; the list itself lives in the owner's private vault, not here) returns nothing; `python tests/test_ctxhealth.py` 42 OK; `ctxhealth.py pack --out <tmp>` lists only the plugin files (no `.github`, `ai-docs`, `dist`); `git log --stat` shows a single commit; hooks still fire from the same folder after the commit (2026-09-18).

Related: [the publication decision](../decisions/2026-09-18-publish-context-health-as-a-public-repository-in-the-sibling.md); [ai-docs index](../INDEX.md).

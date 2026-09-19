---
title: Publish context-health as a public repository in the sibling-plugin shape
kind: decision
status: active
date: 2026-09-18
verified: 2026-09-18
tags: [release, repo, privacy, pattern]
summary: read before changing the repo layout or release workflow, or when deciding where a plugin should live
---

# Publish context-health as a public repository in the sibling-plugin shape

## Context

The plugin had lived only as a folder and as emailed zips since 2026-09-02; the sibling plugins are public repositories.

## Decision
context-health is published as its own repository, github.com/m4bwav/context-health, in the same shape as chartwright, obsidian-notes, evergreen-protocol and everlast: MIT, author credit only, `AGENTS.md` as the source of truth with `CLAUDE.md` and `.github/copilot-instructions.md` pointing at it, `.claude-plugin/plugin.json` plus `marketplace.json`, a test workflow on Windows, macOS and Linux, a release workflow on `vX.Y.Z` tags that runs `ctxhealth.py pack`, an `ai-docs/` doc set, and a single scrubbed first commit.

## Reasons
Until 2026-09-18 the plugin lived only as a folder and as emailed zips (`context-health-1.x.zip`), so reusing it on another machine meant mailing a file and installing by hand, and every zip carried the owner's absolute paths in `evergreen.json` and SKILL.md. A repository makes `git clone` plus `ctxhealth.py install --agent all` the whole install, keeps `git pull` as the update path, and lets the evergreen refreshes land as commits instead of new zips.

## Alternatives rejected
- Adding it to a local directory marketplace instead: the plugin form cannot set the status line and would double-fire the hooks that `install` already wrote, which the README warns against. The repository can still be added as a marketplace by people who want only the hook and skill.
- Keeping `install` writing the clone's absolute path into `evergreen.json.source`: that dirties a tracked file with a private path in every clone, and a routine `git add -A` or the everlast sync would commit it. `source` is `null` in the repository and `doctor` prints the path instead.
- Keeping history: the folder had no git history, so the first commit is the scrubbed tree.

## Consequences
The local folder stays where it was (the installed hooks and skill junctions point at it), now as a clone whose `origin` is the repository. Environment facts that were in LEARNINGS.md and RESEARCH.md (which machine had which tool, a private project name, four project skill names) were generalised in the repository and belong in the owner's private vault. Versions were aligned at 1.3.0; the release workflow refuses a tag that does not match `.claude-plugin/plugin.json`.

Related: [the scrub and publication procedure](../solutions/2026-09-18-scrub-a-plugin-folder-of-private-paths-and-publish-it-as-a-r.md); [ai-docs index](../INDEX.md).

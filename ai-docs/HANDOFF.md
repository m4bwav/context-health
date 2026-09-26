# Handoff

## Current state
Plugin `context-health` 1.3.2 (latest release tag v1.3.2) is a git repository at https://github.com/m4bwav/context-health (MIT, CI on three operating systems for Python 3.9 and 3.13, release on `vX.Y.Z` tags; since 2026-09-26 the workflows use actions/checkout@v7 and setup-python@v7 on Node 24, and Linux jobs run on ubuntu-26.04 except Python 3.9 on ubuntu-24.04, which has no 3.9 build for 26.04), published 2026-09-18 from a single scrubbed commit after a 57-agent privacy review (five lenses, a refuter and a replacement author per finding; 12 distinct edits, none refuted). The suite (43 tests) passes; `pack` excludes `.github`, `ai-docs` and `dist`; `install` no longer writes the clone path into `evergreen.json`. The local clone is the installed copy (hooks, status line and skill junctions point at it).

## In progress
Nothing open. The evergreen unit still has no TESTS.md / evals suite (noted in C-20260917-1); the research refresh was done 2026-09-26 (C-20260926-1) and is next due 2026-09-29. The release workflow's v7/ubuntu-26.04 changes have not run yet; watch the first run at the next tag.

## Decisions made this session
See [INDEX.md](INDEX.md): publish in the sibling-plugin shape; `evergreen.json.source` stays `null` in the repository; the plugin form is documented but `install` remains the recommended route.

## Next single action
Add the evals suite with `evergreen-test` before the next refresh (due 2026-09-29). CI is green on all six jobs with no deprecation warnings (run 36267921519); the repository was made public on 2026-09-26 after a re-scan of every commit (files and messages) for the scrubbed private strings found nothing.

## Gotchas
Path-bearing edits on this machine go through a Python script file, never a Bash heredoc (backslashes are halved). `everlast.py note` needs `## Context` and `## Reasons` headings in a decision body and truncates slugs at about 60 characters: check the printed filename before writing a `Related:` link to it.

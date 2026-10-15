---
type: Project Overview
title: Close the Gap
description: Knowledge base for the Close the Gap app, organized in the Open Knowledge Format.
resource: README.md
tags: [overview, navigation]
timestamp: 2026-10-15T00:00:00Z
---

# Close the Gap

Close the Gap finds meetings affected when someone is out of office and recommends one action per
meeting: continue without the person, continue with a briefed proxy, or reschedule. Built for the
Google Cloud AI Builder Cup 2026.

Two parts: a FastAPI backend ([backend/](../backend/)) and a React + Vite web app ([web/](../web/)).
The quick command reference lives in [CLAUDE.md](../CLAUDE.md#commands); [setup.md](setup.md) in
this folder is the fuller walkthrough with the *why* and troubleshooting attached. The rest of this
knowledge base is about *what the system is and why it's shaped this way*.

## Map

- [Setup](setup.md) — getting the backend and web app running locally, including optional live
  Gemini.
- [Architecture](architecture/index.md) — how the backend and frontend are layered, and how a
  recommendation gets made (rules vs. Gemini, the privacy rule, the item lifecycle).
- [Concepts](concepts/index.md) — the domain vocabulary: meeting kinds, actions, item status, and
  the product rules that are hardcoded on purpose.
- [Configuration](config/index.md) — what's tunable in `config/settings.toml` vs. the `.env`
  environment, and what each setting does.
- [API](api/index.md) — endpoint reference (the live, authoritative version is always
  `/docs` on the running server).
- [Data](data/index.md) — the seeded demo world: people, personas, absences.
- [log.md](log.md) — chronological history of this knowledge base itself.

## Format

This is an [Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
bundle: plain markdown files with a small YAML frontmatter block, organized as a directory tree, and
linked to each other with normal markdown links. No special tools are needed to read or edit it —
any editor or `git grep` works. Each concept document's `resource` field in its frontmatter points
back to the source file it describes, so you can jump straight to the code.

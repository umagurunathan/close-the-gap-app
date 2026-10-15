---
type: Section Index
title: Configuration
description: Navigation hub for config/settings.toml (tunables) vs. .env (environment).
tags: [config, navigation]
timestamp: 2026-10-15T00:00:00Z
---

# Configuration

- [settings.md](settings.md) — everything in `config/settings.toml`: tunable numbers and word
  lists, organized into WIRED (already read by the app) and RESERVED (agreed, not yet built).
- [env.md](env.md) — everything read from `.env` / the process environment: store backend,
  seed path, CORS origins, the fixed demo clock, the GCP project.

See also: [Concepts → Product rules](../concepts/product-rules.md) for what is deliberately kept
*out* of configuration.

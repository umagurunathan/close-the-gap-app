---
okf_version: "0.1"
---

# Close the Gap: knowledge base

**Close the Gap** finds the meetings affected when someone is out of office, early, and recommends one action per meeting:
- go on without them,
- go on with a briefed proxy, or
- reschedule.

**The AI proposes; a person decides.** It was built for the Google Cloud AI Builder Cup 2026, with a FastAPI backend (`backend/`) and a React + Vite web app (`web/`).

This directory is an **[Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) (OKF v0.1) bundle**:
- **one concept per markdown file**, with YAML frontmatter (`type`, `title`, `description`, `resource`, `tags`, `sources`, `generated`);
- linked with ordinary relative markdown links;
- an `index.md` in every directory, and the change history in [log.md](log.md).

It is written for both humans and AI agents. It was generated from the code at commit `0a944b6` and has not yet been human-verified.

## Where to start

**Humans (judges, new developers):**
1. [Product overview](overview/product.md)
2. [Demo personas](data/demo-personas.md)
3. [System overview](architecture/system-overview.md)
4. [Recommendation pipeline](architecture/recommendation-pipeline.md)
5. [Local setup](operations/local-setup.md)

**AI agents changing code:**
1. [Product rules](concepts/product-rules.md): invariants you must not break
2. [Backend layers](architecture/backend-layers.md): the module map
3. [Privacy rule](architecture/privacy-rule.md)
4. [Meeting card](concepts/meeting-card.md): statuses and lifecycle
5. [Decide on a card](flows/decide-on-a-card.md)
6. [Testing and CI](operations/testing-and-ci.md)
7. [Known quirks](operations/known-quirks.md)

## Sections

- [overview/](overview/index.md): what the product is, the glossary, and its limits
- [concepts/](concepts/index.md): the domain: absences, cards, kinds, actions, proxies, permissions, product rules
- [architecture/](architecture/index.md): how it is built: backend, AI pipeline, guard, privacy, storage, auth, integrations, web app
- [flows/](flows/index.md): step-by-step flows through the code
- [config/](config/index.md): `settings.toml` and environment variables
- [api/](api/index.md): HTTP endpoints and data models
- [data/](data/index.md): the demo world and its personas
- [operations/](operations/index.md): run, deploy, schedule, test, quirks

## Source layout (outside this bundle)

```
backend/   FastAPI app (app/), AI agents (agents/), settings (config/settings.toml), demo seed (seed/seed.json), tests/
web/       React app: Attendee Mode, Organizer Mode, Proxy Requests, Past
README.md  The project README (pitch, try-it, architecture, security, limits)
```

# Architecture

## System
- [System overview](system-overview.md): Firebase Hosting, Cloud Run, Firestore, Vertex AI, Calendar, Secret Manager
- [Backend layers and module map](backend-layers.md): main.py, then Service, then agents and adapters; every module's job

## AI
- [Recommendation pipeline](recommendation-pipeline.md): ADK agent, then single call, then rules; engines
- [ADK meeting advisor agent](adk-advisor.md): three read-only tools bound to one meeting and one viewer
- [Guard (layer C)](guard.md): twelve plain-code checks on every AI answer
- [Prompt-injection defence](prompt-injection-defence.md): typed text is data, never instructions
- [Privacy rule](privacy-rule.md): per-viewer summaries, everywhere
- [Analysis cache and background analysis](analysis-cache.md): pages never wait for the AI
- [Rule-based fallback](rule-based-fallback.md): keyword rules for AI-off and "what rules would have said"

## Backend services
- [Reschedule search](reschedule-search.md): deterministic slot search; Google first
- [Storage](storage.md): Store and calendar adapters, Firestore layout, per-request read cache
- [Authentication, identity and rate limits](auth-and-access.md): Firebase, demo guests, OIDC, limits
- [Google Calendar integration](google-integrations.md): OAuth, sync, write-back
- [Notifications, history and reminders](notifications-and-reminders.md): every email, the outbox, the reminder job
- [Impact metrics and projection](metrics.md): the impact band's formulas

## Web app
- [Web app architecture](frontend-architecture.md): entry chain, api.js, identities, loading and polling
- [Web app UI](frontend-ui.md): tabs, cards, panels, AI display, accessibility

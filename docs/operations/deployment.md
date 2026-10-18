---
type: Runbook
title: Deploy (Cloud Run and Firebase Hosting)
description: How the backend is deployed to Cloud Run (flags, env vars, secrets, IAM, the --set-env-vars trap) and the web app to Firebase Hosting (build, headers, caching).
resource: ../../backend/README.md
tags: [deployment, cloud-run, firebase-hosting, secret-manager, runbook]
sources:
  - resource: ../../backend/README.md
  - resource: ../../README.md
  - resource: ../../backend/Dockerfile
  - resource: ../../backend/.gcloudignore
  - resource: ../../web/firebase.json
  - resource: ../../web/.firebaserc
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Deploy

## Backend → Cloud Run (from `backend/`)

```powershell
gcloud run deploy close-the-gap-api --source . --region asia-south1 --allow-unauthenticated `
  --min-instances 1 --max-instances 1 --concurrency 20 --no-cpu-throttling `
  --set-env-vars "GOOGLE_CLOUD_PROJECT=<project>,AI_ENABLED=true,STORE=firestore,FIRESTORE_PROJECT_ID=<firestore-project>,FIRESTORE_DATABASE=<database>,FIRESTORE_WORKSPACE_ID=company,FIRESTORE_DEMO_WORKSPACE_ID=guest,FIREBASE_AUTH_ENABLED=true,FIREBASE_PROJECT_ID=<firebase-project>,GOOGLE_CALENDAR_ENABLED=true,GOOGLE_CALENDAR_REDIRECT_URI=https://<cloud-run-url>/integrations/google-calendar/callback,WEB_APP_URL=<web-app-url>,CORS_ORIGINS=<web-app-url>" `
  --set-secrets "COMPANY_DIRECTORY=company-directory:latest,GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest,GOOGLE_TOKEN_ENCRYPTION_KEY=google-token-encryption-key:latest"
```

- `--source .` builds the `Dockerfile` in the cloud: `python:3.13-slim` running `uvicorn app.main:app` on `$PORT` (8080). `.gcloudignore` keeps `.venv`, `.env`, caches, `tests/` and `scripts/` out.
- **Why one instance with the CPU always on** (`--min/--max-instances 1`, `--no-cpu-throttling`):
  - background AI analysis keeps running between requests;
  - the AI answer cache, the demo email outbox and the rate-limit counters live in that instance's memory.
- **Concurrency 20** works because of the per-request Firestore read cache.
- **Use `--set-env-vars` only on the first deploy.** It replaces the whole list, so any setting it does not name disappears, and the site becomes unreachable. Afterwards use **`--update-env-vars`**, which changes only the named ones. A later redeploy keeps every setting it does not name.
- **Safety net:** on Cloud Run the backend refuses to start unless `STORE=firestore`. A wiped variable list therefore fails the new revision while the last good one keeps serving.
- `NOW` is ignored on Cloud Run. The live demo always runs on the real clock.

### Service account roles

| Role | Why |
|---|---|
| `roles/aiplatform.user` | Gemini on Vertex AI |
| `roles/datastore.user` (in the database's project) | Firestore |
| `roles/secretmanager.secretAccessor` (on the secrets) | Directory, OAuth client, Fernet key |

Keep secret values in **Secret Manager** versions, never in deployment arguments, source control or the web app.

### Firebase and Google setup

- Firebase Authentication: enable the **Google** sign-in method, and add the Hosting domain to the authorised domains.
- A Google OAuth **web** client with the Calendar callback (and the Meet callback, if used) as redirect URIs.
- The Google sign-in app is not yet verified by Google, so first-time users see an "unverified app" notice.

## Web app → Firebase Hosting (from `web/`)

1. Put the backend URL and the Firebase web settings in `web/.env.production` (git-ignored): `VITE_API_URL`, `VITE_FIREBASE_AUTH_ENABLED=true`, `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID`.
2. Run `npm run build`, which writes to `dist/`.
3. Run `firebase deploy --only hosting`. The project is `close-the-gap-2026` (`.firebaserc`).

`web/firebase.json`:
- **SPA rewrite**: `**` goes to `/index.html`.
- **Security headers** on every path: `X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
- **Caching**: `index.html` is `no-cache`; `/assets/**` is `public, max-age=31536000, immutable`.

## After deploying

- `GET https://<cloud-run-url>/health` should report `"store": "FirestoreStore"`.
- Load the web app as a guest. If the demo area is empty, click **Reset demo data**, because a Firestore startup writes nothing.
- Set up the hourly [reminder job](reminder-job.md).

## Related
- [System overview](../architecture/system-overview.md)
- [Environment variables](../config/environment-variables.md)
- [Reminder job](reminder-job.md)

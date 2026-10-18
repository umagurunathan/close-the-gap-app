---
type: Runbook
title: Reminder job (Cloud Scheduler with OIDC)
description: Set up, test and troubleshoot the hourly Cloud Scheduler call to POST /jobs/run-reminders, which only accepts a Google-signed token for the scheduler service account.
resource: ../../backend/README.md
tags: [cloud-scheduler, oidc, reminders, runbook, security]
sources:
  - resource: ../../backend/README.md
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/tests/test_run_reminders_auth.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Reminder job (Cloud Scheduler with OIDC)

`POST /jobs/run-reminders` sends:
- the proxy reminders;
- the milestone digests (7 days, 3 days, 24, 4 and 2 hours before an undecided key meeting);
- the under-24-hour organizer alert;
- the invitee alert, 1–2 hours before a meeting whose organizer and another key person are both out.

See [Notifications and reminders](../architecture/notifications-and-reminders.md) for what it sends. It runs **for the company area only**.

The endpoint is public on the network, because the web app needs the service public. But it **refuses every call that does not carry a Google-signed OIDC token for the scheduler service account**:
- the token's signature, its audience (this exact URL) and the caller's email are all checked;
- no shared secret is stored anywhere;
- if either setting is missing, every call is refused.

## Setup

Run in PowerShell, replacing the placeholders.

```powershell
gcloud services enable cloudscheduler.googleapis.com iamcredentials.googleapis.com --project <project>
gcloud iam service-accounts create reminder-scheduler --display-name "Reminder scheduler" --project <project>

# your user can impersonate it for local tests; the Scheduler service agent can mint its tokens
gcloud iam service-accounts add-iam-policy-binding reminder-scheduler@<project>.iam.gserviceaccount.com `
  --member "user:<your-email>" --role roles/iam.serviceAccountTokenCreator --project <project>
gcloud iam service-accounts add-iam-policy-binding reminder-scheduler@<project>.iam.gserviceaccount.com `
  --member "serviceAccount:service-<project-number>@gcp-sa-cloudscheduler.iam.gserviceaccount.com" `
  --role roles/iam.serviceAccountTokenCreator --project <project>

# after the first deploy, the service URL is the audience; ADD these two with --update-env-vars
gcloud run services update close-the-gap-api --region asia-south1 `
  --update-env-vars "RUN_REMINDERS_AUDIENCE=https://<cloud-run-url>/jobs/run-reminders,REMINDERS_SCHEDULER_SA=reminder-scheduler@<project>.iam.gserviceaccount.com"

# hourly job
gcloud scheduler jobs create http close-the-gap-reminders --location asia-south1 --schedule "0 * * * *" --time-zone "Asia/Kolkata" `
  --uri https://<cloud-run-url>/jobs/run-reminders --http-method POST `
  --oidc-service-account-email reminder-scheduler@<project>.iam.gserviceaccount.com `
  --oidc-token-audience https://<cloud-run-url>/jobs/run-reminders
```

Use `--update-env-vars`, not `--set-env-vars`, which would delete every other setting. See [Deployment](deployment.md).

## Test locally

Run the backend with `RUN_REMINDERS_AUDIENCE=http://localhost:8000/jobs/run-reminders` and `REMINDERS_SCHEDULER_SA` set. Your user needs the `serviceAccountTokenCreator` binding above.

```powershell
$TOKEN = gcloud auth print-identity-token --impersonate-service-account=reminder-scheduler@<project>.iam.gserviceaccount.com `
  --audiences=http://localhost:8000/jobs/run-reminders --include-email
curl.exe -X POST http://localhost:8000/jobs/run-reminders -H "Authorization: Bearer $TOKEN"
```

| Call | Expected |
|---|---|
| With the scheduler's token | 200 `{"reminders_sent": n}` |
| Without a token | 401 |
| With your own user's token | 403 |
| With the settings unset | 403 (fails closed) |

## Test in the cloud

```powershell
gcloud scheduler jobs run close-the-gap-reminders --location asia-south1
gcloud run services logs read close-the-gap-api --region asia-south1 --limit 50
```

## Notes

- The job is idempotent enough to run more often than hourly:
  - each run sends at most one reminder per pending request, up to 3 in total;
  - the organizer alert is sent once per meeting (`organizerAlerted`);
  - each milestone once per card (`milestonesSent`), never backfilled;
  - the invitee alert once per meeting (`inviteesAlerted`).
- If the Cloud Run URL changes, update both `RUN_REMINDERS_AUDIENCE` and the job's `--oidc-token-audience` and `--uri`.
- The automated tests are `tests/test_run_reminders_auth.py` (12 tests). They cover missing, invalid and wrong-account tokens, an unverified email, case-insensitive email matching, an unreachable Google returning 401 rather than 500, company area only, and the Firebase middleware letting the call through.

## Related
- [Auth and access](../architecture/auth-and-access.md)
- [Notifications and reminders](../architecture/notifications-and-reminders.md)

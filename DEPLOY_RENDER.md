# Deploy Backend to Render (Phone Works Without PC)

This will host your Flask backend online so your Android app works anytime.

## 1) Push project to GitHub

Make sure `Project 2 web app` is in a GitHub repo.

## 2) Create Render Web Service

1. Go to https://render.com and sign in.
2. New -> Web Service.
3. Connect your GitHub repo.
4. Set:
   - Runtime: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Root Directory: `Project 2 web app` (if repo has parent folders)

## 3) Add PostgreSQL in Render

1. New -> PostgreSQL
2. Create DB
3. Copy Internal Database URL

## 4) Environment Variables (Render Web Service)

Set these in Render service environment:

- `SECRET_KEY` = strong random string
- `DATABASE_URL` = PostgreSQL URL from Render
- `GOOGLE_CLIENT_ID` = your Google OAuth client id
- `GOOGLE_CLIENT_SECRET` = your Google OAuth secret
- `MCP_SERVER_URL` = your MCP server URL (optional for now)
- `MCP_TIMEOUT_SECONDS` = `10`
- `MCP_MAX_TOOL_CALLS` = `3`
- `MCP_TOOL_ALLOWLIST` = `transcript_lookup,degree_audit_hint`
- `MODEL_API_KEY` = optional
- `MODEL_NAME` = `mock-model` (or real model name)
- `LOG_LEVEL` = `INFO`

## 5) Update Google OAuth Redirect URI

In Google Cloud Console, add redirect URI:

`https://YOUR-RENDER-SERVICE.onrender.com/auth/callback`

Keep localhost callback too for local testing.

## 6) Deploy

Render will build and deploy automatically.

Test:

- `https://YOUR-RENDER-SERVICE.onrender.com/api/health`

## 7) Point Android App to Online Backend

In `mobile-android-app/app/build.gradle.kts` set:

```kotlin
buildConfigField("String", "BASE_URL", "\"https://YOUR-RENDER-SERVICE.onrender.com\"")
```

Sync Gradle, rebuild APK, install on phone.

Now app works without your PC running.

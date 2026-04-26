# Android + Backend Google Auth Setup

This guide enables secure hybrid mode:

- Offline mode works without backend
- Online mode uses Google Sign-In on Android + backend-issued mobile token

## 1) Google Cloud OAuth Setup

Create OAuth credentials for **Web application** in Google Cloud and copy:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

In OAuth authorized redirect URIs include at least:

- `http://127.0.0.1:5000/auth/callback`

Use NSU account domain policy in app logic (already enforced on backend).

## 2) Backend Environment

In `Project 2 web app/.env` set:

```env
SECRET_KEY=replace-with-strong-secret
GOOGLE_CLIENT_ID=your_web_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_web_client_secret
MOBILE_TOKEN_SECRET=replace-with-strong-random-secret
MOBILE_TOKEN_MAX_AGE_SECONDS=2592000
```

Then run backend:

```powershell
python app.py
```

## 3) Android Environment

In `Project 2 web app/mobile-android-app/gradle.properties` set:

```properties
GOOGLE_WEB_CLIENT_ID=your_web_client_id.apps.googleusercontent.com
```

For emulator, default base URL already works:

- `http://10.0.2.2:5000`

For real phone, update `BASE_URL` in `app/build.gradle.kts` to your PC LAN IP.

## 4) Build & Run

```powershell
cd "D:\CSE 226\Project 2 web app\mobile-android-app"
.\gradlew.bat :app:assembleDebug
```

Install/run app on emulator or device.

## 5) In-App Verification

1. Home -> set mode to **Online**
2. Tap **Sign in with Google**
3. Use `@northsouth.edu` account
4. Verify signed-in label appears
5. Test online Analyze, History, and Chat

## 6) API Notes

Mobile app now uses:

- `POST /api/mobile/auth/google` (exchange Google id_token for app token)
- `GET /api/mobile/auth/me` (validate session)
- `Authorization: Bearer <access_token>` for `/api/mobile/*` and `/api/ai/chat`

Without token, mobile online endpoints return `401 Unauthorized`.

# NSU Transcript Mobile (Hybrid: Offline + Online)

This Android app supports two modes:

- **Offline mode**: local analysis engine + local history (no backend needed)
- **Online mode**: uses Flask backend APIs and MCP chat for parity features

Online mode now includes **Google Sign-In for Android** and backend-issued mobile access token.

## Current Feature Coverage

### Offline

- Manual transcript analysis
- CSV import -> manual rows
- Image OCR import -> manual rows (ML Kit)
- CSE/BBA audit rules
- CGPA, credits, eligibility, issues
- Local device history

### Online

- Backend health check (`/api/health`)
- Analyze via backend (`/api/mobile/analyze`)
- History via backend (`/api/mobile/history`)
- MCP chat via backend (`/api/ai/chat`)
- History details via backend (`/api/mobile/history/<run_id>`)

## Run Details Parity

History screen now includes a **View Details** action showing:

- latest rows
- issues
- course audit (offline full, online basic where backend payload supports)
- CGPA detail rows (offline full, online when backend returns)
- retake summary (offline full)

## Android Google Auth (Online Mode)

To keep mobile hybrid and secure, online APIs require mobile auth token.

1. Backend `.env` must include web Google client:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

2. Set Android Gradle property for Google web client id:

Create `mobile-android-app/gradle.properties` (or user-level `~/.gradle/gradle.properties`) and add:

```properties
GOOGLE_WEB_CLIENT_ID=your_google_web_client_id.apps.googleusercontent.com
```

3. In app Home tab:

- switch to Online mode
- tap **Sign in with Google**
- use NSU (`@northsouth.edu`) account

Then online endpoints (`/api/mobile/*`, `/api/ai/chat`) work with bearer token.

## Open Project

1. Open Android Studio
2. Open folder: `Project 2 web app/mobile-android-app`
3. Let Gradle sync

## Emulator Run (Recommended)

1. Start Flask backend from `Project 2 web app`:

```powershell
python app.py
```

2. (Optional, for MCP chat tool calls) start MCP demo server:

```powershell
python mcp_demo_server.py
```

3. In Android Studio run app on emulator.

Default online backend URL is already:

- `http://10.0.2.2:5000`

## Real Phone Run

If using online mode on a real phone, set `BASE_URL` in `app/build.gradle.kts`:

```kotlin
buildConfigField("String", "BASE_URL", "\"http://YOUR_PC_LAN_IP:5000\"")
```

Then sync, rebuild, install.

## Build APK

Android Studio:

- Build -> Build Bundle(s) / APK(s) -> Build APK(s)

APK path:

- `app/build/outputs/apk/debug/app-debug.apk`

## Manual Input Format

Each row:

`Course_Code, Credits, Grade, Semester`

Example:

`CSE115, 4, A-, Spring 2024`

Valid grades:

`A, A-, B+, B, B-, C+, C, C-, D+, D, F, W`

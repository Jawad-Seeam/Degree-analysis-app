# Project 2 - NSU Transcript Analyzer (Web App)

This is the updated web version of Project 1.

## Features Implemented

1. NSU Google-only sign in (`@northsouth.edu` domain required)
2. No separate signup flow
3. Transcript input via:
   - Manual text
   - CSV upload
   - PDF upload (text extraction)
   - Image upload (OCR extraction)
4. Per-user history of transcript analysis runs
5. Responsive UI focused on fast workflow

## Setup (Terminal)

From this folder, run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Now edit `.env` and set:

- `SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

## Google OAuth Notes

Create OAuth credentials in Google Cloud Console and configure:

- Authorized redirect URI: `http://127.0.0.1:5000/auth/callback`

For production, add your production callback URL too.

## Run

```powershell
python app.py
```

Then open:

`http://127.0.0.1:5000`

## Input Row Format

Expected course row format:

`Course_Code, Credits, Grade, Semester`

Example:

`CSE115, 4, A-, Spring 2024`

## OCR/PDF Caveat

- PDF parser extracts transcript rows from text-based PDFs.
- Scanned PDF/Image parsing uses local Tesseract OCR.

If OCR fails, upload CSV/manual input for guaranteed parsing.

## API Integration (Assignment Ready)

The app now includes authenticated JSON APIs. You must be logged in with NSU Google account in the same browser session.

### 1) Analyze Transcript

`POST /api/analyze`

Supported `input_method`:
- `manual` with `manual_text`
- `csv` with `csv_text`

Example (manual):

```powershell
curl -X POST http://127.0.0.1:5000/api/analyze `
  -H "Content-Type: application/json" `
  -d "{\"input_method\":\"manual\",\"program\":\"CSE\",\"waived\":[\"ENG102\"],\"manual_text\":\"CSE115, 4, A-, Spring 2024\\nMAT116, 3, B+, Fall 2023\"}"
```

Example (csv_text):

```powershell
curl -X POST http://127.0.0.1:5000/api/analyze `
  -H "Content-Type: application/json" `
  -d "{\"input_method\":\"csv\",\"program\":\"CSE\",\"csv_text\":\"Course_Code,Credits,Grade,Semester\\nCSE115,4,A-,Spring 2024\\nMAT116,3,B+,Fall 2023\"}"
```

### 2) List My History

`GET /api/history`

Returns run summaries for logged-in user.

### 3) Get One Run Details

`GET /api/history/<run_id>`

Returns transcript rows, latest rows, CGPA details, issues, waived list, and run metadata.

### 4) Health Check

`GET /api/health`

Useful to demonstrate basic API availability and response format.

## MCP Integration (Backend-Only)

Architecture now:

`Web Frontend -> Python Backend API -> LLM + MCP Client -> MCP Server/Tools`

The web UI uses backend endpoint `POST /api/ai/chat`. No Android code is added yet; this API contract is reusable later for mobile.

### New Environment Variables

Set these in `.env` (see `.env.example`):

- `MCP_SERVER_URL`
- `MCP_TIMEOUT_SECONDS` (default `10`)
- `MCP_MAX_TOOL_CALLS` (default `3`)
- `MCP_TOOL_ALLOWLIST` (comma separated)
- `MODEL_API_KEY`
- `MODEL_NAME`
- `LOG_LEVEL`

### New Endpoints

#### 1) MCP Chat

`POST /api/ai/chat`

Request:

```json
{
  "message": "lookup CSE115",
  "user_id": "web-user-1",
  "context": {"screen": "dashboard"}
}
```

Response:

```json
{
  "reply": "string",
  "tool_trace": [
    {"tool": "tool_name", "status": "ok", "latency_ms": 12}
  ],
  "request_id": "uuid",
  "fallback_used": false
}
```

#### 2) MCP Tool Test

`POST /api/ai/tools/test`

Request:

```json
{
  "tool": "transcript_lookup",
  "arguments": {"query": "CSE115"}
}
```

Response:

```json
{
  "ok": true,
  "tool": "transcript_lookup",
  "latency_ms": 10,
  "result": {},
  "request_id": "uuid"
}
```

### Stable Error Codes

- `TOOL_NOT_ALLOWED`
- `TOOL_VALIDATION_ERROR`
- `TOOL_TIMEOUT`
- `TOOL_EXECUTION_ERROR`

### Guardrails Included

- MCP tool allowlist from `MCP_TOOL_ALLOWLIST`
- Argument schema checks (minimal baseline)
- Max tool calls per request (`MCP_MAX_TOOL_CALLS`)
- Timeout (`MCP_TIMEOUT_SECONDS`)
- Retry policy: max 1 retry for transient failures
- Secret redaction in logs
- No stack trace leakage to frontend

## Cline + MCP Demo

1. Configure Cline MCP to use same server URL as backend `MCP_SERVER_URL`.
2. In Cline, verify tools:
   - list tools
   - call a read tool (example: `transcript_lookup`)
   - call an action/simulated write tool from your MCP server setup
3. Verify backend uses same tool set by calling `POST /api/ai/tools/test`.

### Example Cline Demo Prompts

1. "List available MCP tools and explain what each does."
2. "Use transcript lookup for CSE115 and summarize result."
3. "Run degree audit hint for CSE program and CSE115."
4. "If tool fails, retry once and report fallback behavior."
5. "Show tool latency and compare two tool calls."

### Cline/MCP Troubleshooting

- **Server unreachable**: verify `MCP_SERVER_URL`, network, and server process.
- **No tools returned**: verify MCP server `/tools` endpoint and auth.
- **Timeouts**: increase `MCP_TIMEOUT_SECONDS` or optimize tool server.
- **Auth mismatch**: ensure backend and Cline share correct MCP auth config.

## 5-Minute Teacher Demo Script

1. Show architecture slide/diagram: Web -> Backend -> MCP.
2. Open web dashboard AI Chat and ask a question that triggers a tool call (e.g. "lookup CSE115").
3. Show `tool_trace` badges in UI (tool name, status, latency).
4. Show backend logs with `request_id` and MCP latency entries.
5. Show same MCP tool access in Cline to prove shared MCP backend.

## Quick Run / Test Commands

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Run guardrail tests:

```powershell
python -m unittest tests.test_mcp_guardrails
```

## curl Examples (MCP APIs)

```powershell
curl -X POST http://127.0.0.1:5000/api/ai/chat `
  -H "Content-Type: application/json" `
  -d '{"message":"lookup CSE115","user_id":"u-1","context":{}}'
```

```powershell
curl -X POST http://127.0.0.1:5000/api/ai/tools/test `
  -H "Content-Type: application/json" `
  -d '{"tool":"transcript_lookup","arguments":{"query":"CSE115"}}'
```

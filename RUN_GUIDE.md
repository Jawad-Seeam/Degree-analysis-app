# NSU Transcript Analyzer - Run Guide

This file contains all commands to run the web app and CLI.

## 1) Run Web App + MCP

Open two terminals.

### Terminal 1 (MCP server)

```powershell
cd "D:\CSE 226\Project 2 web app"
.\.venv\Scripts\Activate.ps1
python mcp_demo_server.py
```

### Terminal 2 (Web app)

```powershell
cd "D:\CSE 226\Project 2 web app"
.\.venv\Scripts\Activate.ps1
python app.py
```

Open in browser:

- `http://127.0.0.1:5000` (web app)
- `http://127.0.0.1:8000/tools` (MCP tools check)

---

## 2) CLI Setup

Open a new terminal:

```powershell
cd "D:\CSE 226\Project 2 web app"
.\.venv\Scripts\Activate.ps1
```

Check available commands:

```powershell
python cli.py -h
```

Run system health check:

```powershell
python cli.py doctor
```

Start interactive CLI:

```powershell
python cli.py shell
```

---

## 3) CLI Commands (Direct)

### Analyze CSV

```powershell
python cli.py analyze --input-method csv --file ".\Student12.csv" --program BBA --user-id 1
```

### Analyze Manual Input

```powershell
python cli.py analyze --input-method manual --program BBA --user-id 1 --text "ACT201, 3, A, Spring 2007`nBIO103, 3, A, Spring 2007"
```

### Analyze PDF

```powershell
python cli.py analyze --input-method pdf --file ".\Transcript 1.pdf" --program BBA --user-id 1
```

### Analyze Image

```powershell
python cli.py analyze --input-method image --file ".\BBA transcript image.png" --program BBA --user-id 1
```

### History

```powershell
python cli.py history --user-id 1
```

### History Details

```powershell
python cli.py history-details --user-id 1 --run-id 1
```

### Easy Lookup

```powershell
python cli.py lookup --query BIO103 --user-id 1
```

### MCP Chat

```powershell
python cli.py chat --user-id 1 --message "lookup BIO103"
```

### MCP Tool Test

```powershell
python cli.py tool-test --tool transcript_lookup --query BIO103 --user-id 1
```

### JSON Output (optional)

```powershell
python cli.py --output json history --user-id 1
```

---

## 4) Quick Start After PC Restart

### Step A: Start MCP server

```powershell
cd "D:\CSE 226\Project 2 web app"
.\.venv\Scripts\Activate.ps1
python mcp_demo_server.py
```

### Step B: Start web app

```powershell
cd "D:\CSE 226\Project 2 web app"
.\.venv\Scripts\Activate.ps1
python app.py
```

### Step C: Start CLI shell (optional)

```powershell
cd "D:\CSE 226\Project 2 web app"
.\.venv\Scripts\Activate.ps1
python cli.py shell
```

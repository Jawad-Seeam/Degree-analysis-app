import json
import os

from flask import Flask, jsonify, request


app = Flask(__name__)


def _db_path():
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, "instance", "project2.db")


def _semester_to_number(semester):
    season_order = {"SPRING": 0, "SUMMER": 1, "FALL": 2}
    raw = str(semester or "").strip()
    parts = raw.split()
    if len(parts) != 2:
        return -1
    season = parts[0].upper()
    try:
        year = int(parts[1])
    except Exception:
        return -1
    return (year * 10) + season_order.get(season, -1)


def _extract_latest_rows_for_user(user_id):
    if not user_id:
        return {}

    try:
        import sqlite3

        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT transcript_json FROM transcript_run WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (int(user_id),),
        )
        row = cur.fetchone()
        conn.close()
    except Exception:
        return {}

    if not row:
        return {}

    try:
        payload = json.loads(row["transcript_json"] or "[]")
    except Exception:
        return {}

    if not isinstance(payload, list):
        return {}

    latest = {}
    latest_sem_key = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        code = str(item.get("Course_Code", "")).strip().upper()
        if not code:
            continue
        sem_key = _semester_to_number(item.get("Semester", ""))
        if code not in latest or sem_key >= latest_sem_key.get(code, -1):
            latest[code] = item
            latest_sem_key[code] = sem_key
    return latest


@app.get("/")
def index():
    return jsonify(
        {
            "service": "mcp_demo_server",
            "ok": True,
            "endpoints": {
                "list_tools": "GET /tools",
                "call_tool": "POST /tools/<tool_name>/call",
            },
        }
    )


@app.get("/tools")
def list_tools():
    return jsonify(
        {
            "tools": [
                {
                    "name": "transcript_lookup",
                    "description": "Lookup transcript-like course matches",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "user_id": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
                {
                    "name": "degree_audit_hint",
                    "description": "Return a lightweight audit hint",
                    "input_schema": {
                        "type": "object",
                        "properties": {"program": {"type": "string"}, "course_code": {"type": "string"}},
                        "required": ["program", "course_code"],
                    },
                },
            ]
        }
    )


@app.post("/tools/<tool_name>/call")
def call_tool(tool_name):
    payload = request.get_json(silent=True) or {}
    arguments = payload.get("arguments", {})

    if tool_name == "transcript_lookup":
        query = str(arguments.get("query", "")).strip()
        user_id = str(arguments.get("user_id", "")).strip()

        latest_rows = _extract_latest_rows_for_user(user_id)
        transcript_courses = sorted(latest_rows.keys())
        sample_courses = ["CSE115", "MAT116", "ENG102", "EEE141", "ACT201", "BIO103", "BUS101", "FIN254"]
        search_pool = transcript_courses if transcript_courses else sample_courses

        needle = query.upper().replace(" ", "")
        matches = [code for code in search_pool if needle in code]

        rows = []
        for code in matches:
            row = latest_rows.get(code)
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "course_code": code,
                    "credits": row.get("Credits"),
                    "grade": row.get("Grade"),
                    "semester": row.get("Semester"),
                }
            )

        return jsonify(
            {
                "result": {
                    "query": query,
                    "matches": matches,
                    "rows": rows,
                    "source": "mcp_demo_server",
                    "from_transcript": bool(transcript_courses),
                    "pool_size": len(search_pool),
                }
            }
        )

    if tool_name == "degree_audit_hint":
        program = str(arguments.get("program", "")).upper().strip()
        course_code = str(arguments.get("course_code", "")).upper().strip()
        return jsonify(
            {
                "result": {
                    "program": program,
                    "course_code": course_code,
                    "hint": f"For {program}, verify prerequisite chain and minimum grade for {course_code}.",
                    "source": "mcp_demo_server",
                }
            }
        )

    return jsonify({"error": "Unknown tool"}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)

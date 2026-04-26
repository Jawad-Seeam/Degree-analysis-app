import argparse
import json
import os
import shlex
from datetime import datetime

from ai.orchestrator import build_orchestrator
from app import (
    TranscriptRun,
    app,
    build_ocr_preview_payload,
    build_result,
    build_signal_warning,
    extract_text_from_image,
    extract_text_from_pdf,
    make_ocr_preview,
    parse_program_knowledge,
    parse_rows_from_text,
    parse_waived_courses,
    read_rows_from_csv_text,
    read_rows_from_manual,
    run_to_details,
    run_to_summary,
    save_transcript_run,
    should_block_low_confidence,
)


class LocalUpload:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            self._data = f.read()

    def read(self):
        return self._data


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def _supports_color():
    if os.getenv("NO_COLOR"):
        return False
    return True


def _c(text, color):
    if not _supports_color():
        return text
    return f"{color}{text}{RESET}"


def _hr(char="-", width=72):
    print(_c(char * width, DIM))


def _title(text):
    _hr("=")
    print(_c(text, BOLD + CYAN))
    _hr("=")


def _section(text):
    print(f"\n{_c(text, BOLD)}")
    _hr()


def _ok(msg):
    print(_c(f"OK: {msg}", GREEN))


def _warn(msg):
    print(_c(f"WARN: {msg}", YELLOW))


def _err(msg):
    print(_c(f"ERROR: {msg}", RED))


def _print_json(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def _programs():
    here = os.path.dirname(__file__)
    return parse_program_knowledge(os.path.join(here, "program.md"))


def _format_key_values(items):
    for key, value in items:
        print(f"{key:<18}: {value}")


def _truncate(text, width):
    raw = str(text)
    if len(raw) <= width:
        return raw
    if width <= 3:
        return raw[:width]
    return raw[: width - 3] + "..."


def _print_table(headers, rows, widths):
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(_c(line, DIM))
    hrow = "| " + " | ".join(_truncate(h, widths[i]).ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    print(_c(hrow, BOLD))
    print(_c(line, DIM))
    for row in rows:
        prow = "| " + " | ".join(_truncate(row[i], widths[i]).ljust(widths[i]) for i in range(len(widths))) + " |"
        print(prow)
    print(_c(line, DIM))


def _status_chip(label, ok):
    if ok:
        return _c(f"[OK] {label}", GREEN)
    return _c(f"[FAIL] {label}", RED)


def _format_analyze_human(output):
    result = output.get("result", {})
    _title("NSU Transcript Analyzer - Analyze")
    _format_key_values(
        [
            ("Input Method", result.get("input_method", "-")),
            ("Program", result.get("program", "-")),
            ("CGPA", result.get("cgpa", "-")),
            ("Earned Credits", result.get("earned_credits", "-")),
            ("Required Credits", result.get("required_credits", "-")),
            ("Remaining", result.get("remaining_credits", "-")),
            ("Eligible", "Yes" if result.get("eligible") else "No"),
            ("Run ID", output.get("run_id", "not saved")),
        ]
    )

    waived = result.get("waived", []) or []
    issues = result.get("issues", []) or []

    _section("Waived Courses")
    if waived:
        for w in waived:
            print(f"- {w}")
    else:
        print("None")

    _section("Issues")
    if issues:
        for idx, issue in enumerate(issues, start=1):
            print(f"{idx}. {issue}")
    else:
        print("No issues detected.")

    if output.get("ocr_warning"):
        _section("OCR Warning")
        _warn(output["ocr_warning"])


def _format_history_human(output):
    _title("NSU Transcript Analyzer - History")
    print(f"Total Runs: {output.get('count', 0)}")
    _hr()
    runs = output.get("runs", [])
    if not runs:
        print("No runs found.")
        return

    view = runs[:15]
    table_rows = []
    for run in view:
        table_rows.append(
            [
                str(run.get("id", "-")),
                str(run.get("program", "-")),
                str(run.get("input_method", "-")).upper(),
                f"{float(run.get('cgpa', 0)):.2f}",
                "Yes" if run.get("eligible") else "No",
                str(run.get("created_at", "-")),
            ]
        )

    _print_table(
        headers=["Run", "Program", "Input", "CGPA", "Eligible", "Created At"],
        rows=table_rows,
        widths=[6, 8, 8, 6, 8, 28],
    )
    if len(runs) > len(view):
        _warn(f"Showing latest {len(view)} of {len(runs)} runs.")


def _format_history_details_human(output):
    if not output.get("ok"):
        _err(output.get("error", "Unknown error"))
        return

    run = output.get("run", {})
    _title(f"NSU Transcript Analyzer - Run Details #{run.get('id', '-')}")
    _format_key_values(
        [
            ("Program", run.get("program", "-")),
            ("Input", run.get("input_method", "-")),
            ("CGPA", output.get("cgpa", "-")),
            ("Earned Credits", run.get("earned_credits", "-")),
            ("Required Credits", run.get("required_credits", "-")),
            ("Eligible", "Yes" if run.get("eligible") else "No"),
            ("Created", run.get("created_at", "-")),
        ]
    )

    _section("Latest Courses")
    latest_rows = output.get("latest_rows", [])
    if latest_rows:
        for row in latest_rows[:25]:
            print(f"- {row.get('Course_Code')} | {row.get('Grade')} | {row.get('Credits')} cr | {row.get('Semester')}")
        if len(latest_rows) > 25:
            print(f"... and {len(latest_rows) - 25} more")
    else:
        print("No course rows found.")

    _section("Issues")
    issues = output.get("issues", [])
    if issues:
        for idx, issue in enumerate(issues, start=1):
            print(f"{idx}. {issue}")
    else:
        print("No issues detected.")


def _format_chat_human(output):
    _title("NSU Transcript Analyzer - MCP Chat")
    print(f"Reply: {output.get('reply', '-')}")
    print(f"Request ID: {output.get('request_id', '-')}")
    print(f"Fallback Used: {bool(output.get('fallback_used'))}")
    _section("Tool Trace")
    trace = output.get("tool_trace", [])
    if trace:
        for item in trace:
            print(f"- {item.get('tool')} | {item.get('status')} | {item.get('latency_ms')}ms")
    else:
        print("No tool calls.")


def _format_tool_test_human(output):
    _title("NSU Transcript Analyzer - MCP Tool Test")
    _format_key_values(
        [
            ("Tool", output.get("tool", "-")),
            ("OK", bool(output.get("ok"))),
            ("Latency", f"{output.get('latency_ms', 0)}ms"),
            ("Request ID", output.get("request_id", "-")),
        ]
    )
    _section("Result")
    _print_json(output.get("result", {}))


def _print_shell_help():
    _section("Shell Commands")
    print("Type one command per line, without 'python cli.py'.")
    print("- analyze --input-method csv --file .\\Student12.csv --program BBA --user-id 1")
    print("- history --user-id 1")
    print("- history-details --user-id 1 --run-id 3")
    print("- chat --user-id 1 --message \"lookup BIO103\"")
    print("- tool-test --tool transcript_lookup --query BIO103 --user-id 1")
    print("- help")
    print("- home")
    print("- examples")
    print("- doctor")
    print("- exit")


def _print_shell_examples():
    _section("Quick Examples")
    print("1) Analyze CSV and save run")
    print("   analyze --input-method csv --file .\\Student12.csv --program BBA --user-id 1")
    print("2) Analyze manual text")
    print("   analyze --input-method manual --program BBA --user-id 1 --text \"ACT201, 3, A, Spring 2007\"")
    print("3) Check history")
    print("   history --user-id 1")
    print("4) MCP lookup")
    print("   chat --user-id 1 --message \"lookup ACT201\"")


def _print_shell_menu():
    _section("Menu")
    print("1) Help")
    print("2) Examples")
    print("3) History (prompt)")
    print("4) Analyze CSV (prompt)")
    print("5) MCP Chat Lookup (prompt)")
    print("6) MCP Tool Test Lookup (prompt)")
    print("7) History Details (prompt)")
    print("8) Analyze Wizard (guided)")
    print("9) System Doctor")
    print("0) Exit")


def _print_shell_home():
    _title("NSU Transcript Analyzer - Shell Home")
    print(f"Current Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Run 'menu'          : show numbered actions")
    print("Run 'doctor'        : check MCP/DB status")
    print("Run 'help'          : show command examples")
    _hr()


def _doctor_report():
    here = os.path.dirname(__file__)
    db_path = os.path.join(here, "instance", "project2.db")
    checks = []

    checks.append(("Database file", os.path.exists(db_path), db_path))

    mcp_ok = False
    mcp_msg = "unreachable"
    try:
        import requests

        r = requests.get("http://127.0.0.1:8000/tools", timeout=2)
        mcp_ok = r.ok
        mcp_msg = f"status={r.status_code}"
    except Exception as exc:
        mcp_msg = str(exc)
    checks.append(("MCP server (8000)", mcp_ok, mcp_msg))

    web_ok = False
    web_msg = "not running"
    try:
        import requests

        r = requests.get("http://127.0.0.1:5000/api/health", timeout=2)
        web_ok = r.ok
        web_msg = f"status={r.status_code}"
    except Exception as exc:
        web_msg = str(exc)
    checks.append(("Web app (5000)", web_ok, web_msg))

    _title("NSU Transcript Analyzer - Doctor")
    for label, ok, msg in checks:
        print(f"{_status_chip(label, ok)} - {msg}")

    if all(ok for _, ok, _ in checks):
        _ok("All core services look healthy.")
    else:
        _warn("Some checks failed. Start missing services and retry 'doctor'.")


def _wizard_analyze_command():
    method = (input("input method [csv/manual/pdf/image] (default csv): ").strip() or "csv").lower()
    if method not in {"csv", "manual", "pdf", "image"}:
        _warn("Invalid method, defaulting to csv.")
        method = "csv"

    program = (input("program [CSE/BBA] (default CSE): ").strip() or "CSE").upper()
    waived = input("waived courses comma-separated (optional): ").strip()
    user_id = input("user_id to save run (optional): ").strip()

    cmd = f"analyze --input-method {method} --program {program}"
    if waived:
        cmd += f" --waived \"{waived}\""
    if user_id:
        cmd += f" --user-id {user_id}"

    if method in {"csv", "pdf", "image"}:
        default_file = ".\\Student12.csv" if method == "csv" else ""
        file_path = input(f"file path{' (default .\\Student12.csv)' if method == 'csv' else ''}: ").strip() or default_file
        if file_path:
            cmd += f" --file \"{file_path}\""
    else:
        text_file = input("manual text file path (optional): ").strip()
        if text_file:
            cmd += f" --text-file \"{text_file}\""
        else:
            one_line = input("manual single row (optional): ").strip()
            if one_line:
                cmd += f" --text \"{one_line}\""

    return cmd


def _menu_to_command(choice):
    if choice == "3":
        user_id = input("user_id: ").strip() or "1"
        return f"history --user-id {user_id}"

    if choice == "4":
        file_path = input("csv file path: ").strip() or ".\\Student12.csv"
        program = (input("program (CSE/BBA): ").strip() or "CSE").upper()
        user_id = input("user_id to save run (blank = no save): ").strip()
        cmd = f"analyze --input-method csv --file \"{file_path}\" --program {program}"
        if user_id:
            cmd += f" --user-id {user_id}"
        return cmd

    if choice == "5":
        user_id = input("user_id: ").strip() or "1"
        query = input("course query (e.g., BIO103): ").strip() or "BIO103"
        return f"chat --user-id {user_id} --message \"lookup {query}\""

    if choice == "6":
        user_id = input("user_id: ").strip() or "1"
        query = input("course query (e.g., BIO103): ").strip() or "BIO103"
        return f"tool-test --tool transcript_lookup --query {query} --user-id {user_id}"

    if choice == "7":
        user_id = input("user_id: ").strip() or "1"
        run_id = input("run_id: ").strip()
        if not run_id:
            return ""
        return f"history-details --user-id {user_id} --run-id {run_id}"

    if choice == "8":
        return _wizard_analyze_command()

    if choice == "9":
        return "doctor"

    return ""


def cmd_shell(args):
    _title("NSU Transcript Analyzer - Interactive CLI")
    print("Type 'help' to see commands, 'examples' for samples, and 'exit' to quit.")
    print("Tip: Start mcp_demo_server.py in another terminal for MCP commands.")
    print("Type 'menu' for numbered mode.")
    _print_shell_home()
    _print_shell_menu()

    parser = build_parser()

    while True:
        try:
            raw = input("nsu-cli> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting shell.")
            return

        if not raw:
            continue

        lower = raw.lower()
        if lower in {"exit", "quit", "q"}:
            print("Goodbye.")
            return
        if lower in {"help", "?"}:
            _print_shell_help()
            continue
        if lower == "home":
            _print_shell_home()
            continue
        if lower == "examples":
            _print_shell_examples()
            continue
        if lower == "doctor":
            _doctor_report()
            continue
        if lower == "menu":
            _print_shell_menu()
            continue

        if raw in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            if raw == "0":
                print("Goodbye.")
                return
            if raw == "1":
                _print_shell_help()
                continue
            if raw == "2":
                _print_shell_examples()
                continue
            generated = _menu_to_command(raw)
            if not generated:
                _warn("No command generated.")
                continue
            print(f"Running: {generated}")
            raw = generated

        try:
            tokens = shlex.split(raw)
        except ValueError as exc:
            _err(f"Parse error: {exc}")
            continue

        if not tokens:
            continue

        if tokens[0] == "shell":
            _warn("You are already inside shell mode.")
            continue

        if "--output" not in tokens:
            tokens = ["--output", args.output] + tokens

        try:
            parsed = parser.parse_args(tokens)
        except SystemExit:
            _warn("Invalid command. Type 'help' for shell commands.")
            continue

        try:
            parsed.func(parsed)
        except Exception as exc:
            if getattr(parsed, "output", "human") == "json":
                _print_json({"ok": False, "error": str(exc)})
            else:
                _err(str(exc))


def cmd_analyze(args):
    programs = _programs()
    program_key = (args.program or "CSE").strip().upper()
    if program_key not in programs:
        raise ValueError(f"Unknown program '{program_key}'")

    waived = parse_waived_courses(args.waived or "")
    input_method = args.input_method
    rows = []
    ocr_warning = None
    ocr_preview = None
    ocr_payload = None

    if input_method == "manual":
        manual_text = args.text or ""
        if args.text_file:
            with open(args.text_file, "r", encoding="utf-8") as f:
                manual_text = f.read()
        rows = read_rows_from_manual(manual_text)

    elif input_method == "csv":
        if not args.file:
            raise ValueError("--file is required for csv input")
        with open(args.file, "r", encoding="utf-8-sig") as f:
            rows = read_rows_from_csv_text(f.read())

    elif input_method == "pdf":
        if not args.file:
            raise ValueError("--file is required for pdf input")
        uploaded = LocalUpload(args.file)
        text, meta = extract_text_from_pdf(uploaded)
        ocr_warning = build_signal_warning(meta, "PDF")
        rows = parse_rows_from_text(text)
        ocr_preview = make_ocr_preview(text, meta=meta)
        ocr_payload = build_ocr_preview_payload(text, rows, meta)
        if should_block_low_confidence(meta):
            raise ValueError("Analysis blocked due to low OCR confidence. Use clearer file or CSV/manual input.")

    elif input_method == "image":
        if not args.file:
            raise ValueError("--file is required for image input")
        uploaded = LocalUpload(args.file)
        text, meta = extract_text_from_image(uploaded)
        ocr_warning = build_signal_warning(meta, "Image")
        rows = parse_rows_from_text(text)
        ocr_preview = make_ocr_preview(text, meta=meta)
        ocr_payload = build_ocr_preview_payload(text, rows, meta)
        if should_block_low_confidence(meta):
            raise ValueError("Analysis blocked due to low OCR confidence. Use clearer file or CSV/manual input.")

    result = build_result(rows, program_key, waived, programs)

    run_id = None
    if args.user_id is not None:
        run = save_transcript_run(int(args.user_id), input_method, result)
        run_id = run.id

    output = {
        "ok": True,
        "run_id": run_id,
        "result": {
            "input_method": input_method,
            "program": result["program_key"],
            "cgpa": result["cgpa"],
            "earned_credits": result["earned_credits"],
            "required_credits": result["required_credits"],
            "remaining_credits": result["remaining_credits"],
            "eligible": result["eligible"],
            "issues": result["issues"],
            "waived": result["waived"],
        },
    }

    if ocr_warning:
        output["ocr_warning"] = ocr_warning
    if args.show_ocr_preview and ocr_preview:
        output["ocr_preview"] = ocr_preview
    if args.show_ocr_preview and ocr_payload:
        output["ocr_preview_payload"] = ocr_payload

    if args.output == "json":
        _print_json(output)
    else:
        _format_analyze_human(output)


def cmd_history(args):
    runs = TranscriptRun.query.filter_by(user_id=int(args.user_id)).order_by(TranscriptRun.created_at.desc()).all()
    output = {"ok": True, "count": len(runs), "runs": [run_to_summary(run) for run in runs]}
    if args.output == "json":
        _print_json(output)
    else:
        _format_history_human(output)


def cmd_history_details(args):
    run = TranscriptRun.query.filter_by(id=int(args.run_id), user_id=int(args.user_id)).first()
    output = {"ok": False, "error": "Run not found"}
    if run:
        output = {"ok": True, **run_to_details(run)}
    if args.output == "json":
        _print_json(output)
    else:
        _format_history_details_human(output)


def cmd_chat(args):
    context = {}
    if args.context:
        try:
            parsed = json.loads(args.context)
            if isinstance(parsed, dict):
                context = parsed
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid --context JSON: {exc}")

    orchestrator = build_orchestrator()
    result = orchestrator.chat(
        message=args.message,
        user_id=str(args.user_id or "cli-user"),
        context=context,
    )
    if args.output == "json":
        _print_json(result)
    else:
        _format_chat_human(result)


def cmd_tool_test(args):
    if args.query is not None:
        arguments = {"query": args.query}
        if args.user_id is not None:
            arguments["user_id"] = str(args.user_id)
    else:
        try:
            arguments = json.loads(args.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("--arguments must be a JSON object")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid --arguments JSON: {exc}")

    orchestrator = build_orchestrator()
    result = orchestrator.test_tool(tool=args.tool, arguments=arguments)
    if args.output == "json":
        _print_json(result)
    else:
        _format_tool_test_human(result)


def cmd_doctor(args):
    _doctor_report()


def cmd_lookup(args):
    orchestrator = build_orchestrator()
    message = f"lookup {args.query.strip()}"
    result = orchestrator.chat(
        message=message,
        user_id=str(args.user_id),
        context={"source": "cli-lookup"},
    )
    if args.output == "json":
        _print_json(result)
    else:
        _format_chat_human(result)


def build_parser():
    parser = argparse.ArgumentParser(
        description="NSU Transcript Analyzer CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Quick start:\n"
            "  python cli.py shell\n"
            "  python cli.py lookup --query BIO103 --user-id 1\n"
            "  python cli.py doctor"
        ),
    )
    parser.add_argument("--output", choices=["human", "json"], default="human", help="Output format")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Run transcript analysis", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_analyze.add_argument("--input-method", choices=["manual", "csv", "pdf", "image"], required=True)
    p_analyze.add_argument("--program", default="CSE")
    p_analyze.add_argument("--waived", default="")
    p_analyze.add_argument("--file", help="Input file path for csv/pdf/image")
    p_analyze.add_argument("--text", help="Manual transcript text")
    p_analyze.add_argument("--text-file", help="Path to manual transcript text file")
    p_analyze.add_argument("--user-id", type=int, help="Save run under this user id")
    p_analyze.add_argument("--show-ocr-preview", action="store_true", help="Include OCR preview fields in output")
    p_analyze.set_defaults(func=cmd_analyze)

    p_history = sub.add_parser("history", help="List run history for a user", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_history.add_argument("--user-id", type=int, required=True)
    p_history.set_defaults(func=cmd_history)

    p_details = sub.add_parser("history-details", help="Show one run details", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_details.add_argument("--user-id", type=int, required=True)
    p_details.add_argument("--run-id", type=int, required=True)
    p_details.set_defaults(func=cmd_history_details)

    p_chat = sub.add_parser("chat", help="Call MCP chat", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_chat.add_argument("--message", required=True)
    p_chat.add_argument("--user-id", default="cli-user")
    p_chat.add_argument("--context", default="{}", help="JSON object string")
    p_chat.set_defaults(func=cmd_chat)

    p_tool = sub.add_parser("tool-test", help="Direct MCP tool test", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_tool.add_argument("--tool", required=True)
    p_tool.add_argument("--query", help="Shortcut for transcript lookup query")
    p_tool.add_argument("--user-id", help="Optional user id for transcript lookup")
    p_tool.add_argument("--arguments", default="{}", help="JSON object string (used if --query is not set)")
    p_tool.set_defaults(func=cmd_tool_test)

    p_lookup = sub.add_parser("lookup", help="Easy transcript lookup command", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_lookup.add_argument("--query", required=True, help="Course code query, e.g. BIO103")
    p_lookup.add_argument("--user-id", default="1", help="User id for transcript context")
    p_lookup.set_defaults(func=cmd_lookup)

    p_doctor = sub.add_parser("doctor", help="Check local service status", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_doctor.set_defaults(func=cmd_doctor)

    p_shell = sub.add_parser("shell", help="Interactive menu-like CLI", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p_shell.set_defaults(func=cmd_shell)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    with app.app_context():
        try:
            args.func(args)
        except Exception as exc:
            if getattr(args, "output", "human") == "json":
                _print_json({"ok": False, "error": str(exc)})
            else:
                _title("NSU Transcript Analyzer - Error")
                _err(str(exc))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

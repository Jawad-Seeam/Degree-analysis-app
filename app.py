import io
import json
import os
import re
import csv
from datetime import datetime, timedelta, timezone

import fitz
import requests
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image, ImageFilter, ImageOps

from api.ai import ai_bp
from core.config import get_mcp_settings


load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
oauth = OAuth()


GRADE_POINTS = {
    "A": 4.00,
    "A-": 3.70,
    "B+": 3.30,
    "B": 3.00,
    "B-": 2.70,
    "C+": 2.30,
    "C": 2.00,
    "C-": 1.70,
    "D+": 1.30,
    "D": 1.00,
    "F": 0.00,
}

VALID_GRADES = {"A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F", "W"}


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_sub = db.Column(db.String(128), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    avatar_url = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class TranscriptRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    input_method = db.Column(db.String(32), nullable=False)
    program = db.Column(db.String(64), nullable=False)
    cgpa = db.Column(db.Float, nullable=False)
    earned_credits = db.Column(db.Integer, nullable=False)
    required_credits = db.Column(db.Integer, nullable=False)
    eligible = db.Column(db.Boolean, nullable=False)
    issues_json = db.Column(db.Text, nullable=False)
    waived_json = db.Column(db.Text, nullable=False)
    transcript_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship("User", backref=db.backref("runs", lazy=True, order_by="desc(TranscriptRun.created_at)"))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-change-me")
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:///project2.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "home"

    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    with app.app_context():
        db.create_all()

    cfg = get_mcp_settings()
    app.logger.info("MCP settings loaded: %s", cfg.masked())
    app.register_blueprint(ai_bp)

    register_routes(app)
    return app


def build_mobile_token_serializer():
    secret = os.getenv("MOBILE_TOKEN_SECRET", "").strip() or os.getenv("SECRET_KEY", "dev-change-me")
    return URLSafeTimedSerializer(secret_key=secret, salt="mobile-auth-v1")


def issue_mobile_token(user: User):
    serializer = build_mobile_token_serializer()
    payload = {"uid": int(user.id), "sub": user.google_sub, "email": user.email}
    return serializer.dumps(payload)


def resolve_mobile_auth_user(request_obj):
    auth_header = (request_obj.headers.get("Authorization") or "").strip()
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = str(request_obj.args.get("access_token", "") or request_obj.form.get("access_token", "")).strip()
    if not token:
        raise ValueError("Missing access token")

    max_age = int(os.getenv("MOBILE_TOKEN_MAX_AGE_SECONDS", "2592000") or "2592000")
    serializer = build_mobile_token_serializer()
    try:
        payload = serializer.loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise ValueError("Access token expired") from exc
    except BadSignature as exc:
        raise ValueError("Invalid access token") from exc

    uid = payload.get("uid")
    if uid is None:
        raise ValueError("Invalid token payload")

    user = db.session.get(User, int(uid))
    if not user:
        raise ValueError("User not found")

    expected_sub = str(payload.get("sub", "") or "").strip()
    if expected_sub and user.google_sub != expected_sub:
        raise ValueError("Token subject mismatch")

    return user


def parse_program_knowledge(path):
    programs = {}
    current_code = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text.startswith("## [Program:"):
                name = text.replace("## [Program:", "").replace("]", "").strip()
                code = "CSE" if "CSE" in name.upper() or "COMPUTER" in name.upper() else "BBA"
                current_code = code
                programs[current_code] = {
                    "display_name": name,
                    "degree": "",
                    "total_credits": 0,
                    "requirements": {},
                }
            elif current_code and text.startswith("- **Degree**:"):
                programs[current_code]["degree"] = text.split(":", 1)[1].strip()
            elif current_code and text.startswith("- **Total Credits Required**:"):
                programs[current_code]["total_credits"] = int(text.split(":", 1)[1].strip())
            elif current_code and text.startswith("- **") and ":" in text:
                key = text.split("**:", 1)[0].replace("- **", "").strip()
                values = text.split("**:", 1)[1].strip()
                courses = [v.strip().upper() for v in values.split(",") if v.strip()]
                programs[current_code]["requirements"][key] = courses
    return programs


def semester_to_number(semester):
    season_order = {"SPRING": 0, "SUMMER": 1, "FALL": 2}
    parts = semester.split()
    if len(parts) != 2:
        return 999999
    season = parts[0].upper()
    year = int(parts[1])
    return year * 10 + season_order.get(season, 9)


def normalize_row(course_code, credits, grade, semester):
    code = str(course_code).strip().upper()
    sem = str(semester).strip().title()
    grd = str(grade).strip().upper()
    cr = int(float(credits))
    if grd not in VALID_GRADES:
        raise ValueError(f"Invalid grade '{grd}' for {code}")
    if cr < 0:
        raise ValueError(f"Negative credits found for {code}")
    if not re.match(r"^(Spring|Summer|Fall)\s+\d{4}$", sem):
        raise ValueError(f"Semester must be like 'Spring 2024' (found: {sem})")
    return {
        "Course_Code": code,
        "Credits": cr,
        "Grade": grd,
        "Semester": sem,
    }


def read_rows_from_records(records):
    rows = []
    for row in records:
        rows.append(
            normalize_row(
                row.get("Course_Code"),
                row.get("Credits"),
                row.get("Grade"),
                row.get("Semester"),
            )
        )
    if not rows:
        raise ValueError("No valid transcript rows found.")
    return rows


def read_rows_from_csv_upload(uploaded):
    content = uploaded.read().decode("utf-8-sig")
    return read_rows_from_csv_text(content)


def read_rows_from_csv_text(content):
    reader = csv.DictReader(io.StringIO(content))
    headers = set(reader.fieldnames or [])
    required = {"Course_Code", "Credits", "Grade", "Semester"}
    if not required.issubset(headers):
        raise ValueError("CSV must contain columns: Course_Code, Credits, Grade, Semester")
    return read_rows_from_records(list(reader))


def read_rows_from_manual(text):
    rows = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for idx, line in enumerate(lines, start=1):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            raise ValueError(f"Manual line {idx} must be: Course_Code, Credits, Grade, Semester")
        rows.append(normalize_row(parts[0], parts[1], parts[2], parts[3]))
    if not rows:
        raise ValueError("Manual input is empty.")
    return rows


def parse_rows_from_text(raw_text):
    raw_text = normalize_transcript_ocr_text(raw_text)
    csv_re = re.compile(
        r"([A-Za-z]{2,4}\s?[0-9IOL]{3}[A-Za-z]?)\s*[,\t]\s*(\d+(?:\.\d+)?)\s*[,\t]\s*(A\-|A|B\+|B|B\-|C\+|C|C\-|D\+|D|F|W)\s*[,\t]\s*(Spring|Summer|Fall)\s*[-/ ]?\s*(\d{4})",
        re.IGNORECASE,
    )
    ws_re = re.compile(
        r"([A-Za-z]{2,4}\s?[0-9IOL]{3}[A-Za-z]?)\s+(\d+(?:\.\d+)?)\s+(A\-|A|B\+|B\s*\+?\s*|B\-|C\+|C|C\-|D\+|D|F|W)\s+(Spring|Summer|Fall)\s*[-/ ]?\s*(\d{4})",
        re.IGNORECASE,
    )

    rows = []
    for pattern in (csv_re, ws_re):
        for match in pattern.findall(raw_text):
            code, credits, grade, season, year = match
            norm_code = normalize_course_code_token(code)
            norm_grade = normalize_grade_token(grade)
            if not norm_code or norm_grade not in VALID_GRADES:
                continue
            rows.append(normalize_row(norm_code, credits, norm_grade, f"{season.title()} {year}"))
        if rows:
            break

    dedup = {}
    for row in rows:
        key = (row["Course_Code"], row["Semester"], row["Grade"], row["Credits"])
        dedup[key] = row
    rows = list(dedup.values())

    if not rows:
        rows = parse_rows_from_structured_lines(raw_text)

    if not rows:
        rows = parse_rows_from_transcript_layout(raw_text)

    if not rows:
        raise ValueError("Could not extract course rows from PDF/Image. Use a clearer file or upload CSV/manual input.")
    return rows


def normalize_credit_token(token):
    raw = str(token or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d0", raw):
        raw = f"{raw[0]}.0"
    try:
        value = float(raw)
    except Exception:
        return None
    if value < 0 or value > 6:
        return None
    return value


def parse_rows_from_structured_lines(raw_text):
    semester_re = re.compile(r"\b(Spring|Summer|Fall)\s*[-/ ]?\s*(\d{4})\b", re.IGNORECASE)
    course_row_re = re.compile(
        r"(?<![A-Z0-9])([A-Z]{2,4}[0-9IOL]{3}[A-Z]?)(?![A-Z0-9]).{0,90}?"
        r"(\d+(?:\.\d+)?)\s+"
        r"(A\-|A|B\+|BT|B00|BOO|B|B\-|C\+|C|C\-|D\+|D|F|W)\s+"
        r"(\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    rows = []
    current_semester = None

    for raw_line in (raw_text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        header_semester = detect_semester_header(line, semester_re)
        if header_semester:
            current_semester = header_semester

        if not current_semester:
            continue

        lowered = line.lower()
        if any(x in lowered for x in ["course title", "end of transcript", "official transcript"]):
            continue

        for match in course_row_re.finditer(line):
            code = normalize_course_code_token(match.group(1))
            grade = normalize_grade_token(match.group(3))
            credit = normalize_credit_token(match.group(2))
            cc = normalize_credit_token(match.group(4))
            cp = normalize_credit_token(match.group(5))
            if not code or grade not in VALID_GRADES:
                continue
            if credit is None or cc is None or cp is None:
                continue
            if is_suspicious_course_code(code):
                continue

            try:
                rows.append(normalize_row(code, int(round(credit)), grade, current_semester))
            except Exception:
                continue

    dedup = {}
    for row in rows:
        key = (row["Course_Code"], row["Semester"], row["Grade"], row["Credits"])
        dedup[key] = row
    return list(dedup.values())


def parse_rows_from_transcript_layout(raw_text):
    semester_re = re.compile(r"\b(Spring|Summer|Fall)\s*[-/ ]?\s*(\d{4})\b", re.IGNORECASE)
    code_re = re.compile(r"(?<![A-Z0-9])([A-Z]{2,4}[0-9IOL]{3}[A-Z]?)(?![A-Z0-9])", re.IGNORECASE)
    number_re = re.compile(r"\d+(?:\.\d+)?")

    rows = []
    current_semester = None
    cleaned_text = normalize_transcript_ocr_text(raw_text)

    for raw_line in cleaned_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        header_semester = detect_semester_header(line, semester_re)
        if header_semester:
            current_semester = header_semester

        if not current_semester:
            continue

        lowered = line.lower()
        if any(x in lowered for x in ["total credits", "end of transcript"]):
            continue
        if looks_like_pure_course_heading(line):
            continue

        code_hits = list(code_re.finditer(line))
        if not code_hits:
            continue

        multi_sem_hits = list(semester_re.finditer(line))
        use_right_column = len(multi_sem_hits) >= 2

        for idx, hit in enumerate(code_hits):
            if idx > 0 and "course" in lowered and "semester credit" not in lowered:
                continue
            if use_right_column and idx == 0:
                continue
            start = hit.start()
            end = code_hits[idx + 1].start() if idx + 1 < len(code_hits) else len(line)
            segment = line[start:end].strip()

            grade = detect_grade_with_fallback(segment)
            if not grade:
                continue
            code = normalize_course_code_token(hit.group(1))
            if not code or grade not in VALID_GRADES:
                continue
            if is_suspicious_course_code(code):
                continue

            gmatch = re.search(r"\b(A\-|A|B\+|BT|B00|BOO|B|B\-|C\+|C|C\-|D\+|D|F|W)\b", segment, re.IGNORECASE)
            if gmatch:
                before_grade = segment[: gmatch.start()]
                after_grade = segment[gmatch.end() :]
            else:
                before_grade = segment
                after_grade = segment
            credits_float = pick_credit_value(number_re.findall(before_grade))
            if credits_float is None:
                credits_float = pick_credit_value(number_re.findall(after_grade))
            if credits_float is None:
                continue

            credits = int(round(credits_float))
            try:
                rows.append(normalize_row(code, credits, grade, current_semester))
            except Exception:
                continue

    dedup = {}
    for row in rows:
        key = (row["Course_Code"], row["Semester"], row["Grade"], row["Credits"])
        dedup[key] = row
    return list(dedup.values())


def normalize_transcript_ocr_text(raw_text):
    text = raw_text or ""
    replacements = {
        "EEEI": "EEE1",
        "MATII": "MAT11",
        " BT ": " B+ ",
        " B5 ": " B ",
        " A> ": " A- ",
        " B00": " B 0.0",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\b([A-Za-z]{2,4})\s+([0-9IOL]{3}[A-Za-z]?)\b", r"\1\2", text)
    text = re.sub(r"\b([A-FW])\s*\+\b", r"\1+", text)
    text = re.sub(r"\b([A-FW])\s*\-\b", r"\1-", text)
    return text


def normalize_course_code_token(token):
    raw = re.sub(r"[^A-Za-z0-9]", "", (token or "").upper())
    if len(raw) < 5:
        return ""

    m = re.match(r"^([A-Z]{2,4})([0-9IOL]{3})([A-Z]?)$", raw)
    if not m:
        return ""

    prefix, digits, suffix = m.groups()
    allowed_prefixes = {
        "ACT", "ARC", "BAN", "BIO", "BUS", "CHE", "CIV", "CO", "CSE", "ECO", "EEE", "ENG", "ENV",
        "FIN", "HIS", "INT", "LAW", "MAT", "MGT", "MIS", "MKT", "PAD", "PHY", "POL", "SOC", "STA",
        "BEN", "INB", "BUS", "HIS",
    }
    if prefix not in allowed_prefixes:
        return ""

    digit_map = {"I": "1", "L": "1", "O": "0"}
    normalized_digits = "".join(digit_map.get(ch, ch) for ch in digits)
    if not normalized_digits.isdigit():
        return ""
    return f"{prefix}{normalized_digits}{suffix}"


def normalize_grade_token(token):
    grade = (token or "").upper().strip()
    fixes = {"BT": "B+", "8+": "B+", "A>": "A-", "B00": "B", "BOO": "B", "AC": "A", "AS": "A", "AB": "A"}
    grade = fixes.get(grade, grade)
    return grade


def pick_credit_value(number_tokens):
    candidates = []
    for token in number_tokens:
        try:
            value = float(token)
        except Exception:
            continue
        if 0.5 <= value <= 6.0:
            candidates.append(value)
    if not candidates:
        return None
    return candidates[0]


def detect_grade_with_fallback(text):
    grade_re = re.compile(r"\b(A\-|A|B\+|BT|B00|BOO|B|B\-|C\+|C|C\-|D\+|D|F|W)\b", re.IGNORECASE)
    hit = grade_re.search(text or "")
    if hit:
        return normalize_grade_token(hit.group(1))

    loose = (text or "").upper()
    if re.search(r"\bA\s*\+\b", loose):
        return "A"
    if re.search(r"\bA\s*\-\b", loose):
        return "A-"
    if re.search(r"\bB\s*\+\b", loose):
        return "B+"
    if re.search(r"\bB\s*\-\b", loose):
        return "B-"
    if re.search(r"\bC\s*\+\b", loose):
        return "C+"
    if re.search(r"\bC\s*\-\b", loose):
        return "C-"
    if re.search(r"\bD\s*\+\b", loose):
        return "D+"
    if re.search(r"\b[A-FW]\b", loose):
        return re.search(r"\b([A-FW])\b", loose).group(1)
    return ""


def is_suspicious_course_code(code):
    if not code:
        return True
    if re.search(r"(777|888|999|000)", code):
        return True
    if code.startswith("AAA") or code.startswith("ZZZ"):
        return True
    return False


def looks_like_pure_course_heading(line):
    lowered = (line or "").lower()
    heading_terms = ["course title", "course _", "course ", "cr gr", "cc cp", "count", "grade"]
    if any(term in lowered for term in heading_terms):
        if "semester credit" not in lowered and "tgpa" not in lowered and "cgpa" not in lowered:
            return True
    return False


def score_parsed_rows(rows):
    if not rows:
        return -40

    semester_counts = {}
    weird_credit = 0
    for row in rows:
        semester_counts[row["Semester"]] = semester_counts.get(row["Semester"], 0) + 1
        if row["Credits"] not in {1, 2, 3, 4}:
            weird_credit += 1

    sorted_semesters = sorted(semester_counts.keys(), key=semester_to_number)
    jumps = 0
    backward = 0
    prev = None
    for sem in sorted_semesters:
        current = semester_to_number(sem)
        if prev is not None:
            if current < prev:
                backward += 1
            if current - prev > 12:
                jumps += 1
        prev = current

    sparse_semesters = sum(1 for count in semester_counts.values() if count == 1)

    return (
        (len(rows) * 2)
        + (len(sorted_semesters) * 3)
        - (weird_credit * 6)
        - (sparse_semesters * 2)
        - (jumps * 5)
        - (backward * 9)
    )


def detect_semester_header(line, semester_re):
    hits = list(semester_re.finditer(line))
    if not hits:
        return None

    lowered = line.lower()
    if len(hits) > 1 and "semester credit" not in lowered:
        stripped_multi = semester_re.sub("", line).strip(" -:|_\t")
        stripped_multi_count = len([w for w in stripped_multi.split() if w])
        if stripped_multi_count > 1:
            return None

    first = hits[0]
    season = first.group(1).title()
    year = int(first.group(2))
    if year < 2000 or year > 2035:
        return None

    semester = f"{season} {year}"
    stripped = semester_re.sub("", line).strip(" -:|_\t")
    compact_word_count = len([w for w in stripped.split() if w])
    at_start = first.start() <= 2

    if "course" in lowered and not at_start:
        return None
    if "semester credit" in lowered:
        return semester
    if at_start:
        return semester
    if len(hits) > 1 and compact_word_count <= 1:
        return semester
    if compact_word_count <= 2:
        return semester
    return None


def analyze_transcript_text_signal(text):
    source = text or ""
    lowered = source.lower()
    course_codes = len(re.findall(r"\b[A-Z]{2,4}\d{3}[A-Z]?\b", source, re.IGNORECASE))
    semesters = len(re.findall(r"\b(Spring|Summer|Fall)\s+\d{4}\b", source, re.IGNORECASE))
    row_like = len(
        re.findall(
            r"([A-Za-z]{2,4}\d{3}[A-Za-z]?).{0,42}(A\-|A|B\+|B|B\-|C\+|C|C\-|D\+|D|F|W).{0,22}(Spring|Summer|Fall)\s+\d{4}",
            source,
            re.IGNORECASE,
        )
    )

    disclaimer_terms = [
        "controller of examinations",
        "official institutional",
        "cannot be released",
        "without the written consent",
        "not apply toward cgpa",
    ]
    disclaimer_hits = sum(1 for term in disclaimer_terms if term in lowered)

    score = (row_like * 8) + (min(course_codes, 30) * 2) + (semesters * 3) - (disclaimer_hits * 3)
    if score >= 26:
        confidence = "high"
    elif score >= 10:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "score": score,
        "confidence": confidence,
        "course_codes": course_codes,
        "semesters": semesters,
        "row_like": row_like,
        "disclaimer_hits": disclaimer_hits,
    }


def select_transcript_pages(page_entries):
    strong = []
    for entry in page_entries:
        signal = entry["signal"]
        if signal["row_like"] > 0 or (signal["course_codes"] >= 3 and signal["semesters"] >= 1):
            strong.append(entry)

    if strong:
        strong_pages = {entry["page"] for entry in strong}
        selected = []
        for entry in page_entries:
            signal = entry["signal"]
            page_no = entry["page"]
            is_near_strong = any(abs(page_no - p) <= 1 for p in strong_pages)
            if (
                page_no in strong_pages
                or (is_near_strong and signal["score"] >= 2)
                or signal["row_like"] > 0
                or signal["course_codes"] >= 2
            ):
                selected.append(entry)
        return selected

    scored = sorted(page_entries, key=lambda e: e["signal"]["score"], reverse=True)
    fallback = [entry for entry in scored if entry["signal"]["score"] > 0][:2]
    if fallback:
        return fallback

    return [entry for entry in page_entries if entry["text"].strip()]


def build_signal_warning(meta, source_label):
    if not meta:
        return None
    confidence = meta.get("confidence", "low")
    parsed_count = meta.get("parsed_count", 0)
    selected_pages = meta.get("selected_pages", [])
    total_pages = meta.get("total_pages", 0)

    if confidence == "high":
        return None
    if confidence == "medium":
        return (
            f"{source_label} text quality is moderate (pages used: {selected_pages}/{total_pages}). "
            f"Detected rows: {parsed_count}. Please review OCR Preview before trusting final analysis."
        )
    return (
        f"Low OCR confidence for {source_label} (pages used: {selected_pages}/{total_pages}). "
        f"Detected rows: {parsed_count}. Result may be inaccurate. Use CSV/manual input for guaranteed correctness."
    )


def should_block_low_confidence(meta):
    if not meta:
        return False
    parsed_count = int(meta.get("parsed_count", 0))
    if parsed_count < 2:
        return True
    if meta.get("confidence") == "low" and parsed_count < 3:
        return True
    return False


def choose_best_text(candidates):
    best_text = ""
    best_signal = {"score": -999, "row_like": 0, "course_codes": 0}
    for text in candidates:
        clean = (text or "").strip()
        if not clean:
            continue
        signal = analyze_transcript_text_signal(clean)
        bonus = min(len(clean) // 350, 8)
        score = signal["score"] + bonus
        if score > best_signal["score"]:
            best_signal = dict(signal)
            best_signal["score"] = score
            best_text = clean
    return best_text


def choose_best_transcript_text(candidates):
    scored = []
    for idx, text in enumerate(candidates):
        clean = (text or "").strip()
        if not clean:
            continue

        signal = analyze_transcript_text_signal(clean)
        try:
            rows = parse_rows_from_text(clean)
            parsed_count = len(rows)
            semesters = len({row["Semester"] for row in rows})
            row_quality = score_parsed_rows(rows)
        except Exception:
            parsed_count = 0
            semesters = 0
            row_quality = -30

        score = (parsed_count * 10) + (semesters * 6) + signal["score"] + row_quality
        scored.append(
            {
                "idx": idx,
                "text": clean,
                "score": score,
                "parsed_count": parsed_count,
                "semesters": semesters,
            }
        )

    if not scored:
        return choose_best_text(candidates)

    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0]
    if len(scored) == 1:
        return best["text"]

    second = scored[1]
    if second["score"] >= best["score"] - 15 and second["parsed_count"] >= max(3, best["parsed_count"] * 0.65):
        if second["idx"] > best["idx"]:
            return second["text"]

    return best["text"]


def extract_text_from_pdf(file_storage):
    file_bytes = file_storage.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_entries = []
    total_pages = len(doc)

    for page_number, page in enumerate(doc, start=1):
        direct_text = (page.get_text("text") or "").strip()
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        ocr_text = extract_text_from_image_object(image).strip()
        column_text = extract_text_from_image_columns(image).strip()
        page_text = choose_best_transcript_text([direct_text, ocr_text, column_text])

        page_entries.append(
            {
                "page": page_number,
                "text": page_text,
                "signal": analyze_transcript_text_signal(page_text),
            }
        )

    doc.close()

    selected_entries = select_transcript_pages(page_entries)
    merged = "\n\n".join([entry["text"] for entry in selected_entries if entry["text"].strip()]).strip()
    if not merged:
        raise ValueError("No readable text found in PDF. Try a clearer scan or use CSV/manual input.")

    merged_signal = analyze_transcript_text_signal(merged)
    try:
        parsed_count = len(parse_rows_from_text(merged))
    except Exception:
        parsed_count = 0
    meta = {
        "source": "pdf",
        "confidence": merged_signal["confidence"],
        "score": merged_signal["score"],
        "selected_pages": [entry["page"] for entry in selected_entries],
        "total_pages": total_pages,
        "parsed_count": parsed_count,
    }
    return merged, meta


def extract_text_from_image_object(image):
    try:
        import pytesseract
        from pytesseract import TesseractNotFoundError
    except Exception:
        return ""

    try:
        gray = ImageOps.grayscale(image)
        upscaled = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)
        base = ImageOps.autocontrast(upscaled)
        strong = base.point(lambda x: 255 if x > 165 else 0)
        smooth = base.filter(ImageFilter.SHARPEN)

        variants = [base, strong, smooth]
        configs = [
            "--oem 3 --psm 6",
            "--oem 3 --psm 11",
            "--oem 3 --psm 4",
            "--oem 3 --psm 12",
        ]

        texts = []
        for variant in variants:
            for cfg in configs:
                out = pytesseract.image_to_string(variant, config=cfg)
                if out and out.strip():
                    texts.append(out)

        return choose_best_text(texts)
    except TesseractNotFoundError:
        raise ValueError("Image/PDF OCR needs Tesseract installed. Install it and retry.")
    except Exception:
        return ""


def extract_text_from_image_columns(image):
    try:
        import pytesseract
        from pytesseract import Output, TesseractNotFoundError
    except Exception:
        return ""

    try:
        gray = ImageOps.grayscale(image)
        upscaled = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)
        base = ImageOps.autocontrast(upscaled)
        data = pytesseract.image_to_data(base, config="--oem 3 --psm 6", output_type=Output.DICT)

        words = []
        total = len(data.get("text", []))
        for i in range(total):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except Exception:
                conf = -1
            if conf < 20:
                continue
            words.append(
                {
                    "text": text,
                    "x": int(data["left"][i]),
                    "y": int(data["top"][i]),
                    "w": int(data["width"][i]),
                    "h": int(data["height"][i]),
                }
            )

        if not words:
            return ""

        page_width = max((w["x"] + w["w"] for w in words), default=0)
        split_x = page_width // 2 if page_width else 0

        left_words = [w for w in words if (w["x"] + (w["w"] // 2)) <= split_x]
        right_words = [w for w in words if (w["x"] + (w["w"] // 2)) > split_x]

        def rows_to_text(column_words):
            if not column_words:
                return []
            col = sorted(column_words, key=lambda w: (w["y"], w["x"]))
            rows = []
            tolerance = max(10, int(sum(w["h"] for w in col) / max(1, len(col)) * 0.7))

            for w in col:
                cy = w["y"] + (w["h"] // 2)
                placed = False
                for row in rows:
                    if abs(cy - row["cy"]) <= tolerance:
                        row["items"].append(w)
                        row["cy"] = int((row["cy"] * row["count"] + cy) / (row["count"] + 1))
                        row["count"] += 1
                        placed = True
                        break
                if not placed:
                    rows.append({"cy": cy, "count": 1, "items": [w]})

            lines = []
            for row in sorted(rows, key=lambda r: r["cy"]):
                items = sorted(row["items"], key=lambda a: a["x"])
                joined = " ".join(item["text"] for item in items).strip()
                if joined:
                    lines.append(joined)
            return lines

        left_lines = rows_to_text(left_words)
        right_lines = rows_to_text(right_words)

        if not left_lines and not right_lines:
            return ""
        if left_lines and right_lines:
            return "\n".join(left_lines + [""] + right_lines)
        return "\n".join(left_lines or right_lines)
    except TesseractNotFoundError:
        raise ValueError("Image/PDF OCR needs Tesseract installed. Install it and retry.")
    except Exception:
        return ""


def extract_text_from_image(file_storage):
    image_bytes = file_storage.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = choose_best_transcript_text([extract_text_from_image_object(image), extract_text_from_image_columns(image)])
    if text.strip():
        signal = analyze_transcript_text_signal(text)
        try:
            parsed_count = len(parse_rows_from_text(text))
        except Exception:
            parsed_count = 0
        meta = {
            "source": "image",
            "confidence": signal["confidence"],
            "score": signal["score"],
            "selected_pages": [1],
            "total_pages": 1,
            "parsed_count": parsed_count,
        }
        return text, meta
    raise ValueError("Image OCR failed. Use a clearer image or upload CSV/manual input.")


def handle_retakes(rows):
    rows_sorted = sorted(rows, key=lambda r: semester_to_number(r["Semester"]))
    latest = {}
    retakes = {}
    for row in rows_sorted:
        code = row["Course_Code"]
        retakes.setdefault(code, []).append(row)
        latest[code] = row
    return latest, retakes


def count_credits(latest, waived=None):
    waived = waived or []
    total = 0
    for code, row in latest.items():
        if code in waived:
            total += row["Credits"]
        elif row["Grade"] not in {"F", "W"}:
            total += row["Credits"]
    return total


def calculate_cgpa(latest, waived=None):
    waived = waived or []
    total_qp = 0.0
    total_ch = 0
    details = []

    for code in sorted(latest.keys()):
        row = latest[code]
        grade = row["Grade"]
        credits = row["Credits"]

        if code in waived:
            details.append({"course": code, "credits": credits, "grade": grade, "in_cgpa": "No", "reason": "Waived"})
            continue
        if grade == "W":
            details.append({"course": code, "credits": credits, "grade": grade, "in_cgpa": "No", "reason": "Withdrawal"})
            continue
        if credits == 0:
            details.append({"course": code, "credits": credits, "grade": grade, "in_cgpa": "No", "reason": "0-credit"})
            continue

        gp = GRADE_POINTS.get(grade, 0.0)
        quality = gp * credits
        total_qp += quality
        total_ch += credits
        details.append(
            {
                "course": code,
                "credits": credits,
                "grade": grade,
                "gp": f"{gp:.2f}",
                "quality": f"{quality:.2f}",
                "in_cgpa": "Yes",
                "reason": "",
            }
        )

    cgpa = total_qp / total_ch if total_ch else 0.0
    return cgpa, total_qp, total_ch, details


def run_audit(latest, program, waived):
    issues = []
    course_audit = []

    for category, courses in program["requirements"].items():
        for course in courses:
            if course in waived:
                course_audit.append({"category": category, "course": course, "status": "WAIVED", "details": "Requirement waived"})
            elif course not in latest:
                course_audit.append({"category": category, "course": course, "status": "MISSING", "details": "Not found in transcript"})
                issues.append(f"MISSING: {course} ({category})")
            elif latest[course]["Grade"] == "W":
                course_audit.append(
                    {
                        "category": category,
                        "course": course,
                        "status": "INCOMPLETE",
                        "details": f"Withdrawn in {latest[course]['Semester']}",
                    }
                )
                issues.append(f"INCOMPLETE: {course} ({category})")
            elif latest[course]["Grade"] == "F":
                course_audit.append(
                    {
                        "category": category,
                        "course": course,
                        "status": "FAILED",
                        "details": f"Failed in {latest[course]['Semester']}",
                    }
                )
                issues.append(f"FAILED: {course} ({category})")
            else:
                course_audit.append(
                    {
                        "category": category,
                        "course": course,
                        "status": "COMPLETED",
                        "details": f"{latest[course]['Grade']} ({latest[course]['Semester']})",
                    }
                )

    earned = count_credits(latest, waived)
    required = program["total_credits"]
    remaining = max(0, required - earned)
    if remaining:
        issues.append(f"CREDIT DEFICIENCY: Need {remaining} more credits")

    cgpa, _, _, _ = calculate_cgpa(latest, waived)
    if cgpa < 2.0:
        issues.append(f"PROBATION: CGPA {cgpa:.2f} is below 2.00")

    return {
        "course_audit": course_audit,
        "issues": issues,
        "earned": earned,
        "required": required,
        "remaining": remaining,
        "cgpa": cgpa,
        "eligible": len(issues) == 0,
    }


def parse_input_rows(input_method, request_files, request_form):
    if input_method == "manual":
        manual_text = request_form.get("manual_text", "")
        return read_rows_from_manual(manual_text), None, None, None, False

    if input_method == "csv":
        uploaded = request_files.get("csv_file")
        if not uploaded or uploaded.filename == "":
            raise ValueError("Please upload a CSV file.")
        return read_rows_from_csv_upload(uploaded), None, None, None, False

    if input_method == "pdf":
        uploaded = request_files.get("pdf_file")
        if not uploaded or uploaded.filename == "":
            raise ValueError("Please upload a PDF transcript.")
        text, meta = extract_text_from_pdf(uploaded)
        warning = build_signal_warning(meta, "PDF")
        preview = make_ocr_preview(text, meta=meta)
        parsed_rows = []
        try:
            parsed_rows = parse_rows_from_text(text)
        except Exception:
            parsed_rows = []
        preview_payload = build_ocr_preview_payload(text, parsed_rows, meta)
        if should_block_low_confidence(meta):
            return None, preview, preview_payload, warning, True
        if not parsed_rows:
            raise ValueError("Could not extract course rows from PDF/Image. Use a clearer file or upload CSV/manual input.")
        return parsed_rows, preview, preview_payload, warning, False

    if input_method == "image":
        uploaded = request_files.get("image_file")
        if not uploaded or uploaded.filename == "":
            raise ValueError("Please upload a transcript image.")
        text, meta = extract_text_from_image(uploaded)
        warning = build_signal_warning(meta, "Image")
        preview = make_ocr_preview(text, meta=meta)
        parsed_rows = []
        try:
            parsed_rows = parse_rows_from_text(text)
        except Exception:
            parsed_rows = []
        preview_payload = build_ocr_preview_payload(text, parsed_rows, meta)
        if should_block_low_confidence(meta):
            return None, preview, preview_payload, warning, True
        if not parsed_rows:
            raise ValueError("Could not extract course rows from PDF/Image. Use a clearer file or upload CSV/manual input.")
        return parsed_rows, preview, preview_payload, warning, False

    raise ValueError("Unsupported input method.")


def make_ocr_preview(text, limit=22000, meta=None):
    clean = "\n".join([line.rstrip() for line in text.splitlines()]).strip()
    if meta:
        pages = meta.get("selected_pages", [])
        header = (
            f"[OCR confidence: {meta.get('confidence', 'low').upper()} | "
            f"score: {meta.get('score', 0)} | pages: {pages}/{meta.get('total_pages', 0)}]"
        )
        clean = f"{header}\n\n{clean}" if clean else header
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "\n\n[...preview truncated...]"


def build_ocr_preview_payload(text, rows, meta=None):
    rows = rows or []

    name_map = {}
    details_map = {}
    for item in extract_structured_line_details(text):
        key = (item["course_code"], item["semester"])
        name_map[key] = item.get("course_name") or "-"
        details_map[key] = {
            "credit_counted": item.get("credit_counted", "-"),
            "credit_passed": item.get("credit_passed", "-"),
        }

    grouped = {}
    for row in sorted(rows, key=lambda r: (semester_to_number(r["Semester"]), r["Course_Code"])):
        sem = row["Semester"]
        key = (row["Course_Code"], sem)
        detail = details_map.get(key, {})
        grouped.setdefault(sem, []).append(
            {
                "course_code": row["Course_Code"],
                "course_name": name_map.get(key, "-"),
                "credit": row["Credits"],
                "grade": row["Grade"],
                "credit_counted": detail.get("credit_counted", "-"),
                "credit_passed": detail.get("credit_passed", "-"),
            }
        )

    semester_blocks = [{"semester": sem, "rows": grouped[sem]} for sem in sorted(grouped.keys(), key=semester_to_number)]

    summary_rows = []
    semester_re = re.compile(r"\b(Spring|Summer|Fall)\s*[-/ ]?\s*(\d{4})\b", re.IGNORECASE)
    current_semester = None
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        detected_semester = detect_semester_header(line, semester_re)
        if detected_semester:
            current_semester = detected_semester

        if not re.search(r"semester\s*credit|tgpa|cgpa", line, re.IGNORECASE):
            continue
        sc = re.search(r"semester\s*credit\s*:?\s*(\d+(?:\.\d+)?)", line, re.IGNORECASE)
        tg = re.search(r"tgpa\s*:?\s*(\d+(?:\.\d+)?)", line, re.IGNORECASE)
        cg = re.search(r"cgpa\s*:?\s*(\d+(?:\.\d+)?)", line, re.IGNORECASE)
        if sc or tg or cg:
            summary_rows.append(
                {
                    "semester": current_semester or "Unknown Semester",
                    "semester_credit": sc.group(1) if sc else "-",
                    "tgpa": tg.group(1) if tg else "-",
                    "cgpa": cg.group(1) if cg else "-",
                }
            )

    return {
        "meta": {
            "confidence": (meta or {}).get("confidence", "low").upper(),
            "score": (meta or {}).get("score", 0),
            "pages": (meta or {}).get("selected_pages", []),
            "total_pages": (meta or {}).get("total_pages", 0),
        },
        "detected_rows": len(rows),
        "semester_blocks": semester_blocks,
        "summary_rows": summary_rows,
    }


def extract_structured_line_details(text):
    semester_re = re.compile(r"\b(Spring|Summer|Fall)\s*[-/ ]?\s*(\d{4})\b", re.IGNORECASE)
    code_re = re.compile(r"(?<![A-Z0-9])([A-Z]{2,4}[0-9IOL]{3}[A-Z]?)(?![A-Z0-9])", re.IGNORECASE)
    number_re = re.compile(r"\d+(?:\.\d+)?")

    details = []
    current_semester = None
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        header_semester = detect_semester_header(line, semester_re)
        if header_semester:
            current_semester = header_semester
        if not current_semester:
            continue

        lowered = line.lower()
        if any(x in lowered for x in ["course title", "total credits", "end of transcript"]):
            continue

        code_hits = list(code_re.finditer(line))
        if not code_hits:
            continue

        for idx, hit in enumerate(code_hits):
            start = hit.start()
            end = code_hits[idx + 1].start() if idx + 1 < len(code_hits) else len(line)
            segment = line[start:end].strip()
            if len(segment) < 6:
                continue

            code = normalize_course_code_token(hit.group(1))
            if not code or is_suspicious_course_code(code):
                continue

            grade = detect_grade_with_fallback(segment)
            if not grade:
                continue
            if grade not in VALID_GRADES:
                continue

            gmatch = re.search(r"\b(A\-|A|B\+|BT|B00|BOO|B|B\-|C\+|C|C\-|D\+|D|F|W)\b", segment, re.IGNORECASE)
            if gmatch:
                before = segment[: gmatch.start()].strip()
                after = segment[gmatch.end() :].strip()
            else:
                before = segment.strip()
                after = segment.strip()
            numbers_before = [normalize_credit_token(n) for n in number_re.findall(before)]
            numbers_before = [n for n in numbers_before if n is not None]
            numbers_after = [normalize_credit_token(n) for n in number_re.findall(after)]
            numbers_after = [n for n in numbers_after if n is not None]
            if not numbers_before:
                continue

            credit_val = numbers_before[-1]
            cc_val = numbers_after[0] if len(numbers_after) >= 1 else None
            cp_val = numbers_after[1] if len(numbers_after) >= 2 else None

            name_part = before
            if numbers_before:
                num_token_re = re.compile(r"\b\d+(?:\.\d+)?\b")
                name_part = num_token_re.sub("", before).strip()
            name_part = re.sub(r"\s+", " ", name_part).strip(" -_|:")

            details.append(
                {
                    "semester": current_semester,
                    "course_code": code,
                    "course_name": name_part or "-",
                    "credit": f"{credit_val:.1f}" if credit_val is not None else "-",
                    "grade": grade,
                    "credit_counted": f"{cc_val:.1f}" if cc_val is not None else "-",
                    "credit_passed": f"{cp_val:.1f}" if cp_val is not None else "-",
                }
            )

    dedup = {}
    for item in details:
        dedup[(item["course_code"], item["semester"])] = item
    return list(dedup.values())


def parse_waived_courses(value):
    if not value:
        return []
    if isinstance(value, str):
        return [w.strip().upper() for w in value.split(",") if w.strip()]
    if isinstance(value, list):
        return [str(w).strip().upper() for w in value if str(w).strip()]
    raise ValueError("'waived' must be a comma-separated string or a list.")


def save_transcript_run(user_id, input_method, result):
    run = TranscriptRun(
        user_id=user_id,
        input_method=input_method,
        program=result["program_key"],
        cgpa=result["cgpa"],
        earned_credits=result["earned_credits"],
        required_credits=result["required_credits"],
        eligible=result["eligible"],
        issues_json=json.dumps(result["issues"]),
        waived_json=json.dumps(result["waived"]),
        transcript_json=json.dumps(result["rows"]),
    )
    db.session.add(run)
    db.session.commit()
    return run


def run_to_summary(run):
    return {
        "id": run.id,
        "input_method": run.input_method,
        "program": run.program,
        "cgpa": run.cgpa,
        "earned_credits": run.earned_credits,
        "required_credits": run.required_credits,
        "eligible": run.eligible,
        "created_at": run.created_at.isoformat(),
    }


def run_to_details(run):
    transcript_rows = json.loads(run.transcript_json)
    issues = json.loads(run.issues_json)
    waived = json.loads(run.waived_json)
    latest, _ = handle_retakes(transcript_rows)
    cgpa, total_qp, total_ch, cgpa_details = calculate_cgpa(latest, waived)
    return {
        "run": run_to_summary(run),
        "waived": waived,
        "issues": issues,
        "transcript_rows": transcript_rows,
        "latest_rows": [latest[k] for k in sorted(latest.keys())],
        "cgpa": round(cgpa, 2),
        "total_qp": round(total_qp, 2),
        "total_ch": total_ch,
        "cgpa_details": cgpa_details,
    }


def build_result(rows, program_key, waived, programs):
    latest, retakes = handle_retakes(rows)
    cgpa, total_qp, total_ch, cgpa_details = calculate_cgpa(latest, waived)
    audit_result = run_audit(latest, programs[program_key], waived)

    retake_summary = []
    for code, attempts in sorted(retakes.items()):
        if len(attempts) > 1:
            retake_summary.append({
                "course": code,
                "attempts": [f"{a['Grade']} ({a['Semester']})" for a in attempts],
            })

    return {
        "rows": rows,
        "program_key": program_key,
        "program": programs[program_key],
        "waived": waived,
        "latest_rows": [latest[key] for key in sorted(latest.keys())],
        "cgpa": round(cgpa, 2),
        "total_qp": round(total_qp, 2),
        "total_ch": total_ch,
        "earned_credits": audit_result["earned"],
        "required_credits": audit_result["required"],
        "remaining_credits": audit_result["remaining"],
        "eligible": audit_result["eligible"],
        "issues": audit_result["issues"],
        "course_audit": audit_result["course_audit"],
        "cgpa_details": cgpa_details,
        "retake_summary": retake_summary,
    }


def register_routes(app):
    programs = parse_program_knowledge(os.path.join(os.path.dirname(__file__), "program.md"))
    dhaka_tz = timezone(timedelta(hours=6))

    @app.template_filter("localtime")
    def localtime_filter(value, fmt="%Y-%m-%d %H:%M"):
        if not value:
            return ""
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(dhaka_tz).strftime(fmt)

    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/login")
    def login():
        if not oauth.google.client_id:
            flash("Google OAuth is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env", "error")
            return redirect(url_for("home"))
        redirect_uri = url_for("auth_callback", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route("/auth/callback")
    def auth_callback():
        token = oauth.google.authorize_access_token()
        user_info = token.get("userinfo")
        if not user_info:
            user_info = oauth.google.userinfo()

        email = user_info.get("email", "").lower().strip()
        if not email.endswith("@northsouth.edu"):
            flash("Only North South University Google accounts are allowed.", "error")
            return redirect(url_for("home"))

        google_sub = user_info.get("sub")
        if not google_sub:
            flash("Google profile data is incomplete. Please retry.", "error")
            return redirect(url_for("home"))

        user = User.query.filter_by(google_sub=google_sub).first()
        if not user:
            user = User(
                google_sub=google_sub,
                email=email,
                name=user_info.get("name", email.split("@")[0]),
                avatar_url=user_info.get("picture"),
            )
            db.session.add(user)
        else:
            user.email = email
            user.name = user_info.get("name", user.name)
            user.avatar_url = user_info.get("picture") or user.avatar_url

        db.session.commit()
        login_user(user)
        return redirect(url_for("dashboard"))

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        session.clear()
        flash("Signed out successfully.", "success")
        return redirect(url_for("home"))

    @app.route("/dashboard", methods=["GET", "POST"])
    @login_required
    def dashboard():
        result = None
        ocr_preview = None
        ocr_preview_payload = None
        ocr_warning = None
        analysis_blocked = False
        selected_input = "manual"
        if request.method == "POST":
            try:
                input_method = request.form.get("input_method", "manual")
                selected_input = input_method
                program_key = request.form.get("program", "CSE")
                waived_raw = request.form.get("waived", "")
                waived = parse_waived_courses(waived_raw)

                rows, ocr_preview, ocr_preview_payload, ocr_warning, analysis_blocked = parse_input_rows(
                    input_method, request.files, request.form
                )
                if analysis_blocked:
                    flash(
                        "Analysis blocked due to low OCR confidence. Please upload a clearer PDF/Image or use CSV/manual input.",
                        "error",
                    )
                    if ocr_warning:
                        flash(ocr_warning, "warning")
                    return render_template(
                        "dashboard.html",
                        programs=programs,
                        result=None,
                        ocr_preview=ocr_preview,
                        ocr_preview_payload=ocr_preview_payload,
                        ocr_warning=ocr_warning,
                        selected_input=selected_input,
                    )

                if input_method in {"pdf", "image"} and len(rows) < 8:
                    flash(
                        f"Only {len(rows)} course rows were extracted from OCR. Please review OCR Preview and verify the output.",
                        "warning",
                    )

                result = build_result(rows, program_key, waived, programs)
                result["input_method"] = input_method
                result["ocr_preview"] = ocr_preview
                result["ocr_preview_payload"] = ocr_preview_payload
                result["ocr_warning"] = ocr_warning

                save_transcript_run(current_user.id, input_method, result)
                if ocr_warning:
                    flash(ocr_warning, "warning")
                flash("Transcript processed and saved to your history.", "success")

            except Exception as exc:
                flash(str(exc), "error")

        return render_template(
            "dashboard.html",
            programs=programs,
            result=result,
            ocr_preview=ocr_preview,
            ocr_preview_payload=ocr_preview_payload,
            ocr_warning=ocr_warning,
            selected_input=selected_input,
        )

    @app.route("/history")
    @login_required
    def history():
        runs = TranscriptRun.query.filter_by(user_id=current_user.id).order_by(TranscriptRun.created_at.desc()).all()
        return render_template("history.html", runs=runs)

    @app.route("/history/<int:run_id>")
    @login_required
    def history_details(run_id):
        run = TranscriptRun.query.filter_by(id=run_id, user_id=current_user.id).first_or_404()
        details = run_to_details(run)
        return render_template(
            "history_details.html",
            run=run,
            transcript_rows=details["transcript_rows"],
            latest_rows=details["latest_rows"],
            issues=details["issues"],
            waived=details["waived"],
            cgpa=details["cgpa"],
            cgpa_details=details["cgpa_details"],
        )

    @app.route("/api/analyze", methods=["POST"])
    @login_required
    def api_analyze():
        payload = request.get_json(silent=True) or {}
        input_method = str(payload.get("input_method", "manual")).strip().lower()
        program_key = str(payload.get("program", "CSE")).strip().upper()

        if program_key not in programs:
            return jsonify({"ok": False, "error": f"Unknown program '{program_key}'"}), 400

        try:
            waived = parse_waived_courses(payload.get("waived", []))

            if input_method == "manual":
                rows = read_rows_from_manual(str(payload.get("manual_text", "")))
            elif input_method == "csv":
                rows = read_rows_from_csv_text(str(payload.get("csv_text", "")))
            else:
                return jsonify({"ok": False, "error": "API currently supports input_method: manual or csv"}), 400

            result = build_result(rows, program_key, waived, programs)
            run = save_transcript_run(current_user.id, input_method, result)

            return jsonify(
                {
                    "ok": True,
                    "run_id": run.id,
                    "result": {
                        "input_method": input_method,
                        "program": result["program_key"],
                        "cgpa": result["cgpa"],
                        "earned_credits": result["earned_credits"],
                        "required_credits": result["required_credits"],
                        "remaining_credits": result["remaining_credits"],
                        "eligible": result["eligible"],
                        "waived": result["waived"],
                        "issues": result["issues"],
                        "latest_rows": result["latest_rows"],
                        "course_audit": result["course_audit"],
                        "retake_summary": result["retake_summary"],
                    },
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.route("/api/mobile/auth/google", methods=["POST"])
    def api_mobile_auth_google():
        payload = request.get_json(silent=True) or {}
        id_token = str(payload.get("id_token", "")).strip()
        if not id_token:
            return jsonify({"ok": False, "error": "id_token is required"}), 400

        audience = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        if not audience:
            return jsonify({"ok": False, "error": "GOOGLE_CLIENT_ID is not configured"}), 500

        try:
            tokeninfo = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
                timeout=8,
            )
            tokeninfo.raise_for_status()
            data = tokeninfo.json() or {}
        except Exception:
            return jsonify({"ok": False, "error": "Failed to verify Google token"}), 401

        aud = str(data.get("aud", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        sub = str(data.get("sub", "")).strip()
        name = str(data.get("name", "")).strip() or (email.split("@")[0] if email else "NSU User")
        avatar_url = str(data.get("picture", "")).strip() or None

        if aud != audience:
            return jsonify({"ok": False, "error": "Token audience mismatch"}), 401
        if not sub or not email:
            return jsonify({"ok": False, "error": "Google token missing user fields"}), 401
        if not email.endswith("@northsouth.edu"):
            return jsonify({"ok": False, "error": "Only North South University accounts are allowed"}), 403

        user = User.query.filter_by(google_sub=sub).first()
        if not user:
            user = User(google_sub=sub, email=email, name=name, avatar_url=avatar_url)
            db.session.add(user)
        else:
            user.email = email
            user.name = name or user.name
            user.avatar_url = avatar_url or user.avatar_url
        db.session.commit()

        token = issue_mobile_token(user)
        return jsonify(
            {
                "ok": True,
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": int(os.getenv("MOBILE_TOKEN_MAX_AGE_SECONDS", "2592000") or "2592000"),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "avatar_url": user.avatar_url,
                },
            }
        )

    @app.route("/api/mobile/auth/email", methods=["POST"])
    def api_mobile_auth_email():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "") or "").strip().lower()
        name = str(payload.get("name", "") or "").strip()

        if not email:
            return jsonify({"ok": False, "error": "email is required"}), 400
        if not email.endswith("@northsouth.edu"):
            return jsonify({"ok": False, "error": "Only North South University accounts are allowed"}), 403

        fallback_sub = f"email:{email}"
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User.query.filter_by(google_sub=fallback_sub).first()

        if not user:
            user = User(
                google_sub=fallback_sub,
                email=email,
                name=name or email.split("@")[0],
                avatar_url=None,
            )
            db.session.add(user)
        else:
            user.email = email
            if name:
                user.name = name

        db.session.commit()

        token = issue_mobile_token(user)
        return jsonify(
            {
                "ok": True,
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": int(os.getenv("MOBILE_TOKEN_MAX_AGE_SECONDS", "2592000") or "2592000"),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "avatar_url": user.avatar_url,
                },
            }
        )

    @app.route("/api/mobile/auth/me", methods=["GET"])
    def api_mobile_auth_me():
        try:
            user = resolve_mobile_auth_user(request)
            return jsonify(
                {
                    "ok": True,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "avatar_url": user.avatar_url,
                    },
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 401

    @app.route("/api/mobile/analyze", methods=["POST"])
    def api_mobile_analyze():
        payload = request.get_json(silent=True) or {}
        input_method = str(payload.get("input_method", "manual")).strip().lower()
        program_key = str(payload.get("program", "CSE")).strip().upper()
        try:
            user = resolve_mobile_auth_user(request)
            user_id = int(user.id)
        except Exception:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        if program_key not in programs:
            return jsonify({"ok": False, "error": f"Unknown program '{program_key}'"}), 400

        try:
            waived = parse_waived_courses(payload.get("waived", []))

            if input_method == "manual":
                rows = read_rows_from_manual(str(payload.get("manual_text", "")))
            elif input_method == "csv":
                rows = read_rows_from_csv_text(str(payload.get("csv_text", "")))
            else:
                return jsonify({"ok": False, "error": "Mobile API supports input_method: manual or csv"}), 400

            result = build_result(rows, program_key, waived, programs)
            run = save_transcript_run(user_id, input_method, result)

            return jsonify(
                {
                    "ok": True,
                    "run_id": run.id,
                    "result": {
                        "input_method": input_method,
                        "program": result["program_key"],
                        "cgpa": result["cgpa"],
                        "earned_credits": result["earned_credits"],
                        "required_credits": result["required_credits"],
                        "remaining_credits": result["remaining_credits"],
                        "eligible": result["eligible"],
                        "waived": result["waived"],
                        "issues": result["issues"],
                        "latest_rows": result["latest_rows"],
                        "course_audit": result["course_audit"],
                        "retake_summary": result["retake_summary"],
                    },
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.route("/api/mobile/history", methods=["GET"])
    def api_mobile_history():
        try:
            user = resolve_mobile_auth_user(request)
            user_id = int(user.id)
        except Exception:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        runs = TranscriptRun.query.filter_by(user_id=user_id).order_by(TranscriptRun.created_at.desc()).all()
        return jsonify({"ok": True, "count": len(runs), "runs": [run_to_summary(run) for run in runs]})

    @app.route("/api/mobile/history/<int:run_id>", methods=["GET"])
    def api_mobile_history_details(run_id):
        try:
            user = resolve_mobile_auth_user(request)
            user_id = int(user.id)
        except Exception:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        run = TranscriptRun.query.filter_by(id=run_id, user_id=user_id).first()
        if not run:
            return jsonify({"ok": False, "error": "Run not found"}), 404
        return jsonify({"ok": True, **run_to_details(run)})

    @app.route("/api/mobile/ocr/extract", methods=["POST"])
    def api_mobile_ocr_extract():
        try:
            resolve_mobile_auth_user(request)
        except Exception:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        input_method = str(request.form.get("input_method", "")).strip().lower()
        source_label = str(request.form.get("source_label", "Transcript") or "Transcript").strip()
        if input_method not in {"pdf", "image"}:
            return jsonify({"ok": False, "error": "input_method must be 'pdf' or 'image'"}), 400

        file_key = "pdf_file" if input_method == "pdf" else "image_file"
        uploaded = request.files.get(file_key) or request.files.get("file")
        if not uploaded or uploaded.filename == "":
            return jsonify({"ok": False, "error": f"Missing upload for {file_key}"}), 400

        try:
            if input_method == "pdf":
                raw_text, meta = extract_text_from_pdf(uploaded)
            else:
                raw_text, meta = extract_text_from_image(uploaded)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        rows = []
        try:
            rows = parse_rows_from_text(raw_text)
        except Exception:
            rows = []

        signal = analyze_transcript_text_signal(raw_text)
        detected_rows = len(rows)
        confidence = str((meta or {}).get("confidence") or signal.get("confidence", "low")).upper()
        score = int((meta or {}).get("score", signal.get("score", 0)))
        effective_meta = {
            "source": input_method,
            "confidence": confidence.lower(),
            "score": score,
            "selected_pages": (meta or {}).get("selected_pages", [1]),
            "total_pages": (meta or {}).get("total_pages", 1),
            "parsed_count": detected_rows,
        }
        blocked = should_block_low_confidence(effective_meta)
        warning = build_signal_warning(effective_meta, source_label)
        preview = make_ocr_preview(raw_text, meta=effective_meta)
        manual_text = "\n".join(
            [f"{r['Course_Code']}, {r['Credits']}, {r['Grade']}, {r['Semester']}" for r in rows]
        )

        return jsonify(
            {
                "ok": True,
                "manual_text": manual_text,
                "confidence": confidence,
                "score": score,
                "detected_rows": detected_rows,
                "blocked": blocked,
                "warning": warning,
                "preview": preview,
            }
        )

    @app.route("/api/mobile/ai/chat", methods=["POST"])
    def api_mobile_ai_chat():
        from ai.mcp_client import MCPClientError
        from ai.orchestrator import MCPGuardrailError, build_orchestrator

        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "") or "").strip()
        context = payload.get("context", {})
        if not isinstance(context, dict):
            context = {}

        try:
            user = resolve_mobile_auth_user(request)
            user_id = str(user.id)
        except Exception:
            return jsonify({"reply": "Sign in required for chat", "tool_trace": [], "request_id": "-", "fallback_used": True}), 401

        if not message:
            return jsonify({"reply": "Message is required", "tool_trace": [], "request_id": "-", "fallback_used": True}), 400

        orchestrator = build_orchestrator()
        try:
            result = orchestrator.chat(message=message, user_id=user_id, context=context)
            return jsonify(
                {
                    "reply": result.get("reply", ""),
                    "tool_trace": result.get("tool_trace", []),
                    "request_id": result.get("request_id", "-"),
                    "fallback_used": bool(result.get("fallback_used", False)),
                }
            )
        except MCPGuardrailError as exc:
            return jsonify(
                {
                    "reply": f"Tool blocked: {exc.message}",
                    "tool_trace": [{"tool": "guardrail", "status": exc.code.lower(), "latency_ms": 0}],
                    "request_id": "-",
                    "fallback_used": True,
                }
            )
        except MCPClientError:
            return jsonify(
                {
                    "reply": "I could not complete tool execution right now. Please retry.",
                    "tool_trace": [{"tool": "transcript_lookup", "status": "error", "latency_ms": 0}],
                    "request_id": "-",
                    "fallback_used": True,
                }
            )
        except Exception:
            return jsonify(
                {
                    "reply": "Unexpected backend error while processing chat.",
                    "tool_trace": [{"tool": "chat", "status": "error", "latency_ms": 0}],
                    "request_id": "-",
                    "fallback_used": True,
                }
            )

    @app.route("/api/health", methods=["GET"])
    def api_health():
        return jsonify(
            {
                "ok": True,
                "service": "nsu-transcript-analyzer",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "authenticated": current_user.is_authenticated,
            }
        )

    @app.route("/api/ocr/parse", methods=["POST"])
    def api_ocr_parse():
        payload = request.get_json(silent=True) or {}
        raw_text = str(payload.get("raw_text", "") or "")
        source_label = str(payload.get("source_label", "Image") or "Image").strip() or "Image"

        if not raw_text.strip():
            return jsonify({"ok": False, "error": "raw_text is required"}), 400

        rows = []
        try:
            rows = parse_rows_from_text(raw_text)
        except Exception:
            rows = []

        signal = analyze_transcript_text_signal(raw_text)
        confidence = signal.get("confidence", "low")
        parsed_count = len(rows)
        meta = {
            "source": "ocr-parse",
            "confidence": confidence,
            "score": signal.get("score", 0),
            "selected_pages": [1],
            "total_pages": 1,
            "parsed_count": parsed_count,
        }
        warning = build_signal_warning(meta, source_label)
        blocked = should_block_low_confidence(meta)
        manual_text = "\n".join(
            [f"{r['Course_Code']}, {r['Credits']}, {r['Grade']}, {r['Semester']}" for r in rows]
        )
        preview = make_ocr_preview(raw_text, meta=meta)

        return jsonify(
            {
                "ok": True,
                "manual_text": manual_text,
                "confidence": str(confidence).upper(),
                "score": int(signal.get("score", 0)),
                "detected_rows": parsed_count,
                "blocked": blocked,
                "warning": warning,
                "preview": preview,
            }
        )

    @app.route("/api/history", methods=["GET"])
    @login_required
    def api_history():
        runs = TranscriptRun.query.filter_by(user_id=current_user.id).order_by(TranscriptRun.created_at.desc()).all()
        return jsonify({"ok": True, "count": len(runs), "runs": [run_to_summary(run) for run in runs]})

    @app.route("/api/history/<int:run_id>", methods=["GET"])
    @login_required
    def api_history_details(run_id):
        run = TranscriptRun.query.filter_by(id=run_id, user_id=current_user.id).first()
        if not run:
            return jsonify({"ok": False, "error": "Run not found"}), 404
        return jsonify({"ok": True, **run_to_details(run)})


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

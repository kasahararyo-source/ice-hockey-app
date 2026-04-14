from flask import Flask, render_template, request, redirect, url_for, session, g
import os
import hashlib
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ice_hockey_attendance_secret_2026")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL が設定されていません")

ADMIN_PIN_HASH = hashlib.sha256("260410".encode("utf-8")).hexdigest()


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


DEFAULT_MEMBERS = [
    {"name": "大池音々", "pin_hash": hash_pin("110137")},
    {"name": "森田健友", "pin_hash": hash_pin("220284")},
    {"name": "美馬碧仁", "pin_hash": hash_pin("330451")},
    {"name": "荻原瑛史", "pin_hash": hash_pin("440618")},
    {"name": "尾山旭", "pin_hash": hash_pin("550782")},
    {"name": "笠原現", "pin_hash": hash_pin("660945")},
]


def get_db():
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                pin_hash TEXT NOT NULL,
                created_at TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS practices (
                id SERIAL PRIMARY KEY,
                practice_date TEXT NOT NULL,
                practice_time TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                practice_id INTEGER NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
                member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                status TEXT,
                UNIQUE(practice_id, member_id)
            )
        """)

    db.commit()
    seed_default_members()
    migrate_existing_data()


def seed_default_members():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM members")
        count = cur.fetchone()["cnt"]

        if count == 0:
            now = datetime.now().isoformat()
            for member in DEFAULT_MEMBERS:
                cur.execute(
                    "INSERT INTO members (name, pin_hash, created_at) VALUES (%s, %s, %s)",
                    (member["name"], member["pin_hash"], now)
                )

    db.commit()


def migrate_existing_data():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id FROM members ORDER BY id")
        members = cur.fetchall()

        cur.execute("SELECT id FROM practices ORDER BY practice_date ASC, practice_time ASC")
        practices = cur.fetchall()

        for practice in practices:
            for member in members:
                cur.execute(
                    "SELECT 1 FROM attendance WHERE practice_id = %s AND member_id = %s",
                    (practice["id"], member["id"])
                )
                exists = cur.fetchone()

                if not exists:
                    cur.execute(
                        "INSERT INTO attendance (practice_id, member_id, status) VALUES (%s, %s, %s)",
                        (practice["id"], member["id"], None)
                    )

    db.commit()


def format_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weeks = ["月", "火", "水", "木", "金", "土", "日"]
        return f"{dt.month}/{dt.day}({weeks[dt.weekday()]})"
    except Exception:
        return date_str


def is_admin():
    return session.get("role") == "admin"


def is_member():
    return session.get("role") == "member" and session.get("member_id") is not None


def build_summary_for_practices(practices):
    db = get_db()
    summary = {}

    with db.cursor() as cur:
        for practice in practices:
            cur.execute("""
                SELECT m.name, a.status
                FROM attendance a
                JOIN members m ON a.member_id = m.id
                WHERE a.practice_id = %s
                ORDER BY m.id ASC
            """, (practice["id"],))
            rows = cur.fetchall()

            attend_members = [r["name"] for r in rows if r["status"] == "attend"]
            absent_members = [r["name"] for r in rows if r["status"] == "absent"]

            total_answered = len(attend_members) + len(absent_members)
            attend_rate = round((len(attend_members) / total_answered) * 100) if total_answered > 0 else 0

            summary[practice["id"]] = {
                "attend": len(attend_members),
                "absent": len(absent_members),
                "attend_members": attend_members,
                "absent_members": absent_members,
                "attend_rate": attend_rate,
            }

    return summary


@app.context_processor
def inject_helpers():
    return {"format_date": format_date}


@app.route("/")
def home():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id, name FROM members ORDER BY id")
        members = cur.fetchall()

    return render_template("index.html", page="home", members=members)


@app.route("/login/admin", methods=["POST"])
def login_admin():
    pin = request.form.get("pin", "").strip()

    if hash_pin(pin) == ADMIN_PIN_HASH:
        session.clear()
        session["role"] = "admin"
        return redirect(url_for("admin_page"))

    return redirect(url_for("home"))


@app.route("/login/member", methods=["POST"])
def login_member():
    member_id = request.form.get("member_id", "").strip()
    pin = request.form.get("pin", "").strip()

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, name, pin_hash FROM members WHERE id = %s",
            (member_id,)
        )
        member = cur.fetchone()

    if member and member["pin_hash"] == hash_pin(pin):
        session.clear()
        session["role"] = "member"
        session["member_id"] = member["id"]
        session["member_name"] = member["name"]
        return redirect(url_for("member_page"))

    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
def admin_page():
    if not is_admin():
        return redirect(url_for("home"))

    today = datetime.now().strftime("%Y-%m-%d")
    db = get_db()

    with db.cursor() as cur:
        cur.execute("""
            SELECT id, practice_date, practice_time
            FROM practices
            WHERE practice_date >= %s
            ORDER BY practice_date ASC, practice_time ASC
        """, (today,))
        upcoming_practices = cur.fetchall()

        cur.execute("""
            SELECT id, practice_date, practice_time
            FROM practices
            WHERE practice_date < %s
            ORDER BY practice_date DESC, practice_time DESC
        """, (today,))
        past_practices = cur.fetchall()

        cur.execute("""
            SELECT id, name
            FROM members
            ORDER BY id ASC
        """)
        members = cur.fetchall()

    upcoming_summary = build_summary_for_practices(upcoming_practices)
    past_summary = build_summary_for_practices(past_practices)

    return render_template(
        "index.html",
        page="admin",
        upcoming_practices=upcoming_practices,
        past_practices=past_practices,
        members=members,
        upcoming_summary=upcoming_summary,
        past_summary=past_summary,
    )


@app.route("/admin/practice/add", methods=["POST"])
def add_practice():
    if not is_admin():
        return redirect(url_for("home"))

    practice_date = request.form.get("practice_date", "").strip()
    practice_time = request.form.get("practice_time", "").strip()

    if practice_date and practice_time:
        db = get_db()
        with db.cursor() as cur:
            now = datetime.now().isoformat()
            cur.execute(
                "INSERT INTO practices (practice_date, practice_time, created_at) VALUES (%s, %s, %s) RETURNING id",
                (practice_date, practice_time, now)
            )
            practice_id = cur.fetchone()["id"]

            cur.execute("SELECT id FROM members ORDER BY id")
            members = cur.fetchall()

            for member in members:
                cur.execute(
                    "INSERT INTO attendance (practice_id, member_id, status) VALUES (%s, %s, %s)",
                    (practice_id, member["id"], None)
                )

        db.commit()

    return redirect(url_for("admin_page"))


@app.route("/admin/practice/edit/<int:practice_id>", methods=["POST"])
def edit_practice(practice_id):
    if not is_admin():
        return redirect(url_for("home"))

    practice_date = request.form.get("practice_date", "").strip()
    practice_time = request.form.get("practice_time", "").strip()

    if practice_date and practice_time:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                UPDATE practices
                SET practice_date = %s, practice_time = %s
                WHERE id = %s
            """, (practice_date, practice_time, practice_id))

        db.commit()

    return redirect(url_for("admin_page"))


@app.route("/admin/practice/delete/<int:practice_id>", methods=["POST"])
def delete_practice(practice_id):
    if not is_admin():
        return redirect(url_for("home"))

    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM attendance WHERE practice_id = %s", (practice_id,))
        cur.execute("DELETE FROM practices WHERE id = %s", (practice_id,))

    db.commit()
    return redirect(url_for("admin_page"))


@app.route("/admin/member/add", methods=["POST"])
def add_member():
    if not is_admin():
        return redirect(url_for("home"))

    name = request.form.get("name", "").strip()
    pin = request.form.get("pin", "").strip()

    if name and pin:
        db = get_db()
        try:
            with db.cursor() as cur:
                now = datetime.now().isoformat()
                cur.execute(
                    "INSERT INTO members (name, pin_hash, created_at) VALUES (%s, %s, %s) RETURNING id",
                    (name, hash_pin(pin), now)
                )
                member_id = cur.fetchone()["id"]

                cur.execute("SELECT id FROM practices ORDER BY id")
                practices = cur.fetchall()

                for practice in practices:
                    cur.execute(
                        "INSERT INTO attendance (practice_id, member_id, status) VALUES (%s, %s, %s)",
                        (practice["id"], member_id, None)
                    )

            db.commit()

        except Exception:
            db.rollback()

    return redirect(url_for("admin_page"))


@app.route("/member")
def member_page():
    if not is_member():
        return redirect(url_for("home"))

    today = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    member_id = session["member_id"]

    with db.cursor() as cur:
        cur.execute("""
            SELECT
                p.id,
                p.practice_date,
                p.practice_time,
                a.status
            FROM practices p
            LEFT JOIN attendance a
                ON p.id = a.practice_id
            WHERE a.member_id = %s
              AND p.practice_date >= %s
            ORDER BY p.practice_date ASC, p.practice_time ASC
        """, (member_id, today))
        practices = cur.fetchall()

    return render_template(
        "index.html",
        page="member",
        practices=practices,
        member_name=session.get("member_name", "")
    )


@app.route("/member/attendance/<int:practice_id>", methods=["POST"])
def update_attendance(practice_id):
    if not is_member():
        return redirect(url_for("home"))

    status = request.form.get("status", "").strip()
    if status not in ("attend", "absent"):
        return redirect(url_for("member_page"))

    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            UPDATE attendance
            SET status = %s
            WHERE practice_id = %s AND member_id = %s
        """, (status, practice_id, session["member_id"]))

    db.commit()
    return redirect(url_for("member_page"))


with app.app_context():
    init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

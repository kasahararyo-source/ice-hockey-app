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

ADMIN_PIN_HASH = hashlib.sha256("260410".encode()).hexdigest()


def hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()


DEFAULT_MEMBERS = [
    {"name": "大池音々", "pin_hash": hash_pin("110137")},
    {"name": "森田健友", "pin_hash": hash_pin("220284")},
    {"name": "美馬碧仁", "pin_hash": hash_pin("330451")},
    {"name": "荻原瑛史", "pin_hash": hash_pin("440618")},
    {"name": "尾山旭", "pin_hash": hash_pin("550782")},
    {"name": "笠原現", "pin_hash": hash_pin("660945")},
]


# ---------------- DB ----------------

def get_db():
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                pin_hash TEXT,
                created_at TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS practices (
                id SERIAL PRIMARY KEY,
                practice_date TEXT,
                practice_time TEXT,
                created_at TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                practice_id INTEGER,
                member_id INTEGER,
                status TEXT,
                UNIQUE(practice_id, member_id)
            )
        """)

    db.commit()
    seed_members()
    migrate()


def seed_members():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM members")
        count = cur.fetchone()["count"]

        if count == 0:
            now = datetime.now().isoformat()
            for m in DEFAULT_MEMBERS:
                cur.execute(
                    "INSERT INTO members (name, pin_hash, created_at) VALUES (%s,%s,%s)",
                    (m["name"], m["pin_hash"], now)
                )
    db.commit()


def migrate():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id FROM members")
        members = cur.fetchall()

        cur.execute("SELECT id FROM practices")
        practices = cur.fetchall()

        for p in practices:
            for m in members:
                cur.execute(
                    "SELECT 1 FROM attendance WHERE practice_id=%s AND member_id=%s",
                    (p["id"], m["id"])
                )
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO attendance (practice_id, member_id, status) VALUES (%s,%s,%s)",
                        (p["id"], m["id"], None)
                    )
    db.commit()


# ---------------- Utility ----------------

def format_date(d):
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        w = ["月","火","水","木","金","土","日"]
        return f"{dt.month}/{dt.day}({w[dt.weekday()]})"
    except:
        return d


@app.context_processor
def util():
    return {"format_date": format_date}


def is_admin():
    return session.get("role") == "admin"


def is_member():
    return session.get("role") == "member"


# ---------------- Routes ----------------

@app.route("/")
def home():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id,name FROM members ORDER BY id")
        members = cur.fetchall()

    return render_template("index.html", page="home", members=members)


@app.route("/login/admin", methods=["POST"])
def admin_login():
    pin = request.form.get("pin")

    if hash_pin(pin) == ADMIN_PIN_HASH:
        session.clear()
        session["role"] = "admin"
        return redirect("/admin")

    return redirect("/")


@app.route("/login/member", methods=["POST"])
def member_login():
    mid = request.form.get("member_id")
    pin = request.form.get("pin")

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM members WHERE id=%s", (mid,))
        m = cur.fetchone()

    if m and m["pin_hash"] == hash_pin(pin):
        session.clear()
        session["role"] = "member"
        session["member_id"] = m["id"]
        session["member_name"] = m["name"]
        return redirect("/member")

    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- Admin ----------------

@app.route("/admin")
def admin():
    if not is_admin():
        return redirect("/")

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM practices ORDER BY practice_date")
        practices = cur.fetchall()

        cur.execute("SELECT * FROM members")
        members = cur.fetchall()

    return render_template("index.html", page="admin", practices=practices, members=members)


@app.route("/admin/add", methods=["POST"])
def add():
    if not is_admin():
        return redirect("/")

    d = request.form.get("date")
    t = request.form.get("time")

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO practices (practice_date,practice_time,created_at) VALUES (%s,%s,%s) RETURNING id",
            (d, t, datetime.now().isoformat())
        )
        pid = cur.fetchone()["id"]

        cur.execute("SELECT id FROM members")
        members = cur.fetchall()

        for m in members:
            cur.execute(
                "INSERT INTO attendance (practice_id,member_id,status) VALUES (%s,%s,%s)",
                (pid, m["id"], None)
            )

    db.commit()
    return redirect("/admin")


# ---------------- Member ----------------

@app.route("/member")
def member():
    if not is_member():
        return redirect("/")

    db = get_db()
    mid = session["member_id"]

    with db.cursor() as cur:
        cur.execute("""
            SELECT p.id,p.practice_date,p.practice_time,a.status
            FROM practices p
            LEFT JOIN attendance a ON p.id=a.practice_id
            WHERE a.member_id=%s
            ORDER BY p.practice_date
        """, (mid,))
        data = cur.fetchall()

    return render_template("index.html", page="member", practices=data, member_name=session["member_name"])


@app.route("/member/update/<int:pid>", methods=["POST"])
def update(pid):
    if not is_member():
        return redirect("/")

    status = request.form.get("status")

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE attendance SET status=%s WHERE practice_id=%s AND member_id=%s",
            (status, pid, session["member_id"])
        )

    db.commit()
    return redirect("/member")


# ---------------- Init ----------------

with app.app_context():
    init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

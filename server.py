from flask import Flask, render_template, request, redirect, url_for, session, g
import sqlite3
import hashlib

app = Flask(__name__)
app.secret_key = "secret_key_2026"
DATABASE = "attendance_v2.db"

ADMIN_PIN = hashlib.sha256("260410".encode()).hexdigest()

def hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = get_db()

    db.execute("CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY, name TEXT, pin TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS practices (id INTEGER PRIMARY KEY, date TEXT, time TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS attendance (practice_id INTEGER, member_id INTEGER, status TEXT)")

    db.commit()

@app.route("/")
def home():
    db = get_db()
    members = db.execute("SELECT * FROM members").fetchall()
    return render_template("index.html", page="home", members=members)

@app.route("/login/admin", methods=["POST"])
def admin_login():
    if hash_pin(request.form["pin"]) == ADMIN_PIN:
        session["role"] = "admin"
        return redirect("/admin")
    return redirect("/")

@app.route("/login/member", methods=["POST"])
def member_login():
    db = get_db()
    m = db.execute("SELECT * FROM members WHERE id=?", (request.form["member_id"],)).fetchone()

    if m and m["pin"] == hash_pin(request.form["pin"]):
        session["role"] = "member"
        session["member_id"] = m["id"]
        session["member_name"] = m["name"]
        return redirect("/member")

    return redirect("/")

@app.route("/admin")
def admin():
    db = get_db()

    practices = db.execute("SELECT * FROM practices").fetchall()
    members = db.execute("SELECT * FROM members").fetchall()

    summary = {}

    for p in practices:
        rows = db.execute("""
            SELECT m.name, a.status
            FROM attendance a
            JOIN members m ON a.member_id = m.id
            WHERE a.practice_id = ?
        """, (p["id"],)).fetchall()

        attend = [r["name"] for r in rows if r["status"] == "attend"]
        absent = [r["name"] for r in rows if r["status"] == "absent"]
        unanswered = [r["name"] for r in rows if r["status"] is None]

        summary[p["id"]] = {
            "attend": len(attend),
            "absent": len(absent),
            "unanswered": len(unanswered),
            "attend_members": attend,
            "absent_members": absent,
            "unanswered_members": unanswered
        }

    return render_template("index.html", page="admin", practices=practices, members=members, summary=summary)

@app.route("/member")
def member():
    db = get_db()
    practices = db.execute("SELECT * FROM practices").fetchall()
    return render_template("index.html", page="member", practices=practices)

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

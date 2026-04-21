import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row


JST = ZoneInfo("Asia/Tokyo")


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} が設定されていません")
    return value


def get_db_connection():
    return psycopg.connect(get_env("DATABASE_URL"))


def get_today_jst():
    return datetime.now(JST).strftime("%Y-%m-%d")


def fetch_today_attendance_rows():
    today = get_today_jst()

    query = """
        SELECT
            p.practice_time,
            m.name,
            a.status
        FROM practices p
        LEFT JOIN attendance a ON p.id = a.practice_id
        LEFT JOIN members m ON a.member_id = m.id
        WHERE p.practice_date = %s
        ORDER BY m.id ASC
    """

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (today,))
            return cur.fetchall()


def build_body(today, rows):
    practice_time = rows[0]["practice_time"] or "未設定"

    attend, absent, pending = [], [], []

    for r in rows:
        name = r["name"] or "名称未設定"
        status = r["status"]

        if status == "attend":
            attend.append(f"・{name}")
        elif status == "absent":
            absent.append(f"・{name}")
        else:
            pending.append(f"・{name}")

    return f"""本日（{today}）の出欠状況です。

■練習時間
{practice_time}

■参加
{chr(10).join(attend) or '・なし'}

■不参加
{chr(10).join(absent) or '・なし'}

■未回答
{chr(10).join(pending) or '・なし'}

このメールは自動送信です。
"""


def send_email(subject, body):
    user = get_env("GMAIL_USER")
    password = get_env("GMAIL_PASSWORD")

    # ★送信先（ここが今回の要件）
    to_emails = [
        "kasahararyo@gmail.com",
        "karuizawa.buffalos@gmail.com"
    ]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"OB OGビジタ管理 <{user}>"
    msg["To"] = ", ".join(to_emails)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)

    print("送信成功:", to_emails)


def main():
    today = get_today_jst()
    rows = fetch_today_attendance_rows()

    if not rows:
        print(f"{today} は練習予定がないため、メール送信しません。")
        return

    subject = f"【出欠確認】{today}"
    body = build_body(today, rows)

    print("===== SUBJECT =====")
    print(subject)
    print("===== BODY =====")
    print(body)

    send_email(subject, body)


if __name__ == "__main__":
    main()

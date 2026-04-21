import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
import resend


JST = ZoneInfo("Asia/Tokyo")


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} が設定されていません")
    return value


def get_db_connection():
    database_url = get_env("DATABASE_URL")
    return psycopg.connect(database_url)


def get_today_jst():
    return datetime.now(JST).date()


def fetch_today_attendance_rows():
    today = get_today_jst()

    query = """
        SELECT
            e.id AS event_id,
            e.event_date,
            e.title,
            e.start_time,
            u.name,
            a.status,
            a.note
        FROM events e
        LEFT JOIN attendance a
            ON e.id = a.event_id
        LEFT JOIN users u
            ON a.user_id = u.id
        WHERE e.event_date = %s
        ORDER BY e.start_time ASC, u.name ASC
    """

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (today,))
            rows = cur.fetchall()

    return rows


def build_subject(today, rows):
    if not rows:
        return f"【出欠確認】{today.strftime('%Y/%m/%d')} 本日の予定なし"

    title = rows[0]["title"] or "本日の予定"
    return f"【出欠確認】{today.strftime('%Y/%m/%d')} {title}"


def split_attendance(rows):
    joined = []
    absent = []
    pending = []

    for row in rows:
        name = row.get("name") or "名称未設定"
        status = row.get("status") or "未回答"
        note = row.get("note") or ""

        line = f"・{name}"
        if note:
            line += f"（{note}）"

        if status == "参加":
            joined.append(line)
        elif status == "不参加":
            absent.append(line)
        else:
            pending.append(line)

    return joined, absent, pending


def build_body(today, rows):
    if not rows:
        return f"""本日（{today.strftime('%Y/%m/%d')}）の予定は登録されていません。

このメールは自動送信です。
"""

    first = rows[0]
    title = first.get("title") or "予定"
    start_time = first.get("start_time")

    if start_time:
        start_time_text = start_time.strftime("%H:%M")
    else:
        start_time_text = "未設定"

    joined, absent, pending = split_attendance(rows)

    joined_text = "\n".join(joined) if joined else "・なし"
    absent_text = "\n".join(absent) if absent else "・なし"
    pending_text = "\n".join(pending) if pending else "・なし"

    return f"""本日（{today.strftime('%Y/%m/%d')}）の出欠状況です。

■予定
{title}
開始時刻：{start_time_text}

■参加
{joined_text}

■不参加
{absent_text}

■未回答
{pending_text}

このメールは自動送信です。
"""


def send_email(subject, body):
    resend.api_key = get_env("RESEND_API_KEY")
    admin_email = get_env("ADMIN_EMAIL")
    mail_from = get_env("MAIL_FROM")

    response = resend.Emails.send({
        "from": mail_from,
        "to": [admin_email],
        "subject": subject,
        "text": body,
    })

    print("メール送信結果:", response)


def main():
    today = get_today_jst()
    rows = fetch_today_attendance_rows()
    subject = build_subject(today, rows)
    body = build_body(today, rows)

    print("===== SUBJECT =====")
    print(subject)
    print("===== BODY =====")
    print(body)

    send_email(subject, body)


if __name__ == "__main__":
    main()

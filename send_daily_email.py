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
    return datetime.now(JST).strftime("%Y-%m-%d")


def fetch_today_attendance_rows():
    today = get_today_jst()

    query = """
        SELECT
            p.id AS practice_id,
            p.practice_date,
            p.practice_time,
            m.name,
            a.status
        FROM practices p
        LEFT JOIN attendance a
            ON p.id = a.practice_id
        LEFT JOIN members m
            ON a.member_id = m.id
        WHERE p.practice_date = %s
        ORDER BY p.practice_time ASC, m.id ASC
    """

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (today,))
            rows = cur.fetchall()

    return rows


def build_subject(today, rows):
    if not rows:
        return f"【出欠確認】{today} 本日の予定なし"

    practice_time = rows[0]["practice_time"] or ""
    return f"【出欠確認】{today} {practice_time}"


def split_attendance(rows):
    attend = []
    absent = []
    pending = []

    for row in rows:
        name = row.get("name") or "名称未設定"
        status = row.get("status")

        line = f"・{name}"

        if status == "attend":
            attend.append(line)
        elif status == "absent":
            absent.append(line)
        else:
            pending.append(line)

    return attend, absent, pending


def build_body(today, rows):
    if not rows:
        return f"""本日（{today}）の予定は登録されていません。

このメールは自動送信です。
"""

    practice_time = rows[0].get("practice_time") or "未設定"

    attend, absent, pending = split_attendance(rows)

    attend_text = "\n".join(attend) if attend else "・なし"
    absent_text = "\n".join(absent) if absent else "・なし"
    pending_text = "\n".join(pending) if pending else "・なし"

    total_members = len(rows)
    answered_count = len(attend) + len(absent)

    return f"""本日（{today}）の出欠状況です。

■練習時間
{practice_time}

■回答状況
回答済み：{answered_count} / {total_members}

■参加
{attend_text}

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

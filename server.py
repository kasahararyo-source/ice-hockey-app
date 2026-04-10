#!/usr/bin/env python3
import json
import os
import time
import hmac
import base64
import sqlite3
import hashlib
import mimetypes
import secrets
import sys
import urllib.parse
from collections import defaultdict, deque
from datetime import datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_FILES = {
    '/': 'index.html',
    '/index.html': 'index.html',
    '/app.js': 'app.js',
    '/styles.css': 'styles.css',
    '/manifest.webmanifest': 'manifest.webmanifest',
    '/sw.js': 'sw.js',
    '/icon-192.png': 'icon-192.png',
    '/icon-512.png': 'icon-512.png',
}
DB_FILE = Path(os.environ.get('APP_DB_PATH', str(BASE_DIR / 'attendance.db')))
CONFIG_FILE = Path(os.environ.get('APP_CONFIG_PATH', str(BASE_DIR / 'config.json')))
SESSION_TTL_SECONDS = int(os.environ.get('SESSION_TTL_SECONDS', '43200'))
LOGIN_WINDOW_SECONDS = int(os.environ.get('LOGIN_WINDOW_SECONDS', '900'))
MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', '10'))
SECURE_COOKIES = os.environ.get('SECURE_COOKIES', '0') == '1'

SESSIONS = {}
LOGIN_ATTEMPTS = defaultdict(deque)


def utc_now() -> int:
    return int(time.time())


def load_config():
    with CONFIG_FILE.open('r', encoding='utf-8') as f:
        cfg = json.load(f)
    cfg['member_names'] = [m['name'] for m in cfg['members']]
    return cfg


CONFIG = load_config()


def verify_pin(pin: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_b64, hash_b64 = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        rounds = int(rounds_s)
        salt = base64.b64decode(salt_b64.encode('ascii'))
        expected = base64.b64decode(hash_b64.encode('ascii'))
        actual = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, rounds)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def hash_pin(pin: str, rounds: int = 240000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, rounds)
    return 'pbkdf2_sha256${}${}${}'.format(
        rounds,
        base64.b64encode(salt).decode('ascii'),
        base64.b64encode(digest).decode('ascii'),
    )


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS practices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            practice_date TEXT NOT NULL,
            practice_time TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            practice_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            status TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (practice_id, member_name),
            FOREIGN KEY (practice_id) REFERENCES practices(id) ON DELETE CASCADE
        )
    ''')
    count = conn.execute('SELECT COUNT(*) FROM practices').fetchone()[0]
    if count == 0:
        now = datetime.now().isoformat(timespec='seconds')
        cur = conn.execute(
            'INSERT INTO practices (practice_date, practice_time, created_at) VALUES (?, ?, ?)',
            ('2026-04-12', '10:00-12:00', now),
        )
        practice_id = cur.lastrowid
        for name in CONFIG['member_names']:
            conn.execute(
                'INSERT INTO attendance (practice_id, member_name, status, updated_at) VALUES (?, ?, ?, ?)',
                (practice_id, name, None, now),
            )
    conn.commit()
    conn.close()


def db_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def get_all_practices():
    conn = db_connect()
    practices = []
    rows = conn.execute('SELECT id, practice_date, practice_time, created_at FROM practices ORDER BY practice_date ASC, practice_time ASC, id ASC').fetchall()
    for row in rows:
        att_rows = conn.execute(
            'SELECT member_name, status FROM attendance WHERE practice_id = ? ORDER BY member_name ASC',
            (row['id'],),
        ).fetchall()
        attendance = {name: None for name in CONFIG['member_names']}
        for ar in att_rows:
            if ar['status'] == 'yes':
                attendance[ar['member_name']] = True
            elif ar['status'] == 'no':
                attendance[ar['member_name']] = False
            else:
                attendance[ar['member_name']] = None
        practices.append({
            'id': row['id'],
            'date': row['practice_date'],
            'time': row['practice_time'],
            'created_at': row['created_at'],
            'attendance': attendance,
        })
    conn.close()
    return practices


def add_practice(practice_date: str, practice_time: str):
    now = datetime.now().isoformat(timespec='seconds')
    conn = db_connect()
    cur = conn.execute(
        'INSERT INTO practices (practice_date, practice_time, created_at) VALUES (?, ?, ?)',
        (practice_date, practice_time, now),
    )
    pid = cur.lastrowid
    for name in CONFIG['member_names']:
        conn.execute(
            'INSERT INTO attendance (practice_id, member_name, status, updated_at) VALUES (?, ?, ?, ?)',
            (pid, name, None, now),
        )
    conn.commit()
    conn.close()


def delete_practice(practice_id: int):
    conn = db_connect()
    conn.execute('DELETE FROM practices WHERE id = ?', (practice_id,))
    conn.commit()
    conn.close()


def update_attendance(practice_id: int, member_name: str, status):
    status_db = 'yes' if status is True else 'no' if status is False else None
    now = datetime.now().isoformat(timespec='seconds')
    conn = db_connect()
    conn.execute(
        'UPDATE attendance SET status = ?, updated_at = ? WHERE practice_id = ? AND member_name = ?',
        (status_db, now, practice_id, member_name),
    )
    conn.commit()
    conn.close()


def make_session(role: str, member: str | None = None) -> str:
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = {
        'role': role,
        'member': member,
        'expires_at': utc_now() + SESSION_TTL_SECONDS,
    }
    return sid


def purge_sessions():
    now = utc_now()
    expired = [sid for sid, sess in SESSIONS.items() if sess.get('expires_at', 0) <= now]
    for sid in expired:
        SESSIONS.pop(sid, None)


def get_session(handler):
    purge_sessions()
    cookie_header = handler.headers.get('Cookie')
    if not cookie_header:
        return None, None
    c = cookies.SimpleCookie()
    c.load(cookie_header)
    sid = c.get('sid')
    if not sid:
        return None, None
    session = SESSIONS.get(sid.value)
    if session:
        session['expires_at'] = utc_now() + SESSION_TTL_SECONDS
    return sid.value, session


def client_ip(handler) -> str:
    forwarded = handler.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return handler.client_address[0]


def is_rate_limited(ip: str) -> bool:
    now = utc_now()
    q = LOGIN_ATTEMPTS[ip]
    while q and q[0] <= now - LOGIN_WINDOW_SECONDS:
        q.popleft()
    return len(q) >= MAX_LOGIN_ATTEMPTS


def note_login_attempt(ip: str):
    q = LOGIN_ATTEMPTS[ip]
    q.append(utc_now())


class Handler(BaseHTTPRequestHandler):
    server_version = 'IceHockeyAttendance/2.0'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - - [%s] %s\n' % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _json(self, code, payload, set_cookie=None, clear_cookie=False):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if set_cookie:
            cookie = f'sid={set_cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}'
            if SECURE_COOKIES:
                cookie += '; Secure'
            self.send_header('Set-Cookie', cookie)
        if clear_cookie:
            cookie = 'sid=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax'
            if SECURE_COOKIES:
                cookie += '; Secure'
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def _serve_file(self, path):
        rel = STATIC_FILES.get(path)
        if not rel:
            self.send_error(404)
            return
        file_path = BASE_DIR / rel
        if not file_path.exists():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache' if path == '/sw.js' else 'public, max-age=300')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/'):
            return self.handle_api_get(path)
        if path in STATIC_FILES:
            return self._serve_file(path)
        return self._serve_file('/')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/'):
            return self.handle_api_post(path)
        self.send_error(404)

    def handle_api_get(self, path):
        _, session = get_session(self)
        if path == '/api/session':
            if not session:
                return self._json(200, {'logged_in': False, 'team_name': CONFIG['team_name']})
            return self._json(200, {
                'logged_in': True,
                'team_name': CONFIG['team_name'],
                'role': session['role'],
                'member': session.get('member'),
                'members': CONFIG['member_names'] if session['role'] == 'admin' else None,
            })
        if path == '/api/practices':
            if not session:
                return self._json(401, {'error': 'not_logged_in'})
            return self._json(200, {'practices': get_all_practices(), 'members': CONFIG['member_names']})
        return self._json(404, {'error': 'not_found'})

    def handle_api_post(self, path):
        sid, session = get_session(self)
        body = self._read_json()
        if path == '/api/login':
            ip = client_ip(self)
            if is_rate_limited(ip):
                return self._json(429, {'error': 'too_many_attempts'})
            mode = body.get('mode')
            pin = str(body.get('pin', '')).strip()
            if mode == 'admin' and verify_pin(pin, CONFIG['admin_pin_hash']):
                sid = make_session('admin')
                return self._json(200, {'ok': True, 'role': 'admin'}, set_cookie=sid)
            if mode == 'member':
                member_name = body.get('member')
                matched = next((m for m in CONFIG['members'] if m['name'] == member_name and verify_pin(pin, m['pin_hash'])), None)
                if matched:
                    sid = make_session('member', member_name)
                    return self._json(200, {'ok': True, 'role': 'member', 'member': member_name}, set_cookie=sid)
            note_login_attempt(ip)
            return self._json(403, {'error': 'invalid_credentials'})

        if path == '/api/logout':
            if sid:
                SESSIONS.pop(sid, None)
            return self._json(200, {'ok': True}, clear_cookie=True)

        if not session:
            return self._json(401, {'error': 'not_logged_in'})

        if path == '/api/practices/add':
            if session['role'] != 'admin':
                return self._json(403, {'error': 'forbidden'})
            practice_date = str(body.get('date', '')).strip()
            practice_time = str(body.get('time', '')).strip()
            if not practice_date or not practice_time:
                return self._json(400, {'error': 'date_time_required'})
            add_practice(practice_date, practice_time)
            return self._json(200, {'ok': True})

        if path == '/api/practices/delete':
            if session['role'] != 'admin':
                return self._json(403, {'error': 'forbidden'})
            try:
                pid = int(body.get('id', 0))
            except Exception:
                return self._json(400, {'error': 'bad_id'})
            delete_practice(pid)
            return self._json(200, {'ok': True})

        if path == '/api/attendance/update':
            try:
                pid = int(body.get('id', 0))
            except Exception:
                return self._json(400, {'error': 'bad_id'})
            status = body.get('status')
            member_name = body.get('member')
            if status not in [True, False, None]:
                return self._json(400, {'error': 'bad_status'})
            if member_name not in CONFIG['member_names']:
                return self._json(400, {'error': 'bad_member'})
            if session['role'] == 'member' and member_name != session.get('member'):
                return self._json(403, {'error': 'forbidden'})
            update_attendance(pid, member_name, status)
            return self._json(200, {'ok': True})

        return self._json(404, {'error': 'not_found'})


def main():
    init_db()
    port = int(os.environ.get('PORT', '8000'))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f'Serving on http://{host}:{port}')
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()


if __name__ == '__main__':
    main()

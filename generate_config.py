#!/usr/bin/env python3
import json, secrets, base64, hashlib, sys
from pathlib import Path

TEAM_NAME = 'アイスホッケー練習出欠'
PINS = {
    'admin': '260410',
    '大池音々': '110137',
    '森田健友': '220284',
    '美馬碧仁': '330451',
    '荻原瑛史': '440618',
    '尾山旭': '550782',
    '笠原現': '660945',
}


def hash_pin(pin: str, rounds: int = 240000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, rounds)
    return 'pbkdf2_sha256${}${}${}'.format(
        rounds,
        base64.b64encode(salt).decode('ascii'),
        base64.b64encode(digest).decode('ascii'),
    )


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('config.json')
    data = {
        'team_name': TEAM_NAME,
        'admin_pin_hash': hash_pin(PINS['admin']),
        'members': [
            {'name': name, 'pin_hash': hash_pin(pin)}
            for name, pin in PINS.items() if name != 'admin'
        ],
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {target}')


if __name__ == '__main__':
    main()

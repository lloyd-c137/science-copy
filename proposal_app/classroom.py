"""Create individual teacher and student accounts for a classroom database."""

import argparse
from contextlib import closing
from getpass import getpass
import hashlib
from pathlib import Path
import secrets
import sqlite3

from server import connect, init_db, uid


def add_account(database, username, name, role, password):
    if not username.strip() or not name.strip():
        raise ValueError("请填写账号及姓名。")
    if len(password) < 8:
        raise ValueError("请使用至少八个字符的密码。")
    init_db(database, demo=False)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
    with closing(connect(database)) as connection, connection:
        if connection.execute("SELECT 1 FROM users WHERE id IN ('U1','U2','U3')").fetchone():
            raise ValueError("请选择独立的班级数据库。当前库含有演示账号。")
        connection.execute(
            "INSERT INTO users(id,username,name,role,salt,pw) VALUES (?,?,?,?,?,?)",
            (uid("U"), username.strip(), name.strip(), role, salt, digest),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="添加开题活动的真实师生账号")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--role", choices=("teacher", "student"), required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    try:
        password = getpass("此账号的初始密码：")
        if password != getpass("再次输入："):
            raise ValueError("两次密码不一致。")
        add_account(args.db, args.username, args.name, args.role, password)
    except (ValueError, sqlite3.IntegrityError) as exc:
        parser.exit(1, f"创建失败：{exc}\n")
    print(f"已创建账号 {args.username}（{args.name}）。")

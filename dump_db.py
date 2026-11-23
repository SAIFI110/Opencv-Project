"""
Grade 8 Science Platform - MySQL Database Dump & Backup Utility
==============================================================
Creates a full, UTF-8mb4 compliant SQL backup of the MySQL database.
"""

import os
import sys
import time
import argparse
import subprocess
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "rootpassword")
DB_NAME = os.environ.get("DB_NAME", "grade8_science")
DOCKER_CONTAINER = "science_mysql"


def dump_via_docker(output_path: str, container_name: str = DOCKER_CONTAINER) -> bool:
    print(f"📦 Exporting MySQL via Docker container '{container_name}'...")
    cmd = [
        "docker", "exec", container_name,
        "mysqldump",
        f"-u{DB_USER}",
        f"-p{DB_PASSWORD}",
        "--default-character-set=utf8mb4",
        "--single-transaction",
        "--quick",
        "--skip-lock-tables",
        DB_NAME
    ]

    try:
        with open(output_path, "wb") as f_out:
            proc = subprocess.Popen(cmd, stdout=f_out, stderr=subprocess.PIPE)
            _, stderr = proc.communicate()

        if proc.returncode == 0:
            return True

        err_msg = stderr.decode("utf-8", errors="replace").strip()
        if "Using a password on the command line" in err_msg and os.path.getsize(output_path) > 500:
            return True

        print(f"⚠️  Docker mysqldump returned code {proc.returncode}: {err_msg}")
        return False
    except Exception as e:
        print(f"⚠️  Docker execution failed: {e}")
        return False


def restore_dump(input_path: str, container_name: str = DOCKER_CONTAINER) -> bool:
    if not os.path.exists(input_path):
        print(f"❌ Backup file not found: {input_path}")
        return False

    print(f"🔄 Restoring '{DB_NAME}' from '{input_path}' via Docker...")
    cmd = [
        "docker", "exec", "-i", container_name,
        "mysql",
        f"-u{DB_USER}",
        f"-p{DB_PASSWORD}",
        "--default-character-set=utf8mb4",
        DB_NAME
    ]

    try:
        with open(input_path, "rb") as f_in:
            proc = subprocess.Popen(cmd, stdin=f_in, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            print("🎉 Database successfully restored!")
            return True

        err_msg = stderr.decode("utf-8", errors="replace").strip()
        print(f"❌ Restore failed with code {proc.returncode}: {err_msg}")
        return False
    except Exception as e:
        print(f"❌ Restore execution error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="MySQL Backup Utility")
    parser.add_argument("-o", "--output", default="backup_grade8_science.sql")
    parser.add_argument("--container", default=DOCKER_CONTAINER)
    parser.add_argument("--restore", default=None)
    args = parser.parse_args()

    if args.restore:
        success = restore_dump(args.restore, args.container)
        sys.exit(0 if success else 1)

    print("=" * 65)
    print(" 💾 GRADE 8 SCIENCE PLATFORM - MYSQL DATABASE DUMP")
    print(f" Database: {DB_NAME} | Output File: {args.output}")
    print("=" * 65)

    start = time.time()
    success = dump_via_docker(args.output, args.container)

    if success and os.path.exists(args.output):
        kb = os.path.getsize(args.output) / 1024.0
        print(f"✓ Backup Complete in {time.time() - start:.2f}s! ({kb:.2f} KB)")
        print(f"📁 Saved to: {args.output}")
    else:
        print("❌ Dump failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()

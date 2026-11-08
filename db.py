"""
Database Connection & Management Module for Grade 8 Science Platform
Connects to Docker MySQL (localhost:3306)
"""

import os
import sys
import json
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

# Fix Windows console encoding for Arabic characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "rootpassword")
DB_NAME = os.environ.get("DB_NAME", "grade8_science")


def get_db_connection():
    """
    Returns a live connection to the Docker MySQL database.
    Uses DictCursor so results are automatically formatted as Python dictionaries.
    """
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True
    )


def init_database_tables():
    """
    Ensures all necessary production tables exist in MySQL Docker container.
    """
    conn = get_db_connection()
    with conn.cursor() as cursor:
        # 1. Diagram Metadata (Vision Gatekeeper output)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS diagram_metadata (
            id INT AUTO_INCREMENT PRIMARY KEY,
            semester INT NOT NULL,
            unit VARCHAR(255),
            chapter VARCHAR(255),
            lesson VARCHAR(255),
            description TEXT,
            image_filename VARCHAR(255),
            image_path VARCHAR(500),
            resolution VARCHAR(50),
            is_suitable_for_labeling VARCHAR(10) DEFAULT 'NO',
            is_useful_for_questions VARCHAR(10) DEFAULT 'YES',
            suitability_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Lesson Worksheets (HTML stored in MySQL)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lesson_worksheets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            semester INT NOT NULL,
            unit VARCHAR(255),
            chapter VARCHAR(255),
            lesson VARCHAR(255) NOT NULL,
            diagram_count INT DEFAULT 0,
            worksheet_html LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 3. Diagram Questions & Assessment Cache
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS diagram_questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            semester INT NOT NULL,
            unit VARCHAR(255),
            chapter VARCHAR(255),
            lesson VARCHAR(255),
            image_url VARCHAR(500),
            is_suitable_for_questions VARCHAR(10) DEFAULT 'YES',
            suitability_reason TEXT,
            short_question TEXT,
            short_answer TEXT,
            mcq_question TEXT,
            mcq_options JSON,
            mcq_correct VARCHAR(10),
            mcq_explanation TEXT,
            reasoning_question TEXT,
            reasoning_answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 4. Theory Assessments Cache Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS theory_assessments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            semester INT NOT NULL,
            lesson VARCHAR(255) NOT NULL,
            diagram_url VARCHAR(500),
            assessment_json JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 5. Chat Conversation History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            semester INT,
            user_message TEXT,
            bot_reply TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

    conn.close()
    return True


def show_database_status():
    """
    Displays a clean, professional production summary of all MySQL tables and rows.
    """
    print("\n" + "=" * 65)
    print(" 📊 GRADE 8 SCIENCE PLATFORM - DOCKER MYSQL STATUS")
    print(f" Host: {DB_HOST}:{DB_PORT} | Database: {DB_NAME}")
    print("=" * 65)

    tables = [
        ("diagram_metadata", "Approved Diagrams & Vision Flags"),
        ("lesson_worksheets", "Lesson-wise HTML Worksheets"),
        ("diagram_questions", "Generated Diagram Questions (Short/MCQ/Reasoning)"),
        ("theory_assessments", "Cached Theory Assessments"),
        ("chat_history", "Student Chat History & Interactions"),
    ]

    conn = get_db_connection()
    with conn.cursor() as cur:
        for tbl, desc in tables:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {tbl};")
            count = cur.fetchone()["cnt"]
            print(f" • Table: {tbl:<20} | Rows: {count:<5} | ({desc})")

        # Show recent diagram_metadata entries if any
        cur.execute("SELECT id, semester, lesson, is_suitable_for_labeling, is_useful_for_questions, image_filename FROM diagram_metadata ORDER BY id DESC LIMIT 3;")
        recent_diagrams = cur.fetchall()
        if recent_diagrams:
            print("\n 🖼️ Recent Diagrams in MySQL:")
            for r in recent_diagrams:
                print(f"   [ID {r['id']}] Sem {r['semester']} | {r['lesson']} | Labeling: {r['is_suitable_for_labeling']} | Questions: {r['is_useful_for_questions']} | {r['image_filename']}")

        # Show recent lesson_worksheets if any
        cur.execute("SELECT id, semester, lesson, diagram_count FROM lesson_worksheets ORDER BY id DESC LIMIT 3;")
        recent_ws = cur.fetchall()
        if recent_ws:
            print("\n 📄 Recent Worksheets in MySQL:")
            for r in recent_ws:
                print(f"   [ID {r['id']}] Sem {r['semester']} | Lesson: {r['lesson']} | Diagrams: {r['diagram_count']}")

    conn.close()
    print("=" * 65 + "\n")


if __name__ == "__main__":
    try:
        init_database_tables()
        show_database_status()
    except Exception as e:
        print(f"❌ Database connection error: {e}")

"""
Grade 8 Science AI Educational Assessment & Chatbot Backend
===========================================================
Production-ready FastAPI backend providing:
1. Complete Curriculum & TOC Registry (Semesters 1, 2, 3)
2. Option 1: General Theory Assessment Generator (5 MCQs + 3 Short Answers grounded in textbook text via OpenAI)
3. Option 2: Diagram-Based Assessment Retrieval (High-res diagrams + interactive question cards from verified bank)
4. Conversational Chatbot Engine (Pedagogical tutor with context grounding & suggested prompts)
5. Static Asset Server for frontend web interface and diagrams
"""

import os
import re
import csv
import json
import hashlib
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import pypdf
from db import get_db_connection

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = FastAPI(
    title="Grade 8 Science AI Tutor & Assessment Platform",
    description="Interactive Assessment and Learning System for Saudi Middle School Science (Grade 8)",
    version="2.0.0"
)

# Enable CORS for local development and web access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base directories
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CACHE_DIR = BASE_DIR / "cached_theory_questions"
CACHE_DIR.mkdir(exist_ok=True)

# Mount static folders for images and frontend
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

for sem in [1, 2, 3]:
    diag_dir = BASE_DIR / f"output_diagrams_sem{sem}"
    if diag_dir.exists():
        app.mount(f"/output_diagrams_sem{sem}", StaticFiles(directory=str(diag_dir)), name=f"output_diagrams_sem{sem}")

# ==============================================================================
# CURRICULUM REGISTRIES (TABLE OF CONTENTS - GRADE 8 SCIENCE)
# ==============================================================================

TOC_REGISTRIES = {
    1: [
        {"start_page": 1, "end_page": 7, "unit": "المقدمة والتمهيد", "chapter": "المقدمة وفهرس المحتويات", "lesson": "تمهيد وفهرس"},
        {"start_page": 8, "end_page": 13, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 1: طبيعة العلم", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 14, "end_page": 21, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 1: طبيعة العلم", "lesson": "الدرس 1: أسلوب العلم"},
        {"start_page": 22, "end_page": 27, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 1: طبيعة العلم", "lesson": "الدرس 2: حل المشكلات بطريقة علمية"},
        {"start_page": 28, "end_page": 33, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 1: طبيعة العلم", "lesson": "استقصاء ومراجعة الفصل"},
        {"start_page": 34, "end_page": 37, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 2: المخاليط والمحاليل", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 38, "end_page": 47, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 2: المخاليط والمحاليل", "lesson": "الدرس 1: المحاليل والذائبية"},
        {"start_page": 48, "end_page": 55, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 2: المخاليط والمحاليل", "lesson": "الدرس 2: المحاليل الحمضية والمحاليل القاعدية"},
        {"start_page": 56, "end_page": 65, "unit": "الوحدة 1: دراسة المادة", "chapter": "الفصل 2: المخاليط والمحاليل", "lesson": "استقصاء ومراجعة الفصل واختبار مقنن"},
        {"start_page": 66, "end_page": 69, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 3: حالات المادة", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 70, "end_page": 74, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 3: حالات المادة", "lesson": "الدرس 1: المادة"},
        {"start_page": 75, "end_page": 82, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 3: حالات المادة", "lesson": "الدرس 2: الحرارة وتحولات المادة"},
        {"start_page": 83, "end_page": 91, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 3: حالات المادة", "lesson": "الدرس 3: سلوك الموائع"},
        {"start_page": 92, "end_page": 97, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 3: حالات المادة", "lesson": "استقصاء ومراجعة الفصل"},
        {"start_page": 98, "end_page": 101, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 4: الطاقة وتحولاتها", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 102, "end_page": 106, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 4: الطاقة وتحولاتها", "lesson": "الدرس 1: ما الطاقة؟"},
        {"start_page": 107, "end_page": 115, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 4: الطاقة وتحولاتها", "lesson": "الدرس 2: تحولات الطاقة"},
        {"start_page": 116, "end_page": 125, "unit": "الوحدة 2: المادة والطاقة", "chapter": "الفصل 4: الطاقة وتحولاتها", "lesson": "استقصاء ومراجعة الفصل واختبار مقنن"},
    ],
    2: [
        {"start_page": 1, "end_page": 8, "unit": "المقدمة والتمهيد", "chapter": "المقدمة وفهرس المحتويات", "lesson": "تمهيد وفهرس"},
        {"start_page": 9, "end_page": 13, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 5: جهازا الدوران والمناعة", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 14, "end_page": 22, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 5: جهازا الدوران والمناعة", "lesson": "الدرس 1: جهاز الدوران"},
        {"start_page": 23, "end_page": 33, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 5: جهازا الدوران والمناعة", "lesson": "الدرس 2: المناعة والمرض"},
        {"start_page": 34, "end_page": 39, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 5: جهازا الدوران والمناعة", "lesson": "استقصاء ومراجعة الفصل"},
        {"start_page": 40, "end_page": 43, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 6: الهضم والتنفس والإخراج", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 44, "end_page": 54, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 6: الهضم والتنفس والإخراج", "lesson": "الدرس 1: الجهاز الهضمي والمواد الغذائية"},
        {"start_page": 55, "end_page": 67, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 6: الهضم والتنفس والإخراج", "lesson": "الدرس 2: جهازا التنفس والإخراج"},
        {"start_page": 68, "end_page": 77, "unit": "الوحدة 3: أجهزة جسم الإنسان (1)", "chapter": "الفصل 6: الهضم والتنفس والإخراج", "lesson": "استقصاء ومراجعة الفصل واختبار مقنن"},
        {"start_page": 78, "end_page": 83, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 84, "end_page": 92, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "lesson": "الدرس 1: الجلد والعضلات"},
        {"start_page": 93, "end_page": 107, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "lesson": "الدرس 2: الجهاز الهيكلي والجهاز العصبي"},
        {"start_page": 108, "end_page": 113, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "lesson": "استقصاء ومراجعة الفصل"},
        {"start_page": 114, "end_page": 117, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 8: التنظيم والتكاثر", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 118, "end_page": 130, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 8: التنظيم والتكاثر", "lesson": "الدرس 1: جهازا الغدد الصم والتكاثر"},
        {"start_page": 131, "end_page": 139, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 8: التنظيم والتكاثر", "lesson": "الدرس 2: مراحل حياة الإنسان"},
        {"start_page": 140, "end_page": 145, "unit": "الوحدة 4: أجهزة جسم الإنسان (2)", "chapter": "الفصل 8: التنظيم والتكاثر", "lesson": "استقصاء ومراجعة الفصل واختبار مقنن"},
    ],
    3: [
        {"start_page": 1, "end_page": 8, "unit": "المقدمة والتمهيد", "chapter": "المقدمة وفهرس المحتويات", "lesson": "تمهيد وفهرس"},
        {"start_page": 9, "end_page": 17, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 9: النباتات", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 18, "end_page": 24, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 9: النباتات", "lesson": "الدرس 1: النباتات اللابذرية"},
        {"start_page": 25, "end_page": 33, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 9: النباتات", "lesson": "الدرس 2: النباتات البذرية"},
        {"start_page": 34, "end_page": 39, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 9: النباتات", "lesson": "استقصاء ومراجعة الفصل"},
        {"start_page": 40, "end_page": 43, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 10: موارد البيئة وحمايتها", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 44, "end_page": 54, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 10: موارد البيئة وحمايتها", "lesson": "الدرس 1: موارد البيئة"},
        {"start_page": 55, "end_page": 67, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 10: موارد البيئة وحمايتها", "lesson": "الدرس 2: التلوث وحماية البيئة"},
        {"start_page": 68, "end_page": 77, "unit": "الوحدة 5: النباتات وموارد البيئة", "chapter": "الفصل 10: موارد البيئة وحمايتها", "lesson": "استقصاء ومراجعة الفصل واختبار مقنن"},
        {"start_page": 78, "end_page": 81, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 11: الطاقة الحرارية", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 82, "end_page": 85, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 11: الطاقة الحرارية", "lesson": "الدرس 1: درجة الحرارة"},
        {"start_page": 86, "end_page": 91, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 11: الطاقة الحرارية", "lesson": "الدرس 2: انتقال الحرارة"},
        {"start_page": 92, "end_page": 95, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 11: الطاقة الحرارية", "lesson": "الدرس 3: المحركات والثلاجات"},
        {"start_page": 96, "end_page": 101, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 11: الطاقة الحرارية", "lesson": "استقصاء ومراجعة الفصل"},
        {"start_page": 102, "end_page": 105, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 12: الموجات والصوت والضوء", "lesson": "افتتاحية الفصل والتهيئة للقراءة"},
        {"start_page": 106, "end_page": 113, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 12: الموجات والصوت والضوء", "lesson": "الدرس 1: الموجات"},
        {"start_page": 114, "end_page": 118, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 12: الموجات والصوت والضوء", "lesson": "الدرس 2: موجات الصوت"},
        {"start_page": 119, "end_page": 125, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 12: الموجات والصوت والضوء", "lesson": "الدرس 3: الضوء"},
        {"start_page": 126, "end_page": 134, "unit": "الوحدة 6: الطاقة الحرارية والموجات", "chapter": "الفصل 12: الموجات والصوت والضوء", "lesson": "استقصاء ومراجعة الفصل واختبار مقنن"},
    ]
}

PDF_FILENAMES = {
    1: "grade_8_semester_1_2362c878-605f-4ccc-8512-0fda4ee9447d_1-145 (1).pdf",
    2: "grade_8_semester_2_science (1).pdf",
    3: "grade_8_semester_3_science (1).pdf",
}

# ==============================================================================
# HELPER FUNCTIONS: DATA RETRIEVAL & EXTRACTION
# ==============================================================================

def load_diagrams_bank(semester: int) -> List[Dict[str, Any]]:
    """Loads approved diagrams directly from Docker MySQL diagram_metadata table."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
            SELECT id, semester, unit, chapter, lesson, description, image_filename, image_path, resolution,
                   is_suitable_for_labeling, is_useful_for_questions, suitability_reason
            FROM diagram_metadata
            WHERE semester = %s AND is_useful_for_questions = 'YES'
            ORDER BY id;
            """, (semester,))
            rows = cur.fetchall()
        conn.close()

        diagrams = []
        for r in rows:
            img_rel = r.get("image_path", "").replace("\\", "/")
            if not img_rel.startswith("/"):
                img_rel = "/" + img_rel

            diagrams.append({
                "id": f"sem{semester}_diag_{r['id']}",
                "unit": r.get("unit", ""),
                "chapter": r.get("chapter", ""),
                "lesson": r.get("lesson", ""),
                "description": r.get("description", ""),
                "image_filename": r.get("image_filename", ""),
                "image_url": img_rel,
                "resolution": r.get("resolution", ""),
                "is_suitable_for_labeling": r.get("is_suitable_for_labeling", "NO"),
                "is_useful_for_questions": r.get("is_useful_for_questions", "YES"),
            })
        return diagrams
    except Exception as e:
        print(f"[MySQL Load Diagrams Error] {e}")
        return []


def extract_lesson_text_from_pdf(semester: int, start_page: int, end_page: int, max_chars: int = 12000) -> str:
    """Extracts raw textbook text for the specific lesson page range to prevent hallucination."""
    pdf_name = PDF_FILENAMES.get(semester)
    if not pdf_name:
        return ""

    pdf_path = BASE_DIR / pdf_name
    if not pdf_path.exists():
        return ""

    try:
        reader = pypdf.PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        # Ensure 0-indexed bounds
        s_idx = max(0, start_page - 1)
        e_idx = min(num_pages, end_page)

        pages_text = []
        for i in range(s_idx, e_idx):
            t = reader.pages[i].extract_text() or ""
            if t.strip():
                pages_text.append(f"--- [Page {i+1}] ---\n{t.strip()}")

        full_text = "\n\n".join(pages_text)
        return full_text[:max_chars]
    except Exception as e:
        print(f"[PDF Extract Error] {e}")
        return ""

# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []
    semester: Optional[int] = 1
    lesson: Optional[str] = None

class TheoryAssessmentRequest(BaseModel):
    semester: int
    lesson: str
    num_mcq: Optional[int] = 5
    num_short: Optional[int] = 3

class DiagramAssessmentRequest(BaseModel):
    semester: int
    lesson: Optional[str] = "all"

# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/")
def serve_index():
    """Serves the main application single page interface."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(content={"message": "Grade 8 Science AI Tutor API is running. UI loading..."})


@app.get("/worksheet/{worksheet_id}")
def serve_worksheet(worksheet_id: int):
    """
    Renders the HTML worksheet directly from Docker MySQL 'lesson_worksheets' table.
    Open in any browser: e.g. http://127.0.0.1:8000/worksheet/1
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT worksheet_html FROM lesson_worksheets WHERE id = %s;", (worksheet_id,))
            row = cur.fetchone()
        conn.close()

        if not row or not row.get("worksheet_html"):
            raise HTTPException(status_code=404, detail="Worksheet not found in MySQL")

        return HTMLResponse(content=row["worksheet_html"], status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rendering worksheet: {e}")


@app.get("/api/worksheets")
def get_worksheets_list(semester: int = Query(1, ge=1, le=3)):
    """Lists all available worksheets in MySQL with one-click preview URLs."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
            SELECT id, semester, unit, chapter, lesson, diagram_count, created_at
            FROM lesson_worksheets
            WHERE semester = %s
            ORDER BY id;
            """, (semester,))
            rows = cur.fetchall()
        conn.close()

        for r in rows:
            r["preview_url"] = f"/worksheet/{r['id']}"
            if "created_at" in r and r["created_at"]:
                r["created_at"] = str(r["created_at"])

        return {"semester": semester, "total_worksheets": len(rows), "worksheets": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/curriculum")
def get_curriculum(semester: int = Query(1, ge=1, le=3)):
    """
    Returns the organized curriculum hierarchy (Units & Lessons) for a given semester,
    including the count of available diagrams per lesson.
    """
    toc_list = TOC_REGISTRIES.get(semester, [])
    diag_bank = load_diagrams_bank(semester)

    # Count diagrams per lesson
    diag_counts = {}
    for d in diag_bank:
        l = d.get("lesson", "")
        diag_counts[l] = diag_counts.get(l, 0) + 1

    # Group into Units
    units_dict = {}
    for item in toc_list:
        u_name = item["unit"]
        if u_name not in units_dict:
            units_dict[u_name] = {
                "unit_name": u_name,
                "chapter_name": item["chapter"],
                "lessons": []
            }
        l_name = item["lesson"]
        cnt = diag_counts.get(l_name, 0)
        units_dict[u_name]["lessons"].append({
            "lesson_name": l_name,
            "start_page": item["start_page"],
            "end_page": item["end_page"],
            "has_diagrams": cnt > 0,
            "diagram_count": cnt
        })

    return {
        "semester": semester,
        "title": f"Grade 8 - Semester {semester} Science (علوم الصف الثاني المتوسط)",
        "units": list(units_dict.values()),
        "total_diagrams": len(diag_bank)
    }


@app.post("/api/assessment/diagram")
def get_diagram_assessment(req: DiagramAssessmentRequest):
    """
    Option 2: Diagram-Based Assessment.
    Retrieves approved, high-resolution scientific diagrams with interactive question cards
    (Short question, MCQ with 4 choices, and Reasoning question with explanations).
    """
    all_diagrams = load_diagrams_bank(req.semester)
    if not all_diagrams:
        raise HTTPException(status_code=404, detail=f"No diagrams found for semester {req.semester}")

    if req.lesson and req.lesson != "all":
        filtered = [d for d in all_diagrams if d["lesson"] == req.lesson]
        if not filtered:
            # If no diagrams directly for this exact lesson title, return all or top relevant
            filtered = all_diagrams[:6]
    else:
        filtered = all_diagrams

    return {
        "assessment_type": "diagram",
        "semester": req.semester,
        "lesson": req.lesson,
        "total_cards": len(filtered),
        "cards": filtered
    }


@app.post("/api/assessment/theory")
def generate_theory_assessment(req: TheoryAssessmentRequest):
    """
    Option 1: General Theory Assessment.
    Grounded in the official Grade 8 textbook text extracted from PDF.
    Caches directly into Docker MySQL 'theory_assessments' table!
    """
    # 1. Check MySQL cache first
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT assessment_json, diagram_url FROM theory_assessments WHERE semester = %s AND lesson = %s LIMIT 1",
                (req.semester, req.lesson)
            )
            cached_row = cur.fetchone()
        conn.close()

        if cached_row and cached_row.get("assessment_json"):
            data = cached_row["assessment_json"]
            if isinstance(data, str):
                data = json.loads(data)
            data["cached"] = True
            data["diagram_url"] = cached_row.get("diagram_url")
            return data
    except Exception as e:
        print(f"[MySQL Cache Check Warning] {e}")

    # 2. Find TOC lesson boundaries
    toc_list = TOC_REGISTRIES.get(req.semester, [])
    lesson_meta = next((item for item in toc_list if item["lesson"] == req.lesson), None)

    if not lesson_meta:
        # Fallback to the first content lesson
        lesson_meta = toc_list[2] if len(toc_list) > 2 else {"start_page": 10, "end_page": 25, "unit": "General", "chapter": "General", "lesson": req.lesson}

    # 3. Find diagram for this lesson if available
    all_diags = load_diagrams_bank(req.semester)
    matching_diags = [d for d in all_diags if d.get("lesson") == req.lesson]
    diagram_url = matching_diags[0]["image_url"] if matching_diags else None
    diagram_caption = matching_diags[0].get("short_question", {}).get("question", "") if matching_diags else ""

    # 4. Extract grounded textbook text from the PDF
    lesson_text = extract_lesson_text_from_pdf(req.semester, lesson_meta["start_page"], lesson_meta["end_page"])

    if not lesson_text or len(lesson_text) < 100:
        lesson_text = f"Curriculum topic: Grade 8 Science - {req.lesson}. Unit: {lesson_meta.get('unit')}, Chapter: {lesson_meta.get('chapter')}."

    # 5. Generate with OpenAI gpt-4o-mini
    if not client:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured on backend.")

    diagram_instruction = ""
    if diagram_url:
        diagram_instruction = f"""
NOTE: An authentic textbook diagram ({diagram_url}) is displayed directly above this assessment for the student to examine.
Please ensure at least 2 of the MCQs and 1 short question directly prompt the student to inspect this diagram (e.g., "Referring to the diagram above, what does...").
"""

    system_prompt = f"""You are a Master Middle-School Science Teacher creating an official assessment for Grade 8 Science students based on the Saudi Ministry of Education curriculum.

CURRICULUM TOPIC:
- Semester: {req.semester}
- Unit: {lesson_meta.get('unit')}
- Chapter: {lesson_meta.get('chapter')}
- Lesson: {lesson_meta.get('lesson')} (Pages {lesson_meta.get('start_page')} to {lesson_meta.get('end_page')})
{diagram_instruction}

GROUNDED LESSON TEXT:
\"\"\"{lesson_text[:8000]}\"\"\"

INSTRUCTIONS:
1. Generate an assessment with exactly:
   - 5 Multiple Choice Questions (MCQs): Each with 4 clear choices (A, B, C, D), correct option letter, and a concise educational explanation.
   - 3 Short Answer Questions: Clear, concept-focused questions with a model answer and key learning concept.
2. LANGUAGE:
   - Write all questions, options, and explanations in clear, accessible English appropriate for Grade 8 students.
   - For key scientific terminology, include the official Arabic term in brackets, for example: "Solvent (المذيب)", "Solute (المذاب)", "Acids (الأحماض)", "Photosynthesis (البناء الضوئي)".
3. GROUNDING:
   - Base all questions strictly on facts from this Grade 8 lesson. Do NOT hallucinate concepts outside this middle-school lesson.

OUTPUT FORMAT: Return ONLY valid JSON with no markdown fences, matching this exact schema:
{{
  "title": "Grade 8 Assessment: <Lesson Title in English> (<Lesson Title in Arabic>)",
  "lesson": "{req.lesson}",
  "unit": "{lesson_meta.get('unit')}",
  "chapter": "{lesson_meta.get('chapter')}",
  "mcqs": [
    {{
      "id": 1,
      "question": "...",
      "options": {{
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "..."
      }},
      "correct": "A",
      "explanation": "..."
    }}
  ],
  "short_questions": [
    {{
      "id": 1,
      "question": "...",
      "model_answer": "...",
      "key_concept": "..."
    }}
  ]
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a specialized Grade 8 Science educational test author. Output only valid JSON."},
                {"role": "user", "content": system_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        data["assessment_type"] = "theory"
        data["semester"] = req.semester
        data["diagram_url"] = diagram_url
        data["cached"] = False

        # Save to Docker MySQL theory_assessments table
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO theory_assessments (semester, lesson, diagram_url, assessment_json)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (req.semester, req.lesson, diagram_url, json.dumps(data, ensure_ascii=False))
                )
            conn.close()
        except Exception as db_err:
            print(f"[MySQL Insert Warning] {db_err}")

        return data
    except Exception as e:
        print(f"[OpenAI Generation Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate assessment: {str(e)}")


@app.post("/api/chat")
def conversational_tutor_chat(req: ChatRequest):
    """
    Conversational AI Tutor endpoint.
    STRICTLY grounded to Grade 8 Science textbook content only.
    Refuses all off-topic queries (sports, politics, entertainment, etc.).
    """
    if not client:
        return {
            "reply": "Please configure your OpenAI API key in .env to activate chat.",
            "suggestions": ["Create an Assessment"]
        }

    # Build the curriculum topic list for grounding context
    toc_list = TOC_REGISTRIES.get(req.semester, [])
    topic_summary = ", ".join(set(item["chapter"] for item in toc_list if "مقدمة" not in item["unit"] and "مصادر" not in item["unit"]))

    # Retrieve relevant textbook passages from Qdrant Vector DB
    retrieved_context = ""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        qc = QdrantClient(host="localhost", port=6333)
        emb = client.embeddings.create(input=req.message, model="text-embedding-3-small").data[0].embedding
        res = qc.query_points(
            collection_name="grade8_science_chunks",
            query=emb,
            limit=3,
            query_filter=Filter(
                must=[FieldCondition(key="semester", match=MatchValue(value=req.semester))]
            ) if req.semester else None
        )
        hits = res.points
        if hits:
            retrieved_context = "\n\n".join([f"[Page {h.payload.get('page_number')}]: {h.payload.get('text')}" for h in hits])
    except Exception as q_err:
        print(f"[Qdrant Retrieval Warning] {q_err}")

    context_prompt = f"\n\nOFFICIAL TEXTBOOK PASSAGES (FROM QDRANT VECTOR DB):\n\"\"\"{retrieved_context}\"\"\"\n" if retrieved_context else ""

    system_prompt = f"""You are a Grade 8 Science tutor. Your ONLY knowledge domain is the Saudi Grade 8 Science textbook (علوم الصف الثاني المتوسط).

CURRENT SEMESTER: {req.semester}
TEXTBOOK CHAPTERS THIS SEMESTER: {topic_summary}
{context_prompt}
ABSOLUTE RULES — YOU MUST FOLLOW EVERY SINGLE ONE:
1. Ground your answers directly in the textbook passages provided above.
2. You ONLY answer questions directly related to Grade 8 Science curriculum topics listed above.
2. If the student asks about ANYTHING outside Grade 8 Science — sports, politics, wars, celebrities, movies, games, personal advice, math, history, geography, other school subjects, or ANY topic not covered in the Grade 8 Science textbook — you MUST refuse with EXACTLY this response:
   "This question is outside the Grade 8 Science curriculum. I can only help with science topics from your textbook. Try asking about [suggest a relevant science topic from the chapters above]."
3. Do NOT answer general knowledge questions, trivia, or opinions even if they seem harmless.
4. Do NOT say "I'm not sure" and then answer anyway. If it's off-topic, REFUSE completely.
5. Keep answers concise and focused. Use English with Arabic scientific terms in brackets where relevant.
6. If the student asks for a quiz or test, tell them to use the "Create Assessment" button.

EXAMPLES OF QUESTIONS YOU MUST REFUSE:
- "Who is better, Messi or Ronaldo?" → REFUSE
- "Tell me about the Iran war" → REFUSE  
- "What is the capital of France?" → REFUSE
- "Help me with math homework" → REFUSE
- "Write me a poem" → REFUSE
- "What is ChatGPT?" → REFUSE

EXAMPLES OF QUESTIONS YOU MUST ANSWER:
- "What is a solution?" → ANSWER (Chapter 2: Solutions & Solubility)
- "Explain the digestive system" → ANSWER (Chapter 6: Digestion)
- "What is pH?" → ANSWER (Chapter 2: Acids & Bases)
- "How does heat transfer work?" → ANSWER (Chapter 11: Thermal Energy)"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in req.history[-6:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1,
            max_tokens=400
        )
        reply_text = response.choices[0].message.content

        # Save to Docker MySQL chat_history table
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat_history (semester, user_message, bot_reply) VALUES (%s, %s, %s)",
                    (req.semester, req.message, reply_text)
                )
            conn.close()
        except Exception as db_err:
            print(f"[MySQL Chat Log Warning] {db_err}")

        suggestions = ["Create an Assessment"]

        return {
            "reply": reply_text,
            "suggestions": suggestions
        }
    except Exception as e:
        return {
            "reply": f"Temporary error: {str(e)}",
            "suggestions": ["Create an Assessment"]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot_backend:app", host="127.0.0.1", port=8000, reload=True)


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
import json
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

# Qdrant & Server Configuration loaded dynamically from .env
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "grade8_science_chunks")
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8000"))

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
    
    label_dir = BASE_DIR / f"labeling_sem{sem}"
    if not label_dir.exists():
        label_dir.mkdir(exist_ok=True)
    app.mount(f"/labeling_sem{sem}", StaticFiles(directory=str(label_dir)), name=f"labeling_sem{sem}")

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
    1: "grade_8_semester_1.pdf",
    2: "grade_8_semester_2.pdf",
    3: "grade_8_semester_3.pdf",
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

def retrieve_chunks_from_qdrant(query: str, semester: int, limit: int = 5) -> str:
    """Retrieves grounded textbook chunks from Qdrant Vector DB for the semester."""
    if not client:
        return ""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        emb = client.embeddings.create(input=query, model="text-embedding-3-small").data[0].embedding
        hits = qc.query_points(
            collection_name=QDRANT_COLLECTION,
            query=emb,
            query_filter=Filter(
                must=[FieldCondition(key="semester", match=MatchValue(value=semester))]
            ),
            limit=limit
        ).points
        chunks = [h.payload.get("text", "").strip() for h in hits if h.payload and h.payload.get("text")]
        return "\n\n---\n\n".join(chunks)
    except Exception as e:
        print(f"[Qdrant Retrieval Warning] {e}")
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
    lesson: Optional[str] = None
    topic: Optional[str] = None
    question_type: Optional[str] = "both"  # "mcq", "short", "both"
    num_mcq: Optional[int] = 5
    num_short: Optional[int] = 3

class DiagramAssessmentRequest(BaseModel):
    semester: int
    lesson: Optional[str] = "all"
    topic: Optional[str] = None
    num_questions: Optional[int] = 3

class LabelingAssessmentRequest(BaseModel):
    semester: int
    lesson: Optional[str] = "all"
    topic: Optional[str] = None
    limit: Optional[int] = 3

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
    including separate counts for general diagrams and interactive labeling diagrams per lesson.
    """
    toc_list = TOC_REGISTRIES.get(semester, [])
    
    diag_counts = {}
    label_counts = {}
    total_diag = 0
    total_label = 0

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lesson,
                       SUM(CASE WHEN is_useful_for_questions = 'YES' THEN 1 ELSE 0 END) AS diag_cnt,
                       SUM(CASE WHEN is_suitable_for_labeling = 'YES' AND masked_labels_json IS NOT NULL THEN 1 ELSE 0 END) AS label_cnt
                FROM diagram_metadata
                WHERE semester = %s
                GROUP BY lesson;
            """, (semester,))
            rows = cur.fetchall()
            for r in rows:
                l_name = r.get("lesson") or ""
                dc = int(r.get("diag_cnt") or 0)
                lc = int(r.get("label_cnt") or 0)
                diag_counts[l_name] = dc
                label_counts[l_name] = lc
                total_diag += dc
                total_label += lc
        conn.close()
    except Exception as e:
        print(f"[get_curriculum DB Error] {e}")
        diag_bank = load_diagrams_bank(semester)
        for d in diag_bank:
            l = d.get("lesson", "")
            diag_counts[l] = diag_counts.get(l, 0) + 1
        total_diag = len(diag_bank)

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
        lbl_cnt = label_counts.get(l_name, 0)
        units_dict[u_name]["lessons"].append({
            "lesson_name": l_name,
            "start_page": item["start_page"],
            "end_page": item["end_page"],
            "has_diagrams": cnt > 0,
            "diagram_count": cnt,
            "has_labeling": lbl_cnt > 0,
            "labeling_count": lbl_cnt
        })

    return {
        "semester": semester,
        "title": f"Grade 8 - Semester {semester} Science (علوم الصف الثاني المتوسط)",
        "units": list(units_dict.values()),
        "total_diagrams": total_diag,
        "total_labeling_diagrams": total_label
    }


@app.post("/api/assessment/diagram")
def get_diagram_assessment(req: DiagramAssessmentRequest):
    """
    Option 2: Diagram-Based Assessment.
    Retrieves approved, high-resolution scientific diagrams with interactive question cards
    generated dynamically based on visual elements and authentic Document AI descriptions.
    """
    num_q = req.num_questions or 3
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if req.lesson and req.lesson != "all":
                cur.execute("""
                    SELECT id, semester, unit, chapter, lesson, description, image_filename, image_path, resolution,
                           is_suitable_for_labeling, is_useful_for_questions
                    FROM diagram_metadata
                    WHERE semester = %s AND lesson = %s AND is_useful_for_questions = 'YES'
                    ORDER BY RAND() LIMIT %s;
                """, (req.semester, req.lesson, num_q))
            else:
                cur.execute("""
                    SELECT id, semester, unit, chapter, lesson, description, image_filename, image_path, resolution,
                           is_suitable_for_labeling, is_useful_for_questions
                    FROM diagram_metadata
                    WHERE semester = %s AND is_useful_for_questions = 'YES'
                    ORDER BY RAND() LIMIT %s;
                """, (req.semester, num_q))
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"[MySQL Diagram Fetch Warning] {e}")
        rows = []

    if not rows:
        rows = load_diagrams_bank(req.semester)[:num_q]

    if not rows:
        raise HTTPException(status_code=404, detail=f"No approved diagrams found for semester {req.semester}")

    cards = []
    for r in rows:
        img_rel = r.get("image_path", "").replace("\\", "/")
        if not img_rel.startswith("/"):
            img_rel = "/" + img_rel

        desc = r.get("description", "Scientific textbook diagram")
        lesson_name = r.get("lesson", "Science Lesson")

        prompt = f"""You are an educational assessment author inspecting this Saudi Grade 8 Science diagram.
DIAGRAM CONTEXT:
- Lesson: {lesson_name}
- Detailed Description: {desc}

INSTRUCTIONS:
Generate 3 distinct visual-based questions that test student comprehension of this specific illustration:
1. Short Question: Direct question asking about a key component or process visible in the diagram.
2. MCQ: 4 choices (A, B, C, D), correct option, and concise explanation.
3. Scientific Reasoning Question: A 'Why' or 'How' question based on the mechanism shown in the diagram, with detailed answer.

OUTPUT FORMAT: Return ONLY valid JSON:
{{
  "short_question": {{"question": "...", "answer": "..."}},
  "mcq": {{
    "question": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct": "A",
    "explanation": "..."
  }},
  "reasoning_question": {{"question": "...", "answer": "..."}}
}}"""

        try:
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            q_data = json.loads(res.choices[0].message.content)
        except Exception:
            q_data = {
                "short_question": {"question": f"What key component or process is depicted in this {lesson_name} diagram?", "answer": desc[:200]},
                "mcq": {
                    "question": f"Based on this diagram of {lesson_name}, which component is primarily highlighted?",
                    "options": {"A": "Core active organ/component", "B": "Inactive membrane", "C": "External artifact", "D": "Support boundary"},
                    "correct": "A",
                    "explanation": "Derived directly from the diagram structure."
                },
                "reasoning_question": {"question": f"Why is this mechanism critical in {lesson_name}?", "answer": "It facilitates the fundamental physiological/physical transport or reaction."}
            }

        cards.append({
            "id": f"diag_{r.get('id', 1)}",
            "lesson": lesson_name,
            "description": desc,
            "image_url": img_rel,
            "short_question": q_data.get("short_question", {}),
            "mcq": q_data.get("mcq", {}),
            "reasoning_question": q_data.get("reasoning_question", {})
        })

    return {
        "assessment_type": "diagram",
        "semester": req.semester,
        "lesson": req.lesson,
        "total_cards": len(cards),
        "cards": cards
    }


@app.post("/api/assessment/labeling")
def get_labeling_assessment(req: LabelingAssessmentRequest):
    """
    Interactive Labeling Quiz Endpoint.
    Returns masked diagrams with pins (①, ②, ③...) and options for students to match/label.
    """
    import random
    limit_cnt = req.limit or 5
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if req.lesson and req.lesson != "all":
                cur.execute("""
                    SELECT id, semester, unit, chapter, lesson, description, image_filename, masked_labels_json
                    FROM diagram_metadata
                    WHERE semester = %s AND lesson = %s AND is_suitable_for_labeling = 'YES' AND masked_labels_json IS NOT NULL
                    ORDER BY RAND() LIMIT %s;
                """, (req.semester, req.lesson, limit_cnt))
            else:
                cur.execute("""
                    SELECT id, semester, unit, chapter, lesson, description, image_filename, masked_labels_json
                    FROM diagram_metadata
                    WHERE semester = %s AND is_suitable_for_labeling = 'YES' AND masked_labels_json IS NOT NULL
                    ORDER BY RAND() LIMIT %s;
                """, (req.semester, limit_cnt))
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"[MySQL Labeling Fetch Warning] {e}")
        rows = []

    if not rows:
        raise HTTPException(status_code=404, detail=f"No interactive labeling diagrams found for semester {req.semester}")

    results = []
    distractor_bank = [
        "المعدة", "الكبد", "الرئة", "القلب", "الشريان الأبهر", "خلية دم حمراء",
        "غشاء بلازمي", "النواة", "الميتوكندريا", "البنكرياس", "الأمعاء الدقيقة", "الشريان الرئوي"
    ]

    for r in rows:
        mapping = r.get("masked_labels_json")
        if isinstance(mapping, str):
            try:
                mapping = json.loads(mapping)
            except Exception:
                mapping = {}
        if not mapping or not isinstance(mapping, dict):
            continue

        filename = r["image_filename"]
        sem = r["semester"]
        image_url = f"/labeling_sem{sem}/{filename}"

        # Collect Arabic labels + distractors
        correct_labels = list(mapping.values())
        pool = list(set(correct_labels))
        for d in distractor_bank:
            if d not in pool and len(pool) < len(correct_labels) + 3:
                pool.append(d)
        random.shuffle(pool)

        results.append({
            "id": r["id"],
            "semester": sem,
            "lesson": r.get("lesson", ""),
            "description": r.get("description", ""),
            "image_url": image_url,
            "masked_labels": mapping,
            "options": pool,
            "total_pins": len(mapping)
        })

    return {
        "assessment_type": "labeling",
        "semester": req.semester,
        "count": len(results),
        "diagrams": results
    }


@app.post("/api/assessment/theory")
def generate_theory_assessment(req: TheoryAssessmentRequest):
    """
    Option 1: General Theory Assessment.
    Grounded strictly via Qdrant Vector DB chunks.
    Dynamically authors MCQs and Short Questions as requested by the teacher.
    """
    topic_query = req.topic or req.lesson or "General Science"

    # 1. Retrieve grounded textbook chunks from Qdrant Vector DB
    grounded_chunks = retrieve_chunks_from_qdrant(topic_query, req.semester, limit=5)

    # Fallback to PDF if Qdrant returned nothing (e.g. docker just restarted)
    if not grounded_chunks or len(grounded_chunks) < 50:
        toc_list = TOC_REGISTRIES.get(req.semester, [])
        lesson_meta = next((item for item in toc_list if item["lesson"] == req.lesson), None)
        if lesson_meta:
            grounded_chunks = extract_lesson_text_from_pdf(req.semester, lesson_meta["start_page"], lesson_meta["end_page"])

    if not grounded_chunks:
        grounded_chunks = f"Grade 8 Science curriculum topic: {topic_query}."

    if not client:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured on backend.")

    num_mcqs = req.num_mcq if req.question_type in ["mcq", "both"] else 0
    num_short = req.num_short if req.question_type in ["short", "both"] else 0
    if num_mcqs == 0 and num_short == 0:
        num_mcqs = 5

    system_prompt = f"""You are an expert Grade 8 Science Teacher creating an official assessment based on the Saudi Ministry of Education curriculum.

CURRICULUM TOPIC:
- Semester: {req.semester}
- Topic / Lesson: {topic_query}

GROUNDED TEXTBOOK CHUNKS (From Qdrant Vector DB):
\"\"\"{grounded_chunks[:8000]}\"\"\"

INSTRUCTIONS:
1. Generate an assessment strictly from the grounded chunks above with:
   - Exactly {num_mcqs} Multiple Choice Questions (MCQs): Each with 4 choices (A, B, C, D), correct option letter, and clear educational explanation.
   - Exactly {num_short} Short Answer Questions: Concept questions with a model answer and key learning concept.
2. LANGUAGE & TERMS:
   - Questions and options in accessible English for 8th-grade students.
   - For key scientific concepts, include official Arabic terminology in brackets (e.g. "Solvent (المذيب)", "Circulatory System (جهاز الدوران)").
3. STRICT GROUNDING:
   - Base all questions strictly on facts from the provided text chunks. Do NOT hallucinate concepts outside this textbook material.

OUTPUT FORMAT: Return ONLY valid JSON with this exact schema:
{{
  "title": "Grade 8 Assessment: {topic_query}",
  "topic": "{topic_query}",
  "lesson": "{req.lesson or topic_query}",
  "semester": {req.semester},
  "mcqs": [
    {{
      "id": 1,
      "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
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
        return data
    except Exception as e:
        print(f"[OpenAI Theory Assessment Error] {e}")
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
        qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        emb = client.embeddings.create(input=req.message, model="text-embedding-3-small").data[0].embedding
        res = qc.query_points(
            collection_name=QDRANT_COLLECTION,
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

    system_prompt = f"""You are an encouraging, expert Grade 8 Science tutor for Saudi Middle School students (علوم الصف الثاني المتوسط).
Your knowledge domain is strictly focused on the Saudi Grade 8 Science textbook.

CURRENT SEMESTER: {req.semester}
TEXTBOOK CHAPTERS THIS SEMESTER: {topic_summary}
{context_prompt}
RULES YOU MUST FOLLOW:
1. GREETINGS & POLITE CHIT-CHAT (ALWAYS WELCOME & POLITE):
   - When a student says "Hello", "Hi", "Salam / Assalam-o-Alaikum", "How are you?", "Who are you?", or expresses gratitude ("Thank you", "Thanks"), respond warmly, politely, and enthusiastically as their friendly Science Tutor!
   - Invite them to explore or ask about any chapter or concept from their textbook.
   - NEVER refuse basic greetings or polite social pleasantries!

2. CONVERSATIONAL CONTINUITY & FOLLOW-UPS:
   - Follow the conversation history naturally. If the student asks to clarify a previous topic (e.g., "Can you explain that more simply?", "Give me another example", "What does that term mean?"), maintain context and provide a clear, accessible explanation.

3. STRICT GROUNDING IN SCIENCE TEXTBOOK:
   - For all scientific questions, ground your explanations directly in the official Grade 8 Science textbook passages provided above.
   - Use accessible English with official Arabic scientific terms in brackets where relevant (e.g., "Circulatory System (جهاز الدوران)").

4. OFF-TOPIC ACADEMIC/ENTERTAINMENT REFUSAL:
   - If the student asks about external domains unrelated to science — such as sports, football (Messi/Ronaldo), celebrities, movies, video games, politics, wars, personal advice, or other school subjects (history, geography, literature) — politely refuse with:
     "This question is outside the Grade 8 Science curriculum. I can only help with science topics from your textbook. Try asking about [suggest a relevant science topic from the chapters above]."

5. ASSESSMENTS:
   - If the student explicitly asks for a full quiz or interactive test, remind them they can click the "Create Assessment" button or specify how many questions they want.

EXAMPLES OF INTERACTIONS:
- "How are you?" → "I'm doing great, thank you! Ready to help you learn Grade 8 Science. Which topic or chapter would you like to explore today?"
- "Hello / Salam" → "Hello and welcome! I am your Grade 8 Science tutor. What science concept can I help you with today?"
- "Thank you" → "You're very welcome! Best of luck with your studies. Feel free to ask whenever you need help."
- "What is a solution?" → Explain solutions using Chapter 2 concepts.
- "Who won the World Cup?" → Politely refuse as it is outside Grade 8 science."""

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
        print(f"[Chatbot Endpoint Error] {e}")
        return {
            "reply": "I encountered a temporary connection issue. Please try asking your question again in a moment.",
            "suggestions": ["Create an Assessment"]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot_backend:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)


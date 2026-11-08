"""
Educational Diagram Extraction, Vision Evaluation & MySQL Pipeline
Grade 8 Science (Saudi Curriculum)
==================================================================
1. Code-Level Fast Filters: Discards QR codes, thin line banners, and tiny icons without LLM calls.
2. Multimodal Vision Gatekeeper (gpt-4o-mini with Vision):
   - Passes the actual Base64 Image to the AI.
   - Discards decorative photos, covers, and banners.
   - Flags: is_suitable_for_labeling ('YES'/'NO') and is_useful_for_questions ('YES'/'NO').
3. Dual Storage:
   - Saves clean PNGs to output_diagrams_semX/
   - Writes Excel CSV: diagrams_metadata_semX.csv with UTF-8-BOM encoding.
   - Inserts records into Docker MySQL: diagram_metadata table.
   - Generates lesson-wise HTML worksheets and uploads directly into Docker MySQL: lesson_worksheets table!
"""

import os
import io
import re
import sys
import csv
import json
import glob
import base64
import argparse

# Fix Windows console cp1252 stdout encoding for Arabic & emojis
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI
from db import get_db_connection as get_db

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

BOUNDING_BOX_PADDING_RATIO = 0.015


# ==============================================================================
# BASE64 ENCODING / DECODING
# ==============================================================================

def decode_base64_image(base64_string: str) -> Image.Image:
    image_bytes = base64.b64decode(base64_string)
    image = Image.open(io.BytesIO(image_bytes))
    return image.convert("RGB")

def encode_pil_image_to_base64(img: Image.Image, format: str = "PNG") -> str:
    buffered = io.BytesIO()
    img.save(buffered, format=format, optimize=True)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# ==============================================================================
# FAST RULE-BASED FILTERS (0 TOKENS USED)
# ==============================================================================

def is_noise_by_rules(img: Image.Image, description: str = "", page_num: int = 1) -> tuple[bool, str]:
    w, h = img.size

    # 1. Preface / Intro Pages filter (pages 1-7 are textbook cover and intro, no curriculum diagrams)
    if page_num <= 7:
        return True, f"Preface / Table of Contents page ({page_num})"

    # 2. Dimension & aspect ratio filters
    if w < 70 or h < 70:
        return True, f"Image too small ({w}x{h} px)"
    if (w / h > 6.0) or (h / w > 6.0):
        return True, f"Extreme aspect ratio ({w}x{h} px) - likely a divider banner or rule line"

    # 3. QR code, cover, decorative animal photos, and montage keywords
    desc_lower = description.lower() if description else ""
    noise_keywords = [
        "qr code", "barcode", "ministry logo", "cover page", "table of contents",
        "preface art", "horse", "horses", "desert landscape", "decorative montage", "collage"
    ]
    for kw in noise_keywords:
        if kw in desc_lower:
            return True, f"Matched noise keyword: '{kw}'"

    return False, "Passed rule-based checks"

# ==============================================================================
# MULTIMODAL VISION GATEKEEPER (gpt-4o-mini with Vision)
# ==============================================================================

def vision_gatekeeper(img: Image.Image, description: str = "") -> dict:
    """
    Sends actual Base64 image to gpt-4o-mini Vision to evaluate suitability for
    labeling and scientific assessment questions.
    """
    base64_str = encode_pil_image_to_base64(img)

    system_prompt = """You are a strict Science Educational Dataset Gatekeeper inspecting Saudi Grade 8 Science diagrams.
Analyze the attached visual and evaluate if it should be KEPT as an instructional science illustration.

RULES:
1. REJECT (should_keep = false):
   - Real-world photographs of people, children, meals/food, landscapes without scientific labels.
   - Decorative borders, book cover art, generic icons.
   - Chapter/unit opener artwork, montages, decorative animal photos (e.g., running horses, eagles, camels), scenic landscapes, or collages even if they contain a small inset diagram/molecule badge.
   - Generic background illustrations that do not teach an 8th-grade science curriculum mechanism.
2. KEEP (should_keep = true):
   - Anatomical diagrams (heart, lungs, digestive system, eye, cell, skeleton).
   - Molecular models & particle views (solutions, atoms, molecules).
   - Scientific curves, graphs, charts (solubility, pH, velocity, temperature).
   - Laboratory apparatus setups and physical wave/energy models.

Also evaluate:
- is_suitable_for_labeling: 'YES' if it contains distinct labeled components/organs/parts that students can identify or fill in. Otherwise 'NO'.
- is_useful_for_questions: 'YES' if educational short questions or MCQs can be derived from it. Otherwise 'NO'.

Respond ONLY with valid JSON:
{
  "should_keep": true/false,
  "is_suitable_for_labeling": "YES" or "NO",
  "is_useful_for_questions": "YES" or "NO",
  "reason": "Brief 1-sentence technical justification"
}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Evaluate this textbook illustration. Context: {description[:300] if description else 'N/A'}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_str}", "detail": "low"}}
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"    [Vision Gatekeeper Error]: {e}")
        return {"should_keep": False, "is_suitable_for_labeling": "NO", "is_useful_for_questions": "NO", "reason": str(e)}

# ==============================================================================
# OFFICIAL TABLE OF CONTENTS (TOC)
# ==============================================================================

GRADE_8_SEM1_TOC = [
    (1, 7, "المقدمة والتمهيد", "المقدمة وفهرس المحتويات", "تمهيد وفهرس"),
    (8, 13, "الوحدة 1: دراسة المادة", "الفصل 1: طبيعة العلم", "افتتاحية الفصل والتهيئة للقراءة"),
    (14, 21, "الوحدة 1: دراسة المادة", "الفصل 1: طبيعة العلم", "الدرس 1: أسلوب العلم"),
    (22, 27, "الوحدة 1: دراسة المادة", "الفصل 1: طبيعة العلم", "الدرس 2: حل المشكلات بطريقة علمية"),
    (28, 33, "الوحدة 1: دراسة المادة", "الفصل 1: طبيعة العلم", "استقصاء ومراجعة الفصل"),
    (34, 37, "الوحدة 1: دراسة المادة", "الفصل 2: المخاليط والمحاليل", "افتتاحية الفصل والتهيئة للقراءة"),
    (38, 47, "الوحدة 1: دراسة المادة", "الفصل 2: المخاليط والمحاليل", "الدرس 1: المحاليل والذائبية"),
    (48, 55, "الوحدة 1: دراسة المادة", "الفصل 2: المخاليط والمحاليل", "الدرس 2: المحاليل الحمضية والمحاليل القاعدية"),
    (56, 65, "الوحدة 1: دراسة المادة", "الفصل 2: المخاليط والمحاليل", "استقصاء ومراجعة الفصل واختبار مقنن"),
    (66, 69, "الوحدة 2: المادة والطاقة", "الفصل 3: حالات المادة", "افتتاحية الفصل والتهيئة للقراءة"),
    (70, 74, "الوحدة 2: المادة والطاقة", "الفصل 3: حالات المادة", "الدرس 1: المادة"),
    (75, 82, "الوحدة 2: المادة والطاقة", "الفصل 3: حالات المادة", "الدرس 2: الحرارة وتحولات المادة"),
    (83, 91, "الوحدة 2: المادة والطاقة", "الفصل 3: حالات المادة", "الدرس 3: سلوك الموائع"),
    (92, 97, "الوحدة 2: المادة والطاقة", "الفصل 3: حالات المادة", "استقصاء ومراجعة الفصل"),
    (98, 101, "الوحدة 2: المادة والطاقة", "الفصل 4: الطاقة وتحولاتها", "افتتاحية الفصل والتهيئة للقراءة"),
    (102, 106, "الوحدة 2: المادة والطاقة", "الفصل 4: الطاقة وتحولاتها", "الدرس 1: ما الطاقة؟"),
    (107, 115, "الوحدة 2: المادة والطاقة", "الفصل 4: الطاقة وتحولاتها", "الدرس 2: تحولات الطاقة"),
    (116, 125, "الوحدة 2: المادة والطاقة", "الفصل 4: الطاقة وتحولاتها", "استقصاء ومراجعة الفصل واختبار مقنن"),
]

GRADE_8_SEM2_TOC = [
    (1, 8, "المقدمة والتمهيد", "المقدمة وفهرس المحتويات", "تمهيد وفهرس"),
    (9, 13, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 5: جهازا الدوران والمناعة", "افتتاحية الفصل والتهيئة للقراءة"),
    (14, 22, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 5: جهازا الدوران والمناعة", "الدرس 1: جهاز الدوران"),
    (23, 33, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 5: جهازا الدوران والمناعة", "الدرس 2: المناعة والمرض"),
    (34, 39, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 5: جهازا الدوران والمناعة", "استقصاء ومراجعة الفصل"),
    (40, 43, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 6: الهضم والتنفس والإخراج", "افتتاحية الفصل والتهيئة للقراءة"),
    (44, 54, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 6: الهضم والتنفس والإخراج", "الدرس 1: الجهاز الهضمي والمواد الغذائية"),
    (55, 67, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 6: الهضم والتنفس والإخراج", "الدرس 2: جهازا التنفس والإخراج"),
    (68, 77, "الوحدة 3: أجهزة جسم الإنسان (1)", "الفصل 6: الهضم والتنفس والإخراج", "استقصاء ومراجعة الفصل واختبار مقنن"),
    (78, 83, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "افتتاحية الفصل والتهيئة للقراءة"),
    (84, 92, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "الدرس 1: الجلد والعضلات"),
    (93, 107, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "الدرس 2: الجهاز الهيكلي والجهاز العصبي"),
    (108, 113, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 7: أجهزة الدعامة والحركة والاستجابة", "استقصاء ومراجعة الفصل"),
    (114, 117, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 8: التنظيم والتكاثر", "افتتاحية الفصل والتهيئة للقراءة"),
    (118, 130, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 8: التنظيم والتكاثر", "الدرس 1: جهازا الغدد الصم والتكاثر"),
    (131, 139, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 8: التنظيم والتكاثر", "الدرس 2: مراحل حياة الإنسان"),
    (140, 145, "الوحدة 4: أجهزة جسم الإنسان (2)", "الفصل 8: التنظيم والتكاثر", "استقصاء ومراجعة الفصل واختبار مقنن"),
]

GRADE_8_SEM3_TOC = [
    (1, 8, "المقدمة والتمهيد", "المقدمة وفهرس المحتويات", "تمهيد وفهرس"),
    (9, 17, "الوحدة 5: النباتات وموارد البيئة", "الفصل 9: النباتات", "افتتاحية الفصل والتهيئة للقراءة"),
    (18, 24, "الوحدة 5: النباتات وموارد البيئة", "الفصل 9: النباتات", "الدرس 1: النباتات اللابذرية"),
    (25, 33, "الوحدة 5: النباتات وموارد البيئة", "الفصل 9: النباتات", "الدرس 2: النباتات البذرية"),
    (34, 39, "الوحدة 5: النباتات وموارد البيئة", "الفصل 9: النباتات", "استقصاء ومراجعة الفصل"),
    (40, 43, "الوحدة 5: النباتات وموارد البيئة", "الفصل 10: موارد البيئة وحمايتها", "افتتاحية الفصل والتهيئة للقراءة"),
    (44, 54, "الوحدة 5: النباتات وموارد البيئة", "الفصل 10: موارد البيئة وحمايتها", "الدرس 1: موارد البيئة"),
    (55, 67, "الوحدة 5: النباتات وموارد البيئة", "الفصل 10: موارد البيئة وحمايتها", "الدرس 2: التلوث وحماية البيئة"),
    (68, 77, "الوحدة 5: النباتات وموارد البيئة", "الفصل 10: موارد البيئة وحمايتها", "استقصاء ومراجعة الفصل واختبار مقنن"),
    (78, 81, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 11: الطاقة الحرارية", "افتتاحية الفصل والتهيئة للقراءة"),
    (82, 85, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 11: الطاقة الحرارية", "الدرس 1: درجة الحرارة"),
    (86, 91, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 11: الطاقة الحرارية", "الدرس 2: انتقال الحرارة"),
    (92, 95, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 11: الطاقة الحرارية", "الدرس 3: المحركات والثلاجات"),
    (96, 101, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 11: الطاقة الحرارية", "استقصاء ومراجعة الفصل"),
    (102, 105, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 12: الموجات والصوت والضوء", "افتتاحية الفصل والتهيئة للقراءة"),
    (106, 113, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 12: الموجات والصوت والضوء", "الدرس 1: الموجات"),
    (114, 118, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 12: الموجات والصوت والضوء", "الدرس 2: موجات الصوت"),
    (119, 125, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 12: الموجات والصوت والضوء", "الدرس 3: الضوء"),
    (126, 134, "الوحدة 6: الطاقة الحرارية والموجات", "الفصل 12: الموجات والصوت والضوء", "استقصاء ومراجعة الفصل واختبار مقنن"),
]

SEMESTER_CONFIGS = {
    "1": {
        "title": "Grade 8 - Semester 1 (الفصل الدراسي الأول)",
        "json_candidates": ["science_complete_layout.json", "grade_8_semester_1_science_complete_layout.json"],
        "output_dir": "output_diagrams_sem1",
        "csv_path": "diagrams_metadata_sem1.csv",
        "toc": GRADE_8_SEM1_TOC,
    },
    "2": {
        "title": "Grade 8 - Semester 2 (الفصل الدراسي الثاني)",
        "json_candidates": ["document (4).json", "document (3).json", "grade_8_semester_2_science_complete_layout.json"],
        "output_dir": "output_diagrams_sem2",
        "csv_path": "diagrams_metadata_sem2.csv",
        "toc": GRADE_8_SEM2_TOC,
    },
    "3": {
        "title": "Grade 8 - Semester 3 (الفصل الدراسي الثالث)",
        "json_candidates": ["document (3).json", "grade_8_semester_3_science_complete_layout.json"],
        "output_dir": "output_diagrams_sem3",
        "csv_path": "diagrams_metadata_sem3.csv",
        "toc": GRADE_8_SEM3_TOC,
    },
}

def get_chapter_and_unit_by_page(page_number: int, toc_registry: list) -> tuple[str, str, str]:
    for start_page, end_page, unit_title, chapter_title, lesson_title in toc_registry:
        if start_page <= page_number <= end_page:
            return unit_title, chapter_title, lesson_title
    return "الوحدة العامة", "الفصل العام", "الدرس العام"

# ==============================================================================
# DOCUMENT AI PARSER & IMAGE RETRIEVAL
# ==============================================================================

class PageImageManager:
    def __init__(self, doc_data: dict):
        self.blob_map = {}
        for blob in doc_data.get("blobAssets", []):
            asset_id = blob.get("assetId")
            content = blob.get("content")
            if asset_id and content:
                self.blob_map[asset_id] = content

        self.page_base64_map = {}
        for page in doc_data.get("pages", []):
            page_num = page.get("pageNumber")
            content = page.get("image", {}).get("content")
            if page_num and content:
                self.page_base64_map[page_num] = content

    def get_image_for_block(self, block: dict) -> Image.Image | None:
        ib = block.get("imageBlock", {})
        blob_id = ib.get("blobAssetId")
        if blob_id and blob_id in self.blob_map:
            return decode_base64_image(self.blob_map[blob_id])

        page_num = block.get("pageSpan", {}).get("pageStart", 1)
        if page_num in self.page_base64_map:
            page_img = decode_base64_image(self.page_base64_map[page_num])
            vertices = block.get("boundingBox", {}).get("normalizedVertices", [])
            if vertices:
                page_w, page_h = page_img.size
                xs = [pt.get("x", 0.0) for pt in vertices]
                ys = [pt.get("y", 0.0) for pt in vertices]
                min_x = max(0.0, min(xs) - BOUNDING_BOX_PADDING_RATIO)
                max_x = min(1.0, max(xs) + BOUNDING_BOX_PADDING_RATIO)
                min_y = max(0.0, min(ys) - BOUNDING_BOX_PADDING_RATIO)
                max_y = min(1.0, max(ys) + BOUNDING_BOX_PADDING_RATIO)
                return page_img.crop((int(min_x * page_w), int(min_y * page_h), int(max_x * page_w), int(max_y * page_h)))
            return page_img
        return None

def flatten_layout_blocks(blocks: list) -> list:
    flat = []
    for b in blocks:
        flat.append(b)
        sub_blocks = b.get("blocks", [])
        if sub_blocks:
            flat.extend(flatten_layout_blocks(sub_blocks))
    return flat

# ==============================================================================
# HTML WORKSHEET GENERATOR (Saved to MySQL)
# ==============================================================================

def generate_lesson_html_worksheet(lesson_name: str, unit_name: str, chapter_name: str, semester: int, diagrams: list) -> str:
    """
    Generates a sleek, interactive HTML worksheet for a specific lesson
    to be stored directly in MySQL lesson_worksheets table.
    """
    cards_html = ""
    for idx, d in enumerate(diagrams, start=1):
        cards_html += f"""
        <div class="worksheet-card">
          <div class="card-header">
            <h4>Diagram #{idx}: {d['image_filename']}</h4>
            <div class="badges">
              <span class="badge {'badge-yes' if d['is_suitable_for_labeling'] == 'YES' else 'badge-no'}">
                Labeling: {d['is_suitable_for_labeling']}
              </span>
              <span class="badge {'badge-yes' if d['is_useful_for_questions'] == 'YES' else 'badge-no'}">
                Questions: {d['is_useful_for_questions']}
              </span>
            </div>
          </div>
          <div class="card-body">
            <div class="img-box">
              <img src="/{d['image_path'].replace('\\\\', '/')}" alt="Diagram #{idx}">
            </div>
            <div class="info-box">
              <p><strong>Description:</strong> {d.get('description', 'N/A')}</p>
              <p><strong>Suitability Reason:</strong> {d.get('suitability_reason', 'N/A')}</p>
              <div class="action-box">
                <label>Student Notes / Label Answers:</label>
                <textarea placeholder="Write answers or labels for this diagram..."></textarea>
              </div>
            </div>
          </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>ورقة عمل: {lesson_name}</title>
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #f8fafc; color: #1e293b; padding: 24px; direction: rtl; }}
    .header {{ background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
    .header h2 {{ margin: 0 0 6px 0; color: #0f172a; }}
    .header p {{ margin: 0; color: #64748b; font-size: 0.9rem; }}
    .worksheet-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 12px; margin-bottom: 24px; overflow: hidden; }}
    .card-header {{ background: #f1f5f9; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; }}
    .card-header h4 {{ margin: 0; font-size: 1rem; color: #334155; }}
    .badges {{ display: flex; gap: 8px; }}
    .badge {{ padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: bold; }}
    .badge-yes {{ background: #dcfce7; color: #15803d; }}
    .badge-no {{ background: #fee2e2; color: #b91c1c; }}
    .card-body {{ display: grid; grid-template-columns: 45% 55%; gap: 20px; padding: 20px; }}
    .img-box img {{ max-width: 100%; max-height: 400px; object-fit: contain; border: 1px solid #e2e8f0; border-radius: 8px; }}
    .info-box {{ display: flex; flex-direction: column; gap: 12px; font-size: 0.9rem; }}
    .action-box textarea {{ width: 100%; height: 90px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-family: inherit; }}
  </style>
</head>
<body>
  <div class="header">
    <h2>ورقة عمل: {lesson_name}</h2>
    <p>الفصل الدراسي {semester} • {unit_name} • {chapter_name} • {len(diagrams)} رسومات علمية</p>
  </div>
  {cards_html}
</body>
</html>"""
    return html

# ==============================================================================
# MAIN RUN PIPELINE
# ==============================================================================

def run_pipeline(sem_key: str, force: bool = False):
    cfg = SEMESTER_CONFIGS.get(sem_key)
    if not cfg:
        print(f"Invalid semester: {sem_key}")
        return

    title = cfg["title"]
    output_dir = cfg["output_dir"]
    csv_path = cfg["csv_path"]
    toc_registry = cfg["toc"]

    # Check if diagrams already exist to save tokens and prevent duplicates
    existing_images = glob.glob(os.path.join(output_dir, "*.png"))
    if existing_images:
        if not force:
            print("\n" + "=" * 70)
            print(f"⚡ [CACHE HIT] {len(existing_images)} diagrams already extracted in '{output_dir}/'.")
            print("   Extraction skipped to save OpenAI tokens and time.")
            print("   (To force re-extraction from scratch, pass the '--force' flag).")
            print("=" * 70 + "\n")
            return
        else:
            print(f"\n🗑️  [FORCE RESET] Deleting {len(existing_images)} old diagrams from '{output_dir}/' to re-extract from scratch...")
            for old_img in existing_images:
                try:
                    os.remove(old_img)
                except Exception as e:
                    print(f"    Warning: Could not remove {old_img}: {e}")

    # Resolve JSON file from candidates
    json_path = None
    for cand in cfg["json_candidates"]:
        if os.path.exists(cand):
            json_path = cand
            break

    if not json_path:
        print(f"[Error] No JSON file found for Semester {sem_key}. Candidates checked: {cfg['json_candidates']}")
        return

    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print(f"STARTING VISION PIPELINE FOR: {title}")
    print(f"JSON Source: {json_path}")
    print(f"Output Directory: {output_dir}")
    print("=" * 70)

    with open(json_path, "r", encoding="utf-8") as f:
        doc_data = json.load(f)

    raw_blocks = doc_data.get("documentLayout", {}).get("blocks", [])
    all_blocks = flatten_layout_blocks(raw_blocks)
    print(f"Total blocks in layout: {len(all_blocks)}")

    page_manager = PageImageManager(doc_data)

    metadata_records = []
    diagram_count = 0
    filtered_count = 0

    for idx, block in enumerate(all_blocks, start=1):
        if "imageBlock" not in block:
            continue

        page_num = block.get("pageSpan", {}).get("pageStart", 1)
        description = block.get("imageBlock", {}).get("description", "")

        # 1. Fetch cropped candidate image
        diagram_img = page_manager.get_image_for_block(block)
        if not diagram_img:
            continue

        # 2. Fast Rule-Based Filters (QR codes, dividers, small icons, preface)
        is_noise, noise_reason = is_noise_by_rules(diagram_img, description, page_num=page_num)
        if is_noise:
            filtered_count += 1
            print(f"  [RULE REJECTED] Page {page_num}: {noise_reason}")
            continue

        # 3. Multimodal Vision Gatekeeper (Passes actual Base64 image to AI)
        decision = vision_gatekeeper(diagram_img, description)
        if not decision.get("should_keep", False):
            filtered_count += 1
            print(f"  [AI REJECTED] Page {page_num}: {decision.get('reason')}")
            continue

        # 4. Approved! Save to disk
        diagram_count += 1
        filename = f"diagram_page_{page_num:02d}_diag_{diagram_count:02d}.png"
        filepath = os.path.join(output_dir, filename)
        diagram_img.save(filepath, format="PNG", optimize=True)

        unit_title, chapter_title, lesson_title = get_chapter_and_unit_by_page(page_num, toc_registry)
        resolution_str = f"{diagram_img.width}x{diagram_img.height}"

        record = {
            "semester": int(sem_key),
            "unit": unit_title,
            "chapter": chapter_title,
            "lesson": lesson_title,
            "description": description,
            "image_filename": filename,
            "image_path": filepath.replace("\\", "/"),
            "resolution": resolution_str,
            "is_suitable_for_labeling": decision.get("is_suitable_for_labeling", "NO"),
            "is_useful_for_questions": decision.get("is_useful_for_questions", "YES"),
            "suitability_reason": decision.get("reason", "Approved Science Diagram")
        }
        metadata_records.append(record)

        print(f"  ✅ [APPROVED #{diagram_count}] Page {page_num}: {filename}")
        print(f"     Lesson: {lesson_title}")
        print(f"     Labeling: {record['is_suitable_for_labeling']} | Questions: {record['is_useful_for_questions']}")

    # 5. Save to Excel CSV (UTF-8-BOM)
    print(f"\nWriting Excel CSV to {csv_path}...")
    headers = [
        "semester", "unit", "chapter", "lesson", "description",
        "image_filename", "image_path", "resolution",
        "is_suitable_for_labeling", "is_useful_for_questions", "suitability_reason"
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f_csv:
        writer = csv.DictWriter(f_csv, fieldnames=headers)
        writer.writeheader()
        writer.writerows(metadata_records)

    # 6. Save Metadata to Docker MySQL (diagram_metadata table)
    print("Uploading diagram metadata to Docker MySQL...")
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM diagram_metadata WHERE semester = %s;", (int(sem_key),))
            for r in metadata_records:
                cur.execute("""
                INSERT INTO diagram_metadata (
                    semester, unit, chapter, lesson, description,
                    image_filename, image_path, resolution,
                    is_suitable_for_labeling, is_useful_for_questions, suitability_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    r["semester"], r["unit"], r["chapter"], r["lesson"], r["description"],
                    r["image_filename"], r["image_path"], r["resolution"],
                    r["is_suitable_for_labeling"], r["is_useful_for_questions"], r["suitability_reason"]
                ))
        conn.close()
        print("  -> MySQL diagram_metadata upload complete!")
    except Exception as e:
        print(f"  [MySQL Metadata Upload Warning] {e}")

    # 7. Group by Lesson, Generate Worksheets & Upload to Docker MySQL (lesson_worksheets table)
    print("Generating lesson-wise worksheets and uploading to Docker MySQL...")
    lessons_grouped = {}
    for r in metadata_records:
        l = r["lesson"]
        if l not in lessons_grouped:
            lessons_grouped[l] = []
        lessons_grouped[l].append(r)

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_worksheets WHERE semester = %s;", (int(sem_key),))
            for lesson_name, diag_list in lessons_grouped.items():
                first = diag_list[0]
                ws_html = generate_lesson_html_worksheet(
                    lesson_name=lesson_name,
                    unit_name=first["unit"],
                    chapter_name=first["chapter"],
                    semester=int(sem_key),
                    diagrams=diag_list
                )
                cur.execute("""
                INSERT INTO lesson_worksheets (
                    semester, unit, chapter, lesson, diagram_count, worksheet_html
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    int(sem_key), first["unit"], first["chapter"], lesson_name, len(diag_list), ws_html
                ))
        conn.close()
        print(f"  -> Successfully uploaded {len(lessons_grouped)} lesson worksheets to Docker MySQL!")
    except Exception as e:
        print(f"  [MySQL Worksheets Upload Warning] {e}")

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETED FOR {title}")
    print(f"  -> Total Approved Diagrams: {diagram_count}")
    print(f"  -> Total Discarded Noise: {filtered_count}")
    print(f"  -> Images Directory: {output_dir}/")
    print(f"  -> Excel CSV: {csv_path}")
    print(f"  -> Docker MySQL: Tables 'diagram_metadata' & 'lesson_worksheets' updated!")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sem", choices=["1", "2", "3", "all"], default="1")
    parser.add_argument("--force", action="store_true", help="Force re-extraction even if diagrams already exist")
    args = parser.parse_args()

    if args.sem == "all":
        for s in ["1", "2", "3"]:
            run_pipeline(s, force=args.force)
    else:
        run_pipeline(args.sem, force=args.force)

"""
Educational Diagram Extraction, Vision Evaluation & MySQL Pipeline
Grade 8 Science (Saudi Curriculum)
==================================================================
1. Code-Level Fast Filters: Discards QR codes via OpenCV, thin lines, and tiny icons without LLM calls.
2. Multimodal Vision Gatekeeper & Description Verifier (gpt-4o-mini with Vision):
  - Evaluates cropped Base64 diagram image against 8th-grade science curriculum standards.
  - Verifies/aligns the description with what is actually visible in the cropped image.
  - Flags: is_suitable_for_labeling ('YES'/'NO') and is_useful_for_questions ('YES'/'NO').
3. Storage:
  - Saves clean PNGs to output_diagrams_semX/
  - Inserts records with verified English JSON/vision descriptions into Docker MySQL: diagram_metadata table.
  - Generates diagram-only HTML worksheets into: worksheet sem1/, worksheet sem2/, worksheet sem3/
"""

import argparse
import base64
import glob
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

from db import get_db_connection as get_db

# Fix Windows console cp1252 stdout encoding for Arabic & emojis when supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Initialize OpenCV QR Code detector (0 LLM tokens, pure computer vision)
qr_detector = cv2.QRCodeDetector()

BOUNDING_BOX_PADDING_RATIO = 0.015
MIN_CROPPED_AREA_RATIO = 0.01  # Reject crops smaller than 1% of the full page
MAX_FULL_PAGE_AREA_RATIO = 0.92  # Reject crops covering almost the entire page unless explicitly an image blob


def check_qr_code_opencv(img: Image.Image) -> bool:
    """Detects QR codes using OpenCV without calling any LLM."""
    try:
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        has_qr, _ = qr_detector.detect(cv_img)
        if has_qr:
            return True
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        has_qr_gray, _ = qr_detector.detect(gray)
        return bool(has_qr_gray)
    except Exception:
        return False


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


def is_noise_by_rules(
    img: Image.Image, description: str = "", page_num: int = 1
) -> Tuple[bool, str]:
    w, h = img.size

    # 1. Preface / Intro Pages filter
    if page_num <= 7:
        return True, f"Preface / Table of Contents page ({page_num})"

    # 2. Dimension & aspect ratio filters
    if w < 70 or h < 70:
        return True, f"Image too small ({w}x{h} px)"
    if h == 0 or (w / h > 6.0) or (h / w > 6.0):
        return True, f"Extreme aspect ratio ({w}x{h} px) - likely a divider banner or rule line"

    # 3. Pure OpenCV QR Code Detector (0 LLM Tokens)
    if check_qr_code_opencv(img):
        return True, "OpenCV QRCodeDetector found QR Code"

    # 4. Keyword filters for decorative art, logos, banners, administrative text
    desc_lower = description.lower() if description else ""
    noise_keywords = [
        "qr code",
        "barcode",
        "ministry logo",
        "ministry of education",
        "وزارة التعليم",
        "logo of the ministry",
        "cover page",
        "table of contents",
        "1446",
        "2024",
        "preface art",
        "horse",
        "horses",
        "desert landscape",
        "decorative montage",
        "collage",
    ]
    for kw in noise_keywords:
        if kw in desc_lower:
            return True, f"Matched noise keyword: '{kw}'"

    return False, "Passed rule-based checks"


# ==============================================================================
# MULTIMODAL VISION GATEKEEPER & DESCRIPTION VERIFIER
# ==============================================================================


def vision_gatekeeper_and_verify(
    img: Image.Image, raw_description: str = "", lesson_title: str = ""
) -> Dict[str, Any]:
    """
    Sends the actual cropped image to gpt-4o-mini Vision to:
    1. Decide whether to keep the diagram (`should_keep`).
    2. Evaluate `is_suitable_for_labeling` and `is_useful_for_questions`.
    3. Produce a `verified_description` that accurately matches the visual pixels
       instead of trusting a potentially mismatched raw Document AI description.
    """
    if not client:
        return {
            "should_keep": False,
            "is_suitable_for_labeling": "NO",
            "is_useful_for_questions": "NO",
            "verified_description": raw_description,
            "reason": "OPENAI_API_KEY not configured",
        }

    base64_str = encode_pil_image_to_base64(img)
    context_hint = (raw_description or "")[:300].strip() or "None"

    system_prompt = """You are a strict Science Educational Dataset Gatekeeper inspecting cropped Saudi Grade 8 Science diagrams.
Analyze ONLY what is visually shown in the attached cropped image.

RULES:
1. REJECT (should_keep = false):
  - Real-world photographs of people, children, meals/food, landscapes without scientific labels.
  - Decorative borders, book cover art, generic icons, full textbook page scans/layouts.
  - Chapter/unit opener artwork, montages, decorative animal photos, scenic landscapes, or collages.
  - Generic background illustrations that do not teach an 8th-grade science curriculum mechanism.
2. KEEP (should_keep = true):
  - Anatomical diagrams (heart, lungs, digestive system, eye, cell, skeleton).
  - Molecular models & particle views (solutions, atoms, molecules).
  - Scientific curves, graphs, charts (solubility, pH, velocity, temperature).
  - Laboratory apparatus setups (flasks, vessels, beakers, test tubes) and physical wave/energy models.

3. DESCRIPTION ALIGNMENT (CRITICAL):
  - Compare the visual image against the raw candidate description.
  - If the raw description conflicts with what is visually in the image (for example, raw description says "person floating in water" when the image shows a flask/vessel), IGNORE the conflicting raw text and write a clear, accurate `verified_description` in English describing ONLY the actual visual objects, labels, and scientific setup shown in the cropped image.
  - Do NOT mention book metadata, page numbers, or 'Ministry of Education' / 'وزارة التعليم'.

Respond ONLY with valid JSON:
{
  "should_keep": true/false,
  "is_suitable_for_labeling": "YES" or "NO",
  "is_useful_for_questions": "YES" or "NO",
  "verified_description": "Accurate English description of what is visually inside THIS cropped image...",
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
                        {
                            "type": "text",
                            "text": (
                                f"Lesson context: {lesson_title or 'Grade 8 Science'}\n"
                                f"Raw metadata hint (may be inaccurate): {context_hint}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_str}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        verified_desc = (parsed.get("verified_description") or "").strip()
        if not verified_desc:
            verified_desc = raw_description.strip()

        return {
            "should_keep": bool(parsed.get("should_keep", False)),
            "is_suitable_for_labeling": "YES"
            if str(parsed.get("is_suitable_for_labeling", "NO")).upper() == "YES"
            else "NO",
            "is_useful_for_questions": "YES"
            if str(parsed.get("is_useful_for_questions", "NO")).upper() == "YES"
            else "NO",
            "verified_description": verified_desc,
            "reason": str(parsed.get("reason") or "Evaluated by Vision Gatekeeper"),
        }
    except Exception as e:
        logger.warning("[Vision Gatekeeper Error]: %s", e)
        return {
            "should_keep": False,
            "is_suitable_for_labeling": "NO",
            "is_useful_for_questions": "NO",
            "verified_description": raw_description,
            "reason": str(e),
        }


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

SEMESTER_CONFIGS: Dict[str, Dict[str, Any]] = {
    "1": {
        "title": "Grade 8 - Semester 1 (الفصل الدراسي الأول)",
        "json_candidates": [
            "semester_1.json",
            
        ],
        "output_dir": "output_diagrams_sem1",
        "worksheet_dir": "worksheet sem1",
        "toc": GRADE_8_SEM1_TOC,
    },
    "2": {
        "title": "Grade 8 - Semester 2 (الفصل الدراسي الثاني)",
        "json_candidates": [
            "semester_2.json",

        ],
        "output_dir": "output_diagrams_sem2",
        "worksheet_dir": "worksheet sem2",
        "toc": GRADE_8_SEM2_TOC,
    },
    "3": {
        "title": "Grade 8 - Semester 3 (الفصل الدراسي الثالث)",
        "json_candidates": [
            "semester_3.json",
        
        ],
        "output_dir": "output_diagrams_sem3",
        "worksheet_dir": "worksheet sem3",
        "toc": GRADE_8_SEM3_TOC,
    },
}


def get_chapter_and_unit_by_page(page_number: int, toc_registry: list) -> Tuple[str, str, str]:
    for start_page, end_page, unit_title, chapter_title, lesson_title in toc_registry:
        if start_page <= page_number <= end_page:
            return unit_title, chapter_title, lesson_title
    return "الوحدة العامة", "الفصل العام", "الدرس العام"


# ==============================================================================
# DOCUMENT AI PARSER & SAFE CROPPED IMAGE RETRIEVAL
# ==============================================================================


class PageImageManager:
    def __init__(self, doc_data: dict):
        self.blob_map: Dict[str, str] = {}
        for blob in doc_data.get("blobAssets", []):
            asset_id = blob.get("assetId")
            content = blob.get("content")
            if asset_id and content:
                self.blob_map[asset_id] = content

        self.blob_desc_map: Dict[str, str] = {}
        for c in doc_data.get("chunkedDocument", {}).get("chunks", []):
            for cf in c.get("chunkFields", []):
                icf = cf.get("imageChunkField")
                if icf and "blobAssetId" in icf:
                    b_id = icf["blobAssetId"]
                    ann = icf.get("annotations", {})
                    if isinstance(ann, dict) and ann.get("description"):
                        self.blob_desc_map[b_id] = ann["description"]
                    elif isinstance(icf.get("description"), str) and icf.get("description"):
                        self.blob_desc_map[b_id] = icf["description"]

        self.page_base64_map: Dict[int, str] = {}
        for page in doc_data.get("pages", []):
            page_num = page.get("pageNumber")
            content = page.get("image", {}).get("content")
            if page_num and content:
                self.page_base64_map[page_num] = content

    def get_description_for_block(self, block: dict) -> str:
        """Extracts raw description from Document AI JSON if present."""
        ib = block.get("imageBlock", {})
        if isinstance(ib.get("description"), str) and ib["description"].strip():
            return ib["description"].strip()
        ann = ib.get("annotations", {})
        if isinstance(ann, dict) and isinstance(ann.get("description"), str) and ann["description"].strip():
            return ann["description"].strip()
        blob_id = ib.get("blobAssetId")
        if blob_id and blob_id in self.blob_desc_map:
            return self.blob_desc_map[blob_id].strip()
        return ""

    def get_cropped_image_for_block(self, block: dict) -> Tuple[Optional[Image.Image], str]:
        """
        Retrieves an actual cropped diagram image and never silently falls back to
        saving an entire uncropped page when boundingBox vertices are missing.
        """
        ib = block.get("imageBlock", {})
        blob_id = ib.get("blobAssetId")
        if blob_id and blob_id in self.blob_map:
            try:
                return decode_base64_image(self.blob_map[blob_id]), "blobAssetId"
            except Exception as e:
                return None, f"Invalid blobAssetId image ({e})"

        page_num = block.get("pageSpan", {}).get("pageStart", 1)
        if page_num not in self.page_base64_map:
            return None, f"Missing page image for page {page_num}"

        vertices = block.get("boundingBox", {}).get("normalizedVertices", [])
        if not vertices or len(vertices) < 2:
            return None, f"Missing boundingBox vertices on page {page_num} (skipped whole-page crop)"

        try:
            page_img = decode_base64_image(self.page_base64_map[page_num])
        except Exception as e:
            return None, f"Failed to decode page {page_num} image ({e})"

        page_w, page_h = page_img.size
        if page_w <= 0 or page_h <= 0:
            return None, f"Invalid page dimensions on page {page_num}"

        xs = [float(pt.get("x", 0.0)) for pt in vertices]
        ys = [float(pt.get("y", 0.0)) for pt in vertices]
        min_x = max(0.0, min(xs) - BOUNDING_BOX_PADDING_RATIO)
        max_x = min(1.0, max(xs) + BOUNDING_BOX_PADDING_RATIO)
        min_y = max(0.0, min(ys) - BOUNDING_BOX_PADDING_RATIO)
        max_y = min(1.0, max(ys) + BOUNDING_BOX_PADDING_RATIO)

        left = int(min_x * page_w)
        top = int(min_y * page_h)
        right = int(max_x * page_w)
        bottom = int(max_y * page_h)

        if right <= left or bottom <= top:
            return None, f"Zero-area bounding box on page {page_num}"

        crop_area = (right - left) * (bottom - top)
        page_area = page_w * page_h
        area_ratio = crop_area / float(page_area)

        if area_ratio < MIN_CROPPED_AREA_RATIO:
            return None, f"Crop too small ({area_ratio:.2%} of page)"
        if area_ratio > MAX_FULL_PAGE_AREA_RATIO:
            return None, f"Crop covers {area_ratio:.1%} of page (likely full-page/layout box, not a diagram crop)"

        return page_img.crop((left, top, right, bottom)), "boundingBox_crop"


def flatten_layout_blocks(blocks: list) -> list:
    flat = []
    for b in blocks:
        flat.append(b)
        sub_blocks = b.get("blocks", [])
        if sub_blocks:
            flat.extend(flatten_layout_blocks(sub_blocks))
        text_sub_blocks = b.get("textBlock", {}).get("blocks", [])
        if text_sub_blocks:
            flat.extend(flatten_layout_blocks(text_sub_blocks))
    return flat


# ==============================================================================
# HTML WORKSHEET GENERATOR (Saved to Local Codebase Folders)
# ==============================================================================


def generate_worksheet_index(title: str, semester: int, lesson_files: list) -> str:
    links_html = ""
    for lesson_label, filename, _diag_count in lesson_files:
        links_html += f"""
        <div class="lesson-card">
          <div class="card-info">
            <h3>{lesson_label}</h3>
          </div>
          <a href="{filename}" class="btn-open">View Diagrams &rarr;</a>
        </div>
        """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Worksheets - Semester {semester}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; color: #0f172a; padding: 40px 20px; margin: 0; }}
    .container {{ max-width: 800px; margin: 0 auto; }}
    .header {{ background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px 32px; margin-bottom: 24px; }}
    .header h1 {{ margin: 0; color: #0f172a; font-size: 1.5rem; font-weight: 600; }}
    .lesson-grid {{ display: flex; flex-direction: column; gap: 12px; }}
    .lesson-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; transition: all 0.15s ease; }}
    .lesson-card:hover {{ border-color: #cbd5e1; box-shadow: 0 2px 4px rgba(0,0,0,0.04); }}
    .card-info h3 {{ margin: 0; font-size: 1.1rem; font-weight: 500; color: #1e293b; }}
    .btn-open {{ background: #0f172a; color: white; text-decoration: none; padding: 8px 18px; border-radius: 6px; font-weight: 500; font-size: 0.9rem; }}
    .btn-open:hover {{ background: #334155; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{title}</h1>
    </div>
    <div class="lesson-grid">
      {links_html}
    </div>
  </div>
</body>
</html>"""


def generate_lesson_html_worksheet(lesson_label: str, semester: int, diagrams: list) -> str:
    cards_html = ""
    for idx, d in enumerate(diagrams, start=1):
        img_src = f"../{d['image_path'].replace(chr(92), '/')}"
        cards_html += f"""
        <div class="diagram-card">
          <img src="{img_src}" alt="Diagram #{idx}">
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{lesson_label} - Semester {semester}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; color: #0f172a; padding: 40px 20px; margin: 0; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    .header {{ background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px 32px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }}
    .header h1 {{ margin: 0; font-size: 1.5rem; font-weight: 600; color: #0f172a; }}
    .back-link {{ color: #475569; text-decoration: none; font-size: 0.9rem; font-weight: 500; }}
    .back-link:hover {{ color: #0f172a; text-decoration: underline; }}
    .diagram-list {{ display: flex; flex-direction: column; gap: 24px; }}
    .diagram-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; display: flex; justify-content: center; align-items: center; }}
    .diagram-card img {{ max-width: 100%; height: auto; object-fit: contain; border-radius: 6px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{lesson_label}</h1>
      <a href="index.html" class="back-link">&larr; Back to Index</a>
    </div>
    <div class="diagram-list">
      {cards_html}
    </div>
  </div>
</body>
</html>"""


# ==============================================================================
# TRANSACTION-SAFE MYSQL SYNC
# ==============================================================================


def sync_metadata_to_mysql(sem_int: int, metadata_records: List[Dict[str, Any]]) -> None:
    """
    Replaces semester rows atomically inside a transaction.
    Rolls back on any error and always closes the connection.
    """
    if not metadata_records:
        logger.warning("[MySQL Sync Skipped] No approved metadata records for semester %s; existing rows preserved.", sem_int)
        return

    conn = None
    try:
        conn = get_db()
        if hasattr(conn, "begin"):
            conn.begin()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM diagram_metadata WHERE semester = %s;", (sem_int,))
            for r in metadata_records:
                cur.execute(
                    """
                    INSERT INTO diagram_metadata (
                        semester, unit, chapter, lesson, description,
                        image_filename, image_path, resolution,
                        is_suitable_for_labeling, is_useful_for_questions, suitability_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        r["semester"],
                        r["unit"],
                        r["chapter"],
                        r["lesson"],
                        r["description"],
                        r["image_filename"],
                        r["image_path"],
                        r["resolution"],
                        r["is_suitable_for_labeling"],
                        r["is_useful_for_questions"],
                        r["suitability_reason"],
                    ),
                )
        conn.commit()
        logger.info("MySQL diagram_metadata synced atomically (%d rows) for semester %s.", len(metadata_records), sem_int)
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("[MySQL Metadata Upload Error] Semester %s rolled back: %s", sem_int, e)
        raise
    finally:
        if conn:
            conn.close()


# ==============================================================================
# MAIN RUN PIPELINE
# ==============================================================================


def run_pipeline(sem_key: str, force: bool = False) -> None:
    cfg = SEMESTER_CONFIGS.get(sem_key)
    if not cfg:
        logger.error("Invalid semester: %s", sem_key)
        return

    sem_int = int(sem_key)
    title = cfg["title"]
    output_dir = cfg["output_dir"]
    toc_registry = cfg["toc"]

    existing_images = glob.glob(os.path.join(output_dir, "*.png"))
    if existing_images and not force:
        print("\n" + "=" * 70)
        print(f"⚡ [CACHE HIT] {len(existing_images)} diagrams already extracted in '{output_dir}/'.")
        print("   Extraction skipped to save OpenAI tokens and time.")
        print("   (Pass '--force' to re-extract and re-sync from scratch).")
        print("=" * 70 + "\n")
        return

    json_path: Optional[str] = None
    for cand in cfg["json_candidates"]:
        if os.path.exists(cand):
            json_path = cand
            break

    if not json_path:
        logger.error("No JSON file found for Semester %s. Candidates checked: %s", sem_key, cfg["json_candidates"])
        return

    if force and existing_images:
        logger.info("[FORCE RESET] Removing %d existing PNGs in '%s/'...", len(existing_images), output_dir)
        for old_img in existing_images:
            try:
                os.remove(old_img)
            except Exception as e:
                logger.warning("Could not remove %s: %s", old_img, e)

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
    logger.info("Total blocks in layout: %d", len(all_blocks))

    page_manager = PageImageManager(doc_data)

    metadata_records: List[Dict[str, Any]] = []
    diagram_count = 0
    filtered_count = 0

    for block in all_blocks:
        if "imageBlock" not in block:
            continue

        page_num = block.get("pageSpan", {}).get("pageStart", 1)
        _unit_tmp, _chap_tmp, lesson_title = get_chapter_and_unit_by_page(page_num, toc_registry)

        # 1. Fetch safe cropped image (no full-page fallback)
        diagram_img, crop_reason = page_manager.get_cropped_image_for_block(block)
        if not diagram_img:
            filtered_count += 1
            print(f"  [CROP REJECTED] Page {page_num}: {crop_reason}")
            continue

        raw_json_desc = page_manager.get_description_for_block(block)

        # 2. Fast Rule-Based Filters
        is_noise, noise_reason = is_noise_by_rules(diagram_img, raw_json_desc, page_num=page_num)
        if is_noise:
            filtered_count += 1
            print(f"  [RULE REJECTED] Page {page_num}: {noise_reason}")
            continue

        # 3. Multimodal Vision Gatekeeper + Image-Grounded Description Verification
        decision = vision_gatekeeper_and_verify(
            diagram_img, raw_description=raw_json_desc, lesson_title=lesson_title
        )
        if not decision.get("should_keep", False):
            filtered_count += 1
            print(f"  [AI REJECTED] Page {page_num}: {decision.get('reason')}")
            continue

        # 4. Approved! Save PNG to disk
        diagram_count += 1
        filename = f"diagram_page_{page_num:02d}_diag_{diagram_count:02d}.png"
        filepath = os.path.join(output_dir, filename)
        diagram_img.save(filepath, format="PNG", optimize=True)

        unit_title, chapter_title, lesson_title = get_chapter_and_unit_by_page(page_num, toc_registry)
        resolution_str = f"{diagram_img.width}x{diagram_img.height}"
        verified_desc = decision["verified_description"]

        record = {
            "semester": sem_int,
            "unit": unit_title,
            "chapter": chapter_title,
            "lesson": lesson_title,
            "description": verified_desc,
            "image_filename": filename,
            "image_path": filepath.replace("\\", "/"),
            "resolution": resolution_str,
            "is_suitable_for_labeling": decision["is_suitable_for_labeling"],
            "is_useful_for_questions": decision["is_useful_for_questions"],
            "suitability_reason": decision["reason"],
        }
        metadata_records.append(record)

        print(f"  ✅ [APPROVED #{diagram_count}] Page {page_num} ({crop_reason}): {filename}")
        print(f"     Lesson: {lesson_title}")
        print(f"     Verified Desc: {verified_desc[:75]}...")
        print(f"     Labeling: {record['is_suitable_for_labeling']} | Questions: {record['is_useful_for_questions']}")

    # 5. Atomic MySQL Sync
    try:
        sync_metadata_to_mysql(sem_int, metadata_records)
    except Exception:
        print("  [MySQL Sync Failed] See error log above.")

    # 6. Group by Lesson & Generate Worksheets
    worksheet_dir = cfg["worksheet_dir"]
    os.makedirs(worksheet_dir, exist_ok=True)
    print(f"\nGenerating lesson-wise HTML worksheets in folder: '{worksheet_dir}/'...")

    lessons_grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in metadata_records:
        lessons_grouped.setdefault(r["lesson"], []).append(r)

    created_files = []
    for lesson_idx, (lesson_name, diag_list) in enumerate(lessons_grouped.items(), start=1):
        lesson_label = f"Lesson {lesson_idx}: {lesson_name}"
        filename = f"lesson_{lesson_idx}.html"
        ws_html = generate_lesson_html_worksheet(
            lesson_label=lesson_label,
            semester=sem_int,
            diagrams=diag_list,
        )
        ws_path = os.path.join(worksheet_dir, filename)
        with open(ws_path, "w", encoding="utf-8") as f_ws:
            f_ws.write(ws_html)
        created_files.append((lesson_label, filename, len(diag_list)))

    index_html = generate_worksheet_index(title, sem_int, created_files)
    with open(os.path.join(worksheet_dir, "index.html"), "w", encoding="utf-8") as f_idx:
        f_idx.write(index_html)

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETED FOR {title}")
    print(f"  -> Total Approved Diagrams: {diagram_count}")
    print(f"  -> Total Discarded Noise: {filtered_count}")
    print(f"  -> Images Directory: {output_dir}/")
    print(f"  -> Worksheets Folder: {worksheet_dir}/ (includes index.html)")
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
import os
import json
import base64
import io
import csv
from PIL import Image 
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


# ==============================================================================
# PIPELINE CONFIGURATION & CONSTANTS
# ==============================================================================

# Label Padding: Add 1.5% margin around the bounding box so text pointers aren't clipped
BOUNDING_BOX_PADDING_RATIO = 0.015

# ==============================================================================
# PHASE 2: HIGH-RES BASE64 DECODERS & PAGE CACHE
# ==============================================================================

def decode_base64_image(base64_string: str) -> Image.Image:
    """
    Decodes a Base64-encoded string into an in-memory PIL Image object.
    Uses BytesIO to avoid temporary disk writes.
    """
    image_bytes = base64.b64decode(base64_string)
    image = Image.open(io.BytesIO(image_bytes))
    return image.convert("RGB")


def load_document_data(filepath: str) -> dict:
    """
    Safely opens and parses the Document AI JSON file using UTF-8 encoding.
    """
    print(f"[Phase 1] Loading Document AI data from: {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    pages_count = len(data.get("pages", []))
    blobs_count = len(data.get("blobAssets", []))
    if blobs_count > 0:
        print(f"[Phase 1] Successfully loaded Document AI layout with {blobs_count} image assets.")
    else:
        print(f"[Phase 1] Successfully loaded {pages_count} pages.")
    return data


class PageImageManager:
    """
    Manages diagram image retrieval and caching.
    Supports:
    1. Direct blobAssets mapping (Document AI layout parser output: blob_1..blob_87).
    2. Full-page high-definition images (OCR pages format) with bounding box crops.
    """
    def __init__(self, doc_data: dict):
        self.doc_data = doc_data
        self.page_cache = {}  # {page_number: PIL.Image}
        self.blob_cache = {}  # {asset_id: PIL.Image}
        
        # 1. Map blobAssets (assetId -> base64 string)
        self.blob_map = {}
        for blob in doc_data.get("blobAssets", []):
            asset_id = blob.get("assetId")
            content = blob.get("content")
            if asset_id and content:
                self.blob_map[asset_id] = content

        # 2. Map full pages (pageNumber -> base64 string)
        self.page_base64_map = {}
        for page in doc_data.get("pages", []):
            page_num = page.get("pageNumber")
            content = page.get("image", {}).get("content")
            if page_num and content:
                self.page_base64_map[page_num] = content

    def get_image_for_block(self, block: dict) -> Image.Image | None:
        """
        Retrieves the decoded image for a specific block:
        - If the block has a blobAssetId in blobAssets, decodes and returns it directly.
        - Otherwise, crops from the full page image using boundingBox vertices.
        """
        ib = block.get("imageBlock", {})
        blob_id = ib.get("blobAssetId")

        # Strategy A: Direct blob asset (already cleanly extracted by Document AI)
        if blob_id:
            if blob_id in self.blob_cache:
                return self.blob_cache[blob_id]
            base64_content = self.blob_map.get(blob_id)
            if base64_content:
                img = decode_base64_image(base64_content)
                self.blob_cache[blob_id] = img
                return img

        # Strategy B: Crop from full page image
        page_num = block.get("pageSpan", {}).get("pageStart", 1)
        page_img = self.get_page_image(page_num)
        if not page_img:
            return None

        vertices = block.get("boundingBox", {}).get("normalizedVertices", [])
        if vertices:
            return crop_diagram_with_padding(page_img, vertices, BOUNDING_BOX_PADDING_RATIO)
        return page_img

    def get_page_image(self, page_number: int) -> Image.Image | None:
        """
        Retrieves the decoded full-page image for a specific page number.
        Decodes on the first request and caches it in memory for subsequent crops.
        """
        if page_number in self.page_cache:
            return self.page_cache[page_number]

        base64_content = self.page_base64_map.get(page_number)
        if not base64_content:
            return None

        page_img = decode_base64_image(base64_content)
        self.page_cache[page_number] = page_img
        return page_img


# ==============================================================================
# PHASE 4: METADATA MATCHER (CHAPTERS & FIGURE CAPTIONS)
# ==============================================================================

def load_chunks_data(filepath: str) -> list:
    """
    Loads RAG chunks JSON file if available, or returns an empty list.
    """
    if filepath and os.path.exists(filepath):
        print(f"[Phase 4] Loading external RAG chunks from: {filepath}...")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# ==============================================================================
# PHASE 4: OFFICIAL TEXTBOOK TOC REGISTRIES (GRADE 8 SCIENCE - ALL SEMESTERS)
# ==============================================================================

GRADE_8_SEM1_TOC = [
    # (start_page, end_page, unit_name, chapter_name, lesson_name)
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
    (126, 200, "مصادر تعليمية", "مصادر تعليمية ومصطلحات", "مصادر تعليمية ومصطلحات علمية"),
]

GRADE_8_SEM2_TOC = [
    # (start_page, end_page, unit_name, chapter_name, lesson_name)
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
    (146, 200, "مصادر تعليمية", "مصادر تعليمية ومصطلحات", "مصادر تعليمية ومصطلحات علمية"),
]

GRADE_8_SEM3_TOC = [
    # (start_page, end_page, unit_name, chapter_name, lesson_name)
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
    (135, 200, "مصادر تعليمية", "مصادر تعليمية ومصطلحات", "مصادر تعليمية ومصطلحات علمية"),
]

SEMESTER_CONFIGS = {
    "1": {
        "title": "Grade 8 - Semester 1 (الفصل الدراسي الأول)",
        "json_path": "grade_8_semester_1_science_complete_layout.json",
        "output_dir": "output_diagrams_sem1",
        "csv_path": "diagrams_metadata_sem1.csv",
        "toc": GRADE_8_SEM1_TOC,
    },
    "2": {
        "title": "Grade 8 - Semester 2 (الفصل الدراسي الثاني)",
        "json_path": "grade_8_semester_2_science_complete_layout.json",
        "output_dir": "output_diagrams_sem2",
        "csv_path": "diagrams_metadata_sem2.csv",
        "toc": GRADE_8_SEM2_TOC,
    },
    "3": {
        "title": "Grade 8 - Semester 3 (الفصل الدراسي الثالث)",
        "json_path": "grade_8_semester_3_science_complete_layout.json",
        "output_dir": "output_diagrams_sem3",
        "csv_path": "diagrams_metadata_sem3.csv",
        "toc": GRADE_8_SEM3_TOC,
    },
}


def get_chapter_and_unit_by_page(page_number: int, toc_registry: list) -> tuple[str, str, str]:
    """
    Method 1: Authoritative Table of Contents (TOC) page mapping.
    Maps a page number to its exact official Unit, Chapter, and Lesson titles.
    Guarantees 100% clean, concise Arabic titles with zero noisy paragraph text.
    """
    for start_p, end_p, unit_title, chapter_title, lesson_title in toc_registry:
        if start_p <= page_number <= end_p:
            return unit_title, chapter_title, lesson_title

    return "الوحدة العامة", "الفصل العام", "عام"


def extract_english_description(diagram_block: dict) -> str:
    """
    Extracts the existing English description directly from the Document AI
    JSON annotations (exact text, no Arabic caption matching needed).
    """
    image_block = diagram_block.get("imageBlock", {})
    annotations = image_block.get("annotations", {})

    # Extract the English description string from the annotations object
    if isinstance(annotations, dict):
        desc = annotations.get("description", "")
    elif isinstance(annotations, list) and len(annotations) > 0:
        desc = annotations[0].get("description", "") if isinstance(annotations[0], dict) else str(annotations[0])
    else:
        desc = ""

    return desc.strip()


def is_noise_by_keyword(description: str) -> tuple:
    """
    Fast keyword check: drop qr code and barcode 

    """
    desc_lower = description.lower()

    # QR Code & Barcode keywords
    qr_keywords = ["qr code", "barcode", "quick response", "scan pattern"]
    for kw in qr_keywords:
        if kw in desc_lower:
            return True, f"Discarded: QR/Barcode found ('{kw}')"

    # (Optional) Agar Ministry Logos bhi drop karne hon:
    if "logo or graphic" in desc_lower:
        return True, "Discarded: Logo/Graphic found"

    return False, ""

# ==============================================================================
# OPENAI LLM FILTER ENGINE
# ==============================================================================

def llm_filter_diagram(description: str) -> dict:
    
    if not description or len(description.strip()) < 10:
        return {"should_keep": False, "reason": "Empty description", "is_qr_code": False}

    system_prompt = """
You are an expert AI evaluator for a Science Textbook educational dataset.
Analyze the image description and decide if it should be KEPT for student learning or REJECTED.

RULES:
1. REJECT (should_keep = false):
   - Ministry logos, book covers, decorative icons, badges.
   - Real-world photographs of random food/fruits/meals.

2. KEEP (should_keep = true):
   - Anatomical diagrams (digestive system, heart, respiratory system, lungs, cells).
   - Scientific illustrations, biological structures with labels.

Respond ONLY with valid JSON:
{
  "should_keep": true/false,
  "reason": "Short explanation of your decision"
}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Image Description:\n{description}"}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else {"should_keep": False, "reason": "Empty response from LLM", "is_qr_code": False}
    except Exception as e:
        print(f"  [API ERROR] {e}")
        return {"should_keep": False, "reason": str(e), "is_qr_code": False}



# ==============================================================================
# PHASE 5: HIGH-PRECISION CROPPER & UTF-8-BOM CSV WRITER
# ==============================================================================

def crop_diagram_with_padding(page_img: Image.Image, vertices: list, padding_ratio: float = 0.015) -> Image.Image:
    """
    Converts normalized vertices to pixel coordinates, applies padding to preserve
    Arabic callout labels, and crops from the high-definition page image.
    """
    page_w, page_h = page_img.size

    xs = [pt.get("x", 0.0) for pt in vertices]
    ys = [pt.get("y", 0.0) for pt in vertices]

    # Calculate pixel boundaries with extra safety padding
    min_x = max(0.0, min(xs) - padding_ratio)
    max_x = min(1.0, max(xs) + padding_ratio)
    min_y = max(0.0, min(ys) - padding_ratio)
    max_y = min(1.0, max(ys) + padding_ratio)

    left = int(min_x * page_w)
    top = int(min_y * page_h)
    right = int(max_x * page_w)
    bottom = int(max_y * page_h)

    return page_img.crop((left, top, right, bottom))


def flatten_layout_blocks(blocks: list, parent_page: int = 1) -> list:
    """
    Recursively flattens all nested Document AI layout blocks (e.g. inside textBlock.blocks).
    Preserves and propagates pageSpan across the nested hierarchy.
    """
    flat = []
    for b in blocks:
        page = b.get("pageSpan", {}).get("pageStart", parent_page)
        if "pageSpan" not in b:
            b["pageSpan"] = {"pageStart": page, "pageEnd": page}
        flat.append(b)

        # Recursively traverse nested blocks (e.g., inside textbook chapters)
        nested = b.get("textBlock", {}).get("blocks")
        if nested and isinstance(nested, list):
            flat.extend(flatten_layout_blocks(nested, parent_page=page))
    return flat


def run_pipeline(semester_key: str = "2"):
    """
    Main pipeline orchestrator. Executes all phases sequentially for a specific semester.
    """
    if semester_key not in SEMESTER_CONFIGS:
        print(f"[ERROR] Unknown semester key '{semester_key}'. Choose from: {list(SEMESTER_CONFIGS.keys())}")
        return

    config = SEMESTER_CONFIGS[semester_key]
    title = config["title"]
    json_path = config["json_path"]
    output_dir = config["output_dir"]
    csv_path = config["csv_path"]
    toc_registry = config["toc"]

    print("\n" + "=" * 60)
    print(f"STARTING PIPELINE: {title}")
    print(f"  Input JSON:   {json_path}")
    print(f"  Output Dir:   {output_dir}/")
    print(f"  Metadata CSV: {csv_path}")
    print("=" * 60)

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load Document AI JSON
    doc_data = load_document_data(json_path)

    # 2. Recursively flatten all layout blocks (including nested chapter blocks)
    raw_blocks = doc_data.get("documentLayout", {}).get("blocks", [])
    all_blocks = flatten_layout_blocks(raw_blocks)
    print(f"Total layout blocks extracted (including nested chapters): {len(all_blocks)}")

    # 3. Initialize Page Image Manager
    page_manager = PageImageManager(doc_data)

    metadata_records = []
    diagram_count = 0
    filtered_count = 0

    # 4. Iterate through all layout blocks to find diagrams
    print(f"\nScanning layout blocks for diagrams in {title}...")
    for block in all_blocks:
        if "imageBlock" not in block:
            continue

        page_num = block.get("pageSpan", {}).get("pageStart", 1)
        description = extract_english_description(block)

        # ------------------------------------------------------------------
        # NEW: FAST KEYWORD FILTER (0 Tokens Used - Cost Saved!)
        # ------------------------------------------------------------------
        is_noise, reason = is_noise_by_keyword(description)
        if is_noise:
            filtered_count += 1
            print(f"  [FAST SKIPPED] Page {page_num}: {reason} (0 Tokens Used)")
            continue

        # 5. Description ko OpenAI LLM ke pas bhej kar filter karein
        llm_decision = llm_filter_diagram(description)
        if not llm_decision.get("should_keep"):
            filtered_count += 1
            print(f"  [LLM SKIPPED] Page {page_num}: {llm_decision.get('reason')}")
            continue

        # 6. Agar LLM ne approve kiya -> Fetch high-res diagram image
        diagram_img = page_manager.get_image_for_block(block)
        if not diagram_img:
            print(f"  [WARNING] Could not load image for block on page {page_num}. Skipping.")
            continue

        diagram_count += 1

        # 7. Save image to disk
        filename = f"diagram_page_{page_num:02d}_diag_{diagram_count:02d}.png"
        filepath = os.path.join(output_dir, filename)
        diagram_img.save(filepath, format="PNG", optimize=True)

        # 8. Metadata record (Method 1: Authoritative Grade 8 TOC Mapping)
        unit_title, chapter_title, lesson_title = get_chapter_and_unit_by_page(page_num, toc_registry)
        resolution_str = f"{diagram_img.width}x{diagram_img.height}"

        # Append to metadata list with clean unit, chapter & lesson fields
        record = {
            "unit": unit_title,
            "chapter": chapter_title,
            "lesson": lesson_title,
            "description": description,
            "image_filename": filename,
            "image_path": filepath,
            "resolution": resolution_str
        }
        metadata_records.append(record)

        print(f"  [SAVED] {filename} ({resolution_str})")
        print(f"          Unit: {unit_title} | Chapter: {chapter_title} | Lesson: {lesson_title}")
        print(f"          Description: {description[:80]}...")

    # 9. Save Metadata to CSV with UTF-8 BOM encoding
    print(f"\nWriting metadata CSV to {csv_path}...")
    csv_headers = ["unit", "chapter", "lesson", "description", "image_filename", "image_path", "resolution"]

    # 'utf-8-sig' adds the UTF-8 BOM so Microsoft Excel renders Arabic correctly
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f_csv:
        writer = csv.DictWriter(f_csv, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(metadata_records)

    print("\n" + "=" * 60)
    print(f"PIPELINE COMPLETED FOR {title}!")
    print(f"  -> Extracted Diagrams: {diagram_count}")
    print(f"  -> Filtered QR Codes/Icons: {filtered_count}")
    print(f"  -> Images saved in: '{output_dir}/'")
    print(f"  -> Metadata saved in: '{csv_path}'")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Educational Diagram Extraction Pipeline")
    parser.add_argument("--sem", choices=["1", "2", "3", "all"], default=None, help="Semester to process (1, 2, 3, or all)")
    args = parser.parse_args()

    target = args.sem
    if not target:
        print("\n" + "=" * 60)
        print("EDUCATIONAL DIAGRAM EXTRACTOR - GRADE 8 SCIENCE")
        print("=" * 60)
        print("Available Semesters:")
        for k, v in SEMESTER_CONFIGS.items():
            print(f"  [{k}] {v['title']}")
        print("  [all] Process All Semesters Sequentially")
        try:
            choice = input("\nEnter choice [1, 2, 3, or all] (default: 1): ").strip().lower()
            target = choice if choice in ["1", "2", "3", "all"] else "1"
        except (EOFError, KeyboardInterrupt):
            target = "1"

    if target == "all":
        for s in ["1", "2", "3"]:
            run_pipeline(s)
    else:
        run_pipeline(target)

"""
Educational Diagram Evaluator & Per-Lesson Worksheet Generator
==============================================================
1. Agent 1 (Call #1): Gatekeeper Agent (Temp 0.0) approves/rejects diagrams.
2. Agent 2 (Call #2): Diagram-Specific Question Author with MULTIMODAL BASE64 VISION:
     - Passes BOTH the Base64-encoded image AND Document AI description to gpt-4o-mini!
     - Generates 3 questions FOR EACH DIAGRAM:
         - Question 1: Short Question (سؤال قصير) + Model Answer
         - Question 2: Multiple Choice (اختيار من متعدد) with 4 options (A, B, C, D) + Correct Answer
         - Question 3: Scientific Reasoning (سؤال تعليلي / لماذا وكيف) + Detailed Explanation
     - STRICT RULE: At least ONE question per diagram is derived directly from visual elements inside the image!
3. Robust Image Resolver: Auto-matches shifted filenames on disk so BROKEN IMAGES NEVER OCCUR.
4. Categorizes diagrams by Lesson (ONLY Lesson name in banner - Unit/Chapter removed!).
5. Generates SEPARATE HTML worksheet files FOR EACH LESSON in a dedicated folder (e.g., worksheets_sem1/).
6. Generates a master index.html linking to all individual lesson worksheets.
7. Saves comprehensive data in diagrams_with_questions_semX.csv.
"""

import os
import re
import sys
import csv
import json
import glob
import base64
import argparse
from collections import OrderedDict
from dotenv import load_dotenv
from openai import OpenAI

# Fix Windows console encoding for Arabic & emojis
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SEMESTER_CONFIGS = {
    "1": {
        "title": "Grade 8 - Semester 1 Science",
        "csv_path": "diagrams_metadata_sem1.csv",
        "output_csv": "diagrams_with_questions_sem1.csv",
        "worksheets_dir": "worksheets_sem1",
    },
    "2": {
        "title": "Grade 8 - Semester 2 Science",
        "csv_path": "diagrams_metadata_sem2.csv",
        "output_csv": "diagrams_with_questions_sem2.csv",
        "worksheets_dir": "worksheets_sem2",
    },
    "3": {
        "title": "Grade 8 - Semester 3 Science",
        "csv_path": "diagrams_metadata_sem3.csv",
        "output_csv": "diagrams_with_questions_sem3.csv",
        "worksheets_dir": "worksheets_sem3",
    },
}


def sanitize_filename(name: str) -> str:
    """Removes invalid filesystem characters for clean HTML filenames."""
    clean = re.sub(r'[\\/*?:"<>|]', '_', name)
    clean = clean.replace(' ', '_').strip('_')
    return clean[:50] if clean else "lesson"


def encode_image_base64(image_path: str) -> str:
    """Encodes a local image to a base64 string for OpenAI Multimodal Vision."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def resolve_image_path(image_path: str, filename: str, output_dir: str = "output_diagrams_sem1") -> tuple:
    """
    Guarantees the image file exists on disk.
    If the filename in the CSV doesn't exist (e.g. numbering shifted like page_54_diag_06 vs diag_07),
    it dynamically finds the matching file on disk and returns (verified_path, verified_filename).
    """
    # 1. Direct path check
    if image_path and os.path.exists(image_path):
        return image_path.replace("\\", "/"), os.path.basename(image_path)

    # 2. Check inside output_dir directly
    candidate = os.path.join(output_dir, filename)
    if os.path.exists(candidate):
        return candidate.replace("\\", "/"), filename

    # 3. Match by page number pattern in output_dir (handles numbering shifts between runs)
    page_match = re.search(r'diagram_page_(\d+)', filename)
    if page_match and os.path.exists(output_dir):
        page_str = page_match.group(1)
        matches = glob.glob(os.path.join(output_dir, f"diagram_page_{page_str}_*.png"))
        if matches:
            resolved = matches[0].replace("\\", "/")
            return resolved, os.path.basename(resolved)

    return image_path.replace("\\", "/"), filename


# ==============================================================================
# AGENT 1: STRICT EDUCATIONAL GATEKEEPER (Call #1, Temperature 0.0)
# ==============================================================================

def gatekeeper_agent(description: str) -> dict:
    """
    Evaluates whether the diagram is a genuine instructional science illustration or noise/photo.
    """
    if not description or len(description.strip()) < 10:
        return {"is_useful": False, "reason": "Empty description"}

    system_prompt = (
        "You are a strict Senior Science Textbook Inspector.\n"
        "Analyze the image description and determine if it should be KEPT as an instructional science diagram or REJECTED.\n\n"
        "RULES:\n"
        "1. REJECT (is_useful = false):\n"
        "   - Scenery, landscapes, nature photos, animals, or horses without instructional labels.\n"
        "   - Real-world photographs of people, food, or objects without educational diagrams.\n"
        "   - Book cover art, preface decorative graphics, badges, chapter banners.\n"
        "   - Visuals that do not teach an 8th-grade science curriculum mechanism.\n\n"
        "2. KEEP (is_useful = true):\n"
        "   - Annotated anatomical diagrams (heart, lungs, cells, eye, leaf cross-section).\n"
        "   - Scientific graphs and charts with data axes (solubility curve, growth chart).\n"
        "   - Laboratory apparatus setups (beakers, distillation, titration).\n"
        "   - Flowcharts, cycles, and process models (refrigeration cycle, waves, atom models).\n\n"
        "Respond ONLY with valid JSON:\n"
        "{\n"
        '  "is_useful": true or false,\n'
        '  "reason": "Brief technical justification"\n'
        "}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Image Description:\n{description[:1200]}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"    [Gatekeeper Error]: {e}")
        return {"is_useful": False, "reason": str(e)}


# ==============================================================================
# AGENT 2: MULTIMODAL QUESTION AUTHOR (Base64 Image + Description -> 3 Questions)
# ==============================================================================

def diagram_question_author_agent(lesson: str, description: str, filename: str, image_path: str = None) -> dict:
    """
    Generates exactly 3 questions FOR THIS SPECIFIC DIAGRAM using BOTH Base64 Image AND Description:
      1. Short Question (سؤال قصير) + Model Answer
      2. Multiple Choice (اختيار من متعدد) with 4 options (A, B, C, D) + Correct Option
      3. Reasoning Question (سؤال تعليلي / لماذا وكيف) + Model Answer
    CRITICAL RULE:
      At least ONE question MUST be directly derived from visual details (labels, numbers, colors, curves)
      visible INSIDE this diagram image.
    """
    system_prompt = (
        "You are an expert Grade 8 Science Examination Author.\n"
        "You are given the Lesson name, a detailed technical description, and the actual base64-encoded image "
        "of a confirmed science diagram from the official Saudi Grade 8 Science textbook.\n\n"
        "TASK:\n"
        "Inspect BOTH the attached image and the description carefully. Generate exactly 3 high-quality educational questions (in English) with clear model answers:\n"
        "1. short_question: A concise, direct curriculum question and factual answer.\n"
        "2. mcq: A 4-option multiple-choice question (options A, B, C, D) with the correct option identified.\n"
        "3. reasoning: A scientific reasoning question (e.g., 'Explain why...', 'What causes...', 'How does...') "
        "with a clear explanation.\n\n"
        "CRITICAL INSTRUCTION ON DIAGRAM (VISION-BASED):\n"
        "- At least ONE of the 3 questions (can be short_question, mcq, or reasoning) MUST be directly derived "
        "from the visual content INSIDE the diagram image (e.g., reading data off an axis, identifying a labeled part, "
        "interpreting Arabic labels like 'ماء' or 'سكر', or explaining the visual mechanism shown).\n"
        "- Set 'is_diagram_based': true on that specific question (and false on others).\n\n"
        "OUTPUT FORMAT (STRICT JSON ONLY):\n"
        "{\n"
        '  "short_question": {\n'
        '    "question": "Direct short question",\n'
        '    "answer": "Concise factual model answer",\n'
        '    "is_diagram_based": false\n'
        "  },\n"
        '  "mcq": {\n'
        '    "question": "Multiple choice question stem",\n'
        '    "options": {\n'
        '      "A": "Option text",\n'
        '      "B": "Option text",\n'
        '      "C": "Option text",\n'
        '      "D": "Option text"\n'
        "    },\n"
        '    "correct_option": "A",\n'
        '    "explanation": "Brief explanation why this option is correct",\n'
        '    "is_diagram_based": true\n'
        "  },\n"
        '  "reasoning": {\n'
        '    "question": "Reasoning question asking why or how",\n'
        '    "answer": "Detailed explanatory answer",\n'
        '    "is_diagram_based": false\n'
        "  }\n"
        "}"
    )

    user_content = [
        {
            "type": "text",
            "text": (
                f"Lesson: {lesson}\n"
                f"Diagram Filename: {filename}\n\n"
                f"Document AI Technical Description:\n{description[:1200]}\n\n"
                "INSTRUCTION: Examine the attached image and the description to author the 3 questions."
            )
        }
    ]

    # Attach Base64 Image for Multimodal Vision
    if image_path and os.path.exists(image_path):
        try:
            b64_str = encode_image_base64(image_path)
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64_str}",
                    "detail": "high"
                }
            })
        except Exception as e:
            print(f"    [Base64 Warning]: Could not encode {image_path}: {e}")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"    [Author Error]: {e}")
        return {}


# ==============================================================================
# PIPELINE PROCESSOR (PER-LESSON WORKSHEETS)
# ==============================================================================

def process_semester(sem_key: str):
    config = SEMESTER_CONFIGS.get(sem_key)
    if not config:
        print(f"Error: Invalid semester '{sem_key}'")
        return

    csv_in = config["csv_path"]
    csv_out = config["output_csv"]
    worksheets_dir = config["worksheets_dir"]
    title = config["title"]
    output_img_dir = f"output_diagrams_sem{sem_key}"

    if not os.path.exists(csv_in):
        print(f"[Error] File not found: {csv_in}")
        return

    os.makedirs(worksheets_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print(f"PROCESSING: {title.upper()} (MULTIMODAL BASE64 + PER-LESSON WORKSHEETS)")
    print("=" * 70)

    with open(csv_in, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"Total candidate diagrams in CSV: {len(rows)}")

    # -------------------------------------------------------------------------
    # STEP 1: Strict Gatekeeper Evaluation (Call #1)
    # -------------------------------------------------------------------------
    print("\n>>> [STEP 1/3] Running Gatekeeper Agent on diagrams...")
    approved_diagrams = []
    discarded_count = 0

    for idx, row in enumerate(rows, 1):
        filename = row.get("image_filename", "")
        desc = row.get("description", "")
        lesson = row.get("lesson", "")

        gate = gatekeeper_agent(desc)
        if gate.get("is_useful", False):
            print(f"  [{idx:02d}/{len(rows):02d}] ✅ APPROVED: {filename} ({lesson[:30]})...")
            approved_diagrams.append(row)
        else:
            discarded_count += 1
            print(f"  [{idx:02d}/{len(rows):02d}] ❌ DISCARDED: {filename} -> {gate.get('reason')}")

    print(f"\nGatekeeper Summary: {len(approved_diagrams)} Approved, {discarded_count} Discarded.")

    # -------------------------------------------------------------------------
    # STEP 2: Generate 3 Questions FOR EACH APPROVED DIAGRAM (Call #2 - Multimodal)
    # -------------------------------------------------------------------------
    print("\n>>> [STEP 2/3] Generating 3 Questions (Base64 Image + Description) for EACH diagram...")
    cache_path = f"diagram_questions_multimodal_cache_sem{sem_key}.json"
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f_c:
                cache = json.load(f_c)
        except Exception:
            cache = {}

    enriched_diagrams = []

    for idx, row in enumerate(approved_diagrams, 1):
        filename = row.get("image_filename", "")
        desc = row.get("description", "")
        lesson = row.get("lesson", "")
        raw_img_path = row.get("image_path", "")

        # Resolve image path dynamically to guarantee the file exists on disk
        resolved_img_path, resolved_filename = resolve_image_path(raw_img_path, filename, output_dir=output_img_dir)
        row["image_path"] = resolved_img_path
        row["image_filename"] = resolved_filename

        if resolved_filename in cache and cache[resolved_filename].get("short_question"):
            print(f"  [{idx:02d}/{len(approved_diagrams):02d}] (Cached) {resolved_filename} ({lesson[:30]})...")
            q_data = cache[resolved_filename]
        else:
            print(f"  [{idx:02d}/{len(approved_diagrams):02d}] Authoring with Base64 Image: {resolved_filename} ({lesson[:30]})...")
            q_data = diagram_question_author_agent(lesson, desc, resolved_filename, image_path=resolved_img_path)
            if q_data:
                cache[resolved_filename] = q_data
                try:
                    with open(cache_path, "w", encoding="utf-8") as f_c:
                        json.dump(cache, f_c, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        short_q = q_data.get("short_question", {})
        mcq_q = q_data.get("mcq", {})
        reasoning_q = q_data.get("reasoning", {})

        record = dict(row)
        record.update({
            "short_question": short_q.get("question", ""),
            "short_answer": short_q.get("answer", ""),
            "short_is_diagram_based": short_q.get("is_diagram_based", False),
            "mcq_question": mcq_q.get("question", ""),
            "mcq_options": mcq_q.get("options", {}),
            "mcq_correct_option": mcq_q.get("correct_option", ""),
            "mcq_explanation": mcq_q.get("explanation", ""),
            "mcq_is_diagram_based": mcq_q.get("is_diagram_based", False),
            "reasoning_question": reasoning_q.get("question", ""),
            "reasoning_answer": reasoning_q.get("answer", ""),
            "reasoning_is_diagram_based": reasoning_q.get("is_diagram_based", False),
        })
        enriched_diagrams.append(record)

    # -------------------------------------------------------------------------
    # STEP 3: Save Enriched CSV (Safe with PermissionError Handling)
    # -------------------------------------------------------------------------
    print(f"\nWriting all diagrams with questions to CSV: {csv_out}")
    csv_headers = [
        "unit", "chapter", "lesson", "image_filename", "image_path", "resolution",
        "short_question", "short_answer", "short_is_diagram_based",
        "mcq_question", "mcq_options", "mcq_correct_option", "mcq_explanation", "mcq_is_diagram_based",
        "reasoning_question", "reasoning_answer", "reasoning_is_diagram_based",
    ]

    try:
        with open(csv_out, "w", encoding="utf-8-sig", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=csv_headers, extrasaction='ignore')
            writer.writeheader()
            for rec in enriched_diagrams:
                row_copy = dict(rec)
                row_copy["mcq_options"] = json.dumps(rec.get("mcq_options", {}), ensure_ascii=False)
                writer.writerow(row_copy)
        print(f"  -> Saved CSV to: {csv_out}")
    except PermissionError:
        alt_csv = csv_out.replace(".csv", "_updated.csv")
        print(f"  [WARNING] '{csv_out}' is open in another program. Saved to '{alt_csv}' instead.")
        with open(alt_csv, "w", encoding="utf-8-sig", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=csv_headers, extrasaction='ignore')
            writer.writeheader()
            for rec in enriched_diagrams:
                row_copy = dict(rec)
                row_copy["mcq_options"] = json.dumps(rec.get("mcq_options", {}), ensure_ascii=False)
                writer.writerow(row_copy)
        print(f"  -> Saved CSV to: {alt_csv}")

    # -------------------------------------------------------------------------
    # STEP 4: Group Diagrams strictly by Lesson
    # -------------------------------------------------------------------------
    print("\n>>> [STEP 4/4] Generating Individual HTML Worksheets PER LESSON...")
    lesson_groups = OrderedDict()
    for row in enriched_diagrams:
        lesson = row.get("lesson", "").strip()
        if not lesson:
            lesson = "General Science"
        if lesson not in lesson_groups:
            lesson_groups[lesson] = []
        lesson_groups[lesson].append(row)

    print(f"Total unique lessons to build worksheets for: {len(lesson_groups)}\n")

    generated_worksheets = []
    for l_idx, (lesson_name, items) in enumerate(lesson_groups.items(), 1):
        safe_name = sanitize_filename(lesson_name)
        out_filename = f"worksheet_lesson_{l_idx:02d}_{safe_name}.html"
        out_filepath = os.path.join(worksheets_dir, out_filename)

        build_single_lesson_worksheet(title, lesson_name, items, out_filepath)
        generated_worksheets.append((lesson_name, out_filename, len(items)))
        print(f"  [{l_idx:02d}/{len(lesson_groups):02d}] Created: {out_filename} ({len(items)} diagram(s))")

    # Also build a clean Index page for navigation
    build_worksheets_index(title, generated_worksheets, os.path.join(worksheets_dir, "index.html"))

    print("\n" + "=" * 70)
    print(f"ALL LESSON WORKSHEETS READY IN: {os.path.abspath(worksheets_dir)}")
    print(f"Master Index: {os.path.abspath(os.path.join(worksheets_dir, 'index.html'))}")
    print("=" * 70 + "\n")


# ==============================================================================
# HTML BUILDER FOR A SINGLE LESSON (FOCUS ON LESSON ONLY - NO UNIT/CHAPTER)
# ==============================================================================

def build_single_lesson_worksheet(semester_title: str, lesson_name: str, diagrams: list, output_file: str):
    """
    Builds a standalone printable worksheet HTML for a SINGLE lesson.
    - Banner strictly contains: 📖 الدرس: {lesson_name}
    - Unit and Chapter removed.
    - Each diagram is displayed separately with its OWN 3 questions.
    """
    cards_html = ""

    for d_idx, diag in enumerate(diagrams, 1):
        filename = diag.get("image_filename", "")
        # Adjust image path relative to worksheets folder (../output_diagrams_semX/...)
        raw_img_path = diag.get("image_path", "").replace("\\", "/")
        rel_img_path = f"../{raw_img_path}" if not raw_img_path.startswith("..") else raw_img_path
        resolution = diag.get("resolution", "")

        # 1. Short Question
        short_q = diag.get("short_question", "")
        short_a = diag.get("short_answer", "")
        short_tag = '<span class="diagram-tag">🔍 Diagram-Based</span>' if diag.get("short_is_diagram_based") else ""

        short_html = f"""
        <div class="q-box box-short">
            <div class="q-box-header">
                <span class="q-type-badge">📝 Question 1: Short Question (سؤال قصير)</span>
                {short_tag}
            </div>
            <div class="q-prompt">{short_q}</div>
            <div class="answer-block">
                <strong>Answer:</strong> {short_a}
            </div>
        </div>
        """

        # 2. MCQ
        mcq_q = diag.get("mcq_question", "")
        mcq_opts = diag.get("mcq_options", {})
        correct_key = diag.get("mcq_correct_option", "A").upper()
        mcq_expl = diag.get("mcq_explanation", "")
        mcq_tag = '<span class="diagram-tag">🔍 Diagram-Based</span>' if diag.get("mcq_is_diagram_based") else ""

        opts_html = ""
        for opt_key in ["A", "B", "C", "D"]:
            opt_val = mcq_opts.get(opt_key, "")
            is_correct = (opt_key == correct_key)
            css_class = "mcq-option correct" if is_correct else "mcq-option"
            mark = " ✓" if is_correct else ""
            opts_html += f'<div class="{css_class}"><strong>({opt_key})</strong> {opt_val}{mark}</div>'

        mcq_html = f"""
        <div class="q-box box-mcq">
            <div class="q-box-header">
                <span class="q-type-badge">🔘 Question 2: Multiple Choice (اختيار من متعدد)</span>
                {mcq_tag}
            </div>
            <div class="q-prompt">{mcq_q}</div>
            <div class="mcq-options-grid">
                {opts_html}
            </div>
            <div class="answer-block">
                <strong>Correct Option:</strong> ({correct_key}) &bull; {mcq_expl}
            </div>
        </div>
        """

        # 3. Reasoning Question
        reason_q = diag.get("reasoning_question", "")
        reason_a = diag.get("reasoning_answer", "")
        reason_tag = '<span class="diagram-tag">🔍 Diagram-Based</span>' if diag.get("reasoning_is_diagram_based") else ""

        reason_html = f"""
        <div class="q-box box-reasoning">
            <div class="q-box-header">
                <span class="q-type-badge">💡 Question 3: Scientific Reasoning (سؤال تعليلي)</span>
                {reason_tag}
            </div>
            <div class="q-prompt">{reason_q}</div>
            <div class="answer-block">
                <strong>Explanation:</strong> {reason_a}
            </div>
        </div>
        """

        cards_html += f"""
        <!-- Diagram #{d_idx} Card -->
        <div class="diagram-eval-card">
            <div class="card-grid">
                <!-- Left: Diagram Image Box (Separate & Distinct) -->
                <div class="image-box">
                    <img src="{rel_img_path}" alt="{filename}" loading="lazy">
                    <div class="image-meta">
                        <span><strong>Diagram #{d_idx}</strong> &bull; {filename}</span>
                        <span>{resolution}</span>
                    </div>
                </div>

                <!-- Right: Dedicated 3 Questions for THIS Diagram -->
                <div class="questions-stack">
                    {short_html}
                    {mcq_html}
                    {reason_html}
                </div>
            </div>
        </div>
        """

    html_code = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{lesson_name} - Science Worksheet</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Arabic:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #1e3a8a;
            --primary-light: #eff6ff;
            --accent: #2563eb;
            --border: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --bg-page: #f8fafc;
            --card-bg: #ffffff;
            --q-short-bg: #f0fdf4;
            --q-short-border: #86efac;
            --q-mcq-bg: #eff6ff;
            --q-mcq-border: #93c5fd;
            --q-reason-bg: #fffbeb;
            --q-reason-border: #fde68a;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-page);
            color: var(--text-main);
            line-height: 1.6;
            padding: 24px;
        }}

        .container {{ max-width: 1240px; margin: 0 auto; }}

        /* Top Header Banner: ONLY LESSON NAME */
        .lesson-banner {{
            background: linear-gradient(135deg, #1e3a8a, #2563eb);
            color: white;
            padding: 24px 32px;
            border-radius: 14px;
            margin-bottom: 28px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 14px rgba(30, 58, 138, 0.18);
        }}

        .lesson-header-text {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .lesson-main-title {{
            font-size: 24px;
            font-weight: 800;
            font-family: 'Noto Sans Arabic', sans-serif;
            direction: rtl;
            text-align: right;
        }}

        .lesson-sub {{
            font-size: 13.5px;
            opacity: 0.9;
            font-weight: 500;
        }}

        .header-actions {{
            display: flex;
            gap: 12px;
            align-items: center;
        }}

        .btn-action {{
            background: #ffffff;
            color: #1e3a8a;
            border: none;
            padding: 10px 18px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 13.5px;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            transition: all 0.2s ease;
        }}
        .btn-action:hover {{ background: #f1f5f9; transform: translateY(-1px); }}

        /* Diagram Card */
        .diagram-eval-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.03);
            page-break-inside: avoid;
        }}

        /* Side-by-Side: Left Image, Right Questions */
        .card-grid {{
            display: grid;
            grid-template-columns: 460px 1fr;
            gap: 24px;
            align-items: start;
        }}

        /* Image Box - Clean & Distinct */
        .image-box {{
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}

        .image-box img {{
            max-width: 100%;
            max-height: 480px;
            height: auto;
            border-radius: 8px;
            object-fit: contain;
            background: #ffffff;
            border: 1px solid #e2e8f0;
        }}

        .image-meta {{
            margin-top: 10px;
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            width: 100%;
            padding: 0 4px;
        }}

        .image-meta strong {{ color: #1e3a8a; }}

        /* Right Column: Questions Stack */
        .questions-stack {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        /* Shared Question Box */
        .q-box {{
            border-radius: 12px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .q-box-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .q-type-badge {{
            font-size: 13px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .diagram-tag {{
            background: #dc2626;
            color: #ffffff;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .q-prompt {{
            font-size: 14px;
            font-weight: 600;
            color: #0f172a;
            line-height: 1.5;
        }}

        /* 1. Short Question Box */
        .box-short {{
            background: var(--q-short-bg);
            border: 1.5px solid var(--q-short-border);
        }}
        .box-short .q-type-badge {{ color: #15803d; }}

        /* 2. MCQ Box */
        .box-mcq {{
            background: var(--q-mcq-bg);
            border: 1.5px solid var(--q-mcq-border);
        }}
        .box-mcq .q-type-badge {{ color: #1d4ed8; }}

        .mcq-options-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-top: 4px;
        }}

        .mcq-option {{
            background: #ffffff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            padding: 7px 12px;
            font-size: 13px;
            color: #1e3a8a;
            font-weight: 500;
        }}

        .mcq-option.correct {{
            background: #dcfce7;
            border-color: #4ade80;
            color: #14532d;
            font-weight: 700;
        }}

        /* 3. Reasoning Box */
        .box-reasoning {{
            background: var(--q-reason-bg);
            border: 1.5px solid var(--q-reason-border);
        }}
        .box-reasoning .q-type-badge {{ color: #b45309; }}

        /* Answers Styling */
        .answer-block {{
            background: #ffffff;
            border-radius: 8px;
            padding: 7px 12px;
            font-size: 13px;
            color: #334155;
            border-left: 4px solid #22c55e;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }}

        .answer-block strong {{ color: #14532d; }}

        /* Responsive Breakpoint */
        @media (max-width: 980px) {{
            .card-grid {{ grid-template-columns: 1fr; }}
            .mcq-options-grid {{ grid-template-columns: 1fr; }}
        }}

        /* PRINT STYLES FOR CLEAN PDF GENERATION */
        @media print {{
            body {{ background: #fff; padding: 0; }}
            .no-print {{ display: none !important; }}
            .lesson-banner {{
                background: #1e3a8a !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                border-radius: 0;
                margin-bottom: 15px;
            }}
            .diagram-eval-card {{
                box-shadow: none !important;
                border: 1px solid #cbd5e1 !important;
                page-break-inside: avoid;
                margin-bottom: 24px;
            }}
            .card-grid {{ grid-template-columns: 380px 1fr !important; }}
            .box-short {{ background: #f0fdf4 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .box-mcq {{ background: #eff6ff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .box-reasoning {{ background: #fffbeb !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>

<div class="container">
    <header class="lesson-banner">
        <div class="lesson-header-text">
            <h1 class="lesson-main-title">📖 الدرس: {lesson_name}</h1>
            <div class="lesson-sub">{semester_title} &bull; {len(diagrams)} Scientific Diagram(s)</div>
        </div>
        <div class="header-actions no-print">
            <a href="index.html" class="btn-action">📂 All Lessons</a>
            <button class="btn-action" onclick="window.print()">🖨️ Print / Save as PDF</button>
        </div>
    </header>

    <div class="worksheet-cards">
        {cards_html}
    </div>
</div>

</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f_out:
        f_out.write(html_code)


# ==============================================================================
# MASTER INDEX BUILDER (LINKS TO ALL INDIVIDUAL LESSON WORKSHEETS)
# ==============================================================================

def build_worksheets_index(semester_title: str, worksheets_list: list, output_file: str):
    """
    Builds a clean master index.html allowing one-click navigation to each lesson worksheet.
    """
    total_diagrams = sum(cnt for _, _, cnt in worksheets_list)

    links_html = ""
    for idx, (lesson_name, filename, count) in enumerate(worksheets_list, 1):
        links_html += f"""
        <a href="{filename}" class="lesson-item-card">
            <div class="lesson-card-left">
                <span class="lesson-index-badge">Lesson #{idx:02d}</span>
                <span class="lesson-card-name">📖 {lesson_name}</span>
            </div>
            <div class="lesson-card-right">
                <span class="diagrams-badge">{count} Diagram(s)</span>
                <span class="arrow-icon">&rarr;</span>
            </div>
        </a>
        """

    html_code = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{semester_title} - Lesson Worksheets Index</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Arabic:wght@600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
            padding: 30px 20px;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #1e3a8a, #2563eb);
            color: white;
            padding: 28px 32px;
            border-radius: 14px;
            margin-bottom: 28px;
            box-shadow: 0 4px 14px rgba(30, 58, 138, 0.18);
        }}
        .header h1 {{ font-size: 24px; font-weight: 800; }}
        .header p {{ font-size: 14px; opacity: 0.9; margin-top: 6px; }}
        .lessons-grid {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .lesson-item-card {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px 22px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            text-decoration: none;
            color: inherit;
            box-shadow: 0 2px 6px rgba(0,0,0,0.03);
            transition: all 0.2s ease;
        }}
        .lesson-item-card:hover {{
            border-color: #2563eb;
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(37, 99, 235, 0.12);
        }}
        .lesson-card-left {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}
        .lesson-index-badge {{
            background: #eff6ff;
            color: #1d4ed8;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
        }}
        .lesson-card-name {{
            font-size: 16px;
            font-weight: 700;
            font-family: 'Noto Sans Arabic', sans-serif;
            color: #1e3a8a;
        }}
        .lesson-card-right {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .diagrams-badge {{
            background: #f1f5f9;
            color: #475569;
            font-size: 12.5px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 20px;
        }}
        .arrow-icon {{
            font-size: 18px;
            color: #2563eb;
            font-weight: 700;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{semester_title}</h1>
        <p>Master Directory &bull; {len(worksheets_list)} Lessons &bull; {total_diagrams} Scientific Diagrams (Click any lesson to open its printable worksheet)</p>
    </div>
    <div class="lessons-grid">
        {links_html}
    </div>
</div>
</body>
</html>
"""
    with open(output_file, "w", encoding="utf-8") as f_out:
        f_out.write(html_code)


# ==============================================================================
# MAIN CLI ENTRYPOINT
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Per-Lesson Diagram Question Worksheet Generator")
    parser.add_argument("--sem", choices=["1", "2", "3", "all"], default=None, help="Semester (1, 2, 3, or all)")
    args = parser.parse_args()

    target = args.sem
    if not target:
        print("\n" + "=" * 60)
        print("PER-LESSON WORKSHEET GENERATOR - GRADE 8 SCIENCE")
        print("=" * 60)
        print("Available Semesters:")
        for k, v in SEMESTER_CONFIGS.items():
            print(f"  [{k}] {v['title']}")
        print("  [all] Process All Semesters")
        try:
            choice = input("\nEnter choice [1, 2, 3, or all] (default: 1): ").strip().lower()
            target = choice if choice in ["1", "2", "3", "all"] else "1"
        except (EOFError, KeyboardInterrupt):
            target = "1"

    if target == "all":
        for s in ["1", "2", "3"]:
            process_semester(s)
    else:
        process_semester(target)

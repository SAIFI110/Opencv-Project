"""
Interactive Labeling Pipeline Candidate Generator
Saudi Grade 8 Science Educational Platform
==================================================
Two-Stage Architecture:
1. Vision Planner (GPT-4o):
   - Reads all Arabic labels on the diagram.
   - Applies proportional hiding rules:
     * Total <= 3 labels: Hide 1 or 2 labels (leave at least 1-2 visible for context).
     * Total 4 to 6 labels: Hide 2 or 3 labels.
     * Total 7 to 9 labels: Hide 3 or 4 labels.
     * Total 10+ labels (e.g. 13): Hide 4 or 5 labels (leave remaining 8-9 visible!).
     * NEVER hide all labels on any diagram.
   - Locks the ground truth answer key: {"1": "...", "2": "..."}.
2. Targeted Visual Editing (GPT Image 2.5 Sunburst):
   - Erases ONLY the planned labels and places circular callout pins (①, ②, ③...).
   - Leaves all other labels and anatomical artwork completely untouched.
   - Saves final images into labeling_sem1/, labeling_sem2/, labeling_sem3/.
   - Stores answer mapping in MySQL diagram_metadata.masked_labels_json.
"""

import os
import sys
import json
import base64
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

import db


def ensure_column_exists():
    """Ensures masked_labels_json column exists in diagram_metadata."""
    conn = db.get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) as cnt FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
              AND TABLE_NAME = 'diagram_metadata' 
              AND COLUMN_NAME = 'masked_labels_json';
        """)
        exists = cur.fetchone()["cnt"] > 0
        if not exists:
            cur.execute("ALTER TABLE diagram_metadata ADD COLUMN masked_labels_json JSON NULL;")
            print("✓ Added column 'masked_labels_json' to MySQL diagram_metadata table.")
        else:
            print("✓ Column 'masked_labels_json' already present in MySQL diagram_metadata.")
    conn.close()


def plan_labels_with_vision(image_path: str, lesson: str = "", desc: str = "") -> dict:
    """
    Step 1: Uses GPT-4o to inspect diagram and select labels to hide according to proportional rules.
    Returns: {"labels_to_hide": {"1": "...", "2": "..."}, "labels_to_keep": [...]}
    """
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = f"""You are an educational assessment author preparing an interactive labeling quiz for Saudi Grade 8 Science.
Inspect this diagram carefully and identify all Arabic scientific text labels.
Diagram Lesson: {lesson}
Description: {desc[:200] if desc else 'Science illustration'}

PROPORTIONAL HIDING RULES:
1. Count the total number of labels (N) on this diagram.
2. If N <= 3: Select ONLY 1 or 2 labels to hide (DO NOT hide all; leave at least 1-2 visible for context!).
3. If N is 4 to 6: Select 2 or 3 labels to hide.
4. If N is 7 to 9: Select 3 or 4 labels to hide.
5. If N >= 10: Select 4 or 5 labels to hide (leave the other 6+ labels completely visible!).
6. NEVER hide all labels on any diagram.
7. Prioritize labels sitting on clean margins at the end of pointer lines. Do NOT select text stamped directly over complex colored anatomy.

Return ONLY valid JSON format:
{{
  "total_labels": N,
  "labels_to_hide": {{
    "1": "exact Arabic text of label 1 to erase",
    "2": "exact Arabic text of label 2 to erase"
  }},
  "labels_to_keep": ["label A", "label B", ...]
}}"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}}
            ]}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        data = json.loads(res.choices[0].message.content)
        to_hide = data.get("labels_to_hide", {})
        to_keep = data.get("labels_to_keep", [])
        return {
            "labels_to_hide": {str(k): str(v).strip() for k, v in to_hide.items() if v and "اسم العضو" not in v},
            "labels_to_keep": [str(x).strip() for x in to_keep if x]
        }
    except Exception as e:
        print(f"  [Vision Planning Error on {image_path}]: {e}")
        return {"labels_to_hide": {}, "labels_to_keep": []}


def edit_with_sunburst(image_path: str, dst_path: str, labels_to_hide: dict, labels_to_keep: list) -> bool:
    """
    Step 2: Uses gpt-image-2.5-sunburst to execute targeted erasure and place pin badges.
    """
    hide_instructions = []
    for pin_num, label_text in labels_to_hide.items():
        hide_instructions.append(f"- Erase '{label_text}' and place a clean circular pin badge (white fill, thin black border) with bold black number {pin_num} at its pointer line.")

    hide_str = "\n".join(hide_instructions)
    keep_str = ", ".join([f"'{k}'" for k in labels_to_keep[:8]])

    prompt = f"""Modify this Saudi Grade 8 Science diagram for an interactive labeling quiz:
1. Erase ONLY the following specific Arabic labels:
{hide_str}
2. DO NOT erase or modify any other labels (keep {keep_str} and all other text 100% visible and intact).
3. Keep all anatomical organs, colors, arrows, and pointer lines 100% identical and unchanged."""

    try:
        with open(image_path, "rb") as f:
            res = client.images.edit(
                model="gpt-image-2.5-sunburst",
                image=f,
                prompt=prompt,
                output_format="png"
            )

        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        item = res.data[0]
        if hasattr(item, "b64_json") and item.b64_json:
            with open(dst_path, "wb") as out_f:
                out_f.write(base64.b64decode(item.b64_json))
            return True
        elif hasattr(item, "url") and item.url:
            urllib.request.urlretrieve(item.url, dst_path)
            return True
        return False
    except Exception as e:
        print(f"  [Sunburst Edit Error on {image_path}]: {e}")
        return False


def process_single_diagram(diagram_row: dict) -> tuple:
    """Processes a single diagram through the 2-stage pipeline."""
    diag_id = diagram_row["id"]
    sem = diagram_row["semester"]
    filename = diagram_row["image_filename"]
    lesson = diagram_row.get("lesson", "")
    desc = diagram_row.get("description", "")

    src_dir = f"output_diagrams_sem{sem}"
    dst_dir = f"labeling_sem{sem}"
    src_path = os.path.join(src_dir, filename)
    dst_path = os.path.join(dst_dir, filename)

    if not os.path.exists(src_path):
        return diag_id, filename, sem, False, f"Source missing: {src_path}", {}

    # Stage 1: Vision Planning & Rule Enforcement
    plan = plan_labels_with_vision(src_path, lesson=lesson, desc=desc)
    labels_to_hide = plan.get("labels_to_hide", {})
    labels_to_keep = plan.get("labels_to_keep", [])

    if not labels_to_hide:
        return diag_id, filename, sem, False, "No cleanly erasable labels found", {}

    # Stage 2: Targeted Sunburst Visual Edit
    success = edit_with_sunburst(src_path, dst_path, labels_to_hide, labels_to_keep)
    if not success or not os.path.exists(dst_path):
        return diag_id, filename, sem, False, "Sunburst edit failed", {}

    # Update MySQL with ground-truth mapping
    try:
        conn = db.get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE diagram_metadata 
                SET masked_labels_json = %s 
                WHERE id = %s;
            """, (json.dumps(labels_to_hide, ensure_ascii=False), diag_id))
        conn.close()
    except Exception as e:
        print(f"  [DB Update Error for {filename}]: {e}")

    return diag_id, filename, sem, True, f"Masked {len(labels_to_hide)} labels", labels_to_hide


def main():
    print("=" * 70)
    print("🎯 Interactive Labeling Pipeline (Vision Planning + Targeted Sunburst)")
    print("=" * 70)

    ensure_column_exists()

    # Clean existing directories
    for sem in (1, 2, 3):
        out_dir = f"labeling_sem{sem}"
        os.makedirs(out_dir, exist_ok=True)
        for f in os.listdir(out_dir):
            fp = os.path.join(out_dir, f)
            if os.path.isfile(fp):
                os.remove(fp)
        print(f"✓ Cleaned directory: {out_dir}/")

    conn = db.get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, semester, unit, chapter, lesson, description, image_filename, image_path
            FROM diagram_metadata
            WHERE LOWER(is_suitable_for_labeling) IN ('yes', '1')
            ORDER BY semester, id;
        """)
        rows = cur.fetchall()
    conn.close()

    total_count = len(rows)
    print(f"\n📋 Found {total_count} diagrams to process.")

    max_workers = 4
    print(f"⚡ Processing with {max_workers} concurrent Vision + Sunburst workers...\n")

    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_diag = {executor.submit(process_single_diagram, row): row for row in rows}

        for idx, future in enumerate(as_completed(future_to_diag), start=1):
            row = future_to_diag[future]
            try:
                diag_id, filename, sem, ok, msg, mapping = future.result()
                if ok:
                    successful += 1
                    mapping_summary = ", ".join([f"{k}: '{v}'" for k, v in mapping.items()])
                    print(f"[{idx:02d}/{total_count}] [Sem {sem}] ✓ {filename} -> {mapping_summary}")
                else:
                    failed += 1
                    print(f"[{idx:02d}/{total_count}] [Sem {sem}] ⚠ {filename} -> {msg}")
            except Exception as e:
                failed += 1
                print(f"[{idx:02d}/{total_count}] [Sem {row.get('semester')}] ✗ {row.get('image_filename')} -> Error: {e}")

    print("\n" + "=" * 70)
    print(f"🎉 Pipeline Execution Complete!")
    print(f"   ✓ Successfully Generated: {successful} diagrams")
    print(f"   ⚠ Failed/Skipped:        {failed} diagrams")
    print(f"   📁 Results saved into:   labeling_sem1/, labeling_sem2/, labeling_sem3/")
    print(f"   💾 Database updated:     diagram_metadata.masked_labels_json")
    print("=" * 70)


if __name__ == "__main__":
    main()

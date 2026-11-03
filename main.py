"""
Educational Diagram & Worksheet Pipeline - Master Runner
=========================================================
Runs the complete 2-stage automated pipeline:
  Stage 1: Diagram Extraction & Quality Filtering (from Document AI JSON)
  Stage 2: Question Generation & HTML Worksheet Creation (with Model Answers)

Usage:
  python main.py --sem 1       # Run for Semester 1
  python main.py --sem 2       # Run for Semester 2
  python main.py --sem 3       # Run for Semester 3
  python main.py --sem all     # Run for All Semesters
  python main.py               # Interactive menu
"""

import sys
import argparse
from extract_diagrams import run_pipeline, SEMESTER_CONFIGS
from generate_questions_worksheet import process_semester

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding="utf-8")


def run_end_to_end(sem_key: str):
    """
    Executes the full pipeline end-to-end for a given semester:
      1. Calls extract_diagrams.py (crops images, discards noise via Call #1).
      2. Calls generate_questions_worksheet.py (generates questions via Call #2 & creates HTML).
    """
    title = SEMESTER_CONFIGS.get(sem_key, {}).get("title", f"Semester {sem_key}")

    print("\n" + "#" * 70)
    print(f"# MASTER PIPELINE: STARTING {title.upper()}")
    print("#" * 70)

    # -------------------------------------------------------------------------
    # STAGE 1: Diagram Extraction (from Document AI JSON)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(">>> [STAGE 1/2] RUNNING DIAGRAM EXTRACTION...")
    print("=" * 60)
    run_pipeline(sem_key)

    # -------------------------------------------------------------------------
    # STAGE 2: Two-Agent Evaluation, Questions & HTML Worksheet
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(">>> [STAGE 2/2] RUNNING EVALUATION, QUESTIONS & WORKSHEET BUILDER...")
    print("=" * 60)
    process_semester(sem_key)

    print("\n" + "#" * 70)
    print(f"# MASTER PIPELINE: COMPLETED FOR {title.upper()}!")
    print("#" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Master Runner: Grade 8 Science Diagram Extraction & Question Worksheets"
    )
    parser.add_argument(
        "--sem",
        choices=["1", "2", "3", "all"],
        default=None,
        help="Semester to process (1, 2, 3, or all)",
    )
    args = parser.parse_args()

    target = args.sem
    if not target:
        print("\n" + "=" * 65)
        print("MASTER EDUCATIONAL DIAGRAM & WORKSHEET SYSTEM")
        print("=" * 65)
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
            run_end_to_end(s)
    else:
        run_end_to_end(target)

"""
Sync Labeling Candidates with MySQL Database
Saudi Grade 8 Science Educational Platform
===========================================
1. Scans labeling_sem1/, labeling_sem2/, labeling_sem3/ on disk.
2. For all remaining images on disk:
   - Sets is_suitable_for_labeling = 'YES' in diagram_metadata.
   - Keeps their masked_labels_json intact.
3. For any diagram that was deleted from disk:
   - Sets is_suitable_for_labeling = 'NO' in diagram_metadata.
   - Sets masked_labels_json = NULL.
"""

import os
import sys
import db

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def sync_candidates():
    print("=" * 65)
    print("🔄 Syncing Hand-Picked Labeling Diagrams with Database")
    print("=" * 65)

    conn = db.get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, semester, image_filename, is_suitable_for_labeling FROM diagram_metadata;")
        rows = cur.fetchall()

    total_approved = 0
    total_rejected = 0

    with conn.cursor() as cur:
        for r in rows:
            diag_id = r["id"]
            sem = r["semester"]
            filename = r["image_filename"]
            folder = f"labeling_sem{sem}"
            disk_path = os.path.join(folder, filename)

            is_present = os.path.isfile(disk_path)

            if is_present:
                # User kept this diagram -> Approved!
                cur.execute("""
                    UPDATE diagram_metadata
                    SET is_suitable_for_labeling = 'YES'
                    WHERE id = %s;
                """, (diag_id,))
                total_approved += 1
            else:
                # User deleted this diagram -> Mark NO and clear masked_labels_json
                cur.execute("""
                    UPDATE diagram_metadata
                    SET is_suitable_for_labeling = 'NO',
                        masked_labels_json = NULL
                    WHERE id = %s;
                """, (diag_id,))
                total_rejected += 1

    conn.close()

    print(f"✓ Sync Complete!")
    print(f"  🌟 Approved & Kept ('YES'): {total_approved} diagrams")
    print(f"  ❌ Discarded & Reset ('NO'):  {total_rejected} diagrams")
    print("=" * 65)


if __name__ == "__main__":
    sync_candidates()


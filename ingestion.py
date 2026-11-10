"""
Ingest Grade 8 Science Textbook PDFs into Docker Qdrant Vector Database
High-performance batching: 50 chunks per OpenAI embedding API call.
"""
import os
import sys
import pypdf
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
client_openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "grade8_science_chunks")
VECTOR_SIZE = 1536  # OpenAI text-embedding-3-small dimension

# 1. Connect to Qdrant running in Docker
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# 2. Re-create collection
print(f"Initializing collection '{COLLECTION_NAME}' in Qdrant Docker ({QDRANT_HOST}:{QDRANT_PORT})...")
qdrant.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
)

PDF_FILES = {
    1: "grade_8_semester_1.pdf",
    2: "grade_8_semester_2.pdf",
    3: "grade_8_semester_3.pdf",
}

def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50):
    """Splits text into overlapping word chunks so concepts are never cut mid-sentence."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if len(chunk.strip()) > 80:  # Ignore tiny useless lines
            chunks.append(chunk)
    return chunks

# Collect all chunks across all semesters first
all_chunks_data = []

for semester, pdf_path in PDF_FILES.items():
    if not os.path.exists(pdf_path):
        print(f"Warning: {pdf_path} not found, skipping.")
        continue

    print(f"Extracting pages from Semester {semester} PDF: {pdf_path}...")
    reader = pypdf.PdfReader(pdf_path)

    for page_idx, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        if len(raw_text.strip()) < 100:
            continue  # Skip cover / empty pages

        page_chunks = chunk_text(raw_text)
        for chunk in page_chunks:
            all_chunks_data.append({
                "semester": semester,
                "page_number": page_idx,
                "text": chunk
            })

print(f"\nTotal extracted chunks across all textbooks: {len(all_chunks_data)}")
print("Generating embeddings and uploading to Qdrant Docker in batches of 64...")

BATCH_SIZE = 64
total_uploaded = 0

for i in range(0, len(all_chunks_data), BATCH_SIZE):
    batch = all_chunks_data[i:i + BATCH_SIZE]
    texts = [item["text"] for item in batch]

    # Batch embedding API call
    emb_res = client_openai.embeddings.create(
        input=texts,
        model="text-embedding-3-small"
    )

    points = []
    for offset, emb_obj in enumerate(emb_res.data):
        point_id = i + offset + 1
        item = batch[offset]
        points.append(
            PointStruct(
                id=point_id,
                vector=emb_obj.embedding,
                payload={
                    "semester": item["semester"],
                    "page_number": item["page_number"],
                    "text": item["text"]
                }
            )
        )

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    total_uploaded += len(points)
    print(f"  -> Uploaded {total_uploaded}/{len(all_chunks_data)} chunks to Qdrant...")

print(f"\n🎉 SUCCESS! All {total_uploaded} chunks successfully embedded and indexed in Qdrant Docker!")
print(f"Qdrant Dashboard available at: http://localhost:6333/dashboard")

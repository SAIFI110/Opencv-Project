# AI Tutor & Interactive Assessment Platform
> **Interactive AI Learning and Multimodal Assessment System for Saudi Middle School Science (علوم الصف الثاني المتوسط)**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/Model-GPT--4o--mini-412991.svg)](https://openai.com/)
[![Qdrant](https://img.shields.io/badge/Vector%20DB-Qdrant-red.svg)](https://qdrant.tech/)
[![MySQL](https://img.shields.io/badge/Database-MySQL%20Docker-4479A1.svg)](https://www.mysql.com/)

---

## 📖 Overview

The **AI Tutor & Assessment Platform** is a specialized, production-ready educational system built to support the official **Saudi Ministry of Education Grade 8 Science Curriculum** across all three semesters. 

The platform bridges textbook learning with real-time AI capabilities, offering students:
1. **Conversational AI Science Tutor**: A grounded, interactive pedagogical tutor providing live, word-by-word streaming responses strictly referencing official textbook concepts while refusing off-topic queries.
2. **Dynamic Diagram-Based Assessments**: Real-time generation of varied, anti-repetitive scientific questions (MCQ, factual short-answer, and scientific reasoning) based on verified textbook diagrams.
3. **Interactive Diagram Labeling**: Visual quizzes featuring masked scientific diagrams with pin-drop markers (①, ②, ③) testing anatomical and structural recall.
4. **General Theory Assessment Engine**: Rapid, on-demand curriculum quizzes grounded in official textbook passages retrieved via semantic vector search.

## 🏗️ System Architecture

The platform follows a modular, decoupled architecture combining Retrieval-Augmented Generation (RAG), computer vision extraction, and asynchronous REST APIs.

<img width="1042" height="1002" alt="Untitled Diagram drawio (1)" src="https://github.com/user-attachments/assets/882d2427-5f88-4562-b700-08afbe4e937c" />


---

## 🛠️ Technology Stack

| Layer | Technology | Role & Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | **FastAPI** (Python 3.12) | High-performance asynchronous API server providing REST endpoints and token streaming. |
| **Web Server** | **Uvicorn** | ASGI web server powering the production FastAPI application. |
| **LLM & Embeddings** | **OpenAI GPT-4o-mini** | Powers the pedagogical chat tutor and structured JSON assessment generation. |
| **Embedding Model** | **text-embedding-3-small** | Generates 1536-dimensional embeddings for textbook chunk vectorization. |
| **Vector Database** | **Qdrant** | High-speed semantic search engine retrieving relevant textbook passages for RAG. |
| **Relational Database**| **MySQL 8.0 (Docker)** | Stores curriculum hierarchy, diagram metadata, and student conversation logs in `utf8mb4`. |
| **Computer Vision** | **OpenCV & PyMuPDF (fitz)** | Extracts high-resolution diagrams from official Ministry PDF textbooks. |
| **Frontend UI** | **HTML5 / CSS3 / Vanilla JS** | Lightweight, dependency-free responsive client interface with ChatGPT-style streaming. |

## 📂 Repository Structure

```text
Opencv-Project/
├── static/                                  # Frontend Web Application Assets
│   ├── index.html                           # Single-page interface structure & modals
│   ├── app.js                               # Client application logic & streaming reader
│   └── styles.css                           # Modern responsive styling & design system
│
├── chatbot_backend.py                       # Main FastAPI application & API endpoints
├── db.py                                    # MySQL connection pool & table schema manager
├── dump_db.py                               # Database export & restore utility script
├── extract_diagrams.py                      # OpenCV & PyMuPDF diagram extraction pipeline
├── ingestion.py                             # Textbook chunk embedding & Qdrant vector ingester
├── sync_labeling_status.py                  # Labeling status synchronizer for database records
│
├── output_diagrams_sem1/                    # Extracted diagrams for Semester 1
├── output_diagrams_sem2/                    # Extracted diagrams for Semester 2
├── output_diagrams_sem3/                    # Extracted diagrams for Semester 3
│
├── labeling_sem1/                           # Masked labeling diagram assets (Semester 1)
├── labeling_sem2/                           # Masked labeling diagram assets (Semester 2)
├── labeling_sem3/                           # Masked labeling diagram assets (Semester 3)
│
├── grade_8_semester_1.pdf                   # Textbook (Sem 1)
├── grade_8_semester_2.pdf                   # Textbook (Sem 2)
├── grade_8_semester_3.pdf                   # Textbook (Sem 3)
│
├── semester_1.json                          # Json data (Sem 1)
├── semester_2.json                          # Json data (Sem 2)
├── semester_3.json                          # Json data (Sem 3)
│
├── backup_grade8_science.sql                # Production MySQL database dump (seed data)
├── docker-compose.yml                       # Docker services configuration
├── Dockerfile                               # Backend Docker container build instructions
├── requirements.txt                         # Python dependencies
└── .env.example                             # Environment variables template
```

### Key Modules Summary:
* **`chatbot_backend.py`**: The core API server powering the conversational AI tutor, diagram quiz generator, theory assessments, and static file serving.
* **`db.py`**: Handles MySQL database connectivity with `utf8mb4` encoding support for Arabic curriculum content and auto-initializes database tables.
* **`dump_db.py`**: CLI utility for creating database backups and restoring `backup_grade8_science.sql` on new machines.
* **`extract_diagrams.py`**: Automated pipeline that parses PDF pages, detects illustration contours via OpenCV, and saves filtered diagrams.
* **`ingestion.py`**: Reads textbooks, chunks content, creates OpenAI embeddings, and indexes them into Qdrant for semantic RAG.

* ## ⚙️ Prerequisites & Environment Setup

### System Prerequisites
* **Python**: `3.10` to `3.12`
* **Container Runtime**: [Docker Desktop](https://www.docker.com/) (running engine)
* **API Access**: [OpenAI API Key](https://platform.openai.com/) (access to `gpt-4o-mini` and `text-embedding-3-small`)

---

### 1. Installation

Clone the repository and initialize an isolated virtual environment:

```bash
# Clone repository
git clone https://github.com/SAIFI110/Opencv-Project.git
cd Opencv-Project

# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Linux / macOS:
source .venv/bin/activate

# Install locked dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 2. Environment Configuration

Copy the sample environment file to create your active `.env`:

```bash
cp .env.example .env
```

Populate the required environment variables:

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | OpenAI API authentication credential | `...` |
| `DB_HOST` | MySQL hostname | `localhost` |
| `DB_PORT` | MySQL exposed container port | `3306` |
| `DB_USER` | MySQL username | `root` |
| `DB_PASSWORD` | MySQL password | `rootpassword` |
| `DB_NAME` | Relational database schema name | `grade8_science` |
| `QDRANT_HOST` | Qdrant vector service hostname | `localhost` |
| `QDRANT_PORT` | Qdrant gRPC / REST API port | `6333` |
| `QDRANT_COLLECTION`| Vector collection namespace | `grade8_science_chunks` |
| `SERVER_HOST` | FastAPI host binding address | `0.0.0.0` |
| `SERVER_PORT` | FastAPI listening port | `8000` |

## 🗄️ Database Provisioning & Vector Ingestion

The platform requires two data stores: a relational store (**MySQL 8.0**) for curriculum metadata and student interactions, and a vector store (**Qdrant**) for textbook semantic retrieval.

---

### 1. Launch Storage Infrastructure

Start the MySQL and Qdrant containers in detached mode:

```bash
docker compose up -d mysql qdrant
```

Verify both containers are running healthy:

```bash
docker ps --filter "name=science_"
```

---

### 2. Populate MySQL Database (Restore Seed Data)

Import the verified schema, curriculum hierarchy, and diagram metadata from the seed SQL dump:

```bash
python dump_db.py --restore backup_grade8_science.sql
```

Verify that all tables and rows are properly loaded:

```bash
python db.py
```
*Expected Output: Confirms live connection and displays non-zero row counts for `diagram_metadata`, `diagram_questions`, `theory_assessments`, and `chat_history`.*

---

### 3. Ingest Textbook Vectors into Qdrant

Extract, chunk, and embed official Grade 8 Science textbooks (`grade_8_semester_1.pdf`, `2`, `3`) into the Qdrant vector database:

```bash
python ingestion.py
```
*Process Summary:*
* Parses all three semester textbooks into overlapping semantic chunks (300 words with 50-word overlap).
* Generates 1536-dimensional embeddings using `text-embedding-3-small` in batches of 50.
* Initializes the `grade8_science_chunks` collection with cosine distance indexing.

## 🚀 Running the Platform

### Option A: Local Development Server (Recommended)
With MySQL and Qdrant containers active, run the FastAPI application directly:

```bash
uvicorn chatbot_backend:app --host 0.0.0.0 --port 8000 --reload
```
Alternatively:
```bash
python chatbot_backend.py
```

### Option B: Full Docker Deployment
Launch all three services (FastAPI app, MySQL, and Qdrant) via Docker Compose:

```bash
docker compose up --build -d
```

---

### Access Points

* **Interactive Web Interface**: [http://localhost:8000](http://localhost:8000)
* **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Alternative API Documentation (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📡 API Reference

| Endpoint | Method | Payload / Parameters | Description |
| :--- | :---: | :--- | :--- |
| `/api/chat` | `POST` | `{"message": str, "semester": int, "history": list}` | Real-time AI tutor conversation with token-by-token text streaming (`text/plain; charset=utf-8`). |
| `/api/assessment/diagram/generate-single` | `POST` | `{"diagram_id": int, "num_questions": int, "previous_questions": list, "variation_seed": int}` | Generates non-repetitive, pedagogically focused diagram comprehension questions (MCQ, Short, Reasoning). |
| `/api/assessment/theory/generate-single` | `POST` | `{"semester": int, "unit": str, "lesson": str, "q_type": str, "previous_questions": list}` | Generates grounded theory questions directly extracted from textbook text. |
| `/api/curriculum` | `GET` | `?semester=1` (1, 2, or 3) | Returns curriculum hierarchy (units, chapters, lessons) with verified diagram counts. |
| `/api/assessment/labeling` | `POST` | `{"semester": int, "lesson": str, "limit": int}` | Returns masked diagrams with pin-marker locations (①, ②, ③) for anatomical and structural recall. |

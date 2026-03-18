# FT-IR AI Analysis Report Generator & Service

[English](README_en.md) | [简体中文](README.md)

This project provides a complete, automated pipeline for Fourier Transform Infrared (FT-IR) spectroscopy: from image recognition and data processing to intelligent diagnostic report generation.
It includes the core engine for **Computer Vision (CV) extraction, Robotic Process Automation (RPA), and LLM-based report generation**, as well as a Web-based **task distribution and asynchronous execution platform (B/S architecture)** suitable for batch processing and network deployments.

## ✨ Key Features

- **Multi-Modal Input Processing**: Supports direct input of FT-IR spectrum images (intelligently extracting coordinate points to CSV) as well as pre-exported CSV raw data files.
- **Image Recognition & Extraction**: Incorporates CV-based pre-processing (`pretreat.py`), spectrum curve tracking/dyeing (`curve_dye.py`), and high-precision coordinate extraction (`extract.py`).
- **Software Automation (RPA)**: Uses RPA scripts (`ir_rpa.py`) to automatically search, control the OMNIC desktop software in the background, and export analysis spectrum PDFs.
- **AI Report Generation**: Combines the extracted curve characteristics and spectrum results to automatically typeset and generate formatted PDF/HTML diagnostic reports.
- **Web Service Integration**: Provides a sleek Web interface (React + Vite) allowing any device on the local network to upload files, manage tasks, poll status, and view real-time WebSocket logs. The FastAPI + Celery backend provides high-concurrency asynchronous queue scheduling.
- **Dual Mode Support**: In addition to the Web Server mode, an intuitive GUI (`run_gui.py`) and a lightweight CLI (`pipeline.py`) are still reserved for quick local processing.

## 📂 Core Directory Structure

```text
IR-Project/
├── Client_Server/            # Web server and client components
│   ├── backend/              # FastAPI backend & Celery async task processing
│   ├── frontend/             # React + Vite frontend interface
│   └── docker-compose.yml    # Docker orchestration for API & database
├── Code/                     # Core business logic and algorithm codebase
│   ├── pipeline.py           # Core processing pipeline scaffold
│   ├── run_gui.py            # Local Tkinter graphical interface entry
│   ├── image_processing/     # Image processing & CV extraction module
│   ├── software_agent/       # OMNIC software RPA control module
│   ├── report_generator/     # Analysis report typesetting & generation module
│   └── Demo/                 # Testing & sample data
└── shared_storage/           # Shared volume for file exchange between server and worker
```

---

## 🚀 Deployment & Running Options

This project supports two running environments: **A. As a Distributed Web Service** and **B. As a Standalone Local App**.
*(Note: Regardless of the strategy, because it involves RPA, the physical host running the RPA Worker must be running a Windows desktop environment with OMNIC software installed.)*

### Option A: Web Client + Async Service (Recommended for Multi-user/Multi-task Scenarios)

The system breaks down jobs into a three-stage serial chain (`preprocess -> rpa -> postprocess`), with frontend states reflecting `queued -> preprocessing -> rpa_running -> postprocessing -> done/failed`.

**Step 1: Start the Base Service (MySQL + FastAPI)**

It is recommended to deploy via Docker:
```bash
cd Client_Server
docker compose up -d --build
```
*Tip: If required by LLMs (e.g., `OPENROUTER_API_KEY`), please configure your system environment variables on the host machine before executing `docker compose up`.*

**Step 2: Start the Local Celery Worker (Core RPA Runtime)**

This MUST be started in a native Windows environment where OMNIC is present.
```powershell
cd Client_Server\backend
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r ..\..\Code\requirements.txt

# Force single-process mode (-P solo) to avoid OMNIC UI conflicts
celery -A app.celery_app:celery_app worker --loglevel=info -P solo -Q preprocess_queue,rpa_queue,postprocess_queue
```

**Step 3: Start the Frontend**

Run the frontend instance on the same machine (or another locally networked machine):
```bash
cd Client_Server\frontend
npm install
npm run dev
```
Afterward, simply visit the frontend URL in your browser to dispatch and monitor tasks.

---

### Option B: Standalone Local App (Portable Usage Scenario)

If you only need to process single tasks on a local machine without starting a web platform.

**Environment Setup**
```bash
cd Code
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

**Using the Graphical User Interface (GUI)**
Quickly launch the processing panel with real-time log display:
```bash
python run_gui.py
```

**Using the Command Line Interface (CLI)**
```bash
# Format: python pipeline.py <Input File> [Output Directory]
python pipeline.py Demo/test_image.jpg ./output
python pipeline.py Demo/7343-3.CSV ./output
```

---

## ⚠️ Notes & Roadmap

1. The `shared_storage` directory bridges the containerized FastAPI (where uploads go) and the local Windows Celery Worker (which processes data and outputs reports). Both read and write to this relative mutual path.
2. Future plans include implementing an **authorization/account system** (to protect LAN API dispatch) and **health check monitoring** (automatically restart mechanics if an unexpected OMNIC pop-up blocks the RPA thread).
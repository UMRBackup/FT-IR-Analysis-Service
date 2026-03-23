# FT-IR AI Analysis Report Generator & Service

[English](README.md) | [简体中文](README_zh.md)

This project provides a complete, automated pipeline for Fourier Transform Infrared (FT-IR) spectroscopy: from image recognition and data processing to intelligent diagnostic report generation.
It includes the core engine for Computer Vision (CV) extraction, Robotic Process Automation (RPA), and LLM-based report generation, as well as a Web-based task distribution and asynchronous execution platform (B/S architecture) suitable for batch processing and network deployments.

## ✨ Key Features

- **Multi-Modal Input Processing**: Supports direct input of FT-IR spectrum images (testing feature) as well as pre-exported CSV raw data files (completed feature).
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

### Option A: Web Client + Async Service

The system breaks down jobs into a three-stage serial chain (`preprocess -> rpa -> postprocess`), with frontend states reflecting `queued -> preprocessing -> rpa_running -> postprocessing -> done/failed`.

Recommended production topology:

- **Container side (Linux/Docker)**: run `api + mysql + pre/post worker` for preprocessing and postprocessing.
- **Windows remote side (one or more machines)**: run `rpa worker` only for OMNIC automation.

This allows horizontal scaling of RPA workers while keeping CPU-bound pre/post stages inside containers.

**Step 1: Start Base Services (MySQL + FastAPI + pre/post worker)**

It is recommended to deploy via Docker:

```bash
cd Client_Server
docker compose up -d --build
```

*Tip: For the requirement of API Keys (Openrouter, Dashscope, CAS, SerpAPI already in use), please configure your system environment variables on the host machine or modify in compose file before executing `docker compose up`.*

**Step 2: Start RPA Workers on one or multiple Windows machines (rpa_queue only)**

This MUST run in a native Windows environment where OMNIC is installed (not inside Linux/Docker).

If the worker runs on another machine, satisfy these 4 rules first:

1. **Use the same physical shared directory**: both API host and worker machine must mount the same network share, for example as `Y:\shared_storage`.
2. **Keep drive mapping consistent when possible**:  the worker should preferably use the same drive letter as the API host to avoid path drift.
3. **DB/Broker IP configuration**: in worker-side `.env`, set `DATABASE_URL / CELERY_BROKER_URL / CELERY_RESULT_BACKEND` host to API host IP.
4. **Open firewall/network path**: worker must reach API host port `3307` (MySQL is used as DB + Celery broker/result backend).

Example mapping command on Windows (run on both machines, point to the same share):

```powershell
net use Y: \\<fileserver>\ftir_shared /persistent:yes
```

Recommended minimum `Client_Server/backend/.env` on the worker machine:

```env
CODE_ROOT=C:\path\to\IR-Project\Code
STORAGE_ROOT=Y:\shared_storage
SHARED_STORAGE_ROOT=Y:\shared_storage

DATABASE_URL=mysql+pymysql://ftir:ftir@<API_HOST_IP>:3307/ftir
CELERY_BROKER_URL=sqla+mysql+pymysql://ftir:ftir@<API_HOST_IP>:3307/ftir
CELERY_RESULT_BACKEND=db+mysql+pymysql://ftir:ftir@<API_HOST_IP>:3307/ftir
```

Then start on each Windows worker machine:

```powershell
cd Client_Server\backend
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r ..\..\Code\requirements.txt

# Force single-process mode (-P solo) to avoid OMNIC UI conflicts
celery -A app.celery_app:celery_app worker --loglevel=info -P solo -Q rpa_queue
```

> Note: On Windows, the default pool may trigger `fast_trace_task` related failures. The code already enforces `solo` on Windows, and keeping `-P solo` in command is still recommended.
>
> Scaling: start worker #2/#3/... with the same command on additional Windows machines; Celery distributes jobs across all workers subscribed to `rpa_queue`.

**Step 3: Start the Frontend**

Run the frontend instance on the same machine (or another locally networked machine):

```bash
cd Client_Server\frontend
npm install
npm run dev
```

Afterward, simply visit the frontend URL in your browser to dispatch and monitor tasks.

---

### Option B: Standalone Local App

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

1. `shared_storage` is the data bridge between API and worker. In cross-machine deployment, both sides must point to the same network share, otherwise workers may fail with missing input/output files.
2. Worker machine should also install `backend/requirements.txt`; missing requirements can break RPA stage.
3. Minimal connectivity checklist:
   - On API host, run `docker compose ps` and confirm `mysql` + `api` are healthy/running.
   - On API host, also confirm `worker_prepost` is running.
   - On worker machine, run `Test-NetConnection <API_HOST_IP> -Port 3307`.
   - After Windows worker starts, logs should show subscription to `rpa_queue`.
4. The future plan is to integrate **authorization/account system** (secure dispatch). Temporarily administration is allocated to all users for the project is still at internal test stage.

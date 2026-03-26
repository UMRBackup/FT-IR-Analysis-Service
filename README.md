# FT-IR AI Analysis Report Generator & Service

[English](README.md) | [简体中文](README_zh.md)

This repository provides a full FT-IR automation stack covering data extraction, OMNIC RPA retrieval, AI report generation, and a Web-based task dispatch platform for asynchronous execution.

The project currently supports two usage modes:

- Web client + FastAPI/Celery backend for multi-user submission and centralized deployment.
- Local GUI/CLI mode for algorithm debugging, offline verification, and single-machine troubleshooting.

## Capabilities

- Upload CSV files and images into the same asynchronous processing pipeline.
- Use a Web client with registration, login, password change, task history, live logs, report download, and task deletion.
- Run tasks through the `preprocess -> rpa -> postprocess` chain.
- Offload the OMNIC stage to Windows RPA workers while container workers handle preprocess and postprocess only.
- Store task inputs, outputs, and intermediate artifacts in shared storage.
- Keep `Code/run_gui.py` and `Code/pipeline.py` as standalone local entry points.

## Directory Layout

```text
IR-Project/
├── Client_Server/
│   ├── backend/                  # FastAPI, Celery, auth, task orchestration
│   ├── frontend/                 # React + Vite Web client
│   ├── deploy/nginx/conf.d/      # Reverse proxy and WebSocket forwarding config
│   ├── docker-compose.yml        # Internal stack (api/mysql/redis/frontend/worker_prepost)
│   └── docker-compose.proxy.yml  # Public Nginx entrypoint on port 80
├── Code/
│   ├── pipeline.py               # Local CLI pipeline
│   ├── run_gui.py                # Local Tkinter GUI
│   ├── image_processing/         # Image preprocessing and extraction
│   ├── software_agent/           # OMNIC automation
│   └── report_generator/         # Report generation
└── shared_storage/               # Shared task inputs, outputs, and artifacts
```

## Architecture

Recommended topology:

- A Linux or Docker host runs `mysql + redis + api + frontend + worker_prepost + nginx`.
- One or more Windows machines run the `rpa_queue` worker with OMNIC installed.
- The Docker host and every Windows worker access the same shared storage.

One current behavior change matters for deployment:

- `mysql`, `redis`, and `api` are now only `expose`d inside the Docker network and are no longer published directly to host ports.
- The default public entrypoint is Nginx from `docker-compose.proxy.yml`, publishing port `80`.
- If an external Windows worker must connect directly to MySQL or Redis, you need an additional reachable endpoint for those services, such as explicit port publishing, an internal proxy, or existing infrastructure. Running the default Compose stack alone does not make container-internal MySQL or Redis reachable from another machine.

## Prerequisites

### 1. Docker host

- Install Docker and Docker Compose.
- Ensure the host can access the NAS/SMB share.
- Provide the following environment variables for the CIFS volume in `Client_Server/docker-compose.yml`:

```env
NAS_HOST=192.168.1.77
NAS_SHARE=zhaozhixuan/shared_storage
NAS_USER=<your_nas_user>
NAS_PASS=<your_nas_password>
NAS_VERS=3.0
```

- In production, also set auth and bootstrap values explicitly:

```env
JWT_SECRET_KEY=<replace_with_a_long_random_secret>
JWT_PREVIOUS_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
JWT_CURRENT_KID=v1
JWT_PREVIOUS_KID=
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=<replace_immediately>
```

Notes:

- If you do not override them, the current Compose defaults are `admin` / `femtotest210` for the initial admin account. That is only acceptable for internal testing.
- Only admins can call the JWT key rotation endpoints.

### 2. Windows RPA workers

- Install OMNIC.
- Install Python, ideally matching the backend major version.
- Make sure the worker can access the same shared storage as the Docker host.
- If the worker uses a UNC path, you can provide `UNC_USERNAME` / `UNC_PASSWORD` in `Client_Server/backend/.env`. Even so, a mapped drive such as `Y:\shared_storage` is still the safer default on Windows because it avoids common session and credential conflicts.

## Recommended Deployment: Unified Web Entry

This is the deployment path that matches the current repository configuration.

### 1. Start the container-side stack

```powershell
cd Client_Server
docker compose -f docker-compose.yml -f docker-compose.proxy.yml up -d --build
```

After startup:

- Open `http://<host-ip>/` in a browser.
- Nginx forwards `/api/` and `/api/v1/tasks/<task_id>/ws` to the backend.
- The frontend build is served by the containerized frontend Nginx, so browser and API remain same-origin.

### 2. Start the Windows RPA worker

On the Windows machine:

```powershell
cd Client_Server\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r ..\..\Code\requirements.txt
```

Create or update `Client_Server/backend/.env` with at least:

```env
CODE_ROOT=C:\path\to\IR-Project\Code
STORAGE_ROOT=Y:\shared_storage
SHARED_STORAGE_ROOT=Y:\shared_storage

JWT_SECRET_KEY=<same_current_secret_as_api>
JWT_PREVIOUS_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
JWT_CURRENT_KID=v1
JWT_PREVIOUS_KID=

DATABASE_URL=mysql+pymysql://ftir:ftir@<DB_HOST>:3306/ftir
CELERY_BROKER_URL=redis://<REDIS_HOST>:6379/0
CELERY_RESULT_BACKEND=redis://<REDIS_HOST>:6379/1

INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=<same_policy_as_server>
```

Then start the worker that consumes only the RPA queue:

```powershell
celery -A app.celery_app:celery_app worker --loglevel=info -P solo -Q rpa_queue
```

Notes:

- Keep `-P solo` on Windows. This is the stable worker mode for OMNIC automation.
- You can scale horizontally by starting multiple Windows workers subscribed to `rpa_queue`.
- Worker-side JWT settings should match the active server-side key configuration.

### 3. First login and user model

The Web client now has a real account system:

- Sign in with the bootstrap admin account for the first admin session.
- Users can self-register from the frontend.
- Newly registered users are not admins.
- Username rule: 3 to 8 characters, letters, digits, underscore, and hyphen only.
- Password rule: 6 to 16 characters, no spaces, and must contain at least one letter and one digit.
- Logged-in users can change their password from the frontend.

### 4. Client workflow

After login, the normal Web workflow is:

1. Upload a `.csv` file or an image.
2. Click create-and-run.
3. Watch live WebSocket logs and task progress.
4. Use the history list to inspect, delete, or download reports.

Task statuses are:

- `queued`
- `preprocessing`
- `rpa_pending`
- `rpa_running`
- `postprocessing`
- `done`
- `failed`

Artifacts are stored under shared storage in the following structure:

```text
shared_storage/
└── tasks/<task_id>/
    ├── input/
    └── output/
```

## Development Notes

### Internal stack only

If you only want the internal containers and do not need the public reverse proxy, run:

```powershell
cd Client_Server
docker compose up -d --build
```

Be aware:

- This does not publish frontend, API, MySQL, or Redis to host ports.
- It is mainly useful for container-internal validation or when you already have another reverse proxy in front.

### Frontend local development

You can still run the Vite dev server directly:

```powershell
cd Client_Server\frontend
npm install
npm run dev
```

The frontend now includes a Vite dev proxy for `/api`, with WebSocket support enabled. By default it forwards to `http://127.0.0.1:8000`.

If your backend is reachable at a different address, add `Client_Server/frontend/.env.development` with:

```env
VITE_DEV_PROXY_TARGET=http://<your-api-host>:8000
```

This lets the frontend keep using `/api/v1` while Vite forwards requests to the configured backend target. That means:

- `npm run dev` is fine for UI work.
- For end-to-end browser testing, point `VITE_DEV_PROXY_TARGET` at your reachable backend or Nginx entrypoint.

## Standalone Local Mode

If you do not need the Web platform, run the full pipeline locally on Windows from the `Code` directory.

### GUI

```powershell
cd Code
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_gui.py
```

### CLI

```powershell
cd Code
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python pipeline.py Demo/7343-3.CSV .\output
```

The CLI creates a timestamped subdirectory under the output root and writes the report plus intermediate files there.

## Troubleshooting

### 1. The homepage loads, but task APIs or live logs fail

Check the following first:

- You are accessing the app through the unified Nginx entrypoint, not directly through the Vite dev server.
- Your reverse proxy still forwards `/api/`.
- Your reverse proxy keeps WebSocket upgrade headers for `/api/v1/tasks/.*/ws`.

### 2. The Windows worker says the shared path is not accessible

Check the following first:

- `STORAGE_ROOT` and `SHARED_STORAGE_ROOT` point to the same physical share used by the Docker host.
- The expected mapped drive, such as `Y:`, exists in the worker session.
- If you are using UNC, verify credentials and look for Windows 1219 or 1326 session conflicts.

### 3. A remote Windows worker cannot reach MySQL or Redis

Check the current config:

- The default Compose stack does not publish MySQL or Redis to the host.
- You must provide reachable endpoints such as `<DB_HOST>:3306` and `<REDIS_HOST>:6379`, then point the worker `.env` to those addresses.
- If you are still following an older document that used `3307`, that was the previous host-mapped MySQL port. The current default Compose stack uses the internal MySQL port `3306`.

### 4. The worker hits Celery pool errors on startup

Make sure the command keeps:

```powershell
-P solo
```

That is the stable Windows configuration for the OMNIC RPA worker.

## Security Recommendations

- Replace the default admin password and default JWT secret immediately.
- Do not keep example credentials or example secrets in production.
- If you expose the service outside a trusted LAN, add HTTPS, a real domain, and tighter CORS policy on top of the existing Nginx setup.
- The backend currently still uses `allow_origins=["*"]`; narrow that down for production.

# FT-IR AI Analysis Report Generator & Service (红外光谱分析与报告生成系统)

[English](README.md) | [简体中文](README_zh.md)

本项目是一套完整的自动化的红外光谱（FT-IR）图像识别、数据处理与诊断报告生成系统。
包含了底层核心的图像信息提取、RPA自动化与大模型报告生成，同时外装了基于 Web 的任务分发与异步执行平台 (B/S架构)，能够实现任务并行和云端服务。

## ✨ 主要功能特性

- **多模态输入处理**：支持直接输入红外光谱图像（功能测试中），也支持直接处理预先导出的 CSV 原始数据文件（已完善）。
- **图像识别与提取**：包含基于计算机视觉的预处理 (`pretreat.py`)、光谱曲线染色 (`curve_dye.py`) 和高精度提取 (`extract.py`)。
- **软件自动化控制 (RPA)**：通过 RPA 脚本 (`ir_rpa.py`) 在后台自动化检索、操控 OMNIC 桌面软件并导出分析图谱 PDF。
- **AI 报告生成**：结合抓取的曲线数字特征与图谱结果，自动排版并生成格式化的 PDF/HTML 诊断报告。
- **Web 服务化接入**：提供 Web 界面（React+Vite）让局域网内任意终端进行文件上传、任务管理、状态轮询和实时 WebSocket 日志查看。并由后端的 FastAPI + Celery 提供高并发的异步列队调度保护机制。
- **本地双端并行支持**：除了 Web 大厅，仍然保留本地图形化端 (`run_gui.py`) 以及用于轻量调用的命令行接口 (`pipeline.py`)。

## 📂 核心目录结构

```text
IR-Project/
├── Client_Server/            # Web 服务端与客户端目录
│   ├── backend/              # FastAPI 后端与 Celery 异步任务处理
│   ├── frontend/             # React + Vite 前端界面
│   └── docker-compose.yml    # API、数据库编排启动文件
├── Code/                     # 核心业务算法代码库
│   ├── pipeline.py           # 核心处理流水线脚手架
│   ├── run_gui.py            # 本地 Tkinter 图形界面入口
│   ├── image_processing/     # 图像处理与 CV 提取模块
│   ├── software_agent/       # OMNIC 软件 RPA 控制模块
│   ├── report_generator/     # 分析报告排版生成模块
│   └── Demo/                 # 测试与样例数据
└── shared_storage/           # 服务端与 Worker 环境交互传输的共享挂载存储区
```

---

## 🚀 启动与运行方案

本项目支持两套运行环境：**A. 作为分布式 Web 服务运行** 以及 **B. 作为本地独立软件运行**。
*(注：不论哪种方案，由于涉及 RPA 控制，运行它的物理主机/Worker机必须处于 Windows 桌面环境并安装了 OMNIC 软件)*

### 方案 A：Web 客户端与异步服务端运行

系统已被编排为三段串接任务链 (`preprocess -> rpa -> postprocess`)，前端状态机包含 `queued -> preprocessing -> rpa_running -> postprocessing -> done/failed` 等。

推荐的生产拓扑：

- **容器侧（Linux/Docker）**：运行 `api + mysql + pre/post worker`，负责预处理和后处理。
- **Windows 异机侧（可多台）**：仅运行 `rpa worker`，负责执行 OMNIC 自动化。

这样可以横向增加多台 RPA worker 提升吞吐，同时把 CPU 型预/后处理固定在容器侧。

**步骤 1：启动基础服务（MySQL + FastAPI + pre/post worker）**

通过 Docker 快速启动：

```bash
cd Client_Server
docker compose up -d --build
```

*提示：环境变量所需的 KEY (目前使用了Openrouter、Dashscope、CAS、SerpAPI），请先在宿主机的系统环境变量配置或在docker配置文件中修改后，再执行 `docker compose up`。*

**步骤 2：在一台或多台 Windows 机器启动 RPA Worker（仅消费 rpa_queue）**

必须在有 OMNIC 的 Windows 原生环境下启动（不能放在 Linux 容器中）。

如果 Worker 部署在另一台机器，请先满足下面 4 条：

1. **共享目录必须是同一份物理目录**：API 宿主机与 Worker 机器要同时挂载到同一个网络共享。
2. **共享盘符建议一致**：Worker 端和 API 宿主机建议使用同名盘符避免配置混淆。
3. **数据库地址配置**：Worker 在异机时，`DATABASE_URL / CELERY_BROKER_URL / CELERY_RESULT_BACKEND` 里的主机名要改成 API 宿主机 IP。
4. **防火墙放通端口**：至少保证 Worker 到 API 宿主机的 `3307`（MySQL 数据库）与 `6379`（Redis broker/结果后端）端口可达。

可参考 Windows 映射命令（两台机器都执行，映射到同一共享）：

```powershell
net use Y: \\<fileserver>\ftir_shared /persistent:yes
```

Worker 机器上的 `Client_Server/backend/.env` 建议至少包含：

```env
CODE_ROOT=C:\path\to\IR-Project\Code
STORAGE_ROOT=Y:\shared_storage
SHARED_STORAGE_ROOT=Y:\shared_storage

JWT_SECRET_KEY=<请替换为高强度随机密钥>
JWT_PREVIOUS_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
JWT_CURRENT_KID=v1
JWT_PREVIOUS_KID=

DATABASE_URL=mysql+pymysql://ftir:ftir@<API_HOST_IP>:3307/ftir
CELERY_BROKER_URL=redis://<API_HOST_IP>:6379/0
CELERY_RESULT_BACKEND=redis://<API_HOST_IP>:6379/1
```

双密钥在线轮换说明：

- 服务签发 token 始终使用当前密钥 (`JWT_SECRET_KEY`, `JWT_CURRENT_KID`)。
- 服务验签时会同时接受当前密钥和上一把密钥（`JWT_PREVIOUS_SECRET_KEY`）。
- 管理员可调用以下接口在线轮换（无需重启进程）：
  - `GET /api/v1/auth/key-info`
  - `POST /api/v1/auth/rotate-key`

然后在每台 Worker 启动：

```powershell
cd Client_Server\backend
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r ..\..\Code\requirements.txt

# 强制单进程模式 (-P solo) 避让 OMNIC 的界面独占与防错
celery -A app.celery_app:celery_app worker --loglevel=info -P solo -Q rpa_queue
```

> 说明：Windows 下默认进程池可能触发 `fast_trace_task` 相关报错，已在代码中对 Windows 强制 `solo`，命令中也建议保留 `-P solo`。
>
> 扩容方式：按同样配置启动第 2/3/... 台 Windows worker（都订阅 `rpa_queue`），Celery 会在这些 worker 间分发 RPA 任务，实现并行处理。

**步骤 3：启动前端与访问**

在该机器（或局域网机器）上启动前端测试：

```bash
cd Client_Server\frontend
npm install
npm run dev
```

之后只需打开浏览器访问前端地址即可进行操作。

---

### 方案 B：本地独立运行

如果只需要单机、单任务快速排查或验证算法逻辑，可以使用原生的本地运行方式。

**环境准备**

```bash
cd Code
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

**使用图形界面 (GUI)**
一键调出处理面板框，实时展示日志：

```bash
python run_gui.py
```

**使用命令行接口 (CLI)**

```bash
# 格式：python pipeline.py <输入文件> [输出目录]
python pipeline.py Demo/test_image.jpg ./output
python pipeline.py Demo/7343-3.CSV ./output
```

---

## ⚠️ 注意事项与未来计划

1. `shared_storage` 负责 API 与 Worker 的数据交换。若为跨机器部署，请统一两端指向，否则 Worker 找不到输入/输出文件。
2. Worker 也需要安装 `backend/requirements.txt`，否则可能因依赖缺失失败。
3. 最小联通性自检：
   - API 宿主机执行 `docker compose ps` 确认 `mysql` 与 `api` 运行中。
   - API 宿主机执行 `docker compose ps` 确认 `worker_prepost` 也在运行。
   - Worker 机器执行 `Test-NetConnection <API_HOST_IP> -Port 3307` 确认数据库端口可达。
   - Windows Worker 启动后日志应显示仅订阅 `rpa_queue`。
4. 计划加入 **权限控制/账户化系统**（保护分发接口安全），但目前处于内部测试阶段，暂时使用全局管理员权限。

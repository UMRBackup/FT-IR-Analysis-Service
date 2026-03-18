# FT-IR AI Analysis Report Generator & Service (红外光谱分析与报告生成系统)

本项目是一套完整的自动化的红外光谱（FT-IR）图像识别、数据处理与智能诊断报告生成系统。
不仅包含了底层核心的**CV提取、RPA自动化与大模型报告生成流水线**，还外装了一套基于 Web 的**任务分发与异步执行平台 (B/S架构)**，使得批量检测与云端/局域网联机使用成为可能。

## ✨ 主要功能特性

- **多模态输入处理**：支持直接输入红外光谱图像（智能提取曲线坐标点阵并转化为CSV），也支持直接处理预先导出的 CSV 原始数据文件。
- **图像识别与提取**：包含基于计算机视觉的预处理 (`pretreat.py`)、光谱曲线染色 (`curve_dye.py`) 和高精度提取 (`extract.py`)。
- **软件自动化控制 (RPA)**：通过 RPA 脚本 (`ir_rpa.py`) 在后台自动化检索、操控 OMNIC 桌面软件并导出分析图谱 PDF。
- **AI 报告生成**：结合抓取的曲线数字特征与图谱结果，自动排版并生成格式化的 PDF/HTML 诊断报告。
- **Web 服务化接入**：提供 Web 界面（React+Vite）让局域网内任意终端进行文件上传、任务管理、状态轮询和实时 WebSocket 日志查看。并由后端的 FastAPI + Celery 提供高并发的异步列队调度保护机制。
- **本地双端并行支持**：除了 Web 大厅，仍然保留了直观的图形化端 (`run_gui.py`) 以及用于轻量调用的命令行接口 (`pipeline.py`)。

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
*(注：不论哪种方案，由于涉及 RPA 控制，运行它的物理主机必须处于 Windows 桌面环境并安装了 OMNIC 软件)*

### 方案 A：Web 客户端与异步服务端运行 (推荐多人/多任务场景)

系统已被编排为三段串接任务链 (`preprocess -> rpa -> postprocess`)，前端状态机包含 `queued -> preprocessing -> rpa_running -> postprocessing -> done/failed` 等。

**步骤 1：启动基础服务 (MySQL + FastAPI)**

建议通过 Docker 快速启动：
```bash
cd Client_Server
docker compose up -d --build
```
*提示：如果有大模型环境变量所需的 KEY (如 `OPENROUTER_API_KEY`)，请先在宿主机的系统环境变量配置再执行 `docker compose up`。*

**步骤 2：启动本机的 Celery Worker (核心 RPA 算力挂载)**

必须在有 OMNIC 的 Windows 原生环境下启动。
```powershell
cd Client_Server\backend
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r ..\..\Code\requirements.txt

# 强制单进程模式 (-P solo) 避让 OMNIC 的界面独占与防错
celery -A app.celery_app:celery_app worker --loglevel=info -P solo -Q preprocess_queue,rpa_queue,postprocess_queue
```

**步骤 3：启动前端与访问**

在该机器（或局域网机器）上启动前端测试：
```bash
cd Client_Server\frontend
npm install
npm run dev
```
之后只需打开浏览器访问前端控制台地址即可进行在线调用与批量派发操作。

---

### 方案 B：本地独立软件运行 (便携使用场景)

如果你只需要单机、单任务快速排查或验证算法逻辑，推荐使用原生的本地运行方式。

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

## ⚠️ 须知与未来计划

1. 本地的 `shared_storage` 用于连接处于容器内的 FastAPI （用来放图）和局域网内的 Windows Celery Worker（处理图并吐出报告）。两方都读写这个相对位置以达到文件一致映射。
2. 未来计划加入 **权限控制/账户化系统**（保护局域网分发的接口安全）、**健康检查监控**（如果 OMNIC 意外弹窗导致 RPA 阻塞能及时报警重启机制）。

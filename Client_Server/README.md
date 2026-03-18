# FT-IR Client Server (MVP 起步版)

这个目录是基于现有 `Code/pipeline.py` 的服务化起步实现，目标是先打通：

- Web 前端上传文件
- 后端创建任务与执行 pipeline
- 查询任务状态
- WebSocket 推送日志

## 当前结构

- `backend/`: FastAPI 服务 + Celery 队列骨架
- `frontend/`: React + Vite Web 客户端
- `plan.md`: 你确认过的分阶段实施规划

## 已实现能力 (本次)

- 后端 API:
  - `POST /api/v1/tasks`: 上传并创建任务
  - `POST /api/v1/tasks/{task_id}/run`: 入队 Celery 任务链（异步执行）
  - `GET /api/v1/tasks/{task_id}`: 查询任务状态
  - `GET /api/v1/tasks/{task_id}/report`: 查询报告路径
  - `GET /api/v1/tasks/{task_id}/logs`: 按游标拉取日志
  - `WS /api/v1/tasks/{task_id}/ws`: 日志事件推送
- 任务状态机基础字段:
  - `queued -> preprocessing -> rpa_running -> postprocessing -> done/failed`
- Celery 队列骨架:
  - `preprocess_queue`
  - `rpa_queue`
  - `postprocess_queue`
- 任务存储:
  - MySQL 持久化任务元数据与日志（服务重启后可查询）
- 前端页面:
  - 文件上传
  - 任务触发
  - 状态刷新
  - 日志面板

## 本地运行步骤

### 1) 启动后端基础服务 (MySQL + API)

可以使用 Docker 快速拉起数据库和基础 API 服务：

```bash
# 这会启动 mysql 和 api 服务。
# 注意：worker 服务被刻意从 docker-compose 里移除了，因为 RPA 任务依赖 Windows 桌面环境（win32api 与 OMNIC）。
docker compose up -d
```

若你更新过 `backend/requirements.txt` 或 `Code/requirements.txt`，请使用重建命令避免容器继续使用旧镜像依赖：

```bash
docker compose up -d --build
```

如果你希望容器中的 pipeline 能直接读取宿主机 API Key（如 `OPENROUTER_API_KEY`、`CAS_API_KEY`、`SERP_API_KEY`），请先在宿主机设置环境变量，再执行 `docker compose up`。

PowerShell 示例：

```powershell
$env:OPENROUTER_API_KEY="your-openrouter-key"
$env:CAS_API_KEY="your-cas-key"
$env:SERP_API_KEY="your-serp-key"
docker compose up -d --build
```

说明：

- `docker-compose.yml` 已使用 `${VAR}` 方式从宿主机注入变量到 `api` 与 `worker` 容器。
- 若你更换了 Key，需要重新创建容器（如 `docker compose up -d --force-recreate`）让新变量生效。

### 共享存储机制与文件系统交互

当前本方案通过统一共享目录实现跨物理和容器架构的路径与数据一致性：

- API 侧由于部署在 Docker 中，它读取通过配置文件或相对路径存储的 `./shared_storage` 文件夹（映射挂载自 `/shared`）。
- 任何由用户在 Web 页面发送的任务图片都会被写入 `./shared_storage/tasks/<task_id>/input`。
- 本地 Windows 操作系统的 Celery Worker 监听任务队列后，直接采用相同的相对路径访问该存储目录读写文件，并通过桌面 OMNIC 实现计算最后回传 PDF 结果。
  
如果在不启动该原生 Windows Worker 的情况下发送任务，它会处于队列堵塞状态（被置为 `queued` 或由超时返回失败）。

### 2) 启动本机的 Celery Worker (必须在有 OMNIC 的原生 Windows 下运行)

由于项目的 `pipeline.py` 会引入对 `win32api` 和桌面环境内 `OMNIC` 的调用，**处理 RPA 的核心流程无法被脱离桌面的 Docker 容器容纳，必须在外部终端本机原生运行**。

在 Windows 终端（管理员）中，切换到 `backend` 目录并激活虚拟环境：

```powershell
cd backend
.venv\Scripts\activate
# 安装所有的相关依赖 (如果你还没安装)
pip install -r requirements.txt
pip install -r ..\..\Code\requirements.txt

# 为了避免在 Windows 下出现 pre-fork 失败（ValueError: not enough values to unpack...），
# 必须显式加上 `-P solo`：
celery -A app.celery_app:celery_app worker --loglevel=info -P solo -Q preprocess_queue,rpa_queue,postprocess_queue
```

注意:

- 完整链路依赖 `Code/software_agent/ir_rpa.py` 对 OMNIC 的 Windows GUI 自动化，所以请确保局域网作为服务器的这台物理电脑安装了 OMNIC 且可以通过该 Worker 控制。
- 若提示环境变量缺失，请在 `backend/.env` 中正确配置 MySQL 账号和相关大模型的各类 API Key。

### 3) 启动前端页面服务

在终端中打开前端文件夹：

```bash
cd frontend
npm install
npm run dev
```

该命令将使用 Vite 启动 Web 开发服务器。在启动成功后，不仅你自己可以通过本地浏览器访问页面，处于**同一局域网下的其他手机/电脑也能通过对应的网络 IP 访问任务大厅**（例如 `http://192.168.1.x:5173` 并自动调用此桌面的 API 来运行任务）。

## 现阶段架构与限制

- 当前 Celery 已成功将代码拆分并编排为三段串接任务链 (`preprocess -> rpa -> postprocess`)。
- **限制**: RPA 操作本质上是模拟键鼠完全独占 Windows 桌面界面的。因此必须通过 `-P solo` 单线程启动 worker 强制严格排队串行处理，多物理机并发调度尚未在系统内落地。

## 下一步建设建议

1. **权限与账号登录系统**：当前系统缺少登录页面，局域网内任意拿到地址的人皆可无视权限提交/删除任务。后续需开发 JWT/OAuth 登录并对 API 和前端路由校验。
2. **任务面板增强**：增加任务历史的分页、用户身份隔离（只看自己的任务）。
3. **监控健康检查**：增加 Windows RPA Worker心跳与状态排它锁监控，防止因为 OMNIC 意外弹窗报错导致整个执行管线死锁。

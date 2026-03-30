# FT-IR AI Analysis Report Generator & Service

[English](README.md) | [简体中文](README_zh.md)

本项目是一套面向 FT-IR 红外光谱处理的完整自动化系统，覆盖数据提取、OMNIC RPA 检索、AI 报告生成，以及基于 Web 的任务分发与异步执行平台。

当前仓库同时包含两套使用方式：

- Web 客户端 + FastAPI/Celery 服务端，适合多人并行提交与集中式部署。
- 本地 GUI/CLI 单机模式，适合算法调试、离线验证和快速排障。

## 主要能力

- 支持 CSV 与图像文件上传，统一进入异步任务链处理。
- 前端内置注册、登录、改密、任务历史、实时日志、报告下载与删除。
- 后端将任务拆分为 `preprocess -> rpa -> postprocess` 三段链路。
- RPA 阶段由安装了 OMNIC 的 Windows Worker 执行，容器侧仅负责预处理和后处理。
- 报告输出为 PDF，任务中间产物和输入输出文件统一落在任务存储根目录中。
- 保留 `Code/run_gui.py` 与 `Code/pipeline.py` 两个本地入口，便于单机运行。

## 目录结构

```text
IR-Project/
├── Client_Server/
│   ├── backend/                  # FastAPI、Celery、认证、任务调度
│   ├── frontend/                 # React + Vite Web 客户端
│   ├── deploy/nginx/conf.d/      # 反向代理与 WebSocket 转发配置
│   ├── docker-compose.yml        # 内部服务栈（api/mysql/redis/frontend/worker_prepost）
│   └── docker-compose.proxy.yml  # 对外 Nginx 入口（默认 80 端口）
├── Code/
│   ├── pipeline.py               # 本地 CLI 处理流水线
│   ├── run_gui.py                # 本地 Tkinter 图形界面
│   ├── image_processing/         # 图像预处理与提取
│   ├── software_agent/           # OMNIC 自动化控制
│   └── report_generator/         # 报告生成
└── Client_Server/shared_storage/ # 本机任务目录（运行时使用）
```

## 系统架构

推荐部署拓扑如下：

- Linux 或 Docker 宿主机运行 `mysql + redis + api + frontend + worker_prepost + nginx`。
- 一台或多台 Windows 机器运行 `rpa_queue` Worker，并安装 OMNIC。
- 当前方案是单机本地目录存储，NAS 仅用于定期备份。

## 运行前准备

### 1. 容器宿主机

- 安装 Docker 与 Docker Compose。
- 确保本机目录 `Client_Server/shared_storage` 可读写（容器会绑定到 `/shared`）。

- 生产环境同时建议提供以下密钥与管理员配置：

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

说明：

- 如果未显式覆盖，Compose 当前默认管理员用户名为 `admin`，默认密码为 `femtotest210`。这只适合内测，正式环境必须替换。
- 管理员可以访问 JWT 密钥轮换接口，普通注册用户不具备该权限。
- 仓库已提供生产模板 [Client_Server/.env.production.example](Client_Server/.env.production.example) 与密钥生成脚本 [Client_Server/scripts/generate-prod-secrets.ps1](Client_Server/scripts/generate-prod-secrets.ps1)，建议先生成随机值，再写入未提交的本地环境文件。

### 2. Windows RPA Worker

- 安装 OMNIC。
- 安装 Python，建议与服务端保持同一主版本。
- 当前默认使用本机目录存储。

## 推荐部署方式：统一 Web 入口

这是当前仓库最符合现状的启动方式。

### 1. 启动容器侧服务

```powershell
cd Client_Server
docker compose -f docker-compose.yml -f docker-compose.proxy.yml up -d --build
```

启动后：

- 浏览器访问 `http://<宿主机IP>/` 即可进入前端。
- Nginx 会将 `/api/` 与 `/api/v1/tasks/<task_id>/ws` 代理到后端。
- 前端构建产物由容器内 Nginx 提供，浏览器与 API 保持同源访问。

### 2. 启动 Windows RPA Worker

在 Windows 机器的仓库目录下执行：

```powershell
cd Client_Server\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r ..\..\Code\requirements.txt
```

创建或更新 `Client_Server/backend/.env`，至少包含：

```env
CODE_ROOT=C:\path\to\IR-Project\Code
STORAGE_ROOT=C:\path\to\IR-Project\Client_Server\shared_storage

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

然后启动只消费 RPA 队列的 Worker：

```powershell
celery -A app.celery_app:celery_app worker --loglevel=info -P solo -Q rpa_queue
```

说明：

- Windows 下必须保持 `-P solo`，否则容易出现 `fast_trace_task` 相关异常。
- 可以启动多台 Windows Worker，并全部订阅 `rpa_queue` 做横向扩容。
- Worker 与 API 共享同一 JWT 当前密钥与 key id，便于一致的登录态校验与密钥轮换。

### 3. 首次登录与用户模型

当前客户端已经启用账号体系：

- 首次可使用管理员账号登录。
- 前端支持普通用户自助注册。
- 新注册用户默认不是管理员。
- 用户名规则：3 到 8 位，仅允许字母、数字、下划线和短横杠。
- 密码规则：6 到 16 位，不能有空格，且至少包含 1 个字母和 1 个数字。
- 已登录用户可以在前端修改密码。

### 4. 客户端使用流程

登录后，Web 客户端的主要操作为：

1. 上传 `.csv` 或图像文件。
2. 点击“创建并运行任务”。
3. 查看实时 WebSocket 日志与状态进度。
4. 在“我的历史任务”中查看、删除或下载报告。

任务状态包含：

- `queued`
- `preprocessing`
- `rpa_pending`
- `rpa_running`
- `postprocessing`
- `done`
- `failed`

任务产物默认位于本机存储根目录下的如下路径：

```text
Client_Server/shared_storage/
└── tasks/<task_id>/
    ├── input/
    └── output/
```

## 开发与调试说明

### 内部服务栈

如果只想拉起内部容器，不对外暴露统一入口，可以执行：

```powershell
cd Client_Server
docker compose up -d --build
```

但要注意：

- 该方式不会自动把前端、API、MySQL、Redis 发布到宿主机端口。
- 更适合容器内部联调，或者你自己已经有额外反向代理时使用。

### 前端本地开发

前端可以单独启动 Vite：

```powershell
cd Client_Server\frontend
npm install
npm run dev
```

当前已经为 Vite 配好了 `/api` 开发代理，默认转发到 `http://127.0.0.1:8000`，并同时支持 WebSocket 日志流。

如果你的后端不在本机 `8000` 端口，可以在 `Client_Server/frontend/.env.development` 中覆盖：

```env
VITE_DEV_PROXY_TARGET=http://<your-api-host>:8000
```

这样前端继续请求 `/api/v1`，Vite 会在开发环境自动代理到目标后端。因此：

- `npm run dev` 适合做界面开发。
- 如果后端已经通过 Nginx 对外提供统一入口，也可以继续直接使用该入口地址作为代理目标。

## 本地单机模式

如果你不需要 Web 平台，只想在 Windows 本机直接跑完整流程，可以使用 `Code` 目录下的本地入口。

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

CLI 默认会在输出根目录下新建时间戳子目录，并将 PDF 与中间产物写入其中。

## 常见问题

### 1. 浏览器能打开首页，但任务接口或日志失败

优先检查：

- 是否通过 Nginx 统一入口访问，而不是直接访问前端开发服务器。
- 反向代理是否保留了 `/api/` 转发。
- 反向代理是否为 `/api/v1/tasks/.*/ws` 保留了 WebSocket Upgrade 头。

### 2. Windows Worker 提示存储目录不可访问

优先检查：

- `STORAGE_ROOT` 是否指向预期的任务根目录。
- 路径所在磁盘是否可读写。
- Windows Worker 进程是否和配置文件使用同一份路径。

### 3. 异机 Windows Worker 无法连接数据库或 Redis

容易被忽略的一点：

- 默认 Compose 没有把 MySQL 和 Redis 发布到宿主机。
- 因此你必须额外提供 `<DB_HOST>:3306` 与 `<REDIS_HOST>:6379` 的可达入口，再把 Worker 的 `.env` 指向这些地址。
- 如果你还在沿用旧文档里的 `3307`，请注意那是早期宿主机映射方案；当前默认 Compose 内部数据库端口是 `3306`。

### 4. Worker 启动后报 Celery 进程池相关错误

请确认启动命令中保留了：

```powershell
-P solo
```

这是 Windows 上运行 OMNIC RPA Worker 的稳定配置。

## 安全建议

- 立即替换默认管理员密码与默认 JWT 密钥。
- 生产环境不要继续使用文档中的示例密钥与示例账号。
- 如果启用公网访问，建议在 Nginx 基础上补齐 HTTPS、域名与更严格的 CORS 策略。
- 当前后端仍允许 `allow_origins=["*"]`，正式环境应按实际域名收紧。

## 生产环境模板与密钥生成

仓库提供了两个辅助文件：

- [Client_Server/.env.production.example](Client_Server/.env.production.example)：容器侧生产环境变量模板。
- [Client_Server/scripts/generate-prod-secrets.ps1](Client_Server/scripts/generate-prod-secrets.ps1)：生成 JWT 密钥、数据库口令、管理员初始密码的 PowerShell 脚本。

示例用法：

```powershell
cd Client_Server
pwsh .\scripts\generate-prod-secrets.ps1
```

如果需要同时生成一份本地未提交的环境文件：

```powershell
cd Client_Server
pwsh .\scripts\generate-prod-secrets.ps1 -WriteEnvFile .env.generated
```

脚本会输出一组可直接填入模板的随机值；如果使用 `-WriteEnvFile`，则会基于模板生成一个未被跟踪的本地环境文件，供 `docker compose --env-file` 或手工整理后使用。

当前 `docker-compose.yml` 已支持通过环境变量覆盖 `MYSQL_ROOT_PASSWORD`、`MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD`，并自动把对应账号口令传入 API 与容器 Worker 的 `DATABASE_URL`。

注意：`docker compose` 在变量替换时会优先读取当前 shell 里已经存在的同名环境变量，再读取 `--env-file`。如果你之前在终端里手工设置过 `JWT_SECRET_KEY`、`MYSQL_PASSWORD` 等值，正式启动前请先清理这些旧变量，或换一个干净的终端会话执行。

## 定期备份到 NAS

仓库已提供两个备份脚本：

- [Client_Server/scripts/backup-to-nas.ps1](Client_Server/scripts/backup-to-nas.ps1)：执行一次备份（MySQL + 数据目录）。
- [Client_Server/scripts/install-nas-backup-task.ps1](Client_Server/scripts/install-nas-backup-task.ps1)：安装 Windows 计划任务（按天定时执行）。

### 1. 准备配置文件

先复制示例配置：

```powershell
cd Client_Server\scripts
Copy-Item .\backup-config.example.json .\backup-config.json
```

编辑 `backup-config.json`，至少确认：

- `NasBackupRoot`：NAS 备份根目录（例如 `\\192.168.1.77\zhaozhixuan\ftir_backup`）。
- `ComposeFile`：Compose 文件路径。
- `EnvFile`：包含 `MYSQL_ROOT_PASSWORD` / `MYSQL_DATABASE` 的环境文件路径。
- `BackupSourcePaths`：需要一起备份的数据目录（默认是 `Client_Server/shared_storage`）。
- `RetentionDays`：保留天数。

### 2. 先手动跑一次备份

```powershell
cd Client_Server\scripts
pwsh .\backup-to-nas.ps1 -ConfigFile .\backup-config.json
```

每次运行会在 NAS 下生成一个时间戳目录，包含：

- `db/<database>.sql`
- `data/<source_folder>/...`
- `manifest.json`

并自动清理超出保留天数的历史备份目录。

### 3. 安装每日定时任务

```powershell
cd Client_Server\scripts
pwsh .\install-nas-backup-task.ps1 -ConfigFile .\backup-config.json -DailyAt 02:30
```

默认任务名为 `FTIR-NAS-Backup`，以 SYSTEM 账号运行。安装后可用以下命令手动触发验证：

```powershell
Start-ScheduledTask -TaskName "FTIR-NAS-Backup"
```

建议：首次部署后在任务计划程序里查看最近运行结果，确认 NAS 路径权限、Docker 访问权限与 MySQL 导出权限都正常。

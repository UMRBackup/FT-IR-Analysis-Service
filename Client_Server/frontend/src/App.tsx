import { useEffect, useMemo, useRef, useState } from "react";
import { buildWsUrl, createTask, getTask, runTask, getTasks, deleteTask, downloadReport } from "./api";
import type { LogEvent, TaskSummary } from "./types";

const MAX_VISIBLE_LOGS = 12;

function isKeyLog(log: LogEvent, previous: LogEvent | null): boolean {
  if (!previous) return true;

  const statusChanged = log.status !== previous.status;
  const progressMilestoneChanged = Math.floor(log.progress / 20) !== Math.floor(previous.progress / 20);
  const isTerminal = log.status === "done" || log.status === "failed";
  const hasImportantKeyword = /(error|failed|done|start|completed|pending)/i.test(log.message);

  return statusChanged || progressMilestoneChanged || isTerminal || hasImportantKeyword;
}

export function App() {
  const [file, setFile] = useState<File | null>(null);
  const [taskId, setTaskId] = useState("");
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [hiddenLogCount, setHiddenLogCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [historyTasks, setHistoryTasks] = useState<TaskSummary[]>([]);

  const wsRef = useRef<WebSocket | null>(null);

  const canSubmit = useMemo(() => !!file && !loading, [file, loading]);

  useEffect(() => {
    loadTasks();
    return () => {
      wsRef.current?.close();
    };
  }, []);

  async function loadTasks() {
    try {
      const data = await getTasks();
      setHistoryTasks(data);
    } catch (e) {
      console.error(e);
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("确定删除该任务吗？")) return;
    try {
      await deleteTask(id);
      loadTasks(); // 刷新列表
      if (id === taskId) {
        setTaskId("");
        setTask(null);
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  }

  useEffect(() => {
    if (!taskId) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getTask(taskId);
        setTask(latest);
        if (latest.status === "done" || latest.status === "failed") {
          wsRef.current?.close();
          window.clearInterval(timer);
        }
      } catch {
        // Keep polling resilient; detailed errors are shown on manual actions.
      }
    }, 1500);

    return () => window.clearInterval(timer);
  }, [taskId]);

  async function onSubmit() {
    if (!file) return;
    setLoading(true);
    setError("");
    setLogs([]);
    setHiddenLogCount(0);

    try {
      const created = await createTask(file);
      setTaskId(created.task_id);

      const ws = new WebSocket(buildWsUrl(created.task_id));
      ws.onmessage = (evt) => {
        const event = JSON.parse(evt.data) as LogEvent;
        setLogs((prev) => {
          const last = prev[prev.length - 1] ?? null;
          if (!isKeyLog(event, last)) {
            setHiddenLogCount((count) => count + 1);
            return prev;
          }

          const compact = [...prev, event].slice(-MAX_VISIBLE_LOGS);
          return compact;
        });
      };
      wsRef.current = ws;

      const result = await runTask(created.task_id);
      setTask(result);
      loadTasks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    if (!taskId) return;
    try {
      setError("");
      const latest = await getTask(taskId);
      setTask(latest);
    } catch (e) {
      setError(e instanceof Error ? e.message : "刷新失败");
    }
  }

  return (
    <main className="page">
      <section className="card">
        <h1>FT-IR 云端任务台</h1>
        <p>上传光谱图片或 CSV。</p>

        <label htmlFor="upload">输入文件</label>
        <input
          id="upload"
          type="file"
          accept=".csv,image/*"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />

        <div className="row">
          <button onClick={onSubmit} disabled={!canSubmit}>
            {loading ? "处理中..." : "创建并运行任务"}
          </button>
          <button onClick={onRefresh} disabled={!taskId}>
            刷新任务状态
          </button>
          {taskId ? <span className="badge">Task ID: {taskId}</span> : null}
        </div>

        {error ? <p className="error">{error}</p> : null}

        {task ? (
          <div>
            <h3>任务状态</h3>
            <div className="row">
              <span className="badge">状态: {task.status}</span>
              <span className="badge">进度: {task.progress}%</span>
            </div>
            <p>{task.message}</p>
            {task.result?.pdf ? (
              <p>
                报告路径: <code>{String(task.result.pdf)}</code>
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="logs">
          <h3>实时日志</h3>
          <p className="muted">仅展示最近 {MAX_VISIBLE_LOGS} 条。</p>
          {hiddenLogCount > 0 ? <p className="muted">已折叠 {hiddenLogCount} 条</p> : null}
          {logs.length === 0 ? <p>暂无日志</p> : null}
          {logs.map((log, idx) => (
            <div className="log-item" key={`${log.created_at}-${idx}`}>
              [{new Date(log.created_at).toLocaleTimeString()}] [{log.progress}%] {log.message}
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3>历史任务</h3>
          <button onClick={loadTasks}>刷新列表</button>
        </div>
        {historyTasks.length === 0 ? (
          <p className="muted">暂无历史任务</p>
        ) : (
          <table style={{ width: "100%", textAlign: "left", marginTop: "1rem", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #ccc" }}>
                <th>任务 ID</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {historyTasks.map((t) => (
                <tr key={t.task_id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.5rem" }}>
                    <small>...{t.task_id.slice(-8)}</small>
                  </td>
                  <td style={{ padding: "0.5rem" }}>{t.status}</td>
                  <td style={{ padding: "0.5rem", display: "flex", gap: "0.5rem" }}>
                    {t.status === "done" && (
                      <button onClick={() => downloadReport(t.task_id)}>下载报告</button>
                    )}
                    <button onClick={() => handleDelete(t.task_id)}>删除</button>
                    <button onClick={() => setTaskId(t.task_id)}>查看状态</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

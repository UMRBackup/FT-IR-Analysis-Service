import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildWsUrl,
  changePassword,
  createTask,
  deleteTask,
  downloadReport,
  getCurrentUser,
  getTask,
  getTasks,
  loginUser,
  logoutUser,
  registerUser,
  runTask,
} from "./api";
import type { LogEvent, TaskSummary, User } from "./types";

const MAX_VISIBLE_LOGS = 12;
const TOKEN_STORAGE_KEY = "ftir_access_token";
const USERNAME_PATTERN = /^[A-Za-z0-9_-]{3,8}$/;
const PASSWORD_PATTERN = /^\S{6,16}$/;

function validateUsername(value: string): string {
  if (!value) return "";
  if (!USERNAME_PATTERN.test(value)) {
    return "用户名需为 3-8 位，仅允许字母/数字/下划线/短横杠，且不能含空格";
  }
  return "";
}

function validatePassword(value: string): string {
  if (!value) return "";
  if (!PASSWORD_PATTERN.test(value)) {
    return "密码需为 6-16 位，且不能包含空格";
  }
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
    return "密码必须同时包含至少 1 个字母和 1 个数字";
  }
  return "";
}

function isKeyLog(log: LogEvent, previous: LogEvent | null): boolean {
  if (!previous) return true;

  const statusChanged = log.status !== previous.status;
  const progressMilestoneChanged = Math.floor(log.progress / 20) !== Math.floor(previous.progress / 20);
  const isTerminal = log.status === "done" || log.status === "failed";
  const hasImportantKeyword = /(error|failed|done|start|completed|pending)/i.test(log.message);

  return statusChanged || progressMilestoneChanged || isTerminal || hasImportantKeyword;
}

async function tryStoreBrowserCredential(username: string, password: string): Promise<void> {
  const win = window as Window & { PasswordCredential?: new (data: unknown) => unknown };
  const nav = navigator as Navigator & {
    credentials?: {
      store?: (credential: unknown) => Promise<unknown>;
    };
  };

  if (!win.PasswordCredential || !nav.credentials?.store) {
    return;
  }

  try {
    const credential = new win.PasswordCredential({
      id: username,
      name: username,
      password,
    });
    await nav.credentials.store(credential);
  } catch {
    // Ignore unsupported browser behavior.
  }
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

  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [authError, setAuthError] = useState("");

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const wsRef = useRef<WebSocket | null>(null);

  const usernameError = useMemo(() => validateUsername(username), [username]);
  const passwordError = useMemo(() => validatePassword(password), [password]);
  const newPasswordError = useMemo(() => validatePassword(newPassword), [newPassword]);

  const canSubmit = useMemo(() => !!file && !loading && !!token, [file, loading, token]);
  const canSubmitAuth = useMemo(() => {
    if (!username || !password) {
      return false;
    }
    if (authMode === "register") {
      return !usernameError && !passwordError;
    }
    return true;
  }, [authMode, password, passwordError, username, usernameError]);

  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!storedToken) {
      return;
    }

    setToken(storedToken);
    void bootstrap(storedToken);

    return () => {
      wsRef.current?.close();
    };
  }, []);

  async function bootstrap(accessToken: string) {
    try {
      const currentUser = await getCurrentUser(accessToken);
      setUser(currentUser);
      await loadTasks(accessToken);
    } catch {
      clearSession();
    }
  }

  async function loadTasks(accessToken = token) {
    if (!accessToken) return;
    try {
      const data = await getTasks(accessToken);
      setHistoryTasks(data);
    } catch (e) {
      console.error(e);
    }
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken("");
    setUser(null);
    setTaskId("");
    setTask(null);
    setLogs([]);
    wsRef.current?.close();
  }

  async function handleAuth() {
    setAuthError("");
    if (!username || !password) {
      setAuthError("请输入用户名和密码");
      return;
    }
    if (authMode === "register" && (usernameError || passwordError)) {
      setAuthError("请先修正账号或密码格式");
      return;
    }

    try {
      if (authMode === "register") {
        await registerUser({ username, password });
      }
      const loginResult = await loginUser({ username, password });
      setToken(loginResult.token.access_token);
      setUser(loginResult.user);
      localStorage.setItem(TOKEN_STORAGE_KEY, loginResult.token.access_token);
      await tryStoreBrowserCredential(username, password);
      await loadTasks(loginResult.token.access_token);
      setPassword("");
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : "认证失败");
    }
  }

  async function handleLogout() {
    try {
      if (token) {
        await logoutUser(token);
      }
    } catch {
      // Force clear even when backend request fails.
    }
    clearSession();
  }

  async function handleChangePassword() {
    if (!token) return;
    if (!oldPassword || !newPassword) {
      alert("请输入旧密码和新密码");
      return;
    }
    if (newPasswordError) {
      alert(newPasswordError);
      return;
    }

    try {
      await changePassword(token, {
        old_password: oldPassword,
        new_password: newPassword,
      });
      setOldPassword("");
      setNewPassword("");
      alert("密码修改成功");
    } catch (e) {
      alert(e instanceof Error ? e.message : "密码修改失败");
    }
  }

  async function handleDelete(id: string) {
    if (!token) return;
    if (!window.confirm("确定删除该任务吗？")) return;
    try {
      await deleteTask(id, token);
      await loadTasks();
      if (id === taskId) {
        setTaskId("");
        setTask(null);
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  }

  useEffect(() => {
    if (!taskId || !token) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getTask(taskId, token);
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
  }, [taskId, token]);

  async function onSubmit() {
    if (!file || !token) return;
    setLoading(true);
    setError("");
    setLogs([]);
    setHiddenLogCount(0);

    try {
      const created = await createTask(file, token);
      setTaskId(created.task_id);

      const ws = new WebSocket(buildWsUrl(created.task_id, token));
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

      const result = await runTask(created.task_id, token);
      setTask(result);
      await loadTasks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    if (!taskId || !token) return;
    try {
      setError("");
      const latest = await getTask(taskId, token);
      setTask(latest);
    } catch (e) {
      setError(e instanceof Error ? e.message : "刷新失败");
    }
  }

  async function handleDownload(taskTaskId: string) {
    if (!token) return;
    try {
      await downloadReport(taskTaskId, token);
    } catch (e) {
      alert(e instanceof Error ? e.message : "下载失败");
    }
  }

  if (!user) {
    return (
      <main className="page">
        <section className="card">
          <h1>FT-IR 云端任务台</h1>
          <p>请先登录后再使用任务功能。</p>

          <div className="row">
            <button onClick={() => setAuthMode("login")} disabled={authMode === "login"}>
              登录
            </button>
            <button onClick={() => setAuthMode("register")} disabled={authMode === "register"}>
              注册
            </button>
          </div>

          <label htmlFor="username">用户名</label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className={usernameError ? "input-invalid" : ""}
          />
          {usernameError ? <p className="field-error">{usernameError}</p> : null}

          <label htmlFor="password">密码</label>
          <input
            id="password"
            type="password"
            autoComplete={authMode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={authMode === "register" && passwordError ? "input-invalid" : ""}
          />
          {authMode === "register" && passwordError ? <p className="field-error">{passwordError}</p> : null}

          <div className="rules-box">
            <p className="rules-title">账号密码规则</p>
            <ul className="rules-list">
              <li>用户名：3-8 位，仅允许字母、数字、下划线(_)、短横杠(-)，不允许空格，不允许重名。</li>
              <li>密码：6-16 位，必须同时包含字母和数字，可含符号（如 !@#），不允许空格。</li>
            </ul>
          </div>

          <button onClick={handleAuth} disabled={!canSubmitAuth}>
            {authMode === "login" ? "登录" : "注册并登录"}
          </button>
          {authError ? <p className="error">{authError}</p> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <section className="card" style={{ marginBottom: "16px" }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <strong>当前用户：</strong>
            <span className="badge">{user.username}</span>
            {user.is_admin ? <span className="badge">管理员</span> : null}
          </div>
          <button onClick={handleLogout}>登出</button>
        </div>

        <h3 style={{ marginBottom: "8px" }}>修改密码</h3>
        <p className="muted">新密码规则：6-16 位，包含字母和数字，可含符号，不允许空格。</p>
        <div className="row">
          <input
            type="password"
            placeholder="旧密码"
            autoComplete="current-password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
          />
          <input
            type="password"
            placeholder="新密码"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className={newPasswordError ? "input-invalid" : ""}
          />
          <button onClick={handleChangePassword} disabled={!oldPassword || !newPassword || !!newPasswordError}>
            更新密码
          </button>
        </div>
        {newPasswordError ? <p className="field-error">{newPasswordError}</p> : null}
      </section>

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

      <section className="card" style={{ marginTop: "16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3>我的历史任务</h3>
          <button onClick={() => loadTasks()}>刷新列表</button>
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
                    {t.status === "done" && <button onClick={() => handleDownload(t.task_id)}>下载报告</button>}
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

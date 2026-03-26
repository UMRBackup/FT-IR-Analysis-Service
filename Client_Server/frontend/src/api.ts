import type { LoginResponse, TaskSummary, User } from "./types";

const BASE_URL = `/api/v1`;

const DETAIL_I18N_MAP: Record<string, string> = {
  "Invalid username or password": "用户名或密码错误",
  "Username already exists": "用户名已存在",
  "Old password is incorrect": "旧密码错误",
  "Authentication required": "请先登录",
  "Invalid or expired token": "登录已过期，请重新登录",
  "Invalid user in token": "登录状态无效，请重新登录",
  Forbidden: "无权限执行该操作",
  "Admin privileges required": "需要管理员权限",
  "Task not found": "任务不存在",
  "Report not ready": "报告尚未生成",
  "Task dispatch failed": "任务派发失败，请稍后重试",
  "new_secret_key must be at least 32 characters": "new_secret_key 长度至少为 32 个字符",
};

function normalizeDetail(detail: string): string {
  const mapped = DETAIL_I18N_MAP[detail.trim()];
  return mapped ?? detail;
}

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string" && data.detail.trim()) {
      return `${fallback}: ${normalizeDetail(data.detail)}`;
    }
  } catch {
    // Ignore parse failures and fallback to status code.
  }
  return `${fallback}: HTTP ${res.status}`;
}

function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
  };
}

export async function registerUser(payload: {
  username: string;
  password: string;
}): Promise<User> {
  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "注册失败"));
  }
  return res.json();
}

export async function loginUser(payload: {
  username: string;
  password: string;
}): Promise<LoginResponse> {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "登录失败"));
  }
  return res.json();
}

export async function logoutUser(token: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/auth/logout`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "登出失败"));
  }
}

export async function getCurrentUser(token: string): Promise<User> {
  const res = await fetch(`${BASE_URL}/auth/me`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "获取用户信息失败"));
  }
  return res.json();
}

export async function changePassword(
  token: string,
  payload: { old_password: string; new_password: string },
): Promise<void> {
  const res = await fetch(`${BASE_URL}/auth/change-password`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "修改密码失败"));
  }
}

export async function createTask(file: File, token: string): Promise<{ task_id: string }> {
  const body = new FormData();
  body.append("file", file);

  const res = await fetch(`${BASE_URL}/tasks`, {
    method: "POST",
    headers: authHeaders(token),
    body,
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "创建任务失败"));
  }
  return res.json();
}

export async function runTask(taskId: string, token: string): Promise<TaskSummary> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}/run`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "运行任务失败"));
  }
  return res.json();
}

export async function getTask(taskId: string, token: string): Promise<TaskSummary> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "查询任务失败"));
  }
  return res.json();
}

export async function getTasks(token: string): Promise<TaskSummary[]> {
  const res = await fetch(`${BASE_URL}/tasks`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "获取任务列表失败"));
  }
  return res.json();
}

export async function deleteTask(taskId: string, token: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "删除任务失败"));
  }
}

export async function downloadReport(taskId: string, token: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}/download`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "下载报告失败"));
  }

  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `${taskId}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export function buildWsUrl(taskId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  return `${protocol}//${host}/api/v1/tasks/${taskId}/ws`;
}

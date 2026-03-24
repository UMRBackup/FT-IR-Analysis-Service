import type { LoginResponse, TaskSummary, User } from "./types";

const BASE_URL = `http://${window.location.hostname}:8000/api/v1`;

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
    throw new Error(`注册失败: ${res.status}`);
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
    throw new Error(`登录失败: ${res.status}`);
  }
  return res.json();
}

export async function logoutUser(token: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/auth/logout`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`登出失败: ${res.status}`);
  }
}

export async function getCurrentUser(token: string): Promise<User> {
  const res = await fetch(`${BASE_URL}/auth/me`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`获取用户失败: ${res.status}`);
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
    throw new Error(`修改密码失败: ${res.status}`);
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
    throw new Error(`创建任务失败: ${res.status}`);
  }
  return res.json();
}

export async function runTask(taskId: string, token: string): Promise<TaskSummary> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}/run`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`运行任务失败: ${res.status}`);
  }
  return res.json();
}

export async function getTask(taskId: string, token: string): Promise<TaskSummary> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`查询任务失败: ${res.status}`);
  }
  return res.json();
}

export async function getTasks(token: string): Promise<TaskSummary[]> {
  const res = await fetch(`${BASE_URL}/tasks`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`获取任务列表失败: ${res.status}`);
  }
  return res.json();
}

export async function deleteTask(taskId: string, token: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`删除任务失败: ${res.status}`);
  }
}

export async function downloadReport(taskId: string, token: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}/download`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`下载报告失败: ${res.status}`);
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

export function buildWsUrl(taskId: string, token: string): string {
  return `ws://${window.location.hostname}:8000/api/v1/tasks/${taskId}/ws?token=${encodeURIComponent(token)}`;
}

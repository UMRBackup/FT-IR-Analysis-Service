import type { TaskSummary } from "./types";

const BASE_URL = `http://${window.location.hostname}:8000/api/v1`;

export async function createTask(file: File): Promise<{ task_id: string }> {
  const body = new FormData();
  body.append("file", file);

  const res = await fetch(`${BASE_URL}/tasks`, {
    method: "POST",
    body,
  });
  if (!res.ok) {
    throw new Error(`创建任务失败: ${res.status}`);
  }
  return res.json();
}

export async function runTask(taskId: string): Promise<TaskSummary> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}/run`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`运行任务失败: ${res.status}`);
  }
  return res.json();
}

export async function getTask(taskId: string): Promise<TaskSummary> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}`);
  if (!res.ok) {
    throw new Error(`查询任务失败: ${res.status}`);
  }
  return res.json();
}

export async function getTasks(): Promise<TaskSummary[]> {
  const res = await fetch(`${BASE_URL}/tasks`);
  if (!res.ok) {
    throw new Error(`获取任务列表失败: ${res.status}`);
  }
  return res.json();
}

export async function deleteTask(taskId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/tasks/${taskId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`删除任务失败: ${res.status}`);
  }
}

export function downloadReport(taskId: string): void {
  window.open(`${BASE_URL}/tasks/${taskId}/download`, "_blank");
}

export function buildWsUrl(taskId: string): string {
  return `ws://${window.location.hostname}:8000/api/v1/tasks/${taskId}/ws`;
}

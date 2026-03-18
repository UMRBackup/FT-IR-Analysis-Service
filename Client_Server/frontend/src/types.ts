export type TaskStatus =
  | "queued"
  | "preprocessing"
  | "rpa_pending"
  | "rpa_running"
  | "postprocessing"
  | "done"
  | "failed";

export interface TaskSummary {
  task_id: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  message: string;
  progress: number;
  result: Record<string, unknown>;
}

export interface LogEvent {
  task_id: string;
  status: TaskStatus;
  progress: number;
  message: string;
  created_at: string;
}

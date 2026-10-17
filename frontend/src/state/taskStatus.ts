import type { TaskStatus } from "../types/task";

/** 用户可以触发的任务操作。 */
export type TaskAction = "confirm" | "cancel";

/**
 * 允许的状态转换表。
 *
 * - `pending` → `confirmed` / `cancelled`
 * - `confirmed` 与 `cancelled` 都是**终态**：重复操作不改变状态
 *
 * 这是纯函数，不依赖 React，便于用 node:test 直接验证。
 */
const TRANSITIONS: Record<TaskStatus, Record<TaskAction, TaskStatus | null>> = {
  pending: { confirm: "confirmed", cancel: "cancelled" },
  confirmed: { confirm: null, cancel: null },
  cancelled: { confirm: null, cancel: null },
};

/** 当前状态下是否允许执行该操作。 */
export function canTransition(
  status: TaskStatus,
  action: TaskAction
): boolean {
  return TRANSITIONS[status][action] !== null;
}

/**
 * 返回操作后的状态。
 * 非法转换或重复操作一律返回原状态，保证幂等。
 */
export function transitionTaskStatus(
  status: TaskStatus,
  action: TaskAction
): TaskStatus {
  return TRANSITIONS[status][action] ?? status;
}

/** 各状态对应的中文文案。 */
export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "待确认",
  confirmed: "已确认",
  cancelled: "已取消",
};

/** 各状态下的说明文案——明确区分「已确认」与「已执行」。 */
export const TASK_STATUS_HINT: Record<TaskStatus, string> = {
  pending: "确认后仅表示你接受了这份计划，不会自动执行。",
  confirmed: "已确认。等待后端执行接口接入后才会真正开始执行。",
  cancelled: "已取消，这份计划不会再被执行。",
};


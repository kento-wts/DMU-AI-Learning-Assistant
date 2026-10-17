/**
 * Agent 任务的类型定义（模拟数据阶段）。
 *
 * 注意：这三个状态只描述**前端本地的确认流程**，不代表后端已经执行任务。
 * 任务真正执行需要等 Agent 后端接口确认并接入后再实现。
 */
export type TaskStatus = "pending" | "confirmed" | "cancelled";

/** 计划中的一个步骤。 */
export interface TaskStepPreview {
  id: string;
  title: string;
  description: string;
}

/** 一次 Agent 任务计划的预览数据。 */
export interface TaskPreviewData {
  id: string;
  title: string;
  description: string;
  steps: TaskStepPreview[];
  /** 数据来源标记：接入真实 Agent 接口前，前端只能展示模拟数据。 */
  dataSource: "mock";
}


import type { TaskPreviewData } from "../types/task";

/**
 * 模拟数据：Agent 后端接口契约尚未确认，这里只用于验证前端交互。
 * 接入真实接口后，这份数据应整体替换为接口返回值。
 */
export const mockTaskPreview: TaskPreviewData = {
  id: "mock-task-plan-001",
  title: "参加 2026 年 A 类创新创业竞赛（备赛计划）",
  description:
    "根据你的专业与年级，把参赛过程拆成四个阶段。当前为演示数据，尚未接入 Agent 后端。",
  steps: [
    {
      id: "step-1",
      title: "确认可参加的 A 类竞赛清单",
      description: "对照 2026 年竞赛列表，筛出信息科学技术学院承办的 A 类赛事。",
    },
    {
      id: "step-2",
      title: "组建队伍并联系指导教师",
      description: "确定 3-5 人团队分工，向学院科创负责老师确认报名窗口。",
    },
    {
      id: "step-3",
      title: "确定选题并完成技术验证",
      description: "选定赛道方向，用两周时间做可行性原型。",
    },
    {
      id: "step-4",
      title: "提交作品并准备答辩",
      description: "按赛事要求打磨材料，预留一周时间准备答辩演示。",
    },
  ],
  dataSource: "mock",
};


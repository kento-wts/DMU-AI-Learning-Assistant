import { useState } from "react";

import { mockTaskPreview } from "../data/mockTaskPreview";
import {
  TASK_STATUS_HINT,
  TASK_STATUS_LABEL,
  canTransition,
  transitionTaskStatus,
} from "../state/taskStatus";
import type { TaskAction } from "../state/taskStatus";
import type { TaskPreviewData, TaskStatus } from "../types/task";
import "./task-preview.css";

interface TaskPreviewCardProps {
  data?: TaskPreviewData;
  initialStatus?: TaskStatus;
}

/**
 * Agent 任务计划预览卡片。
 *
 * 与普通聊天消息的区别：独立卡片、独立标题层级，渲染在聊天区之外，
 * 不复用 `.message` 气泡样式，也不会进入 messages 数组。
 *
 * 当前不调用任何后端接口：确认/取消只改变本地状态。
 */
export default function TaskPreviewCard({
  data = mockTaskPreview,
  initialStatus = "pending",
}: TaskPreviewCardProps) {
  const [status, setStatus] = useState<TaskStatus>(initialStatus);

  const handleAction = (action: TaskAction) => {
    // transitionTaskStatus 对非法/重复操作返回原状态，天然幂等
    setStatus((current) => transitionTaskStatus(current, action));
  };

  const canConfirm = canTransition(status, "confirm");
  const canCancel = canTransition(status, "cancel");
  const titleId = `task-preview-title-${data.id}`;

  return (
    <section className="task-preview" aria-labelledby={titleId}>
      <header className="task-preview__header">
        <div className="task-preview__heading">
          <p className="task-preview__eyebrow">Agent 任务计划 · 模拟数据</p>
          <h2 className="task-preview__title" id={titleId}>
            {data.title}
          </h2>
        </div>
        <span
          className={`task-preview__status task-preview__status--${status}`}
          role="status"
          aria-live="polite"
        >
          {TASK_STATUS_LABEL[status]}
        </span>
      </header>

      <p className="task-preview__desc">{data.description}</p>

      <ol className="task-preview__steps">
        {data.steps.map((step) => (
          <li className="task-preview__step" key={step.id}>
            <h3 className="task-preview__step-title">{step.title}</h3>
            <p className="task-preview__step-desc">{step.description}</p>
          </li>
        ))}
      </ol>

      <p className="task-preview__hint">{TASK_STATUS_HINT[status]}</p>

      <div className="task-preview__actions">
        <button
          type="button"
          className="task-preview__btn task-preview__btn--primary"
          onClick={() => handleAction("confirm")}
          disabled={!canConfirm}
        >
          确认任务
        </button>
        <button
          type="button"
          className="task-preview__btn task-preview__btn--ghost"
          onClick={() => handleAction("cancel")}
          disabled={!canCancel}
        >
          取消任务
        </button>
      </div>
    </section>
  );
}


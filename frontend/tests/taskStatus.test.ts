/**
 * 零依赖测试：Node 内置测试运行器 + 原生 TypeScript 类型剥离。
 * 运行：npm test（等价于 node --test tests/taskStatus.test.ts）
 *
 * 只覆盖纯逻辑与模拟数据结构；DOM 渲染由浏览器手动验证覆盖。
 */
import assert from "node:assert/strict";
import test from "node:test";

import { mockTaskPreview } from "../src/data/mockTaskPreview.ts";
import {
  canTransition,
  transitionTaskStatus,
} from "../src/state/taskStatus.ts";
import type { TaskAction } from "../src/state/taskStatus.ts";
import type { TaskStatus } from "../src/types/task.ts";

test("待确认任务数据完整（标题/描述/步骤）", () => {
  assert.ok(mockTaskPreview.title.trim().length > 0);
  assert.ok(mockTaskPreview.description.trim().length > 0);
  assert.ok(mockTaskPreview.steps.length > 0);
  assert.equal(mockTaskPreview.dataSource, "mock");

  for (const step of mockTaskPreview.steps) {
    assert.ok(step.title.trim().length > 0, "步骤标题不能为空");
    assert.ok(step.description.trim().length > 0, "步骤描述不能为空");
  }

  const ids = mockTaskPreview.steps.map((step) => step.id);
  assert.equal(new Set(ids).size, ids.length, "步骤 id 必须唯一");
});

test("pending 状态允许确认与取消", () => {
  assert.equal(canTransition("pending", "confirm"), true);
  assert.equal(canTransition("pending", "cancel"), true);
});

test("确认后状态变为 confirmed", () => {
  assert.equal(transitionTaskStatus("pending", "confirm"), "confirmed");
});

test("取消后状态变为 cancelled", () => {
  assert.equal(transitionTaskStatus("pending", "cancel"), "cancelled");
});

test("重复确认不会重复确认（幂等）", () => {
  const confirmed = transitionTaskStatus("pending", "confirm");
  assert.equal(transitionTaskStatus(confirmed, "confirm"), "confirmed");
  assert.equal(canTransition(confirmed, "confirm"), false);
});

test("已确认的任务不能被取消", () => {
  assert.equal(transitionTaskStatus("confirmed", "cancel"), "confirmed");
  assert.equal(canTransition("confirmed", "cancel"), false);
});

test("已取消的任务不能通过确认恢复", () => {
  const cancelled = transitionTaskStatus("pending", "cancel");
  assert.equal(transitionTaskStatus(cancelled, "confirm"), "cancelled");
  assert.equal(canTransition(cancelled, "confirm"), false);
});

test("已取消的任务重复取消保持 cancelled", () => {
  assert.equal(transitionTaskStatus("cancelled", "cancel"), "cancelled");
});

test("所有状态-操作组合都符合转换表", () => {
  const expected: Record<TaskStatus, Record<TaskAction, TaskStatus>> = {
    pending: { confirm: "confirmed", cancel: "cancelled" },
    confirmed: { confirm: "confirmed", cancel: "confirmed" },
    cancelled: { confirm: "cancelled", cancel: "cancelled" },
  };

  const statuses: TaskStatus[] = ["pending", "confirmed", "cancelled"];
  const actions: TaskAction[] = ["confirm", "cancel"];

  for (const status of statuses) {
    for (const action of actions) {
      assert.equal(
        transitionTaskStatus(status, action),
        expected[status][action],
        `${status} + ${action}`
      );
    }
  }
});

test("已确认 / 已取消 都是终态（没有任何操作可以再改变）", () => {
  for (const terminal of ["confirmed", "cancelled"] as TaskStatus[]) {
    for (const action of ["confirm", "cancel"] as TaskAction[]) {
      assert.equal(canTransition(terminal, action), false);
      assert.equal(transitionTaskStatus(terminal, action), terminal);
    }
  }
});


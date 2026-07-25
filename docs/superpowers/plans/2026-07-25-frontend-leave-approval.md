# 前端 P0#3 请假审批 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前端地基与 P0#1/#2 之上实现 P0#3 请假审批前端:`/leaves` 页(Tabs:我的申请 / 待我审批 / 全部记录,按权限显隐)、新建申请 / 撤回 / 通过 / 驳回 / 详情含状态历史,并以组件级测试与浏览器实测验收。

**Architecture:** 页面内 `useState`+`useEffect` 管服务器数据(无新运行时依赖);api 层纯函数走地基统一 axios client;AntD Tabs / Table / Modal / Timeline / RangePicker 标准交互;React Testing Library 做组件级测试;验收由执行 Agent 用 chrome-devtools 驱动真实浏览器逐场景截图。

**Tech Stack:** React 18 + TS(strict) + AntD 5.29 + dayjs(antd 依赖,直接可用)+ Zustand + React Router 6 + Vitest + @testing-library/react + axios-mock-adapter

**Spec:** `docs/superpowers/specs/2026-07-25-frontend-leave-approval-design.md`(验收标准见 §8)

## Global Constraints

- 每步 TDD:先写失败测试 → 确认失败 → 实现 → 确认通过 → 提交
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- 所有 npm/npx/vitest 命令在 `frontend/` 目录下执行;git 命令在仓库根执行;Shell 为 git bash(Windows),用 Unix 语法
- 设计决策级变更必须同步 spec;实现细节修复不动 spec
- 不修改 `backend/` 下任何文件
- api 层不做 try/catch;错误信封由 `client` 拦截器统一转 `ApiError(code, message)`,页面层捕获后取 `e.message`
- 消息提示**一律 `App.useApp()` 取 message 实例**,**严禁** antd 静态 `message`(地基 spec §5;测试 render 包装已含 `<AntdApp>`)
- antd `Modal` 用 `destroyOnHidden`;编辑类表单回填用 Form `initialValues` + `key` 重挂载(**禁止** `useEffect` 里 `setFieldsValue`)
- effect 内发请求必须带 cleanup 取消标志(`let cancelled` + `return () => { cancelled = true; }`),响应到达先判 `cancelled` 再 setState(P0 终审教训:快速切换竞态串数据)
- 后端接口契约(以 `backend/app/schemas/leave.py`、`backend/app/api/v1/leaves.py` 为准,TS 类型严格对齐):
  - `POST /leaves {type, start_date, end_date, reason(1-500)}` → 201 `LeaveResponse`;type ∈ `personal|sick|annual|compensatory`
  - `POST /leaves/{id}/cancel` → `LeaveResponse`(仅本人+pending)
  - `GET /leaves/mine?status&page&page_size` → `LeaveListResponse`
  - `GET /leaves/todo?page&page_size` → `LeaveListResponse`
  - `POST /leaves/{id}/approve` → `LeaveResponse`(仅审批人)
  - `POST /leaves/{id}/reject {reason(1-500)}` → `LeaveResponse`(仅审批人)
  - `GET /leaves?department_id&status&type&start_from&end_to&page&page_size` → `LeaveListResponse`
  - `GET /leaves/{id}` → `LeaveDetailResponse`(= LeaveResponse + history)
  - `LeaveResponse{id, type, start_date, end_date, reason, status, applicant: UserBrief, approver: UserBrief, created_at}`;status ∈ `pending|approved|rejected|canceled`
  - `LeaveHistoryItem{from_status: string|null, to_status, actor: UserBrief, comment: string|null, created_at}`(history 按时间升序)
  - 权限:leave:create/list 全角色;leave:approve admin+manager;leave:list_all 仅 admin;详情 = leave:list + 数据归属(越权 403)
  - 错误:时间倒挂/无直属上级/驳回无原因 → 422;区间重叠/已终态仍操作 → 409;非本人/非审批人/越权 → 403;前端统一展示 `e.message`,不做 code 分支
- Seed 账号:admin `admin@company.com` / `Admin123!`;既有验收账号 `e2e.emp@company.com` / `NewEmp123!`(张测试2,employee,技术部)、`demo.user@company.com` / `DemoNew123!`(李演示2,employee,市场部)可复用;manager 账号(赵主管 e2e.mgr)密码未知,验收准备阶段由 admin 新建带"部门主管"角色的账号并设为张测试2的直属上级
- 本机 vite 代理需 `NODE_OPTIONS=--dns-result-order=ipv4first`
- 浏览器实测**严禁禁用 admin 账号**;chrome-devtools `fill` 对已含值输入框是追加而非替换,替换文本用 click → Control+A → `type_text`
- 日期格式:接口 `YYYY-MM-DD`(dayjs `format("YYYY-MM-DD")`);列表"日期"列渲染 `start_date ~ end_date`;时间戳渲染 `YYYY-MM-DD HH:mm`(dayjs)

---

## Task 1: 类型追加 + api/leaves.ts + utils/leave.tsx(中文映射)

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/api/leaves.ts`
- Create: `frontend/src/utils/leave.tsx`
- Test: `frontend/src/api/leaves.test.ts`
- Test: `frontend/src/utils/leave.test.ts`

**Interfaces:**
- Consumes: `client`、`ApiError`(地基 `api/client.ts`)、`UserBrief`(既有 `types/api.ts`)
- Produces(后续任务依赖):
  - 类型 `LeaveType`、`LeaveStatus`、`LeaveResponse`、`LeaveHistoryItem`、`LeaveDetailResponse`、`LeaveListResponse`
  - `createLeave(body)`、`cancelLeave(id)`、`listMine(params)`、`listTodo(params)`、`listAll(params)`、`getLeaveDetail(id)`、`approveLeave(id)`、`rejectLeave(id, reason)`
  - `LEAVE_TYPE_MAP`、`LEAVE_STATUS_MAP`(Record<string, {label, color}>)、`leaveTypeTag(type)`、`leaveStatusTag(status)`(返回 `<Tag>`)

- [ ] **Step 1: 写失败测试 `frontend/src/api/leaves.test.ts`**

```ts
import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { client } from "./client";
import {
  approveLeave,
  cancelLeave,
  createLeave,
  getLeaveDetail,
  listAll,
  listMine,
  listTodo,
  rejectLeave,
} from "./leaves";

const mock = new MockAdapter(client);

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

const leave = {
  id: "l1",
  type: "sick",
  start_date: "2026-08-01",
  end_date: "2026-08-03",
  reason: "感冒",
  status: "pending",
  applicant: { id: "u1", name: "张三" },
  approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
};
const paged = { items: [leave], total: 1, page: 1, page_size: 20 };

describe("leaves api", () => {
  it("createLeave: POST /leaves", async () => {
    mock.onPost("/leaves").reply(201, leave);
    const body = { type: "sick" as const, start_date: "2026-08-01", end_date: "2026-08-03", reason: "感冒" };
    await expect(createLeave(body)).resolves.toEqual(leave);
    expect(JSON.parse(mock.history.post[0].data)).toEqual(body);
  });

  it("cancelLeave: POST /leaves/{id}/cancel 空体", async () => {
    mock.onPost("/leaves/l1/cancel").reply(200, leave);
    await expect(cancelLeave("l1")).resolves.toEqual(leave);
  });

  it("listMine: 带 status;不带时省略", async () => {
    mock.onGet("/leaves/mine").reply(200, paged);
    await listMine({ status: "pending", page: 1, page_size: 20 });
    expect(mock.history.get[0].params).toEqual({ status: "pending", page: 1, page_size: 20 });
    await listMine({ page: 2, page_size: 20 });
    expect(mock.history.get[1].params).toEqual({ page: 2, page_size: 20 });
  });

  it("listTodo: 分页参数", async () => {
    mock.onGet("/leaves/todo").reply(200, paged);
    await listTodo({ page: 1, page_size: 20 });
    expect(mock.history.get[0].params).toEqual({ page: 1, page_size: 20 });
  });

  it("listAll: 全部筛选参数;可选参数缺省时省略", async () => {
    mock.onGet("/leaves").reply(200, paged);
    await listAll({
      department_id: "d1",
      status: "approved",
      type: "annual",
      start_from: "2026-08-01",
      end_to: "2026-08-31",
      page: 1,
      page_size: 20,
    });
    expect(mock.history.get[0].params).toEqual({
      department_id: "d1",
      status: "approved",
      type: "annual",
      start_from: "2026-08-01",
      end_to: "2026-08-31",
      page: 1,
      page_size: 20,
    });
    await listAll({ page: 1, page_size: 20 });
    expect(mock.history.get[1].params).toEqual({ page: 1, page_size: 20 });
  });

  it("getLeaveDetail: GET /leaves/{id}", async () => {
    mock.onGet("/leaves/l1").reply(200, { ...leave, history: [] });
    const resp = await getLeaveDetail("l1");
    expect(resp.history).toEqual([]);
  });

  it("approveLeave: POST /leaves/{id}/approve 空体", async () => {
    mock.onPost("/leaves/l1/approve").reply(200, leave);
    await expect(approveLeave("l1")).resolves.toEqual(leave);
  });

  it("rejectLeave: POST /leaves/{id}/reject 带 reason", async () => {
    mock.onPost("/leaves/l1/reject").reply(200, leave);
    await rejectLeave("l1", "人手不足");
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ reason: "人手不足" });
  });

  it("错误信封透传为 ApiError", async () => {
    mock.onPost("/leaves").reply(409, { error: { code: "CONFLICT", message: "时间区间重叠" } });
    await expect(
      createLeave({ type: "sick", start_date: "2026-08-01", end_date: "2026-08-03", reason: "感冒" })
    ).rejects.toMatchObject({ code: "CONFLICT", message: "时间区间重叠" });
  });
});
```

- [ ] **Step 2: 写失败测试 `frontend/src/utils/leave.test.ts`**

```ts
import { describe, expect, it } from "vitest";

import { LEAVE_STATUS_MAP, LEAVE_TYPE_MAP } from "./leave";

describe("leave maps", () => {
  it("四种类型齐全", () => {
    expect(Object.keys(LEAVE_TYPE_MAP).sort()).toEqual(["annual", "compensatory", "personal", "sick"]);
    expect(LEAVE_TYPE_MAP.personal.label).toBe("事假");
    expect(LEAVE_TYPE_MAP.sick.label).toBe("病假");
    expect(LEAVE_TYPE_MAP.annual.label).toBe("年假");
    expect(LEAVE_TYPE_MAP.compensatory.label).toBe("调休");
  });

  it("四种状态齐全", () => {
    expect(Object.keys(LEAVE_STATUS_MAP).sort()).toEqual(["approved", "canceled", "pending", "rejected"]);
    expect(LEAVE_STATUS_MAP.pending.label).toBe("待审批");
    expect(LEAVE_STATUS_MAP.approved.label).toBe("已通过");
    expect(LEAVE_STATUS_MAP.rejected.label).toBe("已驳回");
    expect(LEAVE_STATUS_MAP.canceled.label).toBe("已撤回");
  });
});
```

- [ ] **Step 3: 运行测试确认失败(import 不存在)**

```bash
cd frontend && npx vitest run src/api/leaves.test.ts src/utils/leave.test.ts
```

- [ ] **Step 4: `types/api.ts` 追加类型**

文件末尾追加:

```ts
export type LeaveType = "personal" | "sick" | "annual" | "compensatory";
export type LeaveStatus = "pending" | "approved" | "rejected" | "canceled";

export interface LeaveResponse {
  id: string;
  type: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: string;
  applicant: UserBrief;
  approver: UserBrief;
  created_at: string;
}

export interface LeaveHistoryItem {
  from_status: string | null;
  to_status: string;
  actor: UserBrief;
  comment: string | null;
  created_at: string;
}

export interface LeaveDetailResponse extends LeaveResponse {
  history: LeaveHistoryItem[];
}

export interface LeaveListResponse {
  items: LeaveResponse[];
  total: number;
  page: number;
  page_size: number;
}
```

- [ ] **Step 5: 实现 `frontend/src/api/leaves.ts`**

```ts
import { client } from "./client";
import type { LeaveDetailResponse, LeaveListResponse, LeaveResponse, LeaveType } from "../types/api";

export async function createLeave(body: {
  type: LeaveType;
  start_date: string;
  end_date: string;
  reason: string;
}): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>("/leaves", body);
  return data;
}

export async function cancelLeave(id: string): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>(`/leaves/${id}/cancel`);
  return data;
}

export async function listMine(params: {
  status?: string;
  page: number;
  page_size: number;
}): Promise<LeaveListResponse> {
  const { data } = await client.get<LeaveListResponse>("/leaves/mine", { params });
  return data;
}

export async function listTodo(params: {
  page: number;
  page_size: number;
}): Promise<LeaveListResponse> {
  const { data } = await client.get<LeaveListResponse>("/leaves/todo", { params });
  return data;
}

export async function listAll(params: {
  department_id?: string;
  status?: string;
  type?: string;
  start_from?: string;
  end_to?: string;
  page: number;
  page_size: number;
}): Promise<LeaveListResponse> {
  const { data } = await client.get<LeaveListResponse>("/leaves", { params });
  return data;
}

export async function getLeaveDetail(id: string): Promise<LeaveDetailResponse> {
  const { data } = await client.get<LeaveDetailResponse>(`/leaves/${id}`);
  return data;
}

export async function approveLeave(id: string): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>(`/leaves/${id}/approve`);
  return data;
}

export async function rejectLeave(id: string, reason: string): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>(`/leaves/${id}/reject`, { reason });
  return data;
}
```

可选参数省略:调用方组装 params 时用条件展开(如 `...(status ? { status } : {})`),与 P0#1 `listUsers` 一致;api 层原样透传。

- [ ] **Step 6: 实现 `frontend/src/utils/leave.tsx`**

```tsx
import { Tag } from "antd";

export const LEAVE_TYPE_MAP: Record<string, { label: string; color: string }> = {
  personal: { label: "事假", color: "blue" },
  sick: { label: "病假", color: "orange" },
  annual: { label: "年假", color: "green" },
  compensatory: { label: "调休", color: "purple" },
};

export const LEAVE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "待审批", color: "gold" },
  approved: { label: "已通过", color: "green" },
  rejected: { label: "已驳回", color: "red" },
  canceled: { label: "已撤回", color: "default" },
};

export function leaveTypeTag(type: string) {
  const m = LEAVE_TYPE_MAP[type] ?? { label: type, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}

export function leaveStatusTag(status: string) {
  const m = LEAVE_STATUS_MAP[status] ?? { label: status, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}
```

- [ ] **Step 7: 测试通过 + 提交**

```bash
cd frontend && npx vitest run src/api/leaves.test.ts src/utils/leave.test.ts
cd .. && git add frontend/src/types/api.ts frontend/src/api/leaves.ts frontend/src/utils/leave.tsx frontend/src/api/leaves.test.ts frontend/src/utils/leave.test.ts
git commit -m "feat(frontend): P0#3 请假审批 api 层 + 类型 + 中文映射"
```

---

## Task 2: LeaveFormModal(新建申请)

**Files:**
- Create: `frontend/src/pages/leaves/LeaveFormModal.tsx`
- Test: `frontend/src/pages/leaves/LeaveFormModal.test.tsx`

**Interfaces:**
- Consumes: `createLeave`(Task 1)、`ApiError`、`LEAVE_TYPE_MAP`(Task 1)
- Props: `{ open: boolean; onClose: () => void; onSuccess: () => void }`

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import dayjs from "dayjs";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ createLeave: vi.fn() }));

import { createLeave } from "../../api/leaves";
import { ApiError } from "../../api/client";
import LeaveFormModal from "./LeaveFormModal";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LeaveFormModal", () => {
  it("提交参数正确:日期格式化 YYYY-MM-DD", async () => {
    vi.mocked(createLeave).mockResolvedValue({} as never);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<LeaveFormModal open onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    // 选类型
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("病假"));
    // 起止日期
    const rangePicker = document.querySelector(".ant-picker") as HTMLElement;
    await user.click(rangePicker);
    const startInput = screen.getByPlaceholderText("开始日期");
    const endInput = screen.getByPlaceholderText("结束日期");
    await user.type(startInput, "2026-08-01");
    await user.type(endInput, "2026-08-03{enter}");
    await user.type(screen.getByLabelText("请假原因"), "感冒发烧");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(createLeave).toHaveBeenCalledWith({
        type: "sick",
        start_date: "2026-08-01",
        end_date: "2026-08-03",
        reason: "感冒发烧",
      })
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("校验:类型/日期/原因必填", async () => {
    render(<LeaveFormModal open onClose={() => {}} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请选择请假类型")).toBeInTheDocument();
    expect(await screen.findByText("请选择起止日期")).toBeInTheDocument();
    expect(await screen.findByText("请输入请假原因")).toBeInTheDocument();
    expect(createLeave).not.toHaveBeenCalled();
  });

  it("失败(409 区间重叠):Modal 内 Alert,不关闭", async () => {
    vi.mocked(createLeave).mockRejectedValue(new ApiError("CONFLICT", "时间区间重叠"));
    const onClose = vi.fn();
    render(<LeaveFormModal open onClose={onClose} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("病假"));
    await user.click(document.querySelector(".ant-picker") as HTMLElement);
    await user.type(screen.getByPlaceholderText("开始日期"), "2026-08-01");
    await user.type(screen.getByPlaceholderText("结束日期"), "2026-08-03{enter}");
    await user.type(screen.getByLabelText("请假原因"), "感冒");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("时间区间重叠")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

说明:RangePicker 在 jsdom 中用 placeholder 输入框键入日期是可行路径;`{enter}` 提交选择。`dayjs` import 仅备需要(如断言面板值)。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `LeaveFormModal.tsx`**

```tsx
import { useState } from "react";
import { Alert, DatePicker, Form, Input, Modal, Select } from "antd";
import type { Dayjs } from "dayjs";

import { createLeave } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveType } from "../../types/api";
import { LEAVE_TYPE_MAP } from "../../utils/leave";

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface LeaveFormValues {
  type: LeaveType;
  range: [Dayjs, Dayjs];
  reason: string;
}

export default function LeaveFormModal({ open, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<LeaveFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: LeaveFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      await createLeave({
        type: values.type,
        start_date: values.range[0].format("YYYY-MM-DD"),
        end_date: values.range[1].format("YYYY-MM-DD"),
        reason: values.reason,
      });
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="新建请假申请"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<LeaveFormValues> form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item name="type" label="请假类型" rules={[{ required: true, message: "请选择请假类型" }]}>
          <Select
            placeholder="请选择"
            options={Object.entries(LEAVE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
          />
        </Form.Item>
        <Form.Item name="range" label="起止日期" rules={[{ required: true, message: "请选择起止日期" }]}>
          <DatePicker.RangePicker style={{ width: "100%" }} placeholder={["开始日期", "结束日期"]} />
        </Form.Item>
        <Form.Item
          name="reason"
          label="请假原因"
          rules={[
            { required: true, message: "请输入请假原因" },
            { max: 500, message: "最多 500 字" },
          ]}
        >
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 4: 测试通过 + 提交**

```bash
cd frontend && npx vitest run src/pages/leaves/LeaveFormModal.test.tsx
cd .. && git add frontend/src/pages/leaves/LeaveFormModal.tsx frontend/src/pages/leaves/LeaveFormModal.test.tsx
git commit -m "feat(frontend): P0#3 新建请假申请弹窗"
```

---

## Task 3: RejectModal + LeaveDetailModal

**Files:**
- Create: `frontend/src/pages/leaves/RejectModal.tsx`
- Create: `frontend/src/pages/leaves/LeaveDetailModal.tsx`
- Test: `frontend/src/pages/leaves/RejectModal.test.tsx`
- Test: `frontend/src/pages/leaves/LeaveDetailModal.test.tsx`

**Interfaces:**
- Consumes: `rejectLeave`、`getLeaveDetail`(Task 1)、`leaveTypeTag`/`leaveStatusTag`/`LEAVE_STATUS_MAP`(Task 1)
- `RejectModal` Props: `{ leaveId: string | null; onClose: () => void; onSuccess: () => void }`
- `LeaveDetailModal` Props: `{ leaveId: string | null; onClose: () => void }`

- [ ] **Step 1: 写失败测试 `RejectModal.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ rejectLeave: vi.fn() }));

import { rejectLeave } from "../../api/leaves";
import { ApiError } from "../../api/client";
import RejectModal from "./RejectModal";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RejectModal", () => {
  it("提交:rejectLeave(id, reason),成功后 onSuccess + onClose", async () => {
    vi.mocked(rejectLeave).mockResolvedValue({} as never);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<RejectModal leaveId="l1" onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("驳回原因"), "人手不足");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(rejectLeave).toHaveBeenCalledWith("l1", "人手不足"));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("校验:原因必填", async () => {
    render(<RejectModal leaveId="l1" onClose={() => {}} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请输入驳回原因")).toBeInTheDocument();
    expect(rejectLeave).not.toHaveBeenCalled();
  });

  it("失败:Modal 内 Alert,不关闭", async () => {
    vi.mocked(rejectLeave).mockRejectedValue(new ApiError("CONFLICT", "单据已终态"));
    const onClose = vi.fn();
    render(<RejectModal leaveId="l1" onClose={onClose} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("驳回原因"), "人手不足");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("单据已终态")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 写失败测试 `LeaveDetailModal.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ getLeaveDetail: vi.fn() }));

import { getLeaveDetail } from "../../api/leaves";
import { ApiError } from "../../api/client";
import LeaveDetailModal from "./LeaveDetailModal";

const detail = {
  id: "l1",
  type: "sick",
  start_date: "2026-08-01",
  end_date: "2026-08-03",
  reason: "感冒",
  status: "rejected",
  applicant: { id: "u1", name: "张三" },
  approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
  history: [
    { from_status: null, to_status: "pending", actor: { id: "u1", name: "张三" }, comment: null, created_at: "2026-07-25T10:00:00" },
    { from_status: "pending", to_status: "rejected", actor: { id: "u2", name: "王主管" }, comment: "人手不足", created_at: "2026-07-25T11:00:00" },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LeaveDetailModal", () => {
  it("字段 + 状态历史渲染(含驳回 comment)", async () => {
    vi.mocked(getLeaveDetail).mockResolvedValue(detail);
    render(<LeaveDetailModal leaveId="l1" onClose={() => {}} />);
    expect(await screen.findByText("感冒")).toBeInTheDocument();
    expect(screen.getByText("张三")).toBeInTheDocument();
    expect(screen.getByText("王主管")).toBeInTheDocument();
    expect(screen.getByText("2026-08-01 ~ 2026-08-03")).toBeInTheDocument();
    // 历史:两行,驳回行含原因
    expect(await screen.findByText(/待审批/)).toBeInTheDocument();
    expect(screen.getByText(/已驳回/)).toBeInTheDocument();
    expect(screen.getByText(/人手不足/)).toBeInTheDocument();
  });

  it("403 越权:Modal 内 Alert", async () => {
    vi.mocked(getLeaveDetail).mockRejectedValue(new ApiError("FORBIDDEN", "无权查看该单据"));
    render(<LeaveDetailModal leaveId="l1" onClose={() => {}} />);
    expect(await screen.findByText("无权查看该单据")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: 运行确认失败**

- [ ] **Step 4: 实现 `RejectModal.tsx`**

```tsx
import { useState } from "react";
import { Alert, Form, Input, Modal } from "antd";

import { rejectLeave } from "../../api/leaves";
import { ApiError } from "../../api/client";

interface Props {
  leaveId: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RejectModal({ leaveId, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<{ reason: string }>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: { reason: string }) {
    if (!leaveId) return;
    setSubmitting(true);
    setError(null);
    try {
      await rejectLeave(leaveId, values.reason);
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="驳回申请"
      open={leaveId !== null}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item
          name="reason"
          label="驳回原因"
          rules={[
            { required: true, message: "请输入驳回原因" },
            { max: 500, message: "最多 500 字" },
          ]}
        >
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 5: 实现 `LeaveDetailModal.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Alert, Descriptions, Modal, Spin, Timeline } from "antd";
import dayjs from "dayjs";

import { getLeaveDetail } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveDetailResponse } from "../../types/api";
import { LEAVE_STATUS_MAP, leaveStatusTag, leaveTypeTag } from "../../utils/leave";

interface Props {
  leaveId: string | null;
  onClose: () => void;
}

export default function LeaveDetailModal({ leaveId, onClose }: Props) {
  const [detail, setDetail] = useState<LeaveDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!leaveId) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    setLoading(true);
    getLeaveDetail(leaveId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [leaveId]);

  return (
    <Modal title="请假详情" open={leaveId !== null} onCancel={onClose} footer={null} destroyOnHidden>
      {loading && <Spin />}
      {error && <Alert type="error" message={error} showIcon />}
      {detail && (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="类型">{leaveTypeTag(detail.type)}</Descriptions.Item>
            <Descriptions.Item label="日期">{`${detail.start_date} ~ ${detail.end_date}`}</Descriptions.Item>
            <Descriptions.Item label="原因">{detail.reason}</Descriptions.Item>
            <Descriptions.Item label="状态">{leaveStatusTag(detail.status)}</Descriptions.Item>
            <Descriptions.Item label="申请人">{detail.applicant.name}</Descriptions.Item>
            <Descriptions.Item label="审批人">{detail.approver.name}</Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {dayjs(detail.created_at).format("YYYY-MM-DD HH:mm")}
            </Descriptions.Item>
          </Descriptions>
          <Timeline
            style={{ marginTop: 16 }}
            items={detail.history.map((h) => ({
              children: `${LEAVE_STATUS_MAP[h.to_status]?.label ?? h.to_status} · ${h.actor.name} · ${dayjs(
                h.created_at
              ).format("YYYY-MM-DD HH:mm")}${h.comment ? ` — ${h.comment}` : ""}`,
            }))}
          />
        </>
      )}
    </Modal>
  );
}
```

- [ ] **Step 6: 测试通过 + 提交**

```bash
cd frontend && npx vitest run src/pages/leaves/RejectModal.test.tsx src/pages/leaves/LeaveDetailModal.test.tsx
cd .. && git add frontend/src/pages/leaves/RejectModal.tsx frontend/src/pages/leaves/RejectModal.test.tsx frontend/src/pages/leaves/LeaveDetailModal.tsx frontend/src/pages/leaves/LeaveDetailModal.test.tsx
git commit -m "feat(frontend): P0#3 驳回弹窗与请假详情弹窗(状态历史时间线)"
```

---

## Task 4: MyLeavesPanel(我的申请)

**Files:**
- Create: `frontend/src/pages/leaves/MyLeavesPanel.tsx`
- Test: `frontend/src/pages/leaves/MyLeavesPanel.test.tsx`

**Interfaces:**
- Consumes: `listMine`、`cancelLeave`(Task 1)、`leaveTypeTag`/`leaveStatusTag`/`LEAVE_STATUS_MAP`(Task 1)、`LeaveFormModal`(Task 2)、`LeaveDetailModal`(Task 3)
- 无 props;自治面板(自管数据 + 两个弹窗)

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({
  listMine: vi.fn(),
  cancelLeave: vi.fn(),
  createLeave: vi.fn(),
  getLeaveDetail: vi.fn(),
}));

import { cancelLeave, listMine } from "../../api/leaves";
import type { LeaveListResponse } from "../../types/api";
import MyLeavesPanel from "./MyLeavesPanel";

const pending = {
  id: "l1", type: "sick", start_date: "2026-08-01", end_date: "2026-08-03",
  reason: "感冒", status: "pending",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
};
const approved = { ...pending, id: "l2", status: "approved", type: "annual", reason: "回家" };

function paged(items: unknown[]): LeaveListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listMine).mockResolvedValue(paged([pending, approved]));
});

describe("MyLeavesPanel", () => {
  it("列表渲染:类型/日期/状态/审批人;pending 行有撤回,终态行无", async () => {
    render(<MyLeavesPanel />);
    expect(await screen.findByText("感冒")).toBeInTheDocument();
    expect(screen.getByText("回家")).toBeInTheDocument();
    expect(screen.getByText("2026-08-01 ~ 2026-08-03")).toBeInTheDocument();
    expect(screen.getAllByText("王主管").length).toBeGreaterThan(0);
    // 撤回按钮仅 1 个(pending 行),详情每行都有
    expect(screen.getAllByRole("button", { name: "撤回" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "详情" })).toHaveLength(2);
  });

  it("status 筛选:带参数重查并回第 1 页", async () => {
    render(<MyLeavesPanel />);
    await screen.findByText("感冒");
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("待审批"));
    await waitFor(() =>
      expect(listMine).toHaveBeenCalledWith({ status: "pending", page: 1, page_size: 20 })
    );
  });

  it("撤回:Popconfirm 确认后调 cancelLeave 并刷新", async () => {
    vi.mocked(cancelLeave).mockResolvedValue({} as never);
    render(<MyLeavesPanel />);
    await screen.findByText("感冒");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "撤回" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(cancelLeave).toHaveBeenCalledWith("l1"));
    await waitFor(() => expect(listMine).toHaveBeenCalledTimes(2));
  });

  it("新建申请:点按钮打开 LeaveFormModal", async () => {
    render(<MyLeavesPanel />);
    await screen.findByText("感冒");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "新建申请" }));
    expect(await screen.findByText("新建请假申请")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `MyLeavesPanel.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Select, Space, Table } from "antd";

import { cancelLeave, listMine } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveResponse } from "../../types/api";
import { LEAVE_STATUS_MAP, leaveStatusTag, leaveTypeTag } from "../../utils/leave";
import LeaveDetailModal from "./LeaveDetailModal";
import LeaveFormModal from "./LeaveFormModal";

const PAGE_SIZE = 20;

export default function MyLeavesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<LeaveResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  const fetchList = useCallback(async (p: number, s: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listMine({ ...(s ? { status: s } : {}), page: p, page_size: PAGE_SIZE });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listMine({ ...(status ? { status } : {}), page, page_size: PAGE_SIZE })
      .then((resp) => {
        if (cancelled) return;
        setItems(resp.items);
        setTotal(resp.total);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, status]);

  async function onCancel(l: LeaveResponse) {
    try {
      await cancelLeave(l.id);
      message.success("已撤回");
      await fetchList(page, status);
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    }
  }

  const columns = [
    { title: "类型", key: "type", render: (_: unknown, l: LeaveResponse) => leaveTypeTag(l.type) },
    { title: "日期", key: "date", render: (_: unknown, l: LeaveResponse) => `${l.start_date} ~ ${l.end_date}` },
    { title: "原因", dataIndex: "reason", key: "reason" },
    { title: "状态", key: "status", render: (_: unknown, l: LeaveResponse) => leaveStatusTag(l.status) },
    { title: "审批人", key: "approver", render: (_: unknown, l: LeaveResponse) => l.approver.name },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, l: LeaveResponse) => (
        <Space>
          {l.status === "pending" && (
            <Popconfirm title="确认撤回该申请?" onConfirm={() => void onCancel(l)}>
              <Button type="link" size="small" danger>
                撤回
              </Button>
            </Popconfirm>
          )}
          <Button type="link" size="small" onClick={() => setDetailId(l.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 140 }}
          value={status}
          onChange={(v) => {
            setPage(1);
            setStatus(v ?? null);
          }}
          options={Object.entries(LEAVE_STATUS_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Button type="primary" onClick={() => setFormOpen(true)}>
          新建申请
        </Button>
      </Space>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<LeaveResponse>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
        }}
      />
      <LeaveFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success("已提交");
          setPage(1);
          setStatus(null);
          void fetchList(1, null);
        }}
      />
      <LeaveDetailModal leaveId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
```

- [ ] **Step 4: 测试通过 + 提交**

```bash
cd frontend && npx vitest run src/pages/leaves/MyLeavesPanel.test.tsx
cd .. && git add frontend/src/pages/leaves/MyLeavesPanel.tsx frontend/src/pages/leaves/MyLeavesPanel.test.tsx
git commit -m "feat(frontend): P0#3 我的申请面板(筛选/撤回/新建入口)"
```

---

## Task 5: TodoLeavesPanel(待我审批)

**Files:**
- Create: `frontend/src/pages/leaves/TodoLeavesPanel.tsx`
- Test: `frontend/src/pages/leaves/TodoLeavesPanel.test.tsx`

**Interfaces:**
- Consumes: `listTodo`、`approveLeave`(Task 1)、`leaveTypeTag`(Task 1)、`RejectModal`、`LeaveDetailModal`(Task 3)

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({
  listTodo: vi.fn(),
  approveLeave: vi.fn(),
  rejectLeave: vi.fn(),
  getLeaveDetail: vi.fn(),
}));

import { approveLeave, listTodo } from "../../api/leaves";
import { ApiError } from "../../api/client";
import TodoLeavesPanel from "./TodoLeavesPanel";

const todo = {
  id: "l1", type: "sick", start_date: "2026-08-01", end_date: "2026-08-03",
  reason: "感冒", status: "pending",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listTodo).mockResolvedValue({ items: [todo], total: 1, page: 1, page_size: 20 });
});

describe("TodoLeavesPanel", () => {
  it("列表渲染:申请人/类型/日期/原因", async () => {
    render(<TodoLeavesPanel />);
    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(screen.getByText("感冒")).toBeInTheDocument();
    expect(screen.getByText("2026-08-01 ~ 2026-08-03")).toBeInTheDocument();
  });

  it("通过:Popconfirm 确认后调 approveLeave 并刷新", async () => {
    vi.mocked(approveLeave).mockResolvedValue({} as never);
    render(<TodoLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "通过" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(approveLeave).toHaveBeenCalledWith("l1"));
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });

  it("驳回:打开 RejectModal", async () => {
    render(<TodoLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "驳回" }));
    expect(await screen.findByText("驳回申请")).toBeInTheDocument();
  });

  it("通过 409(并发已处理):message.error 提示并刷新", async () => {
    vi.mocked(approveLeave).mockRejectedValue(new ApiError("CONFLICT", "单据已终态"));
    render(<TodoLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "通过" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    expect(await screen.findByText("单据已终态")).toBeInTheDocument();
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });
});
```

注:409 用例的 `findByText("单据已终态")` 依赖 message 渲染进 DOM(`App.useApp()` holder),测试基建已含 `<AntdApp>`。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `TodoLeavesPanel.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Space, Table } from "antd";

import { approveLeave, listTodo } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveResponse } from "../../types/api";
import { leaveTypeTag } from "../../utils/leave";
import LeaveDetailModal from "./LeaveDetailModal";
import RejectModal from "./RejectModal";

const PAGE_SIZE = 20;

export default function TodoLeavesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<LeaveResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  function fetchList(p: number) {
    setLoading(true);
    setError(null);
    return listTodo({ page: p, page_size: PAGE_SIZE })
      .then((resp) => {
        setItems(resp.items);
        setTotal(resp.total);
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listTodo({ page, page_size: PAGE_SIZE })
      .then((resp) => {
        if (cancelled) return;
        setItems(resp.items);
        setTotal(resp.total);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page]);

  function errText(e: unknown) {
    return e instanceof ApiError ? e.message : "网络异常,请稍后重试";
  }

  async function onApprove(l: LeaveResponse) {
    try {
      await approveLeave(l.id);
      message.success("已通过");
      await fetchList(page);
    } catch (e) {
      message.error(errText(e));
      await fetchList(page);
    }
  }

  const columns = [
    { title: "申请人", key: "applicant", render: (_: unknown, l: LeaveResponse) => l.applicant.name },
    { title: "类型", key: "type", render: (_: unknown, l: LeaveResponse) => leaveTypeTag(l.type) },
    { title: "日期", key: "date", render: (_: unknown, l: LeaveResponse) => `${l.start_date} ~ ${l.end_date}` },
    { title: "原因", dataIndex: "reason", key: "reason" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, l: LeaveResponse) => (
        <Space>
          <Popconfirm title="确认通过该申请?" onConfirm={() => void onApprove(l)}>
            <Button type="link" size="small">
              通过
            </Button>
          </Popconfirm>
          <Button type="link" size="small" danger onClick={() => setRejectingId(l.id)}>
            驳回
          </Button>
          <Button type="link" size="small" onClick={() => setDetailId(l.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<LeaveResponse>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
        }}
      />
      <RejectModal
        leaveId={rejectingId}
        onClose={() => setRejectingId(null)}
        onSuccess={() => {
          message.success("已驳回");
          void fetchList(page);
        }}
      />
      <LeaveDetailModal leaveId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
```

- [ ] **Step 4: 测试通过 + 提交**

```bash
cd frontend && npx vitest run src/pages/leaves/TodoLeavesPanel.test.tsx
cd .. && git add frontend/src/pages/leaves/TodoLeavesPanel.tsx frontend/src/pages/leaves/TodoLeavesPanel.test.tsx
git commit -m "feat(frontend): P0#3 待我审批面板(通过/驳回)"
```

---

## Task 6: AllLeavesPanel(全部记录,admin)

**Files:**
- Create: `frontend/src/pages/leaves/AllLeavesPanel.tsx`
- Test: `frontend/src/pages/leaves/AllLeavesPanel.test.tsx`

**Interfaces:**
- Consumes: `listAll`、`listDeptTree`(既有 `api/departments.ts`)、`toTreeSelectData`(既有 `utils/deptTree.ts`)、`leaveTypeTag`/`leaveStatusTag`/`LEAVE_TYPE_MAP`/`LEAVE_STATUS_MAP`(Task 1)、`LeaveDetailModal`(Task 3)

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ listAll: vi.fn(), getLeaveDetail: vi.fn() }));
vi.mock("../../api/departments", () => ({ listDeptTree: vi.fn() }));

import { listAll } from "../../api/leaves";
import { listDeptTree } from "../../api/departments";
import AllLeavesPanel from "./AllLeavesPanel";

const leave = {
  id: "l1", type: "sick", start_date: "2026-08-01", end_date: "2026-08-03",
  reason: "感冒", status: "pending",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listAll).mockResolvedValue({ items: [leave], total: 1, page: 1, page_size: 20 });
  vi.mocked(listDeptTree).mockResolvedValue([
    { id: "d1", name: "技术部", parent_id: null, member_count: 2, children: [] },
  ]);
});

describe("AllLeavesPanel", () => {
  it("列表渲染:申请人/类型/状态/审批人", async () => {
    render(<AllLeavesPanel />);
    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(screen.getByText("王主管")).toBeInTheDocument();
  });

  it("状态筛选:带 status 参数重查并回第 1 页", async () => {
    render(<AllLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByPlaceholderText("状态"));
    await user.click(await screen.findByTitle("已通过"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith(expect.objectContaining({ status: "approved", page: 1 }))
    );
  });

  it("部门筛选:TreeSelect 选技术部带 department_id", async () => {
    render(<AllLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByPlaceholderText("部门"));
    const treeDropdown = await screen.findByRole("tree");
    await user.click(within(treeDropdown).getByText("技术部"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith(expect.objectContaining({ department_id: "d1", page: 1 }))
    );
  });

  it("日期区间筛选:start_from/end_to 格式化", async () => {
    render(<AllLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(document.querySelector(".ant-picker") as HTMLElement);
    await user.type(screen.getByPlaceholderText("开始日期"), "2026-08-01");
    await user.type(screen.getByPlaceholderText("结束日期"), "2026-08-31{enter}");
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith(
        expect.objectContaining({ start_from: "2026-08-01", end_to: "2026-08-31", page: 1 })
      )
    );
  });
});
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `AllLeavesPanel.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Alert, Button, DatePicker, Select, Space, Table, TreeSelect } from "antd";
import type { Dayjs } from "dayjs";

import { listAll } from "../../api/leaves";
import { listDeptTree } from "../../api/departments";
import { ApiError } from "../../api/client";
import type { DepartmentNode, LeaveResponse } from "../../types/api";
import { toTreeSelectData } from "../../utils/deptTree";
import { LEAVE_STATUS_MAP, LEAVE_TYPE_MAP, leaveStatusTag, leaveTypeTag } from "../../utils/leave";
import LeaveDetailModal from "./LeaveDetailModal";

const PAGE_SIZE = 20;

interface Filters {
  department_id: string | null;
  status: string | null;
  type: string | null;
  range: [Dayjs, Dayjs] | null;
}

export default function AllLeavesPanel() {
  const [items, setItems] = useState<LeaveResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Filters>({ department_id: null, status: null, type: null, range: null });
  const [tree, setTree] = useState<DepartmentNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDeptTree()
      .then((d) => {
        if (!cancelled) setTree(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listAll({
      ...(filters.department_id ? { department_id: filters.department_id } : {}),
      ...(filters.status ? { status: filters.status } : {}),
      ...(filters.type ? { type: filters.type } : {}),
      ...(filters.range
        ? {
            start_from: filters.range[0].format("YYYY-MM-DD"),
            end_to: filters.range[1].format("YYYY-MM-DD"),
          }
        : {}),
      page,
      page_size: PAGE_SIZE,
    })
      .then((resp) => {
        if (cancelled) return;
        setItems(resp.items);
        setTotal(resp.total);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, filters]);

  function patch(p: Partial<Filters>) {
    setPage(1);
    setFilters((prev) => ({ ...prev, ...p }));
  }

  const columns = [
    { title: "申请人", key: "applicant", render: (_: unknown, l: LeaveResponse) => l.applicant.name },
    { title: "类型", key: "type", render: (_: unknown, l: LeaveResponse) => leaveTypeTag(l.type) },
    { title: "日期", key: "date", render: (_: unknown, l: LeaveResponse) => `${l.start_date} ~ ${l.end_date}` },
    { title: "状态", key: "status", render: (_: unknown, l: LeaveResponse) => leaveStatusTag(l.status) },
    { title: "审批人", key: "approver", render: (_: unknown, l: LeaveResponse) => l.approver.name },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, l: LeaveResponse) => (
        <Button type="link" size="small" onClick={() => setDetailId(l.id)}>
          详情
        </Button>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <TreeSelect
          placeholder="部门"
          allowClear
          style={{ width: 180 }}
          treeData={toTreeSelectData(tree)}
          treeDefaultExpandAll
          value={filters.department_id ?? undefined}
          onChange={(v) => patch({ department_id: (v as string) ?? null })}
        />
        <Select
          placeholder="状态"
          allowClear
          style={{ width: 130 }}
          value={filters.status ?? undefined}
          onChange={(v) => patch({ status: v ?? null })}
          options={Object.entries(LEAVE_STATUS_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Select
          placeholder="类型"
          allowClear
          style={{ width: 130 }}
          value={filters.type ?? undefined}
          onChange={(v) => patch({ type: v ?? null })}
          options={Object.entries(LEAVE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <DatePicker.RangePicker
          placeholder={["开始日期", "结束日期"]}
          value={filters.range}
          onChange={(v) => patch({ range: v })}
        />
      </Space>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<LeaveResponse>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
        }}
      />
      <LeaveDetailModal leaveId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
```

- [ ] **Step 4: 测试通过 + 提交**

```bash
cd frontend && npx vitest run src/pages/leaves/AllLeavesPanel.test.tsx
cd .. && git add frontend/src/pages/leaves/AllLeavesPanel.tsx frontend/src/pages/leaves/AllLeavesPanel.test.tsx
git commit -m "feat(frontend): P0#3 全部记录面板(部门/状态/类型/日期筛选)"
```

---

## Task 7: LeavesPage + 路由 + 菜单

**Files:**
- Create: `frontend/src/pages/leaves/LeavesPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/menu.tsx`
- Test: `frontend/src/pages/leaves/LeavesPage.test.tsx`

**Interfaces:**
- Consumes: 三个面板(Task 4/5/6)、`useAuthStore.hasPermission`(地基)、`MENU_ITEMS`(既有)

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({
  listMine: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  listTodo: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  listAll: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  cancelLeave: vi.fn(),
  createLeave: vi.fn(),
  approveLeave: vi.fn(),
  rejectLeave: vi.fn(),
  getLeaveDetail: vi.fn(),
}));
vi.mock("../../api/departments", () => ({ listDeptTree: vi.fn().mockResolvedValue([]) }));

import { useAuthStore } from "../../store/auth";
import type { CurrentUser } from "../../types/api";
import LeavesPage from "./LeavesPage";

function userWith(perms: string[]): CurrentUser {
  return {
    id: "a1", email: "a@x.com", name: "用户", is_active: true,
    roles: [], department: null, manager: null, permissions: perms,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/leaves"]}>
      <Routes>
        <Route path="/leaves" element={<LeavesPage />} />
        <Route path="/" element={<div>首页占位</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("LeavesPage", () => {
  it("无 leave:list:跳回首页", () => {
    useAuthStore.setState({ token: "t", user: userWith([]) });
    renderPage();
    expect(screen.getByText("首页占位")).toBeInTheDocument();
  });

  it("employee(仅 create+list):仅"我的申请"Tab", () => {
    useAuthStore.setState({ token: "t", user: userWith(["leave:create", "leave:list"]) });
    renderPage();
    expect(screen.getByRole("tab", { name: "我的申请" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "待我审批" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "全部记录" })).not.toBeInTheDocument();
  });

  it("manager(+approve):我的申请 + 待我审批", () => {
    useAuthStore.setState({
      token: "t",
      user: userWith(["leave:create", "leave:list", "leave:approve"]),
    });
    renderPage();
    expect(screen.getByRole("tab", { name: "我的申请" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "待我审批" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "全部记录" })).not.toBeInTheDocument();
  });

  it("admin(全权限):三个 Tab 齐全,默认激活我的申请", () => {
    useAuthStore.setState({
      token: "t",
      user: userWith(["leave:create", "leave:list", "leave:approve", "leave:list_all"]),
    });
    renderPage();
    expect(screen.getByRole("tab", { name: "我的申请" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "待我审批" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "全部记录" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "我的申请" })).toHaveAttribute("aria-selected", "true");
  });
});
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `LeavesPage.tsx`**

```tsx
import { useState } from "react";
import { Card, Tabs } from "antd";
import { Navigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import AllLeavesPanel from "./AllLeavesPanel";
import MyLeavesPanel from "./MyLeavesPanel";
import TodoLeavesPanel from "./TodoLeavesPanel";

export default function LeavesPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("leave:list");

  const tabs = [
    { key: "mine", label: "我的申请", permission: "leave:list", children: <MyLeavesPanel /> },
    { key: "todo", label: "待我审批", permission: "leave:approve", children: <TodoLeavesPanel /> },
    { key: "all", label: "全部记录", permission: "leave:list_all", children: <AllLeavesPanel /> },
  ].filter((t) => hasPermission(t.permission));

  const [activeKey, setActiveKey] = useState<string | null>(null);

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return (
    <Card title="请假审批">
      <Tabs
        activeKey={activeKey ?? tabs[0]?.key}
        onChange={setActiveKey}
        items={tabs.map(({ key, label, children }) => ({ key, label, children }))}
      />
    </Card>
  );
}
```

- [ ] **Step 4: `App.tsx` 追加路由**

import 区追加 `import LeavesPage from "./pages/leaves/LeavesPage";`,children 数组 `{ path: "departments", ... }` 之后追加:

```tsx
{ path: "leaves", element: <LeavesPage /> },
```

- [ ] **Step 5: `menu.tsx` 追加菜单**

import 区 `CalendarOutlined` 加入 `@ant-design/icons` 导入,`MENU_ITEMS` 末尾追加:

```tsx
{ key: "/leaves", label: "请假审批", icon: <CalendarOutlined />, permission: "leave:list" },
```

- [ ] **Step 6: 测试通过 + 提交**

```bash
cd frontend && npx vitest run src/pages/leaves/LeavesPage.test.tsx
cd .. && git add frontend/src/pages/leaves/LeavesPage.tsx frontend/src/pages/leaves/LeavesPage.test.tsx frontend/src/App.tsx frontend/src/components/menu.tsx
git commit -m "feat(frontend): P0#3 请假审批页 Tabs 容器 + 路由 + 菜单"
```

---

## Task 8: 全量验收(自动化门禁 + 浏览器实测)

**Files:**
- 不新增源码;按需勾选 spec §8 验收标准

- [ ] **Step 1: 自动化门禁**

```bash
cd frontend && npx vitest run && npx tsc --noEmit && npx vite build
```

要求:既有 92 + 本期新增全部通过;tsc 零错误;build 成功。

- [ ] **Step 2: 启动环境**

- `docker compose up -d db`(若未运行)
- 后端 uvicorn :8000(若未运行)
- `NODE_OPTIONS=--dns-result-order=ipv4first npx vite`(frontend/,:5173)

- [ ] **Step 3: 验收准备(admin)**

1. admin `admin@company.com` / `Admin123!` 登录
2. 新建 manager 账号:`leave.mgr@company.com` / `LeaveMgr123!`,角色"部门主管",归属设为技术部
3. 张测试2(e2e.emp)归属:部门=技术部,直属上级=leave.mgr 账号(若已是其他上级,改为此账号)

- [ ] **Step 4: employee 场景(e2e.emp@company.com / NewEmp123!)**

1. 登录:菜单有"请假审批";页内仅"我的申请"Tab → 截图
2. 新建申请:病假 2026-08-03 ~ 2026-08-05,原因"感冒" → 成功 toast,列表出现 pending 单(审批人=新 manager)→ 截图
3. 新建重叠申请:病假 2026-08-04 ~ 2026-08-06 → Modal 内 Alert"时间区间重叠"类 409 提示 → 截图
4. 撤回该 pending 单 → toast + 状态变"已撤回";终态行无撤回按钮 → 截图

- [ ] **Step 5: manager 场景(leave.mgr@company.com / LeaveMgr123!)**

1. 登录:有"待我审批"Tab,无"全部记录"Tab → 截图
2. employee 再提交一单(年假 2026-08-10 ~ 2026-08-12,"回家")→ manager 待我审批可见
3. 驳回该单,填原因"项目排期紧张" → toast + 列表该单消失 → 截图
4. employee 再提交一单(事假 2026-08-20 ~ 2026-08-21,"办事")→ manager 通过 → toast → 截图

- [ ] **Step 6: 详情与留痕(任意账号,用被驳回单)**

打开被驳回单详情:字段齐全;Timeline 两行(创建 → 已驳回),驳回行含原因"项目排期紧张" → 截图

- [ ] **Step 7: admin 全部记录**

1. "全部记录"Tab:可见全部单 → 截图
2. 状态筛选"已驳回":仅剩被驳回单 → 截图
3. 部门筛选"技术部":均生效
4. 打开详情:可看任意单 → 截图

- [ ] **Step 8: 勾选 spec §8 + 提交**

勾选 `docs/superpowers/specs/2026-07-25-frontend-leave-approval-design.md` §8 已完成项(浏览器实测证据截图存 `.superpowers/sdd/acceptance/`,gitignored)。

```bash
git add docs/superpowers/specs/2026-07-25-frontend-leave-approval-design.md
git commit -m "test(frontend): P0#3 请假审批前端全量验收通过,勾选 spec 验收标准"
```

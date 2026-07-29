# 报销审批(前端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现报销审批前端:`/expenses` 三 Tab 页面(我的申请/待我审批/全部记录)、新建报销(multipart 附件)、详情弹窗(二级审批状态展示 + 附件鉴权下载)、审批操作,以及消息中心 `ref_type="expense"` 通知点击跳转联动;前置一处后端附加改动(ExpenseResponse 补姓名对象)。

**Architecture:** 纯镜像请假前端模块(`pages/expenses/` 下 1:1 同构新建,不改请假模块任何文件);页面本地态管列表,无新 store;通知模块与报销模块仅靠路由 state(`openExpenseId`)耦合。后端改动仅响应 schema 加字段,ORM 关系与 selectin 加载已存在,零服务层改动。

**Tech Stack:** 后端 FastAPI + pydantic v2 + pytest;前端 React 18 + antd 5 + zustand 4 + react-router 6 + axios;vitest + Testing Library + axios-mock-adapter。

## Global Constraints

- 工作分支:`feature/frontend-expense`(已在此分支,不切分支;分支已含合并后的通知前端代码)
- **顺序约束(用户明确要求):先完成 Task 1(后端)并全量 pytest 通过,再开始任何前端任务**
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- Commit message:中文 Conventional Commits(参照 git log 现有风格,如 `feat(frontend): ...`)
- 设计依据:`docs/superpowers/specs/2026-07-29-frontend-expense-approval-design.md`,实现必须与 spec 一致
- Spec 同步:Task 1 同步后端 spec §6;Task 9 同步通知前端 spec §6(设计决策级变更)
- 不引入新前端依赖;不改动请假模块(`frontend/src/pages/leaves/`、`frontend/src/utils/leave.tsx`、`frontend/src/api/leaves.ts`)任何文件
- 测试命令工作目录:前端 `frontend/`:`npx vitest run <file>`(单文件)/ `npm test`(全量);后端 `backend/`:`python -m pytest tests/<file> -q`。本机无 `uv`,若 `python` 不在 PATH 用 `/d/Application/anaconda3/python -m pytest`
- 本机 localhost IPv6 坑:后端连库/ vite 代理若挂起,主机名改 `127.0.0.1` 或 `NODE_OPTIONS=--dns-result-order=ipv4first`
- 金额 `amount` 在后端 JSON 中为字符串(pydantic Decimal 序列化),前端类型定义为 `string`,展示 `¥{amount}`,提交 `toFixed(2)`,全程不做浮点转换
- 验收截图必须存持久目录 `.superpowers/sdd/acceptance/`(`exp-` 前缀),**禁止**放在 SDD workspace(会随清理被删)

---

### Task 1: 后端 ExpenseResponse 补 applicant/approver 姓名对象

**Files:**
- Modify: `backend/app/schemas/expense.py`(ExpenseResponse 类)
- Modify: `backend/tests/test_expenses_api.py:101-110`(一处断言改写 + 补申请人断言)
- Modify: `backend/tests/test_expense_notifications.py:140`(一处断言改写)
- Modify: `docs/superpowers/specs/2026-07-28-expense-approval-design.md`(§6 设计细则响应形状行)

**Interfaces:**
- Consumes: 既有 ORM 关系 `ExpenseRequest.applicant` / `.approver`(`lazy="selectin"`,`backend/app/models/expense.py:32-36`,已随查询加载);既有 `UserBrief{id, name}`(`backend/app/schemas/user.py:15-19`,expense.py schema 已 import)
- Produces: `ExpenseResponse` JSON 形状变为 `{id, type, amount, reason, status, applicant: {id, name}, approver: {id, name} | null, created_at, updated_at}`——Task 2 前端类型按此定义;`ExpenseDetailResponse` 随之继承

- [ ] **Step 1: Write the failing tests**

修改 `backend/tests/test_expenses_api.py` 的 `test_create_201_and_file_on_disk`(当前 101-110 行区域):

```python
async def test_create_201_and_file_on_disk(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    emp, emp_h = await make_employee_client(db, client, mgr)

    resp = await submit(client, emp_h)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending_l1"
    assert body["applicant"] == {"id": str(emp.id), "name": emp.name}
    assert body["approver"] == {"id": str(mgr.id), "name": mgr.name}
    assert float(body["amount"]) == 1999.5
```

(变化:① `_, emp_h` 改为 `emp, emp_h`;② `assert body["approver_id"] == str(mgr.id)` 替换为上面两行 applicant/approver 断言;其余行不动。)

修改 `backend/tests/test_expense_notifications.py:140`:

```python
    assert resp.json()["approver"] is None
```

(原行 `assert resp.json()["approver_id"] is None` 整行替换,上下文是 `test_large_amount_two_level_chain` 中转 pending_l2 的断言。)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_expenses_api.py::test_create_201_and_file_on_disk tests/test_expense_notifications.py::test_large_amount_two_level_chain -q`
Expected: FAIL(KeyError: 'applicant' / 'approver')

- [ ] **Step 3: Modify the schema**

`backend/app/schemas/expense.py` 的 `ExpenseResponse` 类,把

```python
    applicant_id: uuid.UUID
    approver_id: uuid.UUID | None
```

两行替换为:

```python
    applicant: UserBrief
    approver: UserBrief | None
```

(`UserBrief` 已在该文件 import——`ExpenseHistoryItem.actor` 在用;`uuid` import 仍被 `id` 字段使用,不删。)

- [ ] **Step 4: Run expense tests + full backend suite**

Run: `cd backend && python -m pytest tests/ -k expense -q`
Expected: 全部 PASS(含 model/repository/service/api/notifications 五个 expense 测试文件;ORM 层 `applicant_id` 列未动,工厂与属性断言不受影响)

Run: `cd backend && python -m pytest tests/ -q`
Expected: 全量 PASS,无回归

- [ ] **Step 5: Sync backend spec §6**

`docs/superpowers/specs/2026-07-28-expense-approval-design.md` §6 设计细则中该行:

```
- `ExpenseResponse{id, type, amount, reason, status, applicant_id, approver_id, created_at, updated_at}`;`ExpenseDetailResponse` 加 `history[]`(含 actor 姓名)与 `attachments[]`(id/filename/content_type/size_bytes,不含 stored_path)
```

改为:

```
- `ExpenseResponse{id, type, amount, reason, status, applicant: UserBrief, approver: UserBrief | null, created_at, updated_at}`(applicant/approver 为 `{id, name}` 姓名对象,对齐 LeaveResponse;pending_l2 权限池时 approver 为 null);`ExpenseDetailResponse` 加 `history[]`(含 actor 姓名)与 `attachments[]`(id/filename/content_type/size_bytes,不含 stored_path)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/expense.py backend/tests/test_expenses_api.py backend/tests/test_expense_notifications.py docs/superpowers/specs/2026-07-28-expense-approval-design.md
git commit -m "feat(backend): ExpenseResponse 补 applicant/approver 姓名对象对齐 LeaveResponse"
```

---

### Task 2: 前端类型 + 报销 api 层

**Files:**
- Modify: `frontend/src/types/api.ts`(文件末尾追加)
- Create: `frontend/src/api/expenses.ts`
- Test: `frontend/src/api/expenses.test.ts`

**Interfaces:**
- Consumes: 既有 `client` / `ApiError`(`frontend/src/api/client.ts`);既有 `UserBrief` 类型
- Produces: 类型 `ExpenseType` / `ExpenseStatus` / `ExpenseItem` / `ExpenseHistoryItem` / `ExpenseAttachment` / `ExpenseDetail` / `ExpenseListResponse`;函数 `createExpense(form: FormData): Promise<ExpenseItem>` / `listMine({status?, type?, page, page_size})` / `listTodo({page, page_size})` / `listAll({department_id?, status?, type?, start_from?, end_to?, page, page_size})` / `getExpenseDetail(id): Promise<ExpenseDetail>` / `downloadAttachment(expenseId, attachmentId): Promise<Blob>` / `cancelExpense(id)` / `approveExpense(id)` / `rejectExpense(id, reason)`——Task 3-8 全部消费这些签名

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/api/expenses.test.ts`:

```tsx
import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { client } from "./client";
import {
  approveExpense,
  cancelExpense,
  createExpense,
  downloadAttachment,
  getExpenseDetail,
  listAll,
  listMine,
  listTodo,
  rejectExpense,
} from "./expenses";

const mock = new MockAdapter(client);

const item = {
  id: "e1",
  type: "travel",
  amount: "1999.50",
  reason: "出差打车",
  status: "pending_l1",
  applicant: { id: "u1", name: "张三" },
  approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00",
  updated_at: "2026-07-29T09:00:00",
};

const paged = { items: [item], total: 1, page: 1, page_size: 20 };

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

describe("createExpense", () => {
  it("POST /expenses multipart FormData 原样透传", async () => {
    mock.onPost("/expenses").reply(201, item);
    const fd = new FormData();
    fd.append("type", "travel");
    fd.append("amount", "1999.50");
    fd.append("reason", "出差打车");
    fd.append("files", new File(["x"], "a.png", { type: "image/png" }));
    const resp = await createExpense(fd);
    expect(resp.id).toBe("e1");
    const sent = mock.history.post[0].data as FormData;
    expect(sent).toBeInstanceOf(FormData);
    expect(sent.get("type")).toBe("travel");
    expect(sent.get("amount")).toBe("1999.50");
    expect((sent.get("files") as File).name).toBe("a.png");
  });
});

describe("listMine", () => {
  it("status/type 过滤透传", async () => {
    mock.onGet("/expenses/mine").reply(200, paged);
    const resp = await listMine({ status: "pending_l1", type: "travel", page: 2, page_size: 20 });
    expect(resp.items).toHaveLength(1);
    expect(mock.history.get[0].params).toEqual({ status: "pending_l1", type: "travel", page: 2, page_size: 20 });
  });
});

describe("listTodo", () => {
  it("GET /expenses/todo", async () => {
    mock.onGet("/expenses/todo").reply(200, paged);
    await listTodo({ page: 1, page_size: 20 });
    expect(mock.history.get[0].params).toEqual({ page: 1, page_size: 20 });
  });
});

describe("listAll", () => {
  it("部门/状态/类型/时间过滤透传", async () => {
    mock.onGet("/expenses").reply(200, paged);
    await listAll({ department_id: "d1", status: "approved", type: "office", start_from: "2026-07-01", end_to: "2026-07-31", page: 1, page_size: 20 });
    expect(mock.history.get[0].params).toEqual({
      department_id: "d1", status: "approved", type: "office",
      start_from: "2026-07-01", end_to: "2026-07-31", page: 1, page_size: 20,
    });
  });
});

describe("getExpenseDetail", () => {
  it("GET /expenses/{id} 返回 history + attachments", async () => {
    mock.onGet("/expenses/e1").reply(200, { ...item, history: [], attachments: [{ id: "a1", filename: "a.png", content_type: "image/png", size_bytes: 100, created_at: "2026-07-29T09:00:00" }] });
    const resp = await getExpenseDetail("e1");
    expect(resp.attachments[0].filename).toBe("a.png");
  });
});

describe("downloadAttachment", () => {
  it("GET 附件 blob", async () => {
    mock.onGet("/expenses/e1/attachments/a1").reply(200, new Blob(["x"]));
    const blob = await downloadAttachment("e1", "a1");
    expect(blob).toBeInstanceOf(Blob);
    expect(mock.history.get[0].responseType).toBe("blob");
  });
});

describe("cancelExpense / approveExpense / rejectExpense", () => {
  it("cancel", async () => {
    mock.onPost("/expenses/e1/cancel").reply(200, { ...item, status: "cancelled" });
    expect((await cancelExpense("e1")).status).toBe("cancelled");
  });
  it("approve", async () => {
    mock.onPost("/expenses/e1/approve").reply(200, { ...item, status: "approved" });
    expect((await approveExpense("e1")).status).toBe("approved");
  });
  it("reject 带 reason body", async () => {
    mock.onPost("/expenses/e1/reject").reply(200, { ...item, status: "rejected" });
    await rejectExpense("e1", "发票不清");
    expect(JSON.parse(mock.history.post[0].data as string)).toEqual({ reason: "发票不清" });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/api/expenses.test.ts`
Expected: FAIL,`Failed to resolve import "./expenses"`

- [ ] **Step 3: Write types + api**

修改 `frontend/src/types/api.ts`,文件末尾追加:

```ts
export type ExpenseType = "travel" | "office" | "entertainment" | "transport" | "other";
export type ExpenseStatus = "pending_l1" | "pending_l2" | "approved" | "rejected" | "cancelled";

export interface ExpenseItem {
  id: string;
  type: string;
  amount: string;
  reason: string;
  status: string;
  applicant: UserBrief;
  approver: UserBrief | null;
  created_at: string;
  updated_at: string;
}

export interface ExpenseHistoryItem {
  from_status: string | null;
  to_status: string;
  actor: UserBrief;
  comment: string | null;
  created_at: string;
}

export interface ExpenseAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface ExpenseDetail extends ExpenseItem {
  history: ExpenseHistoryItem[];
  attachments: ExpenseAttachment[];
}

export interface ExpenseListResponse {
  items: ExpenseItem[];
  total: number;
  page: number;
  page_size: number;
}
```

创建 `frontend/src/api/expenses.ts`:

```ts
import { client } from "./client";
import type { ExpenseDetail, ExpenseItem, ExpenseListResponse } from "../types/api";

export async function createExpense(form: FormData): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>("/expenses", form);
  return data;
}

export async function listMine(params: {
  status?: string;
  type?: string;
  page: number;
  page_size: number;
}): Promise<ExpenseListResponse> {
  const { data } = await client.get<ExpenseListResponse>("/expenses/mine", { params });
  return data;
}

export async function listTodo(params: {
  page: number;
  page_size: number;
}): Promise<ExpenseListResponse> {
  const { data } = await client.get<ExpenseListResponse>("/expenses/todo", { params });
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
}): Promise<ExpenseListResponse> {
  const { data } = await client.get<ExpenseListResponse>("/expenses", { params });
  return data;
}

export async function getExpenseDetail(id: string): Promise<ExpenseDetail> {
  const { data } = await client.get<ExpenseDetail>(`/expenses/${id}`);
  return data;
}

export async function downloadAttachment(expenseId: string, attachmentId: string): Promise<Blob> {
  const { data } = await client.get<Blob>(`/expenses/${expenseId}/attachments/${attachmentId}`, {
    responseType: "blob",
  });
  return data;
}

export async function cancelExpense(id: string): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>(`/expenses/${id}/cancel`);
  return data;
}

export async function approveExpense(id: string): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>(`/expenses/${id}/approve`);
  return data;
}

export async function rejectExpense(id: string, reason: string): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>(`/expenses/${id}/reject`, { reason });
  return data;
}
```

(注意:`createExpense` **不手动设 `Content-Type`**——axios 检测 FormData 会自动带 boundary。)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/api/expenses.test.ts`
Expected: 10 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/expenses.ts frontend/src/api/expenses.test.ts
git commit -m "feat(frontend): 报销 api 层与类型定义"
```

---

### Task 3: 报销常量映射 + 新建报销表单 Modal

**Files:**
- Create: `frontend/src/utils/expense.tsx`
- Create: `frontend/src/pages/expenses/ExpenseFormModal.tsx`
- Test: `frontend/src/pages/expenses/ExpenseFormModal.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `createExpense`、`ExpenseType`
- Produces: `EXPENSE_TYPE_MAP` / `EXPENSE_STATUS_MAP` / `expenseTypeTag(type)` / `expenseStatusTag(status)`(Task 4-7 消费);`ExpenseFormModal({ open, onClose, onSuccess })`(Task 5 消费)

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/expenses/ExpenseFormModal.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({ createExpense: vi.fn() }));

import { createExpense } from "../../api/expenses";
import ExpenseFormModal from "./ExpenseFormModal";

function renderModal(onSuccess = vi.fn(), onClose = vi.fn()) {
  render(
    <App>
      <ExpenseFormModal open onClose={onClose} onSuccess={onSuccess} />
    </App>
  );
  return { onSuccess, onClose };
}

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("combobox"));
  const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
  await user.click(dropdown.querySelector('[title="差旅"]') as HTMLElement);
  await user.type(screen.getByLabelText(/金额/), "1999.5");
  await user.type(screen.getByLabelText(/报销说明/), "出差打车");
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ExpenseFormModal", () => {
  it("必填校验:直接确定显示错误", async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请选择报销类型")).toBeInTheDocument();
    expect(screen.getByText("请输入金额")).toBeInTheDocument();
    expect(screen.getByText("请输入报销说明")).toBeInTheDocument();
    expect(createExpense).not.toHaveBeenCalled();
  });

  it("无附件提交:Alert 提示且不提交", async () => {
    renderModal();
    const user = userEvent.setup();
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请上传 1~5 个附件凭证")).toBeInTheDocument();
    expect(createExpense).not.toHaveBeenCalled();
  });

  it("完整提交:FormData 字段正确,成功后 onSuccess + onClose", async () => {
    const { onSuccess, onClose } = renderModal();
    const user = userEvent.setup();
    await fillRequired(user);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "a.png", { type: "image/png" }));
    await screen.findByText("a.png");
    vi.mocked(createExpense).mockResolvedValue({} as never);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(createExpense).toHaveBeenCalledOnce());
    const fd = vi.mocked(createExpense).mock.calls[0][0];
    expect(fd.get("type")).toBe("travel");
    expect(fd.get("amount")).toBe("1999.50");
    expect(fd.get("reason")).toBe("出差打车");
    expect((fd.get("files") as File).name).toBe("a.png");
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("超大文件:拒绝加入并提示", async () => {
    renderModal();
    const user = userEvent.setup();
    const big = new File([new Uint8Array(6 * 1024 * 1024)], "big.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, big);
    await waitFor(() => expect(screen.queryByText("big.png")).not.toBeInTheDocument());
  });

  it("非法扩展名:拒绝加入", async () => {
    renderModal();
    const user = userEvent.setup();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "a.txt", { type: "text/plain" }));
    await waitFor(() => expect(screen.queryByText("a.txt")).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/expenses/ExpenseFormModal.test.tsx`
Expected: FAIL,`Failed to resolve import "../../api/expenses" 的 mock 目标外 — 实际为 Failed to resolve import "./ExpenseFormModal"`

- [ ] **Step 3: Write constants + modal**

创建 `frontend/src/utils/expense.tsx`:

```tsx
import { Tag } from "antd";

export const EXPENSE_TYPE_MAP: Record<string, { label: string; color: string }> = {
  travel: { label: "差旅", color: "blue" },
  office: { label: "办公", color: "green" },
  entertainment: { label: "招待", color: "orange" },
  transport: { label: "交通", color: "purple" },
  other: { label: "其他", color: "default" },
};

export const EXPENSE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending_l1: { label: "待主管审批", color: "gold" },
  pending_l2: { label: "待二级审批", color: "volcano" },
  approved: { label: "已通过", color: "green" },
  rejected: { label: "已驳回", color: "red" },
  cancelled: { label: "已撤回", color: "default" },
};

export function expenseTypeTag(type: string) {
  const m = EXPENSE_TYPE_MAP[type] ?? { label: type, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}

export function expenseStatusTag(status: string) {
  const m = EXPENSE_STATUS_MAP[status] ?? { label: status, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}
```

创建 `frontend/src/pages/expenses/ExpenseFormModal.tsx`:

```tsx
import { useState } from "react";
import { Alert, App, Form, Input, InputNumber, Modal, Select, Upload } from "antd";
import type { UploadFile } from "antd";

import { createExpense } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseType } from "../../types/api";
import { EXPENSE_TYPE_MAP } from "../../utils/expense";

const MAX_FILES = 5;
const MAX_SIZE = 5 * 1024 * 1024;
const ALLOWED_EXT = [".jpg", ".jpeg", ".png", ".pdf"];

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface ExpenseFormValues {
  type: ExpenseType;
  amount: number;
  reason: string;
}

export default function ExpenseFormModal({ open, onClose, onSuccess }: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<ExpenseFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function acceptFile(file: File): boolean {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      message.error("仅支持 jpg/jpeg/png/pdf 格式");
      return false;
    }
    if (file.size > MAX_SIZE) {
      message.error(`单个文件不能超过 5MB`);
      return false;
    }
    return true;
  }

  async function onFinish(values: ExpenseFormValues) {
    if (fileList.length === 0) {
      setError("请上传 1~5 个附件凭证");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("type", values.type);
      fd.append("amount", values.amount.toFixed(2));
      fd.append("reason", values.reason);
      for (const f of fileList) {
        if (f.originFileObj) fd.append("files", f.originFileObj);
      }
      await createExpense(fd);
      onSuccess();
      handleClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setError(null);
    setFileList([]);
    form.resetFields();
    onClose();
  }

  return (
    <Modal
      title="新建报销申请"
      open={open}
      onCancel={handleClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<ExpenseFormValues> form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item name="type" label="报销类型" rules={[{ required: true, message: "请选择报销类型" }]}>
          <Select
            placeholder="请选择"
            options={Object.entries(EXPENSE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
          />
        </Form.Item>
        <Form.Item name="amount" label="金额(元)" rules={[{ required: true, message: "请输入金额" }]}>
          <InputNumber style={{ width: "100%" }} min={0.01} precision={2} placeholder="0.00" />
        </Form.Item>
        <Form.Item
          name="reason"
          label="报销说明"
          rules={[
            { required: true, message: "请输入报销说明" },
            { max: 500, message: "最多 500 字" },
          ]}
        >
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
        <Form.Item label="附件凭证(1~5 个,jpg/png/pdf,单个 ≤5MB)" required>
          <Upload
            fileList={fileList}
            multiple
            beforeUpload={(file) => {
              if (fileList.length >= MAX_FILES) {
                message.error("最多 5 个附件");
                return Upload.LIST_IGNORE;
              }
              if (!acceptFile(file)) return Upload.LIST_IGNORE;
              return false;
            }}
            onChange={({ fileList: fl }) => setFileList(fl.slice(0, MAX_FILES))}
            onRemove={(f) => setFileList((prev) => prev.filter((x) => x.uid !== f.uid))}
          >
            <button type="button" className="ant-btn ant-btn-default">
              点击上传
            </button>
          </Upload>
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

(上传按钮用原生 button + antd class,避免多引 antd Button 仅为 Upload 子元素——如果项目 lint 不喜欢可换 `<Button>`,二选一保持现状即可。)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/expenses/ExpenseFormModal.test.tsx`
Expected: 5 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/expense.tsx frontend/src/pages/expenses/ExpenseFormModal.tsx frontend/src/pages/expenses/ExpenseFormModal.test.tsx
git commit -m "feat(frontend): 报销常量映射与新建报销表单"
```

---

### Task 4: 报销详情弹窗 + 驳回弹窗

**Files:**
- Create: `frontend/src/pages/expenses/ExpenseDetailModal.tsx`
- Create: `frontend/src/pages/expenses/RejectModal.tsx`
- Test: `frontend/src/pages/expenses/ExpenseDetailModal.test.tsx`
- Test: `frontend/src/pages/expenses/RejectModal.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `getExpenseDetail` / `downloadAttachment` / `rejectExpense`;Task 3 的 `expenseTypeTag` / `expenseStatusTag` / `EXPENSE_STATUS_MAP`
- Produces: `ExpenseDetailModal({ expenseId: string | null, onClose: () => void })`(Task 5-8 消费);`RejectModal({ expenseId: string | null, onClose: () => void, onSuccess: () => void })`(Task 6 消费)

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/expenses/ExpenseDetailModal.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));

import { downloadAttachment, getExpenseDetail } from "../../api/expenses";
import type { ExpenseDetail } from "../../types/api";
import ExpenseDetailModal from "./ExpenseDetailModal";

function detail(over: Partial<ExpenseDetail>): ExpenseDetail {
  return {
    id: "e1",
    type: "travel",
    amount: "1999.50",
    reason: "出差打车",
    status: "pending_l1",
    applicant: { id: "u1", name: "张三" },
    approver: { id: "u2", name: "王主管" },
    created_at: "2026-07-29T09:00:00",
    updated_at: "2026-07-29T09:00:00",
    history: [
      { from_status: null, to_status: "pending_l1", actor: { id: "u1", name: "张三" }, comment: null, created_at: "2026-07-29T09:00:00" },
    ],
    attachments: [
      { id: "a1", filename: "发票.png", content_type: "image/png", size_bytes: 2048, created_at: "2026-07-29T09:00:00" },
    ],
    ...over,
  };
}

function renderModal() {
  return render(
    <App>
      <ExpenseDetailModal expenseId="e1" onClose={vi.fn()} />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

describe("ExpenseDetailModal", () => {
  it("L1:当前审批显示 第 1 级 · 主管姓名", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({}));
    renderModal();
    expect(await screen.findByText("报销详情")).toBeInTheDocument();
    expect(screen.getByText("第 1 级 · 王主管")).toBeInTheDocument();
    expect(screen.getByText("¥1999.50")).toBeInTheDocument();
    expect(screen.getByText("待主管审批")).toBeInTheDocument();
  });

  it("L2:当前审批显示 第 2 级 · HR/Admin 权限池", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({ status: "pending_l2", approver: null }));
    renderModal();
    expect(await screen.findByText("第 2 级 · HR/Admin 权限池")).toBeInTheDocument();
  });

  it("终态:当前审批显示 —", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({ status: "approved" }));
    renderModal();
    await screen.findByText("报销详情");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("附件列表渲染,点击触发鉴权下载", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({}));
    vi.mocked(downloadAttachment).mockResolvedValue(new Blob(["x"]));
    renderModal();
    const user = userEvent.setup();
    await user.click(await screen.findByText(/发票\.png/));
    expect(downloadAttachment).toHaveBeenCalledWith("e1", "a1");
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
  });

  it("Timeline 渲染 actor 与驳回原因", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(
      detail({
        status: "rejected",
        history: [
          { from_status: null, to_status: "pending_l1", actor: { id: "u1", name: "张三" }, comment: null, created_at: "2026-07-29T09:00:00" },
          { from_status: "pending_l1", to_status: "rejected", actor: { id: "u2", name: "王主管" }, comment: "发票不清", created_at: "2026-07-29T10:00:00" },
        ],
      })
    );
    renderModal();
    expect(await screen.findByText(/已驳回 · 王主管/)).toBeInTheDocument();
    expect(screen.getByText(/发票不清/)).toBeInTheDocument();
  });
});
```

创建 `frontend/src/pages/expenses/RejectModal.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({ rejectExpense: vi.fn() }));

import { rejectExpense } from "../../api/expenses";
import RejectModal from "./RejectModal";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RejectModal(报销)", () => {
  it("原因为空:校验拦截不提交", async () => {
    render(<RejectModal expenseId="e1" onClose={vi.fn()} onSuccess={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请输入驳回原因")).toBeInTheDocument();
    expect(rejectExpense).not.toHaveBeenCalled();
  });

  it("填写原因提交:调 rejectExpense 并 onSuccess + onClose", async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    vi.mocked(rejectExpense).mockResolvedValue({} as never);
    render(<RejectModal expenseId="e1" onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox"), "发票不清");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(rejectExpense).toHaveBeenCalledWith("e1", "发票不清"));
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/expenses/ExpenseDetailModal.test.tsx src/pages/expenses/RejectModal.test.tsx`
Expected: FAIL,`Failed to resolve import "./ExpenseDetailModal"` / `"./RejectModal"`

- [ ] **Step 3: Write modals**

创建 `frontend/src/pages/expenses/ExpenseDetailModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Alert, App, Button, Descriptions, Modal, Spin, Timeline } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { downloadAttachment, getExpenseDetail } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseAttachment, ExpenseDetail } from "../../types/api";
import { EXPENSE_STATUS_MAP, expenseStatusTag, expenseTypeTag } from "../../utils/expense";

interface Props {
  expenseId: string | null;
  onClose: () => void;
}

function currentApproval(d: ExpenseDetail): string {
  if (d.status === "pending_l1") return `第 1 级 · ${d.approver?.name ?? "主管"}`;
  if (d.status === "pending_l2") return "第 2 级 · HR/Admin 权限池";
  return "—";
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${bytes}B`;
}

export default function ExpenseDetailModal({ expenseId, onClose }: Props) {
  const { message } = App.useApp();
  const [detail, setDetail] = useState<ExpenseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expenseId) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    setLoading(true);
    getExpenseDetail(expenseId)
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
  }, [expenseId]);

  async function onDownload(a: ExpenseAttachment) {
    if (!detail) return;
    try {
      const blob = await downloadAttachment(detail.id, a.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = a.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    }
  }

  return (
    <Modal title="报销详情" open={expenseId !== null} onCancel={onClose} footer={null} destroyOnHidden>
      {loading && <Spin />}
      {error && <Alert type="error" message={error} showIcon />}
      {detail && (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="类型">{expenseTypeTag(detail.type)}</Descriptions.Item>
            <Descriptions.Item label="金额">{`¥${detail.amount}`}</Descriptions.Item>
            <Descriptions.Item label="说明">{detail.reason}</Descriptions.Item>
            <Descriptions.Item label="状态">{expenseStatusTag(detail.status)}</Descriptions.Item>
            <Descriptions.Item label="当前审批">{currentApproval(detail)}</Descriptions.Item>
            <Descriptions.Item label="申请人">{detail.applicant.name}</Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {dayjs(detail.created_at).format("YYYY-MM-DD HH:mm")}
            </Descriptions.Item>
            <Descriptions.Item label="附件凭证">
              {detail.attachments.map((a) => (
                <Button
                  key={a.id}
                  type="link"
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => void onDownload(a)}
                >
                  {`${a.filename}(${formatSize(a.size_bytes)})`}
                </Button>
              ))}
            </Descriptions.Item>
          </Descriptions>
          <Timeline
            style={{ marginTop: 16 }}
            items={detail.history.map((h) => ({
              children: `${EXPENSE_STATUS_MAP[h.to_status]?.label ?? h.to_status} · ${h.actor.name} · ${dayjs(
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

创建 `frontend/src/pages/expenses/RejectModal.tsx`:

```tsx
import { useState } from "react";
import { Alert, Form, Input, Modal } from "antd";

import { rejectExpense } from "../../api/expenses";
import { ApiError } from "../../api/client";

interface Props {
  expenseId: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RejectModal({ expenseId, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<{ reason: string }>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: { reason: string }) {
    if (!expenseId) return;
    setSubmitting(true);
    setError(null);
    try {
      await rejectExpense(expenseId, values.reason);
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setError(null);
    onClose();
  }

  return (
    <Modal
      title="驳回申请"
      open={expenseId !== null}
      onCancel={handleClose}
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/expenses/ExpenseDetailModal.test.tsx src/pages/expenses/RejectModal.test.tsx`
Expected: 7 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/expenses/ExpenseDetailModal.tsx frontend/src/pages/expenses/ExpenseDetailModal.test.tsx frontend/src/pages/expenses/RejectModal.tsx frontend/src/pages/expenses/RejectModal.test.tsx
git commit -m "feat(frontend): 报销详情弹窗(二级审批状态+附件下载)与驳回弹窗"
```

---

### Task 5: 我的申请 Panel

**Files:**
- Create: `frontend/src/pages/expenses/MyExpensesPanel.tsx`
- Test: `frontend/src/pages/expenses/MyExpensesPanel.test.tsx`

**Interfaces:**
- Consumes: Task 2 `listMine` / `cancelExpense`;Task 3 `ExpenseFormModal`、`EXPENSE_TYPE_MAP`、`expenseTypeTag`/`expenseStatusTag`;Task 4 `ExpenseDetailModal`
- Produces: `MyExpensesPanel()`(Task 8 消费)

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/expenses/MyExpensesPanel.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  listMine: vi.fn(),
  cancelExpense: vi.fn(),
  createExpense: vi.fn(),
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));

import { cancelExpense, listMine } from "../../api/expenses";
import type { ExpenseListResponse } from "../../types/api";
import MyExpensesPanel from "./MyExpensesPanel";

const pending = {
  id: "e1", type: "travel", amount: "1999.50", reason: "出差打车", status: "pending_l1",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00", updated_at: "2026-07-29T09:00:00",
};
const approved = { ...pending, id: "e2", status: "approved", type: "office", amount: "88", reason: "买纸" };

function paged(items: unknown[]): ExpenseListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

function renderPanel() {
  return render(
    <App>
      <MyExpensesPanel />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listMine).mockResolvedValue(paged([pending, approved]));
});

describe("MyExpensesPanel", () => {
  it("列表渲染:类型/金额/状态/审批人;pending_l1 行有撤回,终态行无", async () => {
    renderPanel();
    expect(await screen.findByText("出差打车")).toBeInTheDocument();
    expect(screen.getByText("买纸")).toBeInTheDocument();
    expect(screen.getByText("¥1999.50")).toBeInTheDocument();
    expect(screen.getAllByText("王主管").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "撤回" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "详情" })).toHaveLength(2);
  });

  it("status 筛选:带参数重查并回第 1 页", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[0]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("待主管审批"));
    await waitFor(() =>
      expect(listMine).toHaveBeenCalledWith({ status: "pending_l1", page: 1, page_size: 20 })
    );
  });

  it("type 筛选:带参数重查", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[1]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("差旅"));
    await waitFor(() =>
      expect(listMine).toHaveBeenCalledWith({ type: "travel", page: 1, page_size: 20 })
    );
  });

  it("撤回:Popconfirm 确认后调 cancelExpense 并刷新", async () => {
    vi.mocked(cancelExpense).mockResolvedValue({} as never);
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "撤回" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(cancelExpense).toHaveBeenCalledWith("e1"));
    await waitFor(() => expect(listMine).toHaveBeenCalledTimes(2));
  });

  it("新建报销:点按钮打开 ExpenseFormModal", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "新建报销" }));
    expect(await screen.findByText("新建报销申请")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/expenses/MyExpensesPanel.test.tsx`
Expected: FAIL,`Failed to resolve import "./MyExpensesPanel"`

- [ ] **Step 3: Write the panel**

创建 `frontend/src/pages/expenses/MyExpensesPanel.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Select, Space, Table } from "antd";

import { cancelExpense, listMine } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseItem } from "../../types/api";
import { EXPENSE_STATUS_MAP, EXPENSE_TYPE_MAP, expenseStatusTag, expenseTypeTag } from "../../utils/expense";
import ExpenseDetailModal from "./ExpenseDetailModal";
import ExpenseFormModal from "./ExpenseFormModal";

const PAGE_SIZE = 20;

export default function MyExpensesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<ExpenseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | null>(null);
  const [type, setType] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  const fetchList = useCallback(async (p: number, s: string | null, t: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listMine({
        ...(s ? { status: s } : {}),
        ...(t ? { type: t } : {}),
        page: p,
        page_size: PAGE_SIZE,
      });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList(page, status, type);
  }, [page, status, type, fetchList]);

  async function onCancel(e: ExpenseItem) {
    try {
      await cancelExpense(e.id);
      message.success("已撤回");
      await fetchList(page, status, type);
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : "网络异常,请稍后重试");
      await fetchList(page, status, type);
    }
  }

  const columns = [
    { title: "类型", key: "type", render: (_: unknown, e: ExpenseItem) => expenseTypeTag(e.type) },
    { title: "金额", key: "amount", render: (_: unknown, e: ExpenseItem) => `¥${e.amount}` },
    { title: "说明", dataIndex: "reason", key: "reason" },
    { title: "状态", key: "status", render: (_: unknown, e: ExpenseItem) => expenseStatusTag(e.status) },
    { title: "审批人", key: "approver", render: (_: unknown, e: ExpenseItem) => e.approver?.name ?? "—" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, e: ExpenseItem) => (
        <Space>
          {(e.status === "pending_l1" || e.status === "pending_l2") && (
            <Popconfirm title="确认撤回该申请?" onConfirm={() => void onCancel(e)}>
              <Button type="link" size="small" danger>
                撤回
              </Button>
            </Popconfirm>
          )}
          <Button type="link" size="small" onClick={() => setDetailId(e.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 140 }}
          value={status}
          onChange={(v) => {
            setPage(1);
            setStatus(v ?? null);
          }}
          options={Object.entries(EXPENSE_STATUS_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Select
          placeholder="类型筛选"
          allowClear
          style={{ width: 120 }}
          value={type}
          onChange={(v) => {
            setPage(1);
            setType(v ?? null);
          }}
          options={Object.entries(EXPENSE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Button type="primary" onClick={() => setFormOpen(true)}>
          新建报销
        </Button>
      </Space>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<ExpenseItem>
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
      <ExpenseFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success("已提交");
          setPage(1);
          setStatus(null);
          setType(null);
          void fetchList(1, null, null);
        }}
      />
      <ExpenseDetailModal expenseId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/expenses/MyExpensesPanel.test.tsx`
Expected: 5 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/expenses/MyExpensesPanel.tsx frontend/src/pages/expenses/MyExpensesPanel.test.tsx
git commit -m "feat(frontend): 我的报销申请面板"
```

---

### Task 6: 待我审批 Panel

**Files:**
- Create: `frontend/src/pages/expenses/TodoExpensesPanel.tsx`
- Test: `frontend/src/pages/expenses/TodoExpensesPanel.test.tsx`

**Interfaces:**
- Consumes: Task 2 `listTodo` / `approveExpense` / `rejectExpense`;Task 3 `expenseTypeTag` / `expenseStatusTag`;Task 4 `ExpenseDetailModal` / `RejectModal`
- Produces: `TodoExpensesPanel()`(Task 8 消费)

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/expenses/TodoExpensesPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  listTodo: vi.fn(),
  approveExpense: vi.fn(),
  rejectExpense: vi.fn(),
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));

import { approveExpense, listTodo } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseListResponse } from "../../types/api";
import TodoExpensesPanel from "./TodoExpensesPanel";

const l1 = {
  id: "e1", type: "travel", amount: "1999.50", reason: "出差打车", status: "pending_l1",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00", updated_at: "2026-07-29T09:00:00",
};
const l2 = { ...l1, id: "e2", status: "pending_l2", amount: "5000", reason: "团建", approver: null };

function paged(items: unknown[]): ExpenseListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

function renderPanel() {
  return render(
    <App>
      <TodoExpensesPanel />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listTodo).mockResolvedValue(paged([l1, l2]));
});

describe("TodoExpensesPanel", () => {
  it("列表渲染:申请人/金额/级别 Tag;每行有通过/驳回/详情", async () => {
    renderPanel();
    expect(await screen.findByText("出差打车")).toBeInTheDocument();
    expect(screen.getAllByText("张三").length).toBeGreaterThan(0);
    expect(screen.getByText("待主管审批")).toBeInTheDocument();
    expect(screen.getByText("待二级审批")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "通过" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "驳回" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "详情" })).toHaveLength(2);
  });

  it("通过:Popconfirm 确认后调 approveExpense 并刷新", async () => {
    vi.mocked(approveExpense).mockResolvedValue({} as never);
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "通过" })[0]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(approveExpense).toHaveBeenCalledWith("e1"));
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });

  it("通过 409:message 提示且仍刷新列表", async () => {
    vi.mocked(approveExpense).mockRejectedValue(new ApiError("CONFLICT", "该单已被处理"));
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "通过" })[0]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await screen.findByText("该单已被处理");
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });

  it("驳回:打开 RejectModal", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "驳回" })[0]);
    expect(await screen.findByText("驳回申请")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/expenses/TodoExpensesPanel.test.tsx`
Expected: FAIL,`Failed to resolve import "./TodoExpensesPanel"`

- [ ] **Step 3: Write the panel**

创建 `frontend/src/pages/expenses/TodoExpensesPanel.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Space, Table } from "antd";

import { approveExpense, listTodo } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseItem } from "../../types/api";
import { expenseStatusTag, expenseTypeTag } from "../../utils/expense";
import ExpenseDetailModal from "./ExpenseDetailModal";
import RejectModal from "./RejectModal";

const PAGE_SIZE = 20;

export default function TodoExpensesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<ExpenseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  const fetchList = useCallback(async (p: number) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listTodo({ page: p, page_size: PAGE_SIZE });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList(page);
  }, [page, fetchList]);

  async function onApprove(e: ExpenseItem) {
    try {
      await approveExpense(e.id);
      message.success("已通过");
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : "网络异常,请稍后重试");
    }
    await fetchList(page);
  }

  const columns = [
    { title: "申请人", key: "applicant", render: (_: unknown, e: ExpenseItem) => e.applicant.name },
    { title: "类型", key: "type", render: (_: unknown, e: ExpenseItem) => expenseTypeTag(e.type) },
    { title: "金额", key: "amount", render: (_: unknown, e: ExpenseItem) => `¥${e.amount}` },
    { title: "说明", dataIndex: "reason", key: "reason" },
    { title: "级别", key: "status", render: (_: unknown, e: ExpenseItem) => expenseStatusTag(e.status) },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, e: ExpenseItem) => (
        <Space>
          <Popconfirm title="确认通过该申请?" onConfirm={() => void onApprove(e)}>
            <Button type="link" size="small">
              通过
            </Button>
          </Popconfirm>
          <Button type="link" size="small" danger onClick={() => setRejectingId(e.id)}>
            驳回
          </Button>
          <Button type="link" size="small" onClick={() => setDetailId(e.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<ExpenseItem>
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
        expenseId={rejectingId}
        onClose={() => setRejectingId(null)}
        onSuccess={() => {
          message.success("已驳回");
          void fetchList(page);
        }}
      />
      <ExpenseDetailModal expenseId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/expenses/TodoExpensesPanel.test.tsx`
Expected: 4 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/expenses/TodoExpensesPanel.tsx frontend/src/pages/expenses/TodoExpensesPanel.test.tsx
git commit -m "feat(frontend): 报销待我审批面板"
```

---

### Task 7: 全部记录 Panel

**Files:**
- Create: `frontend/src/pages/expenses/AllExpensesPanel.tsx`
- Test: `frontend/src/pages/expenses/AllExpensesPanel.test.tsx`

**Interfaces:**
- Consumes: Task 2 `listAll`;既有 `listDeptTree`(`../../api/departments`)、`toTreeSelectData`(`../../utils/deptTree`)、`DepartmentNode` 类型;Task 3 映射;Task 4 `ExpenseDetailModal`
- Produces: `AllExpensesPanel()`(Task 8 消费)

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/expenses/AllExpensesPanel.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  listAll: vi.fn(),
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));
vi.mock("../../api/departments", () => ({ listDeptTree: vi.fn() }));

import { listDeptTree } from "../../api/departments";
import { listAll } from "../../api/expenses";
import type { ExpenseListResponse } from "../../types/api";
import AllExpensesPanel from "./AllExpensesPanel";

const item = {
  id: "e1", type: "travel", amount: "1999.50", reason: "出差打车", status: "pending_l1",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00", updated_at: "2026-07-29T09:00:00",
};

function paged(items: unknown[]): ExpenseListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

function renderPanel() {
  return render(
    <App>
      <AllExpensesPanel />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listAll).mockResolvedValue(paged([item]));
  vi.mocked(listDeptTree).mockResolvedValue([
    { id: "d1", name: "技术部", parent_id: null, member_count: 3, children: [] },
  ]);
});

describe("AllExpensesPanel", () => {
  it("初始加载:listAll 仅带分页参数,渲染申请人/金额/状态", async () => {
    renderPanel();
    expect(await screen.findByText("出差打车")).toBeInTheDocument();
    expect(screen.getByText("张三")).toBeInTheDocument();
    expect(screen.getByText("¥1999.50")).toBeInTheDocument();
    expect(listAll).toHaveBeenCalledWith({ page: 1, page_size: 20 });
  });

  it("状态筛选透传", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[1]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("已通过"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith({ status: "approved", page: 1, page_size: 20 })
    );
  });

  it("类型筛选透传", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[2]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("差旅"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith({ type: "travel", page: 1, page_size: 20 })
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/expenses/AllExpensesPanel.test.tsx`
Expected: FAIL,`Failed to resolve import "./AllExpensesPanel"`

- [ ] **Step 3: Write the panel**

创建 `frontend/src/pages/expenses/AllExpensesPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Alert, Button, DatePicker, Select, Space, Table, TreeSelect } from "antd";
import type { Dayjs } from "dayjs";

import { listAll } from "../../api/expenses";
import { listDeptTree } from "../../api/departments";
import { ApiError } from "../../api/client";
import type { DepartmentNode, ExpenseItem } from "../../types/api";
import { toTreeSelectData } from "../../utils/deptTree";
import { EXPENSE_STATUS_MAP, EXPENSE_TYPE_MAP, expenseStatusTag, expenseTypeTag } from "../../utils/expense";
import ExpenseDetailModal from "./ExpenseDetailModal";

const PAGE_SIZE = 20;

interface Filters {
  department_id: string | null;
  status: string | null;
  type: string | null;
  range: [Dayjs, Dayjs] | null;
}

export default function AllExpensesPanel() {
  const [items, setItems] = useState<ExpenseItem[]>([]);
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
    { title: "申请人", key: "applicant", render: (_: unknown, e: ExpenseItem) => e.applicant.name },
    { title: "类型", key: "type", render: (_: unknown, e: ExpenseItem) => expenseTypeTag(e.type) },
    { title: "金额", key: "amount", render: (_: unknown, e: ExpenseItem) => `¥${e.amount}` },
    { title: "说明", dataIndex: "reason", key: "reason" },
    { title: "状态", key: "status", render: (_: unknown, e: ExpenseItem) => expenseStatusTag(e.status) },
    { title: "审批人", key: "approver", render: (_: unknown, e: ExpenseItem) => e.approver?.name ?? "—" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, e: ExpenseItem) => (
        <Button type="link" size="small" onClick={() => setDetailId(e.id)}>
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
          style={{ width: 140 }}
          value={filters.status ?? undefined}
          onChange={(v) => patch({ status: v ?? null })}
          options={Object.entries(EXPENSE_STATUS_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Select
          placeholder="类型"
          allowClear
          style={{ width: 120 }}
          value={filters.type ?? undefined}
          onChange={(v) => patch({ type: v ?? null })}
          options={Object.entries(EXPENSE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <DatePicker.RangePicker
          placeholder={["开始日期", "结束日期"]}
          value={filters.range}
          onChange={(v) => patch({ range: v as [Dayjs, Dayjs] | null })}
        />
      </Space>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<ExpenseItem>
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
      <ExpenseDetailModal expenseId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/expenses/AllExpensesPanel.test.tsx`
Expected: 3 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/expenses/AllExpensesPanel.tsx frontend/src/pages/expenses/AllExpensesPanel.test.tsx
git commit -m "feat(frontend): 报销全部记录面板(部门/状态/类型/时间筛选)"
```

---

### Task 8: ExpensesPage 页面壳 + 菜单 + 路由 + openExpenseId 联动

**Files:**
- Create: `frontend/src/pages/expenses/ExpensesPage.tsx`
- Modify: `frontend/src/components/menu.tsx`(import 行 + MENU_ITEMS 追加)
- Modify: `frontend/src/App.tsx`(import 行 + children 路由)
- Test: `frontend/src/pages/expenses/ExpensesPage.test.tsx`

**Interfaces:**
- Consumes: Task 5/6/7 三个 Panel;Task 4 `ExpenseDetailModal`;既有 `useAuthStore.hasPermission`
- Produces: 路由 `/expenses`(RequireAuth 内);行为契约:带 `location.state.openExpenseId` 进入自动打开详情弹窗,关闭弹窗清除 state——Task 9 生产该 state

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/expenses/ExpensesPage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./MyExpensesPanel", () => ({ default: () => <div>我的申请面板</div> }));
vi.mock("./TodoExpensesPanel", () => ({ default: () => <div>待我审批面板</div> }));
vi.mock("./AllExpensesPanel", () => ({ default: () => <div>全部记录面板</div> }));
vi.mock("../../api/expenses", () => ({
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));

import { getExpenseDetail } from "../../api/expenses";
import { useAuthStore } from "../../store/auth";
import type { CurrentUser } from "../../types/api";
import ExpensesPage from "./ExpensesPage";

function userWith(permissions: string[]): CurrentUser {
  return {
    id: "u1", email: "a@x.com", name: "用户", is_active: true,
    roles: [], department: null, manager: null, permissions,
  };
}

const detail = {
  id: "E1", type: "travel", amount: "100", reason: "打车", status: "pending_l1",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00", updated_at: "2026-07-29T09:00:00",
  history: [], attachments: [],
};

function PathProbe() {
  const loc = useLocation();
  return <div data-testid="path">{loc.pathname}</div>;
}

function renderPage(perms: string[], state?: object) {
  useAuthStore.setState({ token: "t", user: userWith(perms) });
  return render(
    <App>
      <MemoryRouter initialEntries={[{ pathname: "/expenses", ...(state ? { state } : {}) }]}>
        <Routes>
          <Route path="/" element={<PathProbe />} />
          <Route path="/expenses" element={<ExpensesPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("ExpensesPage", () => {
  it("Tab 按权限过滤:仅 expense:list 只见我的申请;全权限见三个", async () => {
    renderPage(["expense:list"]);
    expect(await screen.findByRole("tab", { name: "我的申请" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "待我审批" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "全部记录" })).not.toBeInTheDocument();
  });

  it("approve_l2 无 approve 也可见待我审批", async () => {
    renderPage(["expense:list", "expense:approve_l2"]);
    expect(await screen.findByRole("tab", { name: "待我审批" })).toBeInTheDocument();
  });

  it("无 expense:list:重定向首页", async () => {
    renderPage([]);
    expect(await screen.findByTestId("path")).toHaveTextContent("/");
  });

  it("携带 openExpenseId state 进入:自动打开详情弹窗", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail);
    renderPage(["expense:list"], { openExpenseId: "E1" });
    expect(await screen.findByText("报销详情")).toBeInTheDocument();
    expect(getExpenseDetail).toHaveBeenCalledWith("E1");
  });

  it("关闭详情弹窗:清除 state,弹窗消失", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail);
    renderPage(["expense:list"], { openExpenseId: "E1" });
    await screen.findByText("报销详情");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByText("报销详情")).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/expenses/ExpensesPage.test.tsx`
Expected: FAIL,`Failed to resolve import "./ExpensesPage"`

- [ ] **Step 3: Write page + menu + route**

创建 `frontend/src/pages/expenses/ExpensesPage.tsx`:

```tsx
import { useState } from "react";
import { Card, Tabs } from "antd";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import AllExpensesPanel from "./AllExpensesPanel";
import ExpenseDetailModal from "./ExpenseDetailModal";
import MyExpensesPanel from "./MyExpensesPanel";
import TodoExpensesPanel from "./TodoExpensesPanel";

export default function ExpensesPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("expense:list");
  const location = useLocation();
  const navigate = useNavigate();
  const openExpenseId =
    (location.state as { openExpenseId?: string } | null)?.openExpenseId ?? null;

  const tabs = [
    { key: "mine", label: "我的申请", show: hasPermission("expense:list"), children: <MyExpensesPanel /> },
    {
      key: "todo",
      label: "待我审批",
      show: hasPermission("expense:approve") || hasPermission("expense:approve_l2"),
      children: <TodoExpensesPanel />,
    },
    { key: "all", label: "全部记录", show: hasPermission("expense:list_all"), children: <AllExpensesPanel /> },
  ].filter((t) => t.show);

  const [activeKey, setActiveKey] = useState<string | null>(null);

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return (
    <Card title="报销审批">
      <Tabs
        activeKey={activeKey ?? tabs[0]?.key}
        onChange={setActiveKey}
        items={tabs.map(({ key, label, children }) => ({ key, label, children }))}
      />
      <ExpenseDetailModal
        expenseId={openExpenseId}
        onClose={() => navigate(".", { replace: true, state: null })}
      />
    </Card>
  );
}
```

修改 `frontend/src/components/menu.tsx`:
- import 行把 `PayCircleOutlined` 加入 `@ant-design/icons` 的导入列表
- `MENU_ITEMS` 在 leaves 行之后追加:

```ts
  { key: "/expenses", label: "报销审批", icon: <PayCircleOutlined />, permission: "expense:list" },
```

修改 `frontend/src/App.tsx`:
- import 区在 `import NotificationsPage from "./pages/notifications/NotificationsPage";` 之后加:`import ExpensesPage from "./pages/expenses/ExpensesPage";`(注意保持字母序:expenses 排在 leaves 之后、notifications 之前更佳——若 lint 要求排序则放在 LeavesPage import 之后)
- children 数组在 `{ path: "leaves", element: <LeavesPage /> },` 之后加:`{ path: "expenses", element: <ExpensesPage /> },`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/expenses/ExpensesPage.test.tsx`
Expected: 5 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/expenses/ExpensesPage.tsx frontend/src/pages/expenses/ExpensesPage.test.tsx frontend/src/components/menu.tsx frontend/src/App.tsx
git commit -m "feat(frontend): 报销审批页面壳、菜单项与 /expenses 路由"
```

---

### Task 9: 消息中心 ref_type 分发接 expense 分支

**Files:**
- Modify: `frontend/src/pages/notifications/NotificationsPage.tsx`(`onClickItem` 的跳转分支)
- Modify: `frontend/src/pages/notifications/NotificationsPage.test.tsx`(加 ExpensesProbe 路由 + 2 个测试)
- Modify: `docs/superpowers/specs/2026-07-29-frontend-notification-design.md`(§6 扩展预留首条标记已实现)

**Interfaces:**
- Consumes: Task 8 的 `state: { openExpenseId }` 契约;既有 `openLeaveId` 分支
- Produces: 无新接口;行为契约:`ref_type === "expense"` → `navigate("/expenses", { state: { openExpenseId: ref_id } })`;未知 ref_type 仍仅标记已读不跳转

- [ ] **Step 1: Write the failing tests**

修改 `frontend/src/pages/notifications/NotificationsPage.test.tsx`:

① 在 `LeavesProbe` 函数之后追加一个 probe:

```tsx
function ExpensesProbe() {
  const loc = useLocation();
  return <div data-testid="expenses-state">{JSON.stringify(loc.state)}</div>;
}
```

② `renderPage` 的 `<Routes>` 中在 `/leaves` 路由之后追加一行:

```tsx
          <Route path="/expenses" element={<ExpensesProbe />} />
```

③ 文件末尾(最后一个 `});` 之前,`describe("NotificationsPage")` 块内)追加 2 个测试:

```tsx
  it("点击报销通知:标记已读 + 跳转 /expenses 带 openExpenseId", async () => {
    mockedList.mockResolvedValue({
      items: [item({ id: "n9", type: "expense_submitted", ref_type: "expense", ref_id: "E9" })],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockedMarkRead.mockResolvedValue(item({ id: "n9", read_at: "2026-07-29T10:00:00" }));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("新的待审批任务"));
    await waitFor(() => expect(mockedMarkRead).toHaveBeenCalledWith("n9"));
    await waitFor(() =>
      expect(screen.getByTestId("expenses-state")).toHaveTextContent('{"openExpenseId":"E9"}')
    );
  });

  it("未知 ref_type:仅标记已读,不跳转", async () => {
    mockedList.mockResolvedValue({
      items: [item({ id: "n8", ref_type: "system", ref_id: "S1" })],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockedMarkRead.mockResolvedValue(item({ id: "n8", read_at: "2026-07-29T10:00:00" }));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("新的待审批任务"));
    await waitFor(() => expect(mockedMarkRead).toHaveBeenCalledWith("n8"));
    expect(screen.queryByTestId("expenses-state")).not.toBeInTheDocument();
    expect(screen.queryByTestId("leaves-state")).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/notifications/NotificationsPage.test.tsx`
Expected: 新增「点击报销通知」FAIL(断言不到 expenses-state);「未知 ref_type」可能已通过(既有降级行为),不强制红

- [ ] **Step 3: Modify NotificationsPage**

`frontend/src/pages/notifications/NotificationsPage.tsx` 的 `onClickItem` 中,把

```tsx
    if (n.ref_type === "leave") {
      navigate("/leaves", { state: { openLeaveId: n.ref_id } });
    }
```

改为:

```tsx
    if (n.ref_type === "leave") {
      navigate("/leaves", { state: { openLeaveId: n.ref_id } });
    } else if (n.ref_type === "expense") {
      navigate("/expenses", { state: { openExpenseId: n.ref_id } });
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/notifications/NotificationsPage.test.tsx`
Expected: 全部 PASS(既有 + 新增 2 个)

- [ ] **Step 5: Sync notification spec §6**

`docs/superpowers/specs/2026-07-29-frontend-notification-design.md` §6 扩展预留第一条:

```
- 未来报销通知(`ref_type="expense"`):点击跳转处按 `ref_type` 分发——本期仅 `"leave"` 一个分支,未知 `ref_type` 降级为"仅标记已读不跳转",不报错。
```

改为:

```
- 报销通知(`ref_type="expense"`)跳转分支已实现(2026-07-29 报销前端):点击 → `navigate("/expenses", { state: { openExpenseId } })`;未知 `ref_type` 仍降级为"仅标记已读不跳转",不报错。
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/notifications/NotificationsPage.tsx frontend/src/pages/notifications/NotificationsPage.test.tsx docs/superpowers/specs/2026-07-29-frontend-notification-design.md
git commit -m "feat(frontend): 消息中心接通报销通知跳转 /expenses 联动"
```

---

### Task 10: 全量验收 + spec 勾选

**Files:**
- Modify: `docs/superpowers/specs/2026-07-29-frontend-expense-approval-design.md`(§10 六个 `- [ ]` → `- [x]`)

**Interfaces:**
- Consumes: Task 1-9 全部产出
- Produces: 可 PR 的完整分支

- [ ] **Step 1: Run full test suites + typecheck**

Run: `cd frontend && npm test`
Expected: 全部 PASS(既有 + 本分支新增,无回归)

Run: `cd frontend && npm run typecheck`
Expected: 0 errors

Run: `cd backend && python -m pytest tests/ -q`
Expected: 全量 PASS,无回归

- [ ] **Step 2: Browser 验收(必做)**

用 chrome-devtools MCP 驱动浏览器实测(docker postgres + 后端 :8000 + 前端 `npm run dev`;本机后端启动:`cd backend && DATABASE_URL="postgresql+asyncpg://oa:oa@127.0.0.1:5432/oa" python -m uvicorn app.main:app --port 8000`,无 uv 时用 anaconda python;admin 账号 `admin@company.com` / `Admin123!`;另需一个员工账号提交报销,可复用 seed 员工或新建验收账号):

1. 员工新建 ≤2000 报销(带 1 个附件)→ 主管待办可见 → 主管通过 → 员工「我的申请」状态「已通过」且收到通知
2. 员工新建 >2000 报销 → 主管通过 → 状态「待二级审批」、详情「当前审批」显示第 2 级权限池 → admin 待办可见 → admin 通过 → 详情 Timeline 两级留痕、状态「已通过」
3. 任一级驳回 → 状态「已驳回」,详情可见驳回原因
4. 详情弹窗点击附件 → 下载文件可打开
5. 消息中心点击报销通知 → 跳转 `/expenses` 自动打开详情弹窗,角标 -1
6. 无 `expense:list` 用户直接访问 `/expenses` → 重定向首页

**截图全部存 `.superpowers/sdd/acceptance/`,`exp-` 前缀**(如 `exp-1-created.png`……)——禁止放 SDD workspace。

- [ ] **Step 3: Tick spec acceptance boxes**

把 `docs/superpowers/specs/2026-07-29-frontend-expense-approval-design.md` §10 的 6 个 `- [ ]` 全部改为 `- [x]`。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-29-frontend-expense-approval-design.md
git commit -m "test(frontend): 报销审批模块全量验收通过,勾选 spec 验收标准"
```

---

## Self-Review 记录

- **Spec 覆盖**:§1 范围→Task 1(后端字段)/Task 2-9(前端);§2 决策→各 Task 镜像实现;§3 接口形状→Task 1(后端)+Task 2(前端类型,amount: string 依 pydantic Decimal 序列化);§4 单元表→Task 2(api/类型)/Task 3(常量+表单)/Task 4(详情+驳回)/Task 5-7(三 Panel)/Task 8(页面壳+菜单+路由)/Task 9(通知联动);§5 数据流→Task 5-7(本地态+操作重拉)/Task 4(blob 下载)/Task 8(openExpenseId);§6 扩展→不实现;§7 错误处理→各组件测试覆盖(409/422/下载失败);§8 测试策略→各任务测试 + Task 10 浏览器 6 场景;§9 部署→Task 1 无迁移;§10 验收→Task 10 勾选。
- **占位符扫描**:无 TBD/TODO;所有代码块完整可复制。Task 9 Step 2 对「未知 ref_type」测试允许不红(既有降级行为已正确),已注明。
- **类型一致性**:`ExpenseItem/ExpenseDetail/ExpenseAttachment/ExpenseHistoryItem/ExpenseListResponse` Task 2 定义,Task 3-8 消费一致;`expenseTypeTag/expenseStatusTag/EXPENSE_*_MAP` Task 3 定义,Task 4-7 消费一致;`ExpenseFormModal({open,onClose,onSuccess})` Task 3 定义、Task 5 消费;`ExpenseDetailModal({expenseId,onClose})` Task 4 定义、Task 5/6/7/8 消费;`RejectModal({expenseId,onClose,onSuccess})` Task 4 定义、Task 6 消费;`openExpenseId` state Task 8 消费、Task 9 生产,键名一致;后端 `applicant: UserBrief / approver: UserBrief | None` Task 1 定义、Task 2 前端类型镜像。
- **已知取舍**:①面板测试用 antd DOM 定位(combobox 顺序、dropdown 查询),与请假既有测试同风格,antd 升级时同进退;②详情弹窗内不放审批操作按钮(spec §5 提到"也可在详情弹窗内触发"——本期收窄为 Todo 面板操作,详情纯展示,避免按钮权限矩阵重复实现;若验收认为需要再追加);③ExpenseFormModal 上传按钮用原生 button 套 antd class,与 antd Upload 子元素习惯一致;④Task 8 测试 mock 三个 Panel 以隔离页面壳契约,Panel 自身行为由各自测试覆盖。

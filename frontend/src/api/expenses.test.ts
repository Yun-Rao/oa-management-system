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

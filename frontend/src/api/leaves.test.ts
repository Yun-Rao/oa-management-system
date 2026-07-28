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

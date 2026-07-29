import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { client } from "./client";
import { getUnreadCount, listNotifications, markAllRead, markRead } from "./notifications";

const mock = new MockAdapter(client);

const item = {
  id: "n1",
  type: "leave_submitted",
  title: "新的待审批任务",
  content: "张三 提交了 2026-08-01 ~ 2026-08-02 的事假申请,待您审批",
  ref_type: "leave",
  ref_id: "L1",
  read_at: null,
  created_at: "2026-07-29T09:00:00",
};

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

describe("listNotifications", () => {
  it("全部:不传 is_read", async () => {
    mock.onGet("/notifications").reply((config) => [
      200,
      { items: [item], total: 1, page: 1, page_size: 20, _params: config.params },
    ]);
    const resp = await listNotifications({ page: 1, page_size: 20 });
    expect(resp.items).toHaveLength(1);
    expect((resp as unknown as { _params: object })._params).toEqual({
      page: 1,
      page_size: 20,
    });
  });

  it("未读:is_read=false 透传", async () => {
    mock.onGet("/notifications").reply((config) => [
      200,
      { items: [], total: 0, page: 1, page_size: 20, _params: config.params },
    ]);
    await listNotifications({ is_read: false, page: 2, page_size: 20 });
    expect((mock.history.get[0].params as object)).toEqual({
      is_read: false,
      page: 2,
      page_size: 20,
    });
  });
});

describe("getUnreadCount", () => {
  it("返回 count 数值", async () => {
    mock.onGet("/notifications/unread-count").reply(200, { count: 3 });
    expect(await getUnreadCount()).toBe(3);
  });
});

describe("markRead", () => {
  it("POST /notifications/{id}/read 并返回通知", async () => {
    mock.onPost("/notifications/n1/read").reply(200, { ...item, read_at: "2026-07-29T10:00:00" });
    const resp = await markRead("n1");
    expect(resp.read_at).toBe("2026-07-29T10:00:00");
  });
});

describe("markAllRead", () => {
  it("POST /notifications/read-all 并返回 updated 数值", async () => {
    mock.onPost("/notifications/read-all").reply(200, { updated: 5 });
    expect(await markAllRead()).toBe(5);
  });
});

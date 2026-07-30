import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { client } from "./client";
import { getDashboard } from "./dashboard";

const mock = new MockAdapter(client);

const summary = {
  month: "2026-07",
  leave_stats: [
    { department_id: "d1", department_name: "技术部", request_count: 5, total_days: 11.5 },
  ],
  expense_stats: [
    { department_id: "d1", department_name: "技术部", request_count: 8, total_amount: "12345.60" },
  ],
  approval_durations: [
    { category: "leave", completed_count: 12, avg_hours: 20.4 },
    { category: "expense", completed_count: 9, avg_hours: null },
  ],
};

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

describe("getDashboard", () => {
  it("带 month 参数透传", async () => {
    mock.onGet("/dashboard").reply(200, summary);
    const resp = await getDashboard("2026-07");
    expect(resp.month).toBe("2026-07");
    expect(resp.expense_stats[0].total_amount).toBe("12345.60");
    expect(mock.history.get[0].params).toEqual({ month: "2026-07" });
  });

  it("省略 month 时不带参数", async () => {
    mock.onGet("/dashboard").reply(200, summary);
    await getDashboard();
    expect(mock.history.get[0].params).toEqual({});
  });
});

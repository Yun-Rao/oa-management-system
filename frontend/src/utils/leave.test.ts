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

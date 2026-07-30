import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

import { getLeaveDetail } from "../../api/leaves";
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

  it("employee(仅 create+list):仅『我的申请』Tab", () => {
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

describe("通知跳转联动", () => {
  const leaveDetail = {
    id: "L1",
    type: "personal",
    start_date: "2026-08-01",
    end_date: "2026-08-02",
    reason: "私事",
    status: "approved",
    applicant: { id: "u1", name: "张三" },
    approver: { id: "u2", name: "主管" },
    created_at: "2026-07-29T09:00:00",
    history: [],
  };

  function renderWithState() {
    useAuthStore.setState({ token: "t", user: userWith(["leave:list"]) });
    return render(
      <MemoryRouter initialEntries={[{ pathname: "/leaves", state: { openLeaveId: "L1" } }]}>
        <Routes>
          <Route path="/leaves" element={<LeavesPage />} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("携带 openLeaveId state 进入:自动打开详情弹窗", async () => {
    vi.mocked(getLeaveDetail).mockResolvedValue(leaveDetail);
    renderWithState();
    expect(await screen.findByText("请假详情")).toBeInTheDocument();
    expect(getLeaveDetail).toHaveBeenCalledWith("L1");
  });

  it("关闭详情弹窗:清除 state,弹窗消失", async () => {
    vi.mocked(getLeaveDetail).mockResolvedValue(leaveDetail);
    renderWithState();
    await screen.findByText("请假详情");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(screen.queryByText("请假详情")).not.toBeInTheDocument()
    );
  });
});

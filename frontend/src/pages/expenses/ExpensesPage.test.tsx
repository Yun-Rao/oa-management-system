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

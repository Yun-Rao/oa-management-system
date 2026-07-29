import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import dayjs from "dayjs";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./LeaveStatsSection", () => ({ default: () => <div>请假统计区</div> }));
vi.mock("./ExpenseStatsSection", () => ({ default: () => <div>报销统计区</div> }));
vi.mock("./DurationSection", () => ({ default: () => <div>时效统计区</div> }));
vi.mock("../../api/dashboard", () => ({ getDashboard: vi.fn() }));

import { getDashboard } from "../../api/dashboard";
import { ApiError } from "../../api/client";
import { useAuthStore } from "../../store/auth";
import type { CurrentUser, DashboardSummary } from "../../types/api";
import DashboardPage from "./DashboardPage";

function userWith(permissions: string[]): CurrentUser {
  return {
    id: "u1", email: "a@x.com", name: "用户", is_active: true,
    roles: [], department: null, manager: null, permissions,
  };
}

const summary: DashboardSummary = {
  month: "2026-07",
  leave_stats: [],
  expense_stats: [],
  approval_durations: [],
};

function PathProbe() {
  const loc = useLocation();
  return <div data-testid="path">{loc.pathname}</div>;
}

function renderPage(perms: string[]) {
  useAuthStore.setState({ token: "t", user: userWith(perms) });
  return render(
    <App>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/" element={<PathProbe />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(getDashboard).mockResolvedValue(summary);
});

describe("DashboardPage", () => {
  it("无 dashboard:view:重定向首页", async () => {
    renderPage([]);
    expect(await screen.findByTestId("path")).toHaveTextContent("/");
  });

  it("默认以当前月拉取并渲染三个统计区", async () => {
    renderPage(["dashboard:view"]);
    expect(await screen.findByText("请假统计区")).toBeInTheDocument();
    expect(screen.getByText("报销统计区")).toBeInTheDocument();
    expect(screen.getByText("时效统计区")).toBeInTheDocument();
    expect(getDashboard).toHaveBeenCalledWith(dayjs().format("YYYY-MM"));
  });

  it("切月份:带新 YYYY-MM 参数重拉", async () => {
    renderPage(["dashboard:view"]);
    await screen.findByText("请假统计区");
    const target = dayjs().month() === 0 ? "02" : "01";
    const targetTitle = `${dayjs().year()}-${target}`;
    const user = userEvent.setup();
    const input = document.querySelector(".ant-picker input") as HTMLElement;
    await user.click(input);
    const cell = await waitFor(() => {
      const el = document.querySelector(`.ant-picker-cell[title="${targetTitle}"]`);
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    await user.click(cell);
    await waitFor(() => expect(getDashboard).toHaveBeenCalledWith(targetTitle));
  });

  it("拉取失败:显示错误 Alert", async () => {
    vi.mocked(getDashboard).mockRejectedValue(new ApiError("INTERNAL", "服务器错误"));
    renderPage(["dashboard:view"]);
    expect(await screen.findByText("服务器错误")).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/notifications", () => ({
  getUnreadCount: vi.fn().mockResolvedValue(2),
}));

import { getUnreadCount } from "../api/notifications";
import { useAuthStore } from "../store/auth";
import { useNotificationStore } from "../store/notification";
import type { CurrentUser } from "../types/api";
import MainLayout from "./MainLayout";

function fakeUser(): CurrentUser {
  return {
    id: "u1", email: "a@x.com", name: "用户", is_active: true,
    roles: [], department: null, manager: null, permissions: [],
  };
}

function PathProbe() {
  const loc = useLocation();
  return <div data-testid="path">{loc.pathname}</div>;
}

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<PathProbe />} />
          <Route path="notifications" element={<PathProbe />} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useAuthStore.setState({ token: "t", user: fakeUser() });
  useNotificationStore.setState({ unreadCount: 0 });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("MainLayout 通知角标", () => {
  it("挂载即拉取未读数并渲染角标", async () => {
    renderLayout();
    await waitFor(() => expect(useNotificationStore.getState().unreadCount).toBe(2));
    expect(await screen.findByText("2")).toBeInTheDocument();
  });

  it("每 30s 轮询一次", async () => {
    vi.useFakeTimers();
    renderLayout();
    await vi.advanceTimersByTimeAsync(0);
    expect(getUnreadCount).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(getUnreadCount).toHaveBeenCalledTimes(2);
  });

  it("卸载后停止轮询", async () => {
    vi.useFakeTimers();
    const { unmount } = renderLayout();
    await vi.advanceTimersByTimeAsync(0);
    unmount();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(getUnreadCount).toHaveBeenCalledTimes(1);
  });

  it("点击铃铛跳转 /notifications", async () => {
    renderLayout();
    const user = userEvent.setup();
    await user.click(screen.getByRole("img", { name: "通知" }));
    expect(await screen.findByTestId("path")).toHaveTextContent("/notifications");
  });
});

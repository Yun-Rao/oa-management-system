import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/notifications", () => ({
  listNotifications: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
}));

import { listNotifications, markAllRead, markRead } from "../../api/notifications";
import { useNotificationStore } from "../../store/notification";
import type { NotificationItem } from "../../types/api";
import NotificationsPage from "./NotificationsPage";

const mockedList = vi.mocked(listNotifications);
const mockedMarkRead = vi.mocked(markRead);
const mockedMarkAll = vi.mocked(markAllRead);

function item(over: Partial<NotificationItem>): NotificationItem {
  return {
    id: "n1",
    type: "leave_submitted",
    title: "新的待审批任务",
    content: "张三 提交了请假申请",
    ref_type: "leave",
    ref_id: "L1",
    read_at: null,
    created_at: "2026-07-29T09:00:00",
    ...over,
  };
}

function LeavesProbe() {
  const loc = useLocation();
  return <div data-testid="leaves-state">{JSON.stringify(loc.state)}</div>;
}

function renderPage() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/notifications"]}>
        <Routes>
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/leaves" element={<LeavesProbe />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useNotificationStore.setState({ unreadCount: 1 });
  mockedList.mockResolvedValue({ items: [item({})], total: 1, page: 1, page_size: 20 });
});

describe("NotificationsPage", () => {
  it("默认『全部』Tab:不传 is_read,渲染标题与内容", async () => {
    renderPage();
    expect(await screen.findByText("新的待审批任务")).toBeInTheDocument();
    expect(screen.getByText("张三 提交了请假申请")).toBeInTheDocument();
    expect(mockedList).toHaveBeenCalledWith({ page: 1, page_size: 20 });
  });

  it("切到『未读』Tab:is_read=false 且重置第 1 页", async () => {
    renderPage();
    await screen.findByText("新的待审批任务");
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "未读" }));
    await waitFor(() =>
      expect(mockedList).toHaveBeenLastCalledWith({
        is_read: false,
        page: 1,
        page_size: 20,
      })
    );
  });

  it("点击未读条目:标记已读 + 角标减一 + 跳转请假详情", async () => {
    mockedMarkRead.mockResolvedValue(item({ read_at: "2026-07-29T10:00:00" }));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("新的待审批任务"));
    await waitFor(() => expect(mockedMarkRead).toHaveBeenCalledWith("n1"));
    await waitFor(() =>
      expect(screen.getByTestId("leaves-state")).toHaveTextContent('{"openLeaveId":"L1"}')
    );
    expect(useNotificationStore.getState().unreadCount).toBe(0);
  });

  it("点击已读条目:不调 markRead,直接跳转", async () => {
    mockedList.mockResolvedValue({
      items: [item({ read_at: "2026-07-29T10:00:00" })],
      total: 1,
      page: 1,
      page_size: 20,
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("新的待审批任务"));
    await waitFor(() =>
      expect(screen.getByTestId("leaves-state")).toHaveTextContent('{"openLeaveId":"L1"}')
    );
    expect(mockedMarkRead).not.toHaveBeenCalled();
  });

  it("全部已读:markAllRead + 角标清零 + 重拉列表", async () => {
    mockedMarkAll.mockResolvedValue(3);
    renderPage();
    await screen.findByText("新的待审批任务");
    mockedList.mockClear();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "全部已读" }));
    await waitFor(() => expect(mockedMarkAll).toHaveBeenCalledOnce());
    expect(useNotificationStore.getState().unreadCount).toBe(0);
    await waitFor(() => expect(mockedList).toHaveBeenCalledOnce());
  });

  it("分页:点击第 2 页重新拉取", async () => {
    mockedList.mockResolvedValue({ items: [item({})], total: 21, page: 1, page_size: 20 });
    renderPage();
    await screen.findByText("新的待审批任务");
    const user = userEvent.setup();
    await user.click(screen.getByTitle("2"));
    await waitFor(() =>
      expect(mockedList).toHaveBeenLastCalledWith({ page: 2, page_size: 20 })
    );
  });
});

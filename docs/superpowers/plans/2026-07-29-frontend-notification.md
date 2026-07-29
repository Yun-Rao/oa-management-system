# P1 消息通知(前端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现消息通知前端:Header 铃铛未读角标(30s 轮询)、`/notifications` 消息中心页(全部/未读 Tab、分页、单条/全部标记已读)、点击通知跳转 `/leaves` 自动打开请假详情弹窗。

**Architecture:** 镜像既有前端分层 `api → store → components/pages`;新建 `useNotificationStore` 只持 `unreadCount`,页面本地态管列表;通知模块与请假模块仅靠路由 state(`openLeaveId`)耦合,`LeaveDetailModal` 零改动复用。

**Tech Stack:** React 18 + antd 5 + zustand 4 + react-router 6 + axios;vitest + Testing Library + axios-mock-adapter。

## Global Constraints

- 工作分支:`feature/frontend-notification`(已在此分支,不切分支)
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- Commit message:中文 Conventional Commits(参照 git log 现有风格,如 `feat(frontend): ...`)
- 设计依据:`docs/superpowers/specs/2026-07-29-frontend-notification-design.md`,实现必须与 spec 一致
- 不改 backend/、不引入新前端依赖(antd/zustand/axios/dayjs/react-router 均已存在)
- 测试命令工作目录为 `frontend/`:`npx vitest run <file>`(单文件)/ `npm test`(全量)
- store 只持有 `unreadCount` 一个数;轮询失败静默不弹错;无新权限点(登录即可)
- 后端接口形状(已上线,直接消费):`GET /notifications?is_read=<bool>&page=&page_size=` → `{items,total,page,page_size}`;`GET /notifications/unread-count` → `{count}`;`POST /notifications/{id}/read` → 通知对象(幂等);`POST /notifications/read-all` → `{updated}`

---

### Task 1: 通知 api 层 + 类型

**Files:**
- Modify: `frontend/src/types/api.ts`(文件末尾追加)
- Create: `frontend/src/api/notifications.ts`
- Test: `frontend/src/api/notifications.test.ts`

**Interfaces:**
- Consumes: 既有 `client`(axios 实例,`frontend/src/api/client.ts`)
- Produces: `NotificationItem` / `NotificationListResponse` 类型;`listNotifications({is_read?, page, page_size})` / `getUnreadCount(): Promise<number>` / `markRead(id): Promise<NotificationItem>` / `markAllRead(): Promise<number>`——Task 2/3 全部消费这些签名

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/api/notifications.test.ts`:

```tsx
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/api/notifications.test.ts`
Expected: FAIL,`Failed to resolve import "./notifications"`

- [ ] **Step 3: Write types + api**

修改 `frontend/src/types/api.ts`,文件末尾追加:

```ts
export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  content: string;
  ref_type: string;
  ref_id: string;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
}
```

创建 `frontend/src/api/notifications.ts`:

```ts
import { client } from "./client";
import type { NotificationItem, NotificationListResponse } from "../types/api";

export async function listNotifications(params: {
  is_read?: boolean;
  page: number;
  page_size: number;
}): Promise<NotificationListResponse> {
  const { data } = await client.get<NotificationListResponse>("/notifications", { params });
  return data;
}

export async function getUnreadCount(): Promise<number> {
  const { data } = await client.get<{ count: number }>("/notifications/unread-count");
  return data.count;
}

export async function markRead(id: string): Promise<NotificationItem> {
  const { data } = await client.post<NotificationItem>(`/notifications/${id}/read`);
  return data;
}

export async function markAllRead(): Promise<number> {
  const { data } = await client.post<{ updated: number }>("/notifications/read-all");
  return data.updated;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/api/notifications.test.ts`
Expected: 5 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/notifications.ts frontend/src/api/notifications.test.ts
git commit -m "feat(frontend): 通知 api 层与类型定义"
```

---

### Task 2: notification store + MainLayout 铃铛角标

**Files:**
- Create: `frontend/src/store/notification.ts`
- Modify: `frontend/src/components/MainLayout.tsx`(全文件替换)
- Test: `frontend/src/components/MainLayout.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `getUnreadCount()`
- Produces: `useNotificationStore`:`{ unreadCount: number; refresh(): Promise<void>; decrement(n: number): void; clear(): void }`——Task 3 消费 `decrement`/`clear`;MainLayout 在 Header 渲染 `Badge count={unreadCount}` + 铃铛(aria-label="通知")

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/components/MainLayout.test.tsx`:

```tsx
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/MainLayout.test.tsx`
Expected: FAIL,`Failed to resolve import "../store/notification"`

- [ ] **Step 3: Write store + MainLayout**

创建 `frontend/src/store/notification.ts`:

```ts
import { create } from "zustand";

import { getUnreadCount } from "../api/notifications";

interface NotificationState {
  unreadCount: number;
  refresh: () => Promise<void>;
  decrement: (n: number) => void;
  clear: () => void;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  unreadCount: 0,

  async refresh() {
    try {
      const count = await getUnreadCount();
      set({ unreadCount: count });
    } catch {
      // 轮询失败静默,下轮重试
    }
  },

  decrement(n) {
    set({ unreadCount: Math.max(0, get().unreadCount - n) });
  },

  clear() {
    set({ unreadCount: 0 });
  },
}));
```

全文件替换 `frontend/src/components/MainLayout.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Badge, Dropdown, Layout, Menu } from "antd";
import { BellOutlined } from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../store/auth";
import { useNotificationStore } from "../store/notification";
import ChangePasswordModal from "./ChangePasswordModal";
import { MENU_ITEMS } from "./menu";

export default function MainLayout() {
  const user = useAuthStore((s) => s.user);
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const refresh = useNotificationStore((s) => s.refresh);
  const navigate = useNavigate();
  const location = useLocation();
  const [pwdOpen, setPwdOpen] = useState(false);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(timer);
  }, [refresh]);

  const items = MENU_ITEMS.filter(
    (m) => m.permission === null || hasPermission(m.permission)
  ).map((m) => ({ key: m.key, icon: m.icon, label: m.label }));

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider theme="light">
        <div
          style={{
            height: 48,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 600,
          }}
        >
          OA 管理系统
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          onClick={({ key }) => navigate(key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{
            background: "#fff",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            padding: "0 24px",
            gap: 24,
          }}
        >
          <Badge count={unreadCount} size="small">
            <BellOutlined
              style={{ fontSize: 18, cursor: "pointer" }}
              aria-label="通知"
              onClick={() => navigate("/notifications")}
            />
          </Badge>
          <Dropdown
            menu={{
              items: [
                { key: "change-password", label: "修改密码" },
                { key: "logout", label: "退出登录" },
              ],
              onClick: ({ key }) => {
                if (key === "change-password") setPwdOpen(true);
                if (key === "logout") {
                  useAuthStore.getState().logout();
                  navigate("/login");
                }
              },
            }}
          >
            <span style={{ cursor: "pointer" }}>{user?.name}</span>
          </Dropdown>
        </Layout.Header>
        <Layout.Content style={{ margin: 16 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
      <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
    </Layout>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/MainLayout.test.tsx`
Expected: 4 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/notification.ts frontend/src/components/MainLayout.tsx frontend/src/components/MainLayout.test.tsx
git commit -m "feat(frontend): 通知未读数 store 与 Header 铃铛角标轮询"
```

---

### Task 3: 消息中心页 + 路由

**Files:**
- Create: `frontend/src/pages/notifications/NotificationsPage.tsx`
- Modify: `frontend/src/App.tsx`(import 行 + children 路由)
- Test: `frontend/src/pages/notifications/NotificationsPage.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `listNotifications/markRead/markAllRead`;Task 2 的 `useNotificationStore.decrement/clear`
- Produces: 路由 `/notifications`(RequireAuth 内,无权限门控);点击条目 `navigate("/leaves", { state: { openLeaveId: ref_id } })`——Task 4 消费该 state

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/notifications/NotificationsPage.test.tsx`:

```tsx
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/notifications/NotificationsPage.test.tsx`
Expected: FAIL,`Failed to resolve import "./NotificationsPage"`

- [ ] **Step 3: Write page + route**

创建 `frontend/src/pages/notifications/NotificationsPage.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Card, List, Space, Tabs, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";

import { listNotifications, markAllRead, markRead } from "../../api/notifications";
import { ApiError } from "../../api/client";
import { useNotificationStore } from "../../store/notification";
import type { NotificationItem } from "../../types/api";

const PAGE_SIZE = 20;

type TabKey = "all" | "unread";

export default function NotificationsPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const decrement = useNotificationStore((s) => s.decrement);
  const clear = useNotificationStore((s) => s.clear);
  const [tab, setTab] = useState<TabKey>("all");
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchList = useCallback(async (t: TabKey, p: number) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listNotifications({
        ...(t === "unread" ? { is_read: false } : {}),
        page: p,
        page_size: PAGE_SIZE,
      });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList(tab, page);
  }, [tab, page, fetchList]);

  async function onClickItem(n: NotificationItem) {
    if (!n.read_at) {
      try {
        await markRead(n.id);
        decrement(1);
        setItems((prev) =>
          prev.map((x) =>
            x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x
          )
        );
      } catch (e) {
        message.error(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      }
    }
    if (n.ref_type === "leave") {
      navigate("/leaves", { state: { openLeaveId: n.ref_id } });
    }
  }

  async function onReadAll() {
    try {
      await markAllRead();
      clear();
      await fetchList(tab, page);
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    }
  }

  return (
    <Card
      title="消息中心"
      extra={<Button onClick={onReadAll}>全部已读</Button>}
    >
      <Tabs
        activeKey={tab}
        onChange={(k) => {
          setTab(k as TabKey);
          setPage(1);
        }}
        items={[
          { key: "all", label: "全部" },
          { key: "unread", label: "未读" },
        ]}
      />
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <List
        rowKey="id"
        loading={loading}
        dataSource={items}
        pagination={{
          current: page,
          total,
          pageSize: PAGE_SIZE,
          showSizeChanger: false,
          onChange: setPage,
        }}
        renderItem={(n) => (
          <List.Item onClick={() => void onClickItem(n)} style={{ cursor: "pointer" }}>
            <List.Item.Meta
              title={
                <Space>
                  {!n.read_at && <Tag color="blue">未读</Tag>}
                  <Typography.Text strong={!n.read_at}>{n.title}</Typography.Text>
                </Space>
              }
              description={n.content}
            />
            <Typography.Text type="secondary">
              {dayjs(n.created_at).format("YYYY-MM-DD HH:mm")}
            </Typography.Text>
          </List.Item>
        )}
      />
    </Card>
  );
}
```

修改 `frontend/src/App.tsx`:

- import 区在 `import LoginPage from "./pages/LoginPage";` 之后加一行:`import NotificationsPage from "./pages/notifications/NotificationsPage";`
- children 数组在 `{ path: "leaves", element: <LeavesPage /> },` 之后加一行:`{ path: "notifications", element: <NotificationsPage /> },`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/notifications/NotificationsPage.test.tsx`
Expected: 6 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/notifications/NotificationsPage.tsx frontend/src/pages/notifications/NotificationsPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): 消息中心页与 /notifications 路由"
```

---

### Task 4: LeavesPage 详情弹窗联动

**Files:**
- Modify: `frontend/src/pages/leaves/LeavesPage.tsx`(全文件替换)
- Test: `frontend/src/pages/leaves/LeavesPage.test.tsx`(文件末尾追加 2 个测试)

**Interfaces:**
- Consumes: Task 3 的 `navigate("/leaves", { state: { openLeaveId } })`;既有 `LeaveDetailModal({ leaveId: string | null, onClose: () => void })` 与 `getLeaveDetail(id)`(均零改动)
- Produces: 无新接口;行为契约:带 `location.state.openLeaveId` 进入 `/leaves` 自动打开详情弹窗,关闭弹窗清除 state

- [ ] **Step 1: Write the failing tests**

在 `frontend/src/pages/leaves/LeavesPage.test.tsx` 文件末尾(最后一个 `});` 之后)追加:

```tsx
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
```

同时确认该文件顶部 import 已含 `userEvent`、`waitFor`、`getLeaveDetail`;缺失则补上:

- `import userEvent from "@testing-library/user-event";`(若缺)
- `render, screen` 后加 `waitFor`:`import { render, screen, waitFor } from "@testing-library/react";`
- 在既有 `import LeavesPage from "./LeavesPage";` 前加:`import { getLeaveDetail } from "../../api/leaves";`

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/leaves/LeavesPage.test.tsx`
Expected: 新增 2 个 FAIL(弹窗未出现)

- [ ] **Step 3: Modify LeavesPage**

全文件替换 `frontend/src/pages/leaves/LeavesPage.tsx`:

```tsx
import { useState } from "react";
import { Card, Tabs } from "antd";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import AllLeavesPanel from "./AllLeavesPanel";
import LeaveDetailModal from "./LeaveDetailModal";
import MyLeavesPanel from "./MyLeavesPanel";
import TodoLeavesPanel from "./TodoLeavesPanel";

export default function LeavesPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("leave:list");
  const location = useLocation();
  const navigate = useNavigate();
  const openLeaveId =
    (location.state as { openLeaveId?: string } | null)?.openLeaveId ?? null;

  const tabs = [
    { key: "mine", label: "我的申请", permission: "leave:list", children: <MyLeavesPanel /> },
    { key: "todo", label: "待我审批", permission: "leave:approve", children: <TodoLeavesPanel /> },
    { key: "all", label: "全部记录", permission: "leave:list_all", children: <AllLeavesPanel /> },
  ].filter((t) => hasPermission(t.permission));

  const [activeKey, setActiveKey] = useState<string | null>(null);

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return (
    <Card title="请假审批">
      <Tabs
        activeKey={activeKey ?? tabs[0]?.key}
        onChange={setActiveKey}
        items={tabs.map(({ key, label, children }) => ({ key, label, children }))}
      />
      <LeaveDetailModal
        leaveId={openLeaveId}
        onClose={() => navigate(".", { replace: true, state: null })}
      />
    </Card>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/leaves/LeavesPage.test.tsx`
Expected: 全部 PASS(既有 + 新增 2 个)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/leaves/LeavesPage.tsx frontend/src/pages/leaves/LeavesPage.test.tsx
git commit -m "feat(frontend): 通知点击跳转请假详情弹窗联动"
```

---

### Task 5: 全量验收 + spec 勾选

**Files:**
- Modify: `docs/superpowers/specs/2026-07-29-frontend-notification-design.md`(§10 五个 `- [ ]` → `- [x]`)

**Interfaces:**
- Consumes: Task 1-4 全部产出
- Produces: 可 PR 的完整分支

- [ ] **Step 1: Run full frontend test suite + typecheck**

Run: `cd frontend && npm test`
Expected: 全部 PASS(既有 + 本分支新增,无回归)

Run: `cd frontend && npm run typecheck`
Expected: 0 errors

- [ ] **Step 2: Browser 验收(必做)**

用 chrome-devtools MCP 驱动浏览器实测(前端 `npm run dev` + 后端已 seed,admin 账号 `admin@company.com` / `Admin123!`):

1. 登录后 Header 出现铃铛与未读数角标;制造一条新通知(另一账号提交请假),≤30s 角标 +1
2. 点击铃铛进入 `/notifications`,列表展示通知;切"未读"Tab 只剩未读
3. 点击一条未读通知 → 跳转 `/leaves` 且自动打开详情弹窗,角标 -1;关闭弹窗后再点铃铛回列表,该条已变已读样式
4. 点击"全部已读" → 角标清零、列表无"未读"Tag
5. 每个场景截图存档

- [ ] **Step 3: Tick spec acceptance boxes**

把 `docs/superpowers/specs/2026-07-29-frontend-notification-design.md` §10 的 5 个 `- [ ]` 全部改为 `- [x]`。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-29-frontend-notification-design.md
git commit -m "test(frontend): 消息通知模块全量验收通过,勾选 spec 验收标准"
```

---

## Self-Review 记录

- **Spec 覆盖**:§3 接口→Task 1;§4 单元表→Task 1(api/类型)/Task 2(store/MainLayout)/Task 3(页面/路由)/Task 4(LeavesPage 联动);§5 数据流→Task 2(轮询)/Task 3(点击/全部已读/Tab);§6 扩展预留→Task 3 `ref_type === "leave"` 分支(未知类型不跳转);§7 错误处理→Task 2 静默轮询/Task 3 message+Alert;§8 测试策略→各任务测试;§9 部署→无;§10 验收→Task 5 勾选。
- **占位符扫描**:无 TBD/TODO;所有代码块完整可复制。
- **类型一致性**:`listNotifications/getUnreadCount/markRead/markAllRead` Task 1 定义、Task 2/3 消费一致;`useNotificationStore` 四成员 Task 2 定义、Task 3 消费 `decrement/clear` 一致;`openLeaveId` state Task 3 生产、Task 4 消费键名一致;`NotificationItem` 字段与后端 `NotificationResponse` 一致。
- **已知取舍**:①store 无独立测试文件——spec §8 明确经组件测试间接覆盖(MainLayout 测试覆盖 refresh/轮询,NotificationsPage 测试覆盖 decrement/clear);②点击未读条目本地 `read_at` 用 `new Date().toISOString()` 仅驱动样式,刷新后以后端值为准;③MainLayout 测试中铃铛用 `role="img" name="通知"` 定位(antd 图标透传 aria-label)。

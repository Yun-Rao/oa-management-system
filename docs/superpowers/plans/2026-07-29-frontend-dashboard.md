# 数据看板(前端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现数据看板前端:`/dashboard` 独立页面(MonthPicker 切月 + 部门请假/报销统计 + 审批时效),菜单与路由接线;零后端改动。

**Architecture:** 页面壳 + 三 Section 纯展示组件(方案 B,与 expenses「页面壳 + Panel」同构);页面本地态持 month(Dayjs),useEffect 带 cancelled 清理拉数;纯 antd(Statistic + Table + Card),零新依赖。

**Tech Stack:** React 18 + antd 5 + zustand 4 + react-router 6 + axios + dayjs;vitest + Testing Library + axios-mock-adapter。

## Global Constraints

- 工作分支:`feature/frontend-dashboard`(已在此分支,不切分支;分支已含合并后的报销前端代码)
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- Commit message:中文 Conventional Commits(参照 git log 现有风格,如 `feat(frontend): ...`)
- 设计依据:`docs/superpowers/specs/2026-07-29-frontend-dashboard-design.md`,实现必须与 spec 一致;后端契约冻结于 `docs/superpowers/specs/2026-07-28-dashboard-design.md` §3,**不改任何后端文件**
- 不引入新前端依赖;不改动请假/报销/通知模块任何文件
- 金额 `total_amount` 为字符串(Decimal 序列化):明细行 `¥{total_amount}` 直拼;**唯一浮点例外**——汇总卡片「总金额合计」允许 `Number` 求和后 `toFixed(2)`(仅展示层)
- 测试断言注意:测试渲染不含 ConfigProvider,antd 用**英文**默认文案(空表 = `No data`);jsdom `getComputedStyle` stderr 警告为环境固有噪声,非缺陷
- 测试命令工作目录:前端 `frontend/`:`npx vitest run <file>`(单文件)/ `npm test`(全量)/ `npm run typecheck`;后端 `backend/`:`python -m pytest tests/ -q`(本机无 uv,`python` 不在 PATH 用 `/d/Application/anaconda3/python -m pytest`)
- 本机 localhost IPv6 坑:后端连库 / vite 代理若挂起,主机名改 `127.0.0.1` 或 `NODE_OPTIONS=--dns-result-order=ipv4first`
- 验收截图必须存持久目录 `.superpowers/sdd/acceptance/`(`dash-` 前缀),**禁止**放在 SDD workspace

---

### Task 1: 前端类型 + dashboard api 层

**Files:**
- Modify: `frontend/src/types/api.ts`(文件末尾追加)
- Create: `frontend/src/api/dashboard.ts`
- Test: `frontend/src/api/dashboard.test.ts`

**Interfaces:**
- Consumes: 既有 `client` / `ApiError`(`frontend/src/api/client.ts`)
- Produces: 类型 `LeaveStatItem` / `ExpenseStatItem` / `ApprovalDurationItem` / `DashboardSummary`;函数 `getDashboard(month?: string): Promise<DashboardSummary>`——Task 2-4 全部消费

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/api/dashboard.test.ts`:

```tsx
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/api/dashboard.test.ts`
Expected: FAIL,`Failed to resolve import "./dashboard"`

- [ ] **Step 3: Write types + api**

修改 `frontend/src/types/api.ts`,文件末尾追加:

```ts
export interface LeaveStatItem {
  department_id: string;
  department_name: string;
  request_count: number;
  total_days: number;
}

export interface ExpenseStatItem {
  department_id: string;
  department_name: string;
  request_count: number;
  total_amount: string;
}

export interface ApprovalDurationItem {
  category: string;
  completed_count: number;
  avg_hours: number | null;
}

export interface DashboardSummary {
  month: string;
  leave_stats: LeaveStatItem[];
  expense_stats: ExpenseStatItem[];
  approval_durations: ApprovalDurationItem[];
}
```

创建 `frontend/src/api/dashboard.ts`:

```ts
import { client } from "./client";
import type { DashboardSummary } from "../types/api";

export async function getDashboard(month?: string): Promise<DashboardSummary> {
  const { data } = await client.get<DashboardSummary>("/dashboard", {
    params: month ? { month } : {},
  });
  return data;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/api/dashboard.test.ts`
Expected: 2 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/dashboard.ts frontend/src/api/dashboard.test.ts
git commit -m "feat(frontend): 数据看板 api 层与类型定义"
```

---

### Task 2: 请假/报销统计 Section

**Files:**
- Create: `frontend/src/pages/dashboard/LeaveStatsSection.tsx`
- Create: `frontend/src/pages/dashboard/ExpenseStatsSection.tsx`
- Test: `frontend/src/pages/dashboard/LeaveStatsSection.test.tsx`
- Test: `frontend/src/pages/dashboard/ExpenseStatsSection.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `LeaveStatItem` / `ExpenseStatItem` 类型
- Produces: `LeaveStatsSection({ stats: LeaveStatItem[] })` / `ExpenseStatsSection({ stats: ExpenseStatItem[] })`(Task 4 消费)

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/dashboard/LeaveStatsSection.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { LeaveStatItem } from "../../types/api";
import LeaveStatsSection from "./LeaveStatsSection";

const rows: LeaveStatItem[] = [
  { department_id: "d1", department_name: "技术部", request_count: 5, total_days: 11.5 },
  { department_id: "d2", department_name: "市场部", request_count: 3, total_days: 4.5 },
];

describe("LeaveStatsSection", () => {
  it("明细渲染部门行;汇总求和:总人次 8、总天数 16", () => {
    render(<LeaveStatsSection stats={rows} />);
    expect(screen.getByText("技术部")).toBeInTheDocument();
    expect(screen.getByText("市场部")).toBeInTheDocument();
    expect(screen.getByText("总人次").parentElement).toHaveTextContent("8");
    expect(screen.getByText("总天数").parentElement).toHaveTextContent("16");
  });

  it("空数组:汇总为 0,表格空态", () => {
    render(<LeaveStatsSection stats={[]} />);
    expect(screen.getByText("总人次").parentElement).toHaveTextContent("0");
    expect(screen.getByText("No data")).toBeInTheDocument();
  });
});
```

创建 `frontend/src/pages/dashboard/ExpenseStatsSection.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ExpenseStatItem } from "../../types/api";
import ExpenseStatsSection from "./ExpenseStatsSection";

const rows: ExpenseStatItem[] = [
  { department_id: "d1", department_name: "技术部", request_count: 8, total_amount: "12345.60" },
  { department_id: "d2", department_name: "市场部", request_count: 2, total_amount: "100.40" },
];

describe("ExpenseStatsSection", () => {
  it("明细金额 ¥ 直拼;汇总总金额 Number 求和 toFixed(2)", () => {
    render(<ExpenseStatsSection stats={rows} />);
    expect(screen.getByText("¥12345.60")).toBeInTheDocument();
    expect(screen.getByText("¥100.40")).toBeInTheDocument();
    expect(screen.getByText("¥12446.00")).toBeInTheDocument();
    expect(screen.getByText("总笔数").parentElement).toHaveTextContent("10");
  });

  it("空数组:汇总 0 与 ¥0.00,表格空态", () => {
    render(<ExpenseStatsSection stats={[]} />);
    expect(screen.getByText("总笔数").parentElement).toHaveTextContent("0");
    expect(screen.getByText("¥0.00")).toBeInTheDocument();
    expect(screen.getByText("No data")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/dashboard/LeaveStatsSection.test.tsx src/pages/dashboard/ExpenseStatsSection.test.tsx`
Expected: FAIL,`Failed to resolve import "./LeaveStatsSection"` / `"./ExpenseStatsSection"`

- [ ] **Step 3: Write the sections**

创建 `frontend/src/pages/dashboard/LeaveStatsSection.tsx`:

```tsx
import { Card, Col, Row, Statistic, Table } from "antd";

import type { LeaveStatItem } from "../../types/api";

interface Props {
  stats: LeaveStatItem[];
}

export default function LeaveStatsSection({ stats }: Props) {
  const totalCount = stats.reduce((s, x) => s + x.request_count, 0);
  const totalDays = stats.reduce((s, x) => s + x.total_days, 0);

  const columns = [
    { title: "部门", dataIndex: "department_name", key: "department_name" },
    { title: "请假人次", dataIndex: "request_count", key: "request_count" },
    { title: "请假天数", dataIndex: "total_days", key: "total_days" },
  ];

  return (
    <Card title="部门请假统计" style={{ marginBottom: 16 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic title="总人次" value={totalCount} />
        </Col>
        <Col span={6}>
          <Statistic title="总天数" value={totalDays} />
        </Col>
      </Row>
      <Table<LeaveStatItem>
        rowKey="department_id"
        columns={columns}
        dataSource={stats}
        pagination={false}
      />
    </Card>
  );
}
```

创建 `frontend/src/pages/dashboard/ExpenseStatsSection.tsx`:

```tsx
import { Card, Col, Row, Statistic, Table } from "antd";

import type { ExpenseStatItem } from "../../types/api";

interface Props {
  stats: ExpenseStatItem[];
}

function sumAmount(stats: ExpenseStatItem[]): string {
  return stats.reduce((s, x) => s + Number(x.total_amount), 0).toFixed(2);
}

export default function ExpenseStatsSection({ stats }: Props) {
  const totalCount = stats.reduce((s, x) => s + x.request_count, 0);

  const columns = [
    { title: "部门", dataIndex: "department_name", key: "department_name" },
    { title: "报销笔数", dataIndex: "request_count", key: "request_count" },
    {
      title: "报销金额",
      key: "total_amount",
      render: (_: unknown, x: ExpenseStatItem) => `¥${x.total_amount}`,
    },
  ];

  return (
    <Card title="部门报销统计" style={{ marginBottom: 16 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic title="总笔数" value={totalCount} />
        </Col>
        <Col span={6}>
          <Statistic title="总金额" value={`¥${sumAmount(stats)}`} />
        </Col>
      </Row>
      <Table<ExpenseStatItem>
        rowKey="department_id"
        columns={columns}
        dataSource={stats}
        pagination={false}
      />
    </Card>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/dashboard/LeaveStatsSection.test.tsx src/pages/dashboard/ExpenseStatsSection.test.tsx`
Expected: 4 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/dashboard/LeaveStatsSection.tsx frontend/src/pages/dashboard/LeaveStatsSection.test.tsx frontend/src/pages/dashboard/ExpenseStatsSection.tsx frontend/src/pages/dashboard/ExpenseStatsSection.test.tsx
git commit -m "feat(frontend): 数据看板请假/报销统计区块"
```

---

### Task 3: 审批时效 Section

**Files:**
- Create: `frontend/src/pages/dashboard/DurationSection.tsx`
- Test: `frontend/src/pages/dashboard/DurationSection.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `ApprovalDurationItem` 类型
- Produces: `DurationSection({ durations: ApprovalDurationItem[] })`(Task 4 消费)

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/dashboard/DurationSection.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ApprovalDurationItem } from "../../types/api";
import DurationSection from "./DurationSection";

describe("DurationSection", () => {
  it("avg_hours 数值显示 {x} 小时;null 显示 —;类别中文名", () => {
    const durations: ApprovalDurationItem[] = [
      { category: "leave", completed_count: 12, avg_hours: 20.4 },
      { category: "expense", completed_count: 0, avg_hours: null },
    ];
    render(<DurationSection durations={durations} />);
    expect(screen.getByText("20.4 小时")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/请假审批/)).toBeInTheDocument();
    expect(screen.getByText(/报销审批/)).toBeInTheDocument();
    expect(screen.getByText(/完成 12 单/)).toBeInTheDocument();
    expect(screen.getByText(/完成 0 单/)).toBeInTheDocument();
  });

  it("未知 category 原样显示", () => {
    render(
      <DurationSection durations={[{ category: "other", completed_count: 1, avg_hours: 1.5 }]} />
    );
    expect(screen.getByText(/other/)).toBeInTheDocument();
    expect(screen.getByText("1.5 小时")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/dashboard/DurationSection.test.tsx`
Expected: FAIL,`Failed to resolve import "./DurationSection"`

- [ ] **Step 3: Write the section**

创建 `frontend/src/pages/dashboard/DurationSection.tsx`:

```tsx
import { Card, Col, Row, Statistic } from "antd";

import type { ApprovalDurationItem } from "../../types/api";

interface Props {
  durations: ApprovalDurationItem[];
}

const CATEGORY_LABEL: Record<string, string> = {
  leave: "请假审批",
  expense: "报销审批",
};

export default function DurationSection({ durations }: Props) {
  return (
    <Card title="审批时效统计">
      <Row gutter={16}>
        {durations.map((d) => (
          <Col span={6} key={d.category}>
            <Statistic
              title={`${CATEGORY_LABEL[d.category] ?? d.category}平均时效(完成 ${d.completed_count} 单)`}
              value={d.avg_hours === null ? "—" : `${d.avg_hours} 小时`}
            />
          </Col>
        ))}
      </Row>
    </Card>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/dashboard/DurationSection.test.tsx`
Expected: 2 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/dashboard/DurationSection.tsx frontend/src/pages/dashboard/DurationSection.test.tsx
git commit -m "feat(frontend): 数据看板审批时效区块"
```

---

### Task 4: DashboardPage 页面壳 + 菜单 + 路由

**Files:**
- Create: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/components/menu.tsx`(import 行 + MENU_ITEMS 追加)
- Modify: `frontend/src/App.tsx`(import 行 + children 路由)
- Test: `frontend/src/pages/dashboard/DashboardPage.test.tsx`

**Interfaces:**
- Consumes: Task 1 `getDashboard` / `DashboardSummary`;Task 2-3 三个 Section;既有 `useAuthStore.hasPermission`
- Produces: 路由 `/dashboard`(RequireAuth 内);行为契约:无 `dashboard:view` → 重定向 `/`;month 变更 → `getDashboard("YYYY-MM")` 重拉

- [ ] **Step 1: Write the failing tests**

创建 `frontend/src/pages/dashboard/DashboardPage.test.tsx`:

```tsx
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
```

(antd 月份 cell 的 `title` 属性格式为 `YYYY-MM`;若与本机 antd 版本实际 DOM 不符,以实际为准微调选择器——断言目标不变:`getDashboard` 以新 `YYYY-MM` 重拉。)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/dashboard/DashboardPage.test.tsx`
Expected: FAIL,`Failed to resolve import "./DashboardPage"`

- [ ] **Step 3: Write page + menu + route**

创建 `frontend/src/pages/dashboard/DashboardPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Alert, Card, DatePicker, Spin } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { Navigate } from "react-router-dom";

import { getDashboard } from "../../api/dashboard";
import { ApiError } from "../../api/client";
import { useAuthStore } from "../../store/auth";
import type { DashboardSummary } from "../../types/api";
import DurationSection from "./DurationSection";
import ExpenseStatsSection from "./ExpenseStatsSection";
import LeaveStatsSection from "./LeaveStatsSection";

export default function DashboardPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("dashboard:view");
  const [month, setMonth] = useState<Dayjs>(() => dayjs());
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDashboard(month.format("YYYY-MM"))
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [month]);

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return (
    <Card
      title="数据看板"
      extra={
        <DatePicker
          picker="month"
          value={month}
          onChange={(v) => {
            if (v) setMonth(v);
          }}
          allowClear={false}
        />
      }
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        {data && (
          <>
            <LeaveStatsSection stats={data.leave_stats} />
            <ExpenseStatsSection stats={data.expense_stats} />
            <DurationSection durations={data.approval_durations} />
          </>
        )}
      </Spin>
    </Card>
  );
}
```

修改 `frontend/src/components/menu.tsx`:
- import 行把 `BarChartOutlined` 加入 `@ant-design/icons` 的导入列表(保持字母序,排在最前)
- `MENU_ITEMS` 在 expenses 行之后追加:

```ts
  { key: "/dashboard", label: "数据看板", icon: <BarChartOutlined />, permission: "dashboard:view" },
```

修改 `frontend/src/App.tsx`:
- import 区在 `import DepartmentPage from "./pages/departments/DepartmentPage";` 之前加:`import DashboardPage from "./pages/dashboard/DashboardPage";`(路径字母序 dashboard < departments)
- children 数组在 `{ path: "expenses", element: <ExpensesPage /> },` 之后加:`{ path: "dashboard", element: <DashboardPage /> },`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/dashboard/DashboardPage.test.tsx`
Expected: 4 个 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/dashboard/DashboardPage.tsx frontend/src/pages/dashboard/DashboardPage.test.tsx frontend/src/components/menu.tsx frontend/src/App.tsx
git commit -m "feat(frontend): 数据看板页面壳、菜单项与 /dashboard 路由"
```

---

### Task 5: 全量验收 + spec 勾选

**Files:**
- Modify: `docs/superpowers/specs/2026-07-29-frontend-dashboard-design.md`(§10 六个 `- [ ]` → `- [x]`)

**Interfaces:**
- Consumes: Task 1-4 全部产出
- Produces: 可 PR 的完整分支

- [ ] **Step 1: Run full test suites + typecheck**

Run: `cd frontend && npm test`
Expected: 全部 PASS(既有 + 本分支新增,无回归)

Run: `cd frontend && npm run typecheck`
Expected: 0 errors

Run: `cd backend && python -m pytest tests/ -q`
Expected: 全量 PASS,无回归(本分支零后端改动,确认即可)

- [ ] **Step 2: Browser 验收(必做)**

用 chrome-devtools MCP 驱动浏览器实测(docker postgres + 后端 :8000 + 前端 `npm run dev`;本机后端启动:`cd backend && DATABASE_URL="postgresql+asyncpg://oa:oa@127.0.0.1:5432/oa" python -m uvicorn app.main:app --port 8000`,无 uv 时用 anaconda python;admin 账号 `admin@company.com` / `Admin123!`;manager 用既有 seed 主管账号,employee 用无 `dashboard:view` 账号;若旧库缺 `dashboard:*` 权限,先重跑幂等 `python -m scripts.seed`):

1. admin 登录 → 菜单可见「数据看板」→ 进入 `/dashboard`:三段统计渲染,请假/报销明细表为多部门多行,汇总卡片数值与明细行求和一致
2. manager 登录 → 明细表仅本部门一行,汇总值等于该行
3. 任一有权限账号:MonthPicker 切到上一个月份 → 列表/卡片按新月重拉(网络面板可见 `month=YYYY-MM` 参数)
4. employee(无 `dashboard:view`)登录 → 菜单无「数据看板」;直接访问 `/dashboard` → 重定向首页

**截图全部存 `.superpowers/sdd/acceptance/`,`dash-` 前缀**(如 `dash-1-admin-multi-dept.png`……)——禁止放 SDD workspace。

- [ ] **Step 3: Tick spec acceptance boxes**

把 `docs/superpowers/specs/2026-07-29-frontend-dashboard-design.md` §10 的 6 个 `- [ ]` 全部改为 `- [x]`。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-29-frontend-dashboard-design.md
git commit -m "test(frontend): 数据看板模块全量验收通过,勾选 spec 验收标准"
```

---

## Self-Review 记录

- **Spec 覆盖**:§1 范围→Task 1-4;§2 架构(方案 B)→Task 2-4 单元拆分;§3 契约→Task 1(类型 total_amount: string)+ Task 2(¥ 直拼 + 唯一浮点例外);§4 单元表→Task 1(api/类型)/Task 2(两 Section)/Task 3(时效 Section)/Task 4(页面壳+菜单+路由);§5 数据流→Task 4(cancelled 清理、Dayjs 持有、重定向);§6 扩展→不实现;§7 错误处理→Task 4(Alert 保留旧数据:catch 只 setError 不清 data)+ Task 2-3(空态);§8 测试策略→各任务测试 + Task 5 浏览器四场景;§9 部署→Task 5 仅确认后端无回归;§10 验收→Task 5 勾选。
- **占位符扫描**:无 TBD/TODO;所有代码块完整可复制。Task 4 月份 cell 选择器一处注明了 antd DOM 版本敏感性与不可变的断言目标。
- **类型一致性**:`LeaveStatItem/ExpenseStatItem/ApprovalDurationItem/DashboardSummary` Task 1 定义,Task 2-4 消费一致;`getDashboard(month?: string)` Task 1 定义、Task 4 消费;`LeaveStatsSection/ExpenseStatsSection({stats})` Task 2 定义、`DurationSection({durations})` Task 3 定义、Task 4 消费,prop 名一致;菜单/路由接线键值 `/dashboard` 与 `dashboard:view` 与后端 seed 权限点一致。
- **已知取舍**:①测试渲染不含 ConfigProvider,空态断言用英文 `No data`(与浏览器中文 `暂无数据` 不矛盾,测试环境无 locale 包);②切月份测试用 antd DOM 定位(`.ant-picker-cell[title]`),与既有面板测试同风格,antd 升级时同进退;③ExpenseStatsSection 汇总金额是计划中唯一 `Number` 转换点,spec §3 已显式授权;④页面失败时保留旧数据(catch 不清 data),靠 Spin 遮罩表达加载中,避免闪空。

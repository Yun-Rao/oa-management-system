# 消息通知模块(前端)— 设计文档

- 版本:v1.0
- 日期:2026-07-29
- 状态:已确认
- 对应 PRD:docs/prd.md §3.4(P1 模块之一)
- 前置模块:消息通知后端(docs/superpowers/specs/2026-07-26-backend-notification-design.md,4 接口已上线)

---

## 1. 范围

**本期做**:站内消息前端——Header 铃铛未读角标(30s 轮询)、独立路由 `/notifications` 消息中心页(全部/未读 Tab、分页、单条/全部标记已读)、点击通知跳转 `/leaves` 并自动打开对应请假单详情弹窗。

**本期不做**:
- WebSocket/SSE 实时推送(后端 spec 已定轮询模型,实时性 = 轮询间隔)
- 通知删除(后端无删除接口,历史长期保留)
- 菜单新增"消息中心"项(入口为 Header 铃铛,登录后任何页面可见)
- 通知类型筛选(本期仅 3 种 leave 类型)
- 报销通知的专属 UI(后端报销触发点尚未接入;列表与跳转结构为未来 `ref_type="expense"` 留扩展,见 §6)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 入口形态 | Header 铃铛 `Badge`(未读数)+ 独立路由 `/notifications` 消息中心页;菜单不加新项 |
| 未读数同步 | 新建 `useNotificationStore`(zustand):角标轮询写入,消息中心页标记已读后同步更新,角标即时刷新 |
| 轮询策略 | MainLayout 挂载即拉一次,之后 30s `setInterval`;卸载清理;失败静默下轮重试 |
| 点击通知 | 未读 → `markRead` + store 同步 + 列表本地更新读态;然后 `navigate("/leaves", { state: { openLeaveId } })`,LeavesPage 检测 state 自动打开 `LeaveDetailModal` |
| 权限 | 无权限点:登录即可(后端 `get_current_user`);路由只需 `RequireAuth` |
| 列表数据流 | 页面本地态管理列表/分页;store 只管 `unreadCount` 一个数,职责单一 |

## 3. 后端接口(既有,直接消费)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/notifications` | `is_read`(bool 可省)+ page/page_size,created_at 倒序;响应 items/total/page/page_size |
| GET | `/notifications/unread-count` | `{count}` |
| POST | `/notifications/{id}/read` | 幂等;非本人 403、不存在 404 |
| POST | `/notifications/read-all` | 返回 `{updated: n}` |

`NotificationResponse{id, type, title, content, ref_type, ref_id, read_at, created_at}`;本期 `ref_type` 恒 `"leave"`,`ref_id` = 请假单 id。

## 4. 架构与组件

镜像既有分层(api → store → pages/components),复用 antd + zustand + react-router 模式。

| 单元 | 文件 | 职责 |
|---|---|---|
| api 层 | `frontend/src/api/notifications.ts` | `listNotifications({is_read?, page, page_size})` / `getUnreadCount()` / `markRead(id)` / `markAllRead()`;错误沿用 `ApiError` |
| 类型 | `frontend/src/types/api.ts`(追加) | `NotificationItem`、`NotificationListResponse`(items/total/page/page_size 分页约定) |
| store | `frontend/src/store/notification.ts` | `useNotificationStore`:`unreadCount`、`refresh()`、`decrement(n)`、`clear()`;镜像 auth store 风格 |
| 铃铛角标 | 改 `frontend/src/components/MainLayout.tsx` | Header 用户名左侧 `Badge count={unreadCount}` + `BellOutlined`;30s 轮询;点击 → `navigate("/notifications")` |
| 消息中心页 | `frontend/src/pages/notifications/NotificationsPage.tsx` | Card + Tabs(全部/未读)+ antd List + 分页 + 右上角"全部已读"按钮 |
| 跳转联动 | 改 `frontend/src/pages/leaves/LeavesPage.tsx` | 读 `location.state?.openLeaveId`,存在则渲染 `LeaveDetailModal leaveId={openLeaveId}`;关闭时 `navigate(".", { replace: true, state: null })` 清除 |
| 路由 | 改 `frontend/src/App.tsx` | `/notifications` → `NotificationsPage`(RequireAuth 内,无权限门控) |

### 单元边界

- store 只持有 `unreadCount` 一个数与三个操作方法,不知道列表存在;页面不直接改角标,只通过 store 方法同步——两者可独立测试。
- `LeavesPage` 对 `openLeaveId` 的处理是纯路由 state 消费:不引入全局"待打开详情"状态,通知模块与请假模块之间仅靠 URL state 耦合,`LeaveDetailModal` 零改动复用。

## 5. 数据流

- **轮询**:MainLayout 挂载 → `refresh()`;之后每 30s 一次;失败静默(下轮重试,不弹错)。
- **点击通知条目**:未读 → `markRead(id)` → `decrement(1)` + 列表本地置读态;随后 `navigate("/leaves", { state: { openLeaveId: ref_id } })`;已读条目直接跳转。标记失败:message 提示,仍允许跳转(详情可读)。
- **全部已读**:`markAllRead()` → `clear()` + 重拉当前页列表。
- **Tab 切换**(全部/未读):重置到第 1 页重拉;"未读"Tab 传 `is_read=false`,"全部"Tab 不传该参数。
- **登出/401**:MainLayout 卸载即停轮询;store 残留 `unreadCount` 在下次登录首次 `refresh()` 时被覆盖,无需显式重置。

## 6. 扩展预留(不实现)

- 未来报销通知(`ref_type="expense"`):点击跳转处按 `ref_type` 分发——本期仅 `"leave"` 一个分支,未知 `ref_type` 降级为"仅标记已读不跳转",不报错。
- 角标轮询间隔 30s 为常量,后续如需可调。

## 7. 错误处理

沿用既有模式:api 层抛 `ApiError`,页面用 `App.useApp()` 的 message 提示;列表加载失败显示 Alert;标记已读失败不阻塞跳转。403/404 由后端语义保证,前端只展示后端 message。

| 场景 | 表现 |
|---|---|
| 列表加载失败 | Alert + 可手动刷新(切换 Tab/分页即重试) |
| unread-count 轮询失败 | 静默,下轮重试 |
| markRead 失败 | message.error,仍跳转详情 |
| markAllRead 失败 | message.error,列表不变 |

## 8. 测试策略

vitest + Testing Library,每个组件配 `.test.tsx`(沿用现状)。

- `api/notifications.test.ts`:4 函数的 URL/参数/返回值(mock client)
- `MainLayout` 测试追加:角标渲染、轮询触发与卸载清理、点击铃铛跳转 `/notifications`
- `NotificationsPage.test.tsx`:Tab 切换调参(`is_read=false` vs 不传)、列表渲染、点击未读条目(markRead + navigate state + store decrement)、点击已读条目(不 markRead)、全部已读(markAllRead + clear + 重拉)、分页
- `LeavesPage.test.tsx` 追加:带 `openLeaveId` state 进入自动打开详情弹窗;关闭后 state 清除(replace)
- store 的 refresh/decrement/clear 通过上述组件测试间接覆盖

## 9. 部署影响

纯前端改动,无新依赖、无环境变量、无后端变更。

## 10. 验收标准(对齐 PRD §3.4)

- [x] Header 铃铛实时(≤30s)显示未读数角标
- [x] 消息中心页可查看历史通知列表(全部/未读筛选、分页)
- [x] 单条通知可标记已读,支持全部标记已读,角标即时同步
- [x] 点击通知跳转请假页并自动打开对应申请详情弹窗
- [x] 未登录访问 `/notifications` 被重定向登录页(RequireAuth 既有行为)

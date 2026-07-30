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

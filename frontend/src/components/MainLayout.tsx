import { useState } from "react";
import { Dropdown, Layout, Menu } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../store/auth";
import ChangePasswordModal from "./ChangePasswordModal";
import { MENU_ITEMS } from "./menu";

export default function MainLayout() {
  const user = useAuthStore((s) => s.user);
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const navigate = useNavigate();
  const location = useLocation();
  const [pwdOpen, setPwdOpen] = useState(false);

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
          }}
        >
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

import { useEffect, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { Spin } from "antd";

import { useAuthStore } from "../store/auth";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (token && !user) {
      // 幂等 GET,StrictMode 双调用无害;失败即登出,由 !token 分支跳转 /login。
      // 渲染判据只看 user 是否就绪,不引入本地 loading 态(避免竞态永久加载)。
      useAuthStore
        .getState()
        .fetchMe()
        .catch(() => useAuthStore.getState().logout());
    }
  }, [token, user]);

  if (!token) {
    return <Navigate to="/login" replace />;
  }
  if (!user) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
        }}
      >
        <Spin size="large" />
      </div>
    );
  }
  return <>{children}</>;
}

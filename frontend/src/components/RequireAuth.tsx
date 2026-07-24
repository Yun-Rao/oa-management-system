import { useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { Spin } from "antd";

import { useAuthStore } from "../store/auth";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (token && !user) {
      setLoading(true);
      useAuthStore
        .getState()
        .fetchMe()
        .catch(() => useAuthStore.getState().logout())
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [token, user]);

  if (!token) {
    return <Navigate to="/login" replace />;
  }
  if (loading || !user) {
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

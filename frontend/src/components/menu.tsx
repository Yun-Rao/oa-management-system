import { ApartmentOutlined, BarChartOutlined, CalendarOutlined, HomeOutlined, PayCircleOutlined, TeamOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

export interface MenuItemConfig {
  key: string;
  label: string;
  icon: ReactNode;
  permission: string | null;
}

export const MENU_ITEMS: MenuItemConfig[] = [
  { key: "/", label: "首页", icon: <HomeOutlined />, permission: null },
  { key: "/users", label: "用户管理", icon: <TeamOutlined />, permission: "user:list" },
  { key: "/departments", label: "部门管理", icon: <ApartmentOutlined />, permission: "department:list" },
  { key: "/leaves", label: "请假审批", icon: <CalendarOutlined />, permission: "leave:list" },
  { key: "/expenses", label: "报销审批", icon: <PayCircleOutlined />, permission: "expense:list" },
  { key: "/dashboard", label: "数据看板", icon: <BarChartOutlined />, permission: "dashboard:view" },
];

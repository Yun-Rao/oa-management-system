import { ApartmentOutlined, HomeOutlined, TeamOutlined } from "@ant-design/icons";
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
];

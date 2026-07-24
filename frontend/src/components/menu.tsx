import { HomeOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

export interface MenuItemConfig {
  key: string;
  label: string;
  icon: ReactNode;
  permission: string | null;
}

export const MENU_ITEMS: MenuItemConfig[] = [
  { key: "/", label: "首页", icon: <HomeOutlined />, permission: null },
];

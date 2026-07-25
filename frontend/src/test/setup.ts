import "@testing-library/jest-dom/vitest";

import React from "react";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { vi } from "vitest";

// 与 main.tsx 保持一致:测试环境同样提供 zhCN locale,
// 使 antd Modal 等组件的默认按钮文案(确 定/取 消)与生产一致。
vi.mock("@testing-library/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@testing-library/react")>();
  const render = (
    ui: React.ReactNode,
    options?: Parameters<typeof actual.render>[1]
  ) => actual.render(React.createElement(ConfigProvider, { locale: zhCN }, ui), options);
  return { ...actual, render: render as typeof actual.render };
});

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof window.ResizeObserver;
}

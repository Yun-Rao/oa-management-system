import axios from "axios";

import type { ApiErrorBody } from "../types/api";

export const TOKEN_KEY = "oa_token";

export class ApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

// 可替换的导航实现,便于测试(jsdom 不支持真实跳转)
export const navigation = {
  toLogin: () => {
    window.location.href = "/login";
  },
};

// 401 时由 auth store 注册的回调(清空内存态,避免 client → store 循环依赖)
let unauthorizedHandler: (() => void) | null = null;
export function onUnauthorized(fn: () => void): void {
  unauthorizedHandler = fn;
}

export const client = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const resp = error.response;
      if (resp?.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        unauthorizedHandler?.();
        const isLoginRequest = (resp.config.url ?? "").includes("/auth/login");
        if (!isLoginRequest && window.location.pathname !== "/login") {
          navigation.toLogin();
        }
      }
      const body: unknown = resp?.data;
      if (
        typeof body === "object" &&
        body !== null &&
        "error" in body &&
        typeof (body as ApiErrorBody).error?.code === "string"
      ) {
        const { code, message } = (body as ApiErrorBody).error;
        return Promise.reject(new ApiError(code, message));
      }
    }
    return Promise.reject(new ApiError("UNKNOWN", "网络异常,请稍后重试"));
  }
);

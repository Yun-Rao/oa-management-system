import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/departments", () => ({
  listDeptTree: vi.fn(),
  listDeptMembers: vi.fn(),
}));
vi.mock("../../api/users", () => ({
  updateUserOrg: vi.fn(),
}));

import { ApiError } from "../../api/client";
import { listDeptMembers, listDeptTree } from "../../api/departments";
import { updateUserOrg } from "../../api/users";
import type { DepartmentNode, UserResponse } from "../../types/api";
import UserOrgModal from "./UserOrgModal";

const tree: DepartmentNode[] = [
  { id: "d1", name: "技术部", parent_id: null, member_count: 2, children: [] },
  { id: "d5", name: "市场部", parent_id: null, member_count: 1, children: [] },
];

const target: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [],
  department: { id: "d1", name: "技术部" },
  manager: { id: "u2", name: "王主管" },
};

const d1Members: UserResponse[] = [
  { id: "u1", email: "a@x.com", name: "张三", is_active: true, roles: [], department: null, manager: null },
  { id: "u2", email: "b@x.com", name: "王主管", is_active: true, roles: [], department: null, manager: null },
];

const d5Members: UserResponse[] = [
  { id: "u9", email: "c@x.com", name: "李市场", is_active: true, roles: [], department: null, manager: null },
];

function deptFormItem() {
  return within(screen.getByText("所属部门").closest(".ant-form-item") as HTMLElement);
}
function managerFormItem() {
  return within(screen.getByText("直属上级").closest(".ant-form-item") as HTMLElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listDeptTree).mockResolvedValue(tree);
  vi.mocked(listDeptMembers).mockImplementation(async (id: string) =>
    id === "d1"
      ? { items: d1Members, total: 2, page: 1, page_size: 100 }
      : { items: d5Members, total: 1, page: 1, page_size: 100 }
  );
});

describe("UserOrgModal", () => {
  it("打开:预填部门与上级;上级候选排除用户自己", async () => {
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    expect(await deptFormItem().findByText("技术部")).toBeInTheDocument();
    await waitFor(() => expect(listDeptMembers).toHaveBeenCalledWith("d1", { page: 1, page_size: 100 }));
    expect(await managerFormItem().findByText("王主管")).toBeInTheDocument();
    // 候选排除自己:打开上级下拉
    const user = userEvent.setup();
    await user.click(managerFormItem().getByRole("combobox"));
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByLabelText("王主管")).toBeInTheDocument();
    expect(within(listbox).queryByLabelText("张三")).not.toBeInTheDocument();
  });

  it("切换部门:清空已选上级并重新拉候选", async () => {
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    await user.click(deptFormItem().getByRole("combobox"));
    const treeDropdown = await screen.findByRole("tree");
    await user.click(within(treeDropdown).getByText("市场部"));
    await waitFor(() => expect(listDeptMembers).toHaveBeenCalledWith("d5", { page: 1, page_size: 100 }));
    // 已选上级被清空
    expect(managerFormItem().queryByText("王主管")).not.toBeInTheDocument();
  });

  it("提交:updateUserOrg 参数正确并触发 onSuccess/onClose", async () => {
    vi.mocked(updateUserOrg).mockResolvedValue(target);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<UserOrgModal user={target} onClose={onClose} onSuccess={onSuccess} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateUserOrg).toHaveBeenCalledWith("u1", { department_id: "d1", manager_id: "u2" })
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("清空部门与上级提交:显式 null(清空语义)", async () => {
    vi.mocked(updateUserOrg).mockResolvedValue({ ...target, department: null, manager: null });
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    // 清空部门
    const deptSelector = deptFormItem().getByText("技术部").closest(".ant-select-selector") as HTMLElement;
    await user.hover(deptSelector);
    await user.click(deptSelector.parentElement!.querySelector(".ant-select-clear") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateUserOrg).toHaveBeenCalledWith("u1", { department_id: null, manager_id: null })
    );
  });

  it("失败(422 上级校验):显示 ApiError.message,不关闭", async () => {
    vi.mocked(updateUserOrg).mockRejectedValue(new ApiError("VALIDATION_ERROR", "直属上级须属于同一部门"));
    const onClose = vi.fn();
    render(<UserOrgModal user={target} onClose={onClose} onSuccess={() => {}} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("直属上级须属于同一部门")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("竞态:切换部门后旧部门慢响应不覆盖新候选", async () => {
    let resolveD1!: (v: { items: UserResponse[]; total: number; page: number; page_size: number }) => void;
    const d1Promise = new Promise<{ items: UserResponse[]; total: number; page: number; page_size: number }>(
      (res) => {
        resolveD1 = res;
      }
    );
    vi.mocked(listDeptMembers).mockImplementation(async (id: string) =>
      id === "d1" ? d1Promise : { items: d5Members, total: 1, page: 1, page_size: 100 }
    );
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    // 初始部门(d1)候选请求挂起中,直接切换到市场部
    await deptFormItem().findByText("技术部");
    const user = userEvent.setup();
    await user.click(deptFormItem().getByRole("combobox"));
    const treeDropdown = await screen.findByRole("tree");
    await user.click(within(treeDropdown).getByText("市场部"));
    await waitFor(() =>
      expect(listDeptMembers).toHaveBeenCalledWith("d5", { page: 1, page_size: 100 })
    );
    // 旧部门慢响应到达,不应覆盖市场部候选
    await act(async () => {
      resolveD1({ items: d1Members, total: 2, page: 1, page_size: 100 });
    });
    await user.click(managerFormItem().getByRole("combobox"));
    const listbox = await screen.findByRole("listbox");
    expect(await within(listbox).findByLabelText("李市场")).toBeInTheDocument();
    expect(within(listbox).queryByLabelText("王主管")).not.toBeInTheDocument();
  });

  it("部门成员超过一页:翻页拉全,末页成员也可选为上级", async () => {
    const blank: UserResponse = {
      id: "x",
      email: "x@x.com",
      name: "成员",
      is_active: true,
      roles: [],
      department: null,
      manager: null,
    };
    const page1 = Array.from({ length: 100 }, (_, i) => ({
      ...blank,
      id: `p1-${i}`,
      name: `成员${i}`,
    }));
    const page2 = [{ ...blank, id: "u-last", name: "末页主管" }];
    vi.mocked(listDeptMembers).mockImplementation(async (_id: string, params: { page: number }) =>
      params.page === 1
        ? { items: page1, total: 101, page: 1, page_size: 100 }
        : { items: page2, total: 101, page: 2, page_size: 100 }
    );
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    await waitFor(() =>
      expect(listDeptMembers).toHaveBeenCalledWith("d1", { page: 2, page_size: 100 })
    );
    // 虚拟滚动下直接找末页选项未必渲染,用搜索过滤
    const user = userEvent.setup();
    await user.click(managerFormItem().getByRole("combobox"));
    await user.type(managerFormItem().getByRole("combobox"), "末页");
    const listbox = await screen.findByRole("listbox");
    expect(await within(listbox).findByLabelText("末页主管")).toBeInTheDocument();
  });

  it("候选尚未含现任上级时:回显姓名而非 UUID", async () => {
    // 候选只有用户自己(被排除后为空),现任上级 u2 不在候选中
    vi.mocked(listDeptMembers).mockResolvedValue({ items: [d1Members[0]], total: 1, page: 1, page_size: 100 });
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    expect(await managerFormItem().findByText("王主管")).toBeInTheDocument();
    expect(managerFormItem().queryByText("u2")).not.toBeInTheDocument();
  });
});

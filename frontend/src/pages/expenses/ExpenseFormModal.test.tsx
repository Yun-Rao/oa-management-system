import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({ createExpense: vi.fn() }));

import { createExpense } from "../../api/expenses";
import ExpenseFormModal from "./ExpenseFormModal";

function renderModal(onSuccess = vi.fn(), onClose = vi.fn()) {
  render(
    <App>
      <ExpenseFormModal open onClose={onClose} onSuccess={onSuccess} />
    </App>
  );
  return { onSuccess, onClose };
}

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("combobox"));
  const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
  await user.click(dropdown.querySelector('[title="差旅"]') as HTMLElement);
  await user.type(screen.getByLabelText(/金额/), "1999.5");
  await user.type(screen.getByLabelText(/报销说明/), "出差打车");
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ExpenseFormModal", () => {
  it("必填校验:直接确定显示错误", async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请选择报销类型")).toBeInTheDocument();
    expect(screen.getByText("请输入金额")).toBeInTheDocument();
    expect(screen.getByText("请输入报销说明")).toBeInTheDocument();
    expect(createExpense).not.toHaveBeenCalled();
  });

  it("无附件提交:Alert 提示且不提交", async () => {
    renderModal();
    const user = userEvent.setup();
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请上传 1~5 个附件凭证")).toBeInTheDocument();
    expect(createExpense).not.toHaveBeenCalled();
  });

  it("完整提交:FormData 字段正确,成功后 onSuccess + onClose", async () => {
    const { onSuccess, onClose } = renderModal();
    const user = userEvent.setup();
    await fillRequired(user);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "a.png", { type: "image/png" }));
    await screen.findByText("a.png");
    vi.mocked(createExpense).mockResolvedValue({} as never);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(createExpense).toHaveBeenCalledOnce());
    const fd = vi.mocked(createExpense).mock.calls[0][0];
    expect(fd.get("type")).toBe("travel");
    expect(fd.get("amount")).toBe("1999.50");
    expect(fd.get("reason")).toBe("出差打车");
    expect((fd.get("files") as File).name).toBe("a.png");
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("超大文件:拒绝加入并提示", async () => {
    renderModal();
    const user = userEvent.setup();
    const big = new File([new Uint8Array(6 * 1024 * 1024)], "big.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, big);
    await waitFor(() => expect(screen.queryByText("big.png")).not.toBeInTheDocument());
  });

  it("非法扩展名:拒绝加入", async () => {
    renderModal();
    const user = userEvent.setup();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "a.txt", { type: "text/plain" }));
    await waitFor(() => expect(screen.queryByText("a.txt")).not.toBeInTheDocument());
  });
});

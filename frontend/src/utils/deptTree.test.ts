import { describe, expect, it } from "vitest";

import type { DepartmentNode } from "../types/api";
import { collectSubtreeIds, findNode, toTreeSelectData } from "./deptTree";

const tree: DepartmentNode[] = [
  {
    id: "d1",
    name: "技术部",
    parent_id: null,
    member_count: 3,
    children: [
      {
        id: "d2",
        name: "前端组",
        parent_id: "d1",
        member_count: 1,
        children: [{ id: "d4", name: "H5 小组", parent_id: "d2", member_count: 0, children: [] }],
      },
      { id: "d3", name: "后端组", parent_id: "d1", member_count: 2, children: [] },
    ],
  },
  { id: "d5", name: "市场部", parent_id: null, member_count: 5, children: [] },
];

describe("deptTree utils", () => {
  it("findNode:按 id 深度查找", () => {
    expect(findNode(tree, "d4")?.name).toBe("H5 小组");
    expect(findNode(tree, "d5")?.name).toBe("市场部");
    expect(findNode(tree, "nope")).toBeNull();
  });

  it("collectSubtreeIds:含自身与全部后代", () => {
    expect([...collectSubtreeIds(findNode(tree, "d1")!)].sort()).toEqual(["d1", "d2", "d3", "d4"]);
    expect([...collectSubtreeIds(findNode(tree, "d3")!)]).toEqual(["d3"]);
  });

  it("toTreeSelectData:转换为 TreeSelect 数据结构", () => {
    const data = toTreeSelectData(tree);
    expect(data).toHaveLength(2);
    expect(data[0]).toMatchObject({ value: "d1", title: "技术部" });
    expect(data[0].children?.[0]).toMatchObject({ value: "d2", title: "前端组" });
  });

  it("toTreeSelectData:excludeIds 排除自身及后代", () => {
    const data = toTreeSelectData(tree, collectSubtreeIds(findNode(tree, "d2")!));
    expect(data[0].children).toHaveLength(1);
    expect(data[0].children?.[0]).toMatchObject({ value: "d3", title: "后端组" });
    expect(JSON.stringify(data)).not.toContain("前端组");
    expect(JSON.stringify(data)).not.toContain("H5 小组");
  });
});

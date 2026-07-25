import type { DepartmentNode } from "../types/api";

export interface DeptTreeSelectNode {
  value: string;
  title: string;
  children?: DeptTreeSelectNode[];
}

export function findNode(nodes: DepartmentNode[], id: string): DepartmentNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

export function collectSubtreeIds(node: DepartmentNode): Set<string> {
  const ids = new Set<string>([node.id]);
  for (const child of node.children) {
    for (const id of collectSubtreeIds(child)) ids.add(id);
  }
  return ids;
}

export function toTreeSelectData(
  nodes: DepartmentNode[],
  excludeIds?: Set<string>
): DeptTreeSelectNode[] {
  return nodes
    .filter((n) => !excludeIds?.has(n.id))
    .map((n) => ({
      value: n.id,
      title: n.name,
      children: toTreeSelectData(n.children, excludeIds),
    }));
}

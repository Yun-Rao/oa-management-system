import { Button, Popconfirm, Space, Tree } from "antd";
import type { TreeDataNode } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";

import type { DepartmentNode } from "../../types/api";
import "./dept.css";

interface Props {
  tree: DepartmentNode[];
  selectedId: string | null;
  canCreate: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  onSelect: (id: string) => void;
  onCreateRoot: () => void;
  onCreateChild: (node: DepartmentNode) => void;
  onEdit: (node: DepartmentNode) => void;
  onDelete: (node: DepartmentNode) => void;
}

interface DeptTreeDataNode extends TreeDataNode {
  dept: DepartmentNode;
  children?: DeptTreeDataNode[];
}

export default function DeptTreePanel({
  tree,
  selectedId,
  canCreate,
  canUpdate,
  canDelete,
  onSelect,
  onCreateRoot,
  onCreateChild,
  onEdit,
  onDelete,
}: Props) {
  const treeData = useMemo<DeptTreeDataNode[]>(
    () =>
      tree.map(function convert(n): DeptTreeDataNode {
        return { key: n.id, title: n.name, dept: n, children: n.children.map(convert) };
      }),
    [tree]
  );

  // defaultExpandAll 只在挂载时生效,而树数据是异步到达的;
  // 改为受控 expandedKeys:数据到达后默认全展开,用户仍可手动折叠。
  const allKeys = useMemo(() => {
    const keys: string[] = [];
    (function walk(ns: DepartmentNode[]) {
      ns.forEach((n) => {
        keys.push(n.id);
        walk(n.children);
      });
    })(tree);
    return keys;
  }, [tree]);
  const [expandedKeys, setExpandedKeys] = useState<string[]>(allKeys);
  useEffect(() => {
    setExpandedKeys(allKeys);
  }, [allKeys]);

  function renderTitle(data: TreeDataNode) {
    const node = (data as DeptTreeDataNode).dept;
    return (
      <span className="dept-tree-node">
        <span>{`${node.name}(${node.member_count})`}</span>
        {(canCreate || canUpdate || canDelete) && (
          <Space size={0} className="dept-tree-actions">
            {canCreate && (
              <Button
                type="text"
                size="small"
                icon={<PlusOutlined />}
                aria-label="新建子部门"
                onClick={(e) => {
                  e.stopPropagation();
                  onCreateChild(node);
                }}
              />
            )}
            {canUpdate && (
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                aria-label="编辑部门"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(node);
                }}
              />
            )}
            {canDelete && (
              <Popconfirm
                title="确认删除该部门?"
                onConfirm={() => onDelete(node)}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  aria-label="删除部门"
                  onClick={(e) => e.stopPropagation()}
                />
              </Popconfirm>
            )}
          </Space>
        )}
      </span>
    );
  }

  return (
    <div>
      {canCreate && (
        <Button type="primary" block style={{ marginBottom: 12 }} onClick={onCreateRoot}>
          新建部门
        </Button>
      )}
      <Tree
        treeData={treeData}
        titleRender={renderTitle}
        selectedKeys={selectedId ? [selectedId] : []}
        expandedKeys={expandedKeys}
        onExpand={(keys) => setExpandedKeys(keys as string[])}
        blockNode
        onSelect={(keys) => {
          const key = keys[0];
          if (typeof key === "string") onSelect(key);
        }}
      />
    </div>
  );
}

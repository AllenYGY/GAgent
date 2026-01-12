import React, { useEffect, useMemo, useState } from 'react';
import { Spin, Tooltip, Button, Space, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { PlanTaskNode } from '@/types';
import { exportPlanAsJson } from '@utils/exportPlan';
import './PlanTreeVisualization.css';

export interface PlanTreeVisualizationProps {
  tasks: PlanTaskNode[];
  loading?: boolean;
  height?: number | string;
  onSelectTask?: (task: PlanTaskNode | null) => void;
  selectedTaskId?: number | null;
  planId?: number | null;
  planTitle?: string | null;
}

interface TreeNode {
  task: PlanTaskNode;
  children: TreeNode[];
}

const getOrderKey = (task: PlanTaskNode): number =>
  typeof task.position === 'number' ? task.position : task.id;

const compareTaskOrder = (a: PlanTaskNode, b: PlanTaskNode): number => {
  const posDiff = getOrderKey(a) - getOrderKey(b);
  if (posDiff !== 0) {
    return posDiff;
  }
  return a.id - b.id;
};

const PlanTreeVisualization: React.FC<PlanTreeVisualizationProps> = ({
  tasks,
  loading,
  height = '480px',
  onSelectTask,
  selectedTaskId,
  planId,
  planTitle,
}) => {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [internalSelectedId, setInternalSelectedId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  const effectiveSelectedId =
    selectedTaskId !== undefined ? selectedTaskId ?? null : internalSelectedId;

  useEffect(() => {
    if (selectedTaskId !== undefined) {
      setInternalSelectedId(selectedTaskId ?? null);
    }
  }, [selectedTaskId]);

  // Build nested tree structure
  const buildTree = useMemo((): TreeNode[] => {
    if (!tasks || tasks.length === 0) return [];

    const roots = tasks
      .filter(task => !task.parent_id || task.task_type?.toLowerCase() === 'root')
      .sort(compareTaskOrder);

    const buildNode = (task: PlanTaskNode): TreeNode => {
      const children = tasks
        .filter(t => t.parent_id === task.id)
        .map(child => buildNode(child))
        .sort((a, b) => compareTaskOrder(a.task, b.task));

      return { task, children };
    };

    return roots.map(root => buildNode(root));
  }, [tasks]);

  // Toggle collapse state
  const toggleCollapse = (taskId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setCollapsed(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  // Select a task
  const handleSelectTask = (task: PlanTaskNode) => {
    if (selectedTaskId === undefined) {
      setInternalSelectedId(task.id);
    }
    onSelectTask?.(task);
  };

  // Render tree nodes recursively
  const renderTreeNode = (
    node: TreeNode,
    isLast: boolean,
    prefix: string = '',
    isRoot: boolean = false,
    depth: number = 0
  ): React.ReactNode => {
    const { task, children } = node;
    const hasChildren = children.length > 0;
    const isCollapsed = collapsed.has(task.id);
    const isSelected = effectiveSelectedId === task.id;
    
    const cleanName = (task.short_name || task.name || '').replace(/^(ROOT|COMPOSITE|ATOMIC):\s*/i, '');
    const displayName = cleanName.length > 30 ? cleanName.substring(0, 30) + '...' : cleanName;
    
    const connector = isRoot ? '' : (isLast ? '└── ' : '├── ');
    const childPrefix = isRoot ? '' : (isLast ? '    ' : '│   ');

    return (
      <div key={task.id} className="plan-tree-node">
        <div 
          className={`plan-tree-node-content task-type-${task.task_type?.toLowerCase()} ${isSelected ? 'selected' : ''}`}
          onClick={() => handleSelectTask(task)}
          data-depth={depth}
        >
          <span className="plan-tree-connector">{prefix}{connector}</span>
          
          {hasChildren && (
            <span 
              className="plan-tree-collapse-btn"
              onClick={(e) => toggleCollapse(task.id, e)}
            >
              {isCollapsed ? '▶' : '▼'}
            </span>
          )}
          
          <Tooltip 
            title={`ID: ${task.id} | Status: ${task.status} | Type: ${task.task_type}`}
            placement="right"
          >
            <span className="plan-tree-node-info">
              <span className="plan-node-name">{displayName}</span>
            </span>
          </Tooltip>
        </div>

        {hasChildren && !isCollapsed && (
          <div className="plan-tree-children">
            {children.map((child, index) =>
              renderTreeNode(
                child,
                index === children.length - 1,
                prefix + childPrefix,
                false,
                depth + 1
              )
            )}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height }}>
        <Spin tip="Loading tasks..." />
      </div>
    );
  }

  if (buildTree.length === 0) {
    return (
      <div style={{ 
        display: 'flex', 
        flexDirection: 'column',
        justifyContent: 'center', 
        alignItems: 'center', 
        height,
        color: '#999',
        fontSize: '12px'
      }}>
        <div>No tasks yet</div>
      </div>
    );
  }

  return (
    <div className="plan-tree-visualization-container" style={{ height }}>
      <div className="plan-tree-content">
        {buildTree.map(rootNode => renderTreeNode(rootNode, true, '', true, 0))}
      </div>
    </div>
  );
};

export default PlanTreeVisualization;

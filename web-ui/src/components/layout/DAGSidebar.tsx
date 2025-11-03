import React, { useEffect, useMemo, useState } from 'react';
import { Card, Typography, Button, Space, Badge, Tooltip, Select, Empty, message } from 'antd';
import {
  NodeIndexOutlined,
  FullscreenOutlined,
  SettingOutlined,
  ReloadOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { usePlanTasks } from '@hooks/usePlans';
import PlanTreeVisualization from '@components/dag/PlanTreeVisualization';
import type { PlanSyncEventDetail, PlanTaskNode } from '@/types';
import { useTasksStore } from '@store/tasks';
import { useChatStore } from '@store/chat';
import { shouldHandlePlanSyncEvent } from '@utils/planSyncEvents';
import { exportPlanAsJson } from '@utils/exportPlan';

const { Title, Text } = Typography;

const DAGSidebar: React.FC = () => {
  const { setCurrentPlan, setTasks, openTaskDrawer, closeTaskDrawer, selectedTaskId } = useTasksStore((state) => ({
    setCurrentPlan: state.setCurrentPlan,
    setTasks: state.setTasks,
    openTaskDrawer: state.openTaskDrawer,
    closeTaskDrawer: state.closeTaskDrawer,
    selectedTaskId: state.selectedTaskId,
  }));
  const { setChatContext, currentWorkflowId, currentSession, currentPlanId, currentPlanTitle } =
    useChatStore((state) => ({
      setChatContext: state.setChatContext,
      currentWorkflowId: state.currentWorkflowId,
      currentSession: state.currentSession,
      currentPlanId: state.currentPlanId,
      currentPlanTitle: state.currentPlanTitle,
    }));
  const [dagVisible, setDagVisible] = useState(true);
  const [rootTaskId, setRootTaskId] = useState<number | null>(null);
  const [selectedPlanTitle, setSelectedPlanTitle] = useState<string | undefined>(
    currentPlanTitle ?? undefined
  );
  const [isExportingPlan, setIsExportingPlan] = useState(false);
  const activePlanId = currentPlanId ?? currentSession?.plan_id ?? null;
  const activePlanTitle = selectedPlanTitle ?? currentPlanTitle ?? currentSession?.plan_title ?? null;

  const {
    data: planTasks = [],
    isFetching: planTasksLoading,
    refetch: refetchTasks,
  } = usePlanTasks({ planId: currentPlanId ?? undefined });

  useEffect(() => {
    const handleTasksUpdated = (event: CustomEvent<PlanSyncEventDetail>) => {
      const detail = event.detail;
      if (
        detail?.type === 'plan_deleted' &&
        detail.plan_id != null &&
        detail.plan_id === (currentPlanId ?? null)
      ) {
        setTasks([]);
        closeTaskDrawer();
        return;
      }
      if (
        !shouldHandlePlanSyncEvent(detail, currentPlanId ?? null, [
          'task_changed',
          'plan_jobs_completed',
          'plan_updated',
        ])
      ) {
        return;
      }
      refetchTasks();
      window.setTimeout(() => {
        refetchTasks();
      }, 800);
    };
    window.addEventListener('tasksUpdated', handleTasksUpdated as EventListener);
    return () => window.removeEventListener('tasksUpdated', handleTasksUpdated as EventListener);
  }, [closeTaskDrawer, currentPlanId, refetchTasks, setTasks]);

  useEffect(() => {
    setTasks(planTasks);
  }, [planTasks, setTasks]);

  useEffect(() => {
    if (planTasks.length > 0) {
      const rootTask = planTasks.find((task) => task.task_type === 'root');
      if (rootTask) {
        if (rootTaskId !== rootTask.id) {
          setRootTaskId(rootTask.id);
          setCurrentPlan(rootTask.name);
          setChatContext({
            planId: currentPlanId ?? undefined,
            planTitle: rootTask.name,
            taskId: rootTask.id,
            taskName: rootTask.name,
          });
        }
        setSelectedPlanTitle(rootTask.name);
      }
    } else if (rootTaskId !== null) {
      setRootTaskId(null);
      setSelectedPlanTitle(undefined);
      setCurrentPlan(null);
      setChatContext({
        planId: null,
        planTitle: null,
        taskId: null,
        taskName: null,
      });
      closeTaskDrawer();
    }
  }, [planTasks, rootTaskId, setCurrentPlan, setChatContext, currentPlanId, closeTaskDrawer]);

  const stats = useMemo(() => {
    if (!planTasks || planTasks.length === 0) {
      return {
        total: 0,
        pending: 0,
        running: 0,
        completed: 0,
        failed: 0,
      };
    }
    return {
      total: planTasks.length,
      pending: planTasks.filter((task) => task.status === 'pending').length,
      running: planTasks.filter((task) => task.status === 'running').length,
      completed: planTasks.filter((task) => task.status === 'completed').length,
      failed: planTasks.filter((task) => task.status === 'failed').length,
    };
  }, [planTasks]);

  const handleRefresh = () => {
    refetchTasks();
  };

  const handleExportPlan = async () => {
    if (!activePlanId) {
      message.warning('No plan is currently selected; unable to export.');
      return;
    }

    setIsExportingPlan(true);
    try {
      const fileName = await exportPlanAsJson(activePlanId, activePlanTitle);
      message.success(`Plan exported as ${fileName}.`);
    } catch (error: any) {
      message.error(error?.message || 'Failed to export plan. Please try again later.');
    } finally {
      setIsExportingPlan(false);
    }
  };

  return (
    <div style={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column',
      background: 'white',
    }}>
      <div style={{ 
        padding: '16px',
        borderBottom: '1px solid #f0f0f0',
        background: 'white',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <NodeIndexOutlined style={{ color: '#1890ff', fontSize: 18 }} />
            <Title level={5} style={{ margin: 0 }}>
              Task graph
            </Title>
          </div>
          
          <Space size={4}>
            <Tooltip title={dagVisible ? 'Hide graph' : 'Show graph'}>
              <Button
                type="text"
                size="small"
                icon={dagVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                onClick={() => setDagVisible(!dagVisible)}
              />
            </Tooltip>
            
            <Tooltip title="View in fullscreen">
              <Button
                type="text"
                size="small"
                icon={<FullscreenOutlined />}
              />
            </Tooltip>
            
            <Tooltip title="Settings">
              <Button
                type="text"
                size="small"
                icon={<SettingOutlined />}
              />
            </Tooltip>
          </Space>
        </div>

        <Space size={16} wrap>
          <Badge count={stats.total} size="small" offset={[8, -2]}>
            <Text type="secondary" style={{ fontSize: 12 }}>Total</Text>
          </Badge>
          <Badge count={stats.running} size="small" color="blue" offset={[8, -2]}>
            <Text type="secondary" style={{ fontSize: 12 }}>Running</Text>
          </Badge>
          <Badge count={stats.completed} size="small" color="green" offset={[8, -2]}>
            <Text type="secondary" style={{ fontSize: 12 }}>Completed</Text>
          </Badge>
          {stats.failed > 0 && (
            <Badge count={stats.failed} size="small" color="red" offset={[8, -2]}>
              <Text type="secondary" style={{ fontSize: 12 }}>Failed</Text>
            </Badge>
          )}
        </Space>

        <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>Current ROOT task:</Text>
          <div
            style={{ 
              padding: '6px 12px',
              background: '#f5f5f5',
              border: '1px solid #d9d9d9',
              borderRadius: '6px',
              fontSize: '14px',
              color: selectedPlanTitle ? '#262626' : '#8c8c8c'
            }}
          >
            {selectedPlanTitle || 'No ROOT task yet'}
          </div>
          <Text type="secondary" style={{ fontSize: 10, color: '#999' }}>
            💡 Each conversation anchors a ROOT task from which subtasks expand.
          </Text>
        </Space>
      </div>

      {dagVisible && (
        <div style={{ 
          flex: 1,
          padding: '8px',
          overflow: 'hidden',
        }}>
          {planTasks && planTasks.length > 0 ? (
            <PlanTreeVisualization
              tasks={planTasks}
              loading={planTasksLoading}
              planId={activePlanId}
              planTitle={activePlanTitle}
              onSelectTask={(task) => {
                if (task) {
                  openTaskDrawer(task);
                  const rootName =
                    selectedPlanTitle ||
                    planTasks.find((t) => t.task_type === 'root')?.name ||
                    null;
                  setChatContext({
                    planTitle: rootName,
                    taskId: task.id,
                    taskName: task.name,
                  });
                } else {
                  closeTaskDrawer();
                  setChatContext({ taskId: null, taskName: null });
                }
              }}
              selectedTaskId={selectedTaskId ?? undefined}
              height="100%"
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                planTasksLoading
                  ? 'Loading tasks...'
                  : (currentWorkflowId || currentSession?.session_id)
                    ? 'No tasks for this session yet'
                    : 'Start a conversation or create a workflow first'
              }
            />
          )}
        </div>
      )}

      <div style={{ 
        padding: '12px 16px',
        borderTop: '1px solid #f0f0f0',
        background: '#fafafa',
      }}>
        <Space size={8} wrap style={{ width: '100%', justifyContent: 'center' }}>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={planTasksLoading}
          >
            Refresh
          </Button>
          <Tooltip title={activePlanId ? 'Export the current plan as a JSON file' : 'Select a plan before exporting'}>
            <Button
              size="small"
              icon={<DownloadOutlined />}
              onClick={handleExportPlan}
              disabled={!activePlanId}
              loading={isExportingPlan}
            >
              Export plan
            </Button>
          </Tooltip>
          <Button size="small" icon={<FullscreenOutlined />}>
            Fullscreen
          </Button>
        </Space>
        
        <div style={{ textAlign: 'center', marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            Live task visualisation
          </Text>
        </div>
      </div>
    </div>
  );
};

export default DAGSidebar;


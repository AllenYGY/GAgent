import React, { useEffect, useMemo, useState } from 'react';
import { Card, Typography, Button, Space, Badge, Tooltip, Select, Empty, message, InputNumber, Divider, Switch, Alert, Tag } from 'antd';
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
import { useSimulationStore } from '@store/simulation';
import { shouldHandlePlanSyncEvent } from '@utils/planSyncEvents';
import { exportPlanAsJson } from '@utils/exportPlan';
import { simulationApi } from '@api/simulation';

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
  const [isDownloadingTranscript, setIsDownloadingTranscript] = useState(false);
  const activePlanId = currentPlanId ?? currentSession?.plan_id ?? null;
  const activePlanTitle = selectedPlanTitle ?? currentPlanTitle ?? currentSession?.plan_title ?? null;
  const {
    enabled: simulationEnabled,
    maxTurns,
    autoAdvance,
    currentRun: simulationRun,
    isLoading: simulationLoading,
    error: simulationError,
    pollingRunId,
    setEnabled: setSimulationEnabled,
    setMaxTurns,
    setAutoAdvance,
    startRun: startSimulationRun,
    advanceRun: advanceSimulationRun,
    refreshRun: refreshSimulationRun,
    cancelRun: cancelSimulationRun,
  } = useSimulationStore((state) => ({
    enabled: state.enabled,
    maxTurns: state.maxTurns,
    autoAdvance: state.autoAdvance,
    currentRun: state.currentRun,
    isLoading: state.isLoading,
    error: state.error,
    pollingRunId: state.pollingRunId,
    setEnabled: state.setEnabled,
    setMaxTurns: state.setMaxTurns,
    setAutoAdvance: state.setAutoAdvance,
    startRun: state.startRun,
    advanceRun: state.advanceRun,
    refreshRun: state.refreshRun,
    cancelRun: state.cancelRun,
  }));
  const isSimulationActive =
    !!simulationRun && !['finished', 'cancelled', 'error'].includes(simulationRun.status);
  const simulationStatusLabel = simulationRun ? simulationRun.status.toUpperCase() : 'IDLE';

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

  const handleToggleSimulation = (checked: boolean) => {
    if (checked) {
      setSimulationEnabled(true);
      return;
    }
    handleCancelSimulation();
  };

  const handleStartSimulation = async () => {
    if (!currentSession?.session_id) {
      message.warning('Select a chat session before starting the simulation.');
      return;
    }
    if (!activePlanId) {
      message.warning('Bind a plan before starting the simulation.');
      return;
    }
    try {
      setSimulationEnabled(true);
      await startSimulationRun({
        session_id: currentSession.session_id,
        plan_id: activePlanId,
      });
      message.success('Simulation run started.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to start the simulation.');
    }
  };

  const handleAdvanceSimulation = async () => {
    if (!simulationRun) {
      return;
    }
    try {
      await advanceSimulationRun();
    } catch (error: any) {
      message.error(error?.message || 'Failed to advance the simulation.');
    }
  };

  const handleRefreshSimulation = async () => {
    if (!simulationRun) {
      return;
    }
    try {
      await refreshSimulationRun(simulationRun.run_id);
    } catch (error: any) {
      message.error(error?.message || 'Failed to refresh simulation status.');
    }
  };

  const handleCancelSimulation = async () => {
    if (!simulationRun) {
      setSimulationEnabled(false);
      return;
    }
    try {
      await cancelSimulationRun();
      message.info('Simulation run cancelled.');
      setSimulationEnabled(false);
    } catch (error: any) {
      message.error(error?.message || 'Failed to cancel the simulation.');
    }
  };

  const handleDownloadTranscript = async () => {
    if (!simulationRun) {
      message.info('Run a simulation before downloading transcripts.');
      return;
    }
    setIsDownloadingTranscript(true);
    try {
      const content = await simulationApi.downloadTranscript(simulationRun.run_id);
      const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `simulation-${simulationRun.run_id}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      message.success('Simulation transcript downloaded.');
    } catch (error: any) {
      console.error('Failed to download simulation transcript:', error);
      message.error(error?.message || 'Failed to download transcript.');
    } finally {
      setIsDownloadingTranscript(false);
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
        <Divider orientation="left" style={{ margin: '0 0 12px 0' }}>
          Simulated user mode
        </Divider>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
            <Text strong>Enable simulated user mode</Text>
            <Switch
              size="small"
              checked={simulationEnabled}
              onChange={handleToggleSimulation}
            />
          </Space>
          {simulationError && (
            <Alert type="error" message="Simulation error" description={simulationError} showIcon />
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            The simulated user automatically suggests actions that refine the currently bound plan.
          </Text>
          {!activePlanId && (
            <Alert
              type="info"
              showIcon
              message="Bind a plan to enable meaningful simulation results."
            />
          )}
          <Space align="center" wrap>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Max turns
            </Text>
            <InputNumber
              size="small"
              min={1}
              max={20}
              value={maxTurns}
              onChange={(value) => setMaxTurns(typeof value === 'number' ? value : 1)}
              disabled={simulationLoading}
            />
            <Space align="center">
              <Text type="secondary" style={{ fontSize: 12 }}>
                Auto advance
              </Text>
              <Switch
                size="small"
                checked={autoAdvance}
                onChange={setAutoAdvance}
                disabled={simulationLoading}
              />
            </Space>
            {simulationRun && (
              <Tag color={isSimulationActive ? 'blue' : 'default'}>
                Status: {simulationStatusLabel}
              </Tag>
            )}
            {pollingRunId && isSimulationActive && (
              <Tag color="geekblue">Auto refreshing</Tag>
            )}
          </Space>
          {simulationRun && (
            <Space direction="vertical" size={4} style={{ fontSize: 12, color: '#595959' }}>
              <Text>Run ID: {simulationRun.run_id}</Text>
              <Text>
                Turns: {simulationRun.turns.length}/{simulationRun.config.max_turns} · Remaining:{' '}
                {simulationRun.remaining_turns}
              </Text>
            </Space>
          )}
          <Space size={8} wrap style={{ width: '100%' }}>
            <Button
              size="small"
              type="primary"
              onClick={handleStartSimulation}
              loading={simulationLoading}
              disabled={simulationLoading || isSimulationActive}
            >
              Start run
            </Button>
            <Button
              size="small"
              onClick={handleAdvanceSimulation}
              disabled={
                simulationLoading ||
                !simulationRun ||
                autoAdvance ||
                simulationRun.status !== 'idle'
              }
            >
              Advance turn
            </Button>
            <Button
              size="small"
              onClick={handleRefreshSimulation}
              disabled={simulationLoading || !simulationRun}
            >
              Refresh status
            </Button>
            <Button
              size="small"
              icon={<DownloadOutlined />}
              onClick={handleDownloadTranscript}
              disabled={simulationLoading || !simulationRun}
              loading={isDownloadingTranscript}
            >
              Download transcript
            </Button>
            <Button
              size="small"
              danger
              onClick={handleCancelSimulation}
              disabled={simulationLoading || !simulationEnabled}
            >
              Stop simulation
            </Button>
          </Space>
        </Space>

        <Divider style={{ margin: '16px 0 12px' }} />
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

import React, { useCallback, useEffect, useMemo } from 'react';
import {
  App as AntdApp,
  Button,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { ReloadOutlined, CopyOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { planTreeApi } from '@api/planTree';
import { usePlanTasks } from '@hooks/usePlans';
import { useChatStore } from '@store/chat';
import { useTasksStore } from '@store/tasks';
import ToolResultCard from '@components/chat/ToolResultCard';
import type { PlanResultItem, PlanTaskNode, PlanSyncEventDetail, ToolResultPayload } from '@/types';
import { shouldHandlePlanSyncEvent } from '@utils/planSyncEvents';

const { Paragraph, Text, Title } = Typography;

const statusColorMap: Record<string, string> = {
  pending: 'gold',
  running: 'processing',
  completed: 'green',
  failed: 'red',
  skipped: 'default',
};

const statusLabelMap: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  skipped: 'Skipped',
};

const TaskDetailDrawer: React.FC = () => {
  const { message } = AntdApp.useApp();
  const {
    isTaskDrawerOpen,
    selectedTaskId,
    selectedTask,
    taskResultCache,
    openTaskDrawer,
    openTaskDrawerById,
    closeTaskDrawer,
    setTaskResult,
  } = useTasksStore((state) => ({
    isTaskDrawerOpen: state.isTaskDrawerOpen,
    selectedTaskId: state.selectedTaskId,
    selectedTask: state.selectedTask,
    taskResultCache: state.taskResultCache,
    openTaskDrawer: state.openTaskDrawer,
    openTaskDrawerById: state.openTaskDrawerById,
    closeTaskDrawer: state.closeTaskDrawer,
    setTaskResult: state.setTaskResult,
  }));

  const { currentPlanId, recentToolResults } = useChatStore((state) => {
    const results: ToolResultPayload[] = [];
    const seen = new Set<string>();
    for (let idx = state.messages.length - 1; idx >= 0 && results.length < 5; idx -= 1) {
      const toolResults = state.messages[idx]?.metadata?.tool_results;
      if (!Array.isArray(toolResults) || toolResults.length === 0) {
        continue;
      }
      for (const payload of toolResults) {
        if (!payload) {
          continue;
        }
        const key = `${payload.name ?? ''}::${payload.summary ?? ''}::${
          payload.result?.query ?? ''
        }`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        results.push(payload);
        if (results.length >= 5) {
          break;
        }
      }
    }
    return {
      currentPlanId: state.currentPlanId,
      recentToolResults: results,
    };
  });

  const {
    data: planTasks = [],
    isFetching: tasksLoading,
    refetch: refetchPlanTasks,
  } = usePlanTasks({ planId: currentPlanId ?? undefined });

  const taskMap = useMemo(() => {
    return new Map<number, PlanTaskNode>(planTasks.map((task) => [task.id, task]));
  }, [planTasks]);

  const activeTask = useMemo<PlanTaskNode | null>(() => {
    if (selectedTaskId == null) {
      return null;
    }
    return taskMap.get(selectedTaskId) ?? selectedTask ?? null;
  }, [selectedTaskId, selectedTask, taskMap]);

  const cachedResult =
    selectedTaskId != null ? taskResultCache[selectedTaskId] ?? undefined : undefined;

  const {
    data: taskResult,
    isFetching: resultLoading,
    refetch: refetchTaskResult,
  } = useQuery<PlanResultItem>({
    queryKey: ['planTree', 'taskResult', currentPlanId ?? null, selectedTaskId ?? null],
    enabled:
      isTaskDrawerOpen && currentPlanId != null && selectedTaskId != null && selectedTaskId > 0,
    initialData: () => cachedResult,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      if (!currentPlanId || !selectedTaskId) {
        throw new Error('Missing plan or task information; unable to fetch execution result.');
      }
      return planTreeApi.getTaskResult(currentPlanId, selectedTaskId);
    },
    onSuccess: (result) => {
      if (selectedTaskId != null) {
        setTaskResult(selectedTaskId, result);
      }
    },
  });

  useEffect(() => {
    if (!isTaskDrawerOpen || !currentPlanId || !selectedTaskId) {
      return;
    }
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<PlanSyncEventDetail>).detail;
      if (
        !shouldHandlePlanSyncEvent(detail, currentPlanId ?? null, [
          'task_changed',
          'plan_jobs_completed',
          'plan_updated',
          'plan_deleted',
        ])
      ) {
        return;
      }
      if (detail?.type === 'plan_deleted' && detail.plan_id === currentPlanId) {
        closeTaskDrawer();
        return;
      }
      void refetchPlanTasks();
      void refetchTaskResult();
      window.setTimeout(() => {
        void refetchPlanTasks();
        void refetchTaskResult();
      }, 800);
    };

    window.addEventListener('tasksUpdated', handler as EventListener);
    return () => {
      window.removeEventListener('tasksUpdated', handler as EventListener);
    };
  }, [
    isTaskDrawerOpen,
    currentPlanId,
    selectedTaskId,
    refetchPlanTasks,
    refetchTaskResult,
    closeTaskDrawer,
  ]);

  const handleRefresh = useCallback(() => {
    if (!currentPlanId || !selectedTaskId) {
      return;
    }
    void refetchPlanTasks();
    void refetchTaskResult();
  }, [currentPlanId, selectedTaskId, refetchPlanTasks, refetchTaskResult]);

  const handleCopyJSON = useCallback(async (value: unknown, successMessage: string) => {
    try {
      const text = JSON.stringify(value, null, 2);
      await navigator.clipboard.writeText(text);
      message.success(successMessage);
    } catch (error) {
      console.warn('Copy failed', error);
      message.error('Copy failed. Please copy manually.');
    }
  }, []);

  const handleCopyTask = useCallback(() => {
    if (!activeTask) {
      return;
    }
    const payload = {
      task: activeTask,
      result: taskResult ?? cachedResult ?? null,
    };
    void handleCopyJSON(payload, 'Task details copied.');
  }, [activeTask, taskResult, cachedResult, handleCopyJSON]);

  const handleDependencyClick = useCallback(
    (dependencyId: number) => {
      if (dependencyId <= 0) {
        return;
      }
      const targetTask = taskMap.get(dependencyId);
      if (targetTask) {
        openTaskDrawer(targetTask);
        return;
      }
      openTaskDrawerById(dependencyId);
    },
    [openTaskDrawer, openTaskDrawerById, taskMap]
  );

  const renderDependencies = () => {
    if (!activeTask?.dependencies || activeTask.dependencies.length === 0) {
      return <Text type="secondary">No dependencies</Text>;
    }
    return (
      <Space wrap size={6}>
        {activeTask.dependencies.map((dep) => (
          <Button
            key={dep}
            size="small"
            type="link"
            onClick={() => handleDependencyClick(dep)}
          >
            Task #{dep}
          </Button>
        ))}
      </Space>
    );
  };

  const renderContextSections = () => {
    const sections = activeTask?.context_sections;
    if (!Array.isArray(sections) || sections.length === 0) {
      return null;
    }
    const items = sections.map((section, index) => {
      const title =
        typeof section?.title === 'string' && section.title.trim().length > 0
          ? section.title
          : `Section ${index + 1}`;
      const content =
        typeof section?.content === 'string'
          ? section.content
          : JSON.stringify(section, null, 2);
      return {
        key: String(index),
        label: title,
        children: <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{content}</Paragraph>,
      };
    });
    return <Collapse size="small" bordered={false} items={items} />;
  };

  const formatContextMetaValue = (value: unknown) => {
    if (value === null || value === undefined) {
      return <Text type="secondary">None</Text>;
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return <Text>{String(value)}</Text>;
    }
    return (
      <Paragraph
        code
        style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
      >
        {JSON.stringify(value, null, 2)}
      </Paragraph>
    );
  };

  const renderContextMeta = () => {
    const meta = activeTask?.context_meta;
    if (meta === null || meta === undefined) {
      return null;
    }

    let normalized: unknown = meta;
    if (typeof meta === 'string') {
      const trimmed = meta.trim();
      if (!trimmed) {
        return null;
      }
      try {
        normalized = JSON.parse(trimmed);
      } catch {
        return (
          <Paragraph
            code
            copyable
            style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
          >
            {trimmed}
          </Paragraph>
        );
      }
    }

    if (typeof normalized !== 'object' || normalized === null) {
      return <Text>{String(normalized)}</Text>;
    }

    if (Array.isArray(normalized)) {
      if (normalized.length === 0) {
        return null;
      }
      return (
        <Paragraph
          code
          copyable
          style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
        >
          {JSON.stringify(normalized, null, 2)}
        </Paragraph>
      );
    }

    const entries = Object.entries(normalized as Record<string, unknown>);
    if (entries.length === 0) {
      return null;
    }

    return (
      <Descriptions column={1} bordered size="small">
        {entries.map(([key, value]) => (
          <Descriptions.Item key={key} label={key}>
            {formatContextMetaValue(value)}
          </Descriptions.Item>
        ))}
      </Descriptions>
    );
  };

  const renderExecutionResult = () => {
    if (resultLoading && !taskResult && !cachedResult) {
      return (
        <div style={{ padding: '12px 0' }}>
          <Spin tip="Loading execution result..." />
        </div>
      );
    }

    const result = taskResult ?? cachedResult;
    if (!result) {
      return <Text type="secondary">No execution result yet</Text>;
    }

    return (
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        {result.status && (
          <Tag color={statusColorMap[result.status] ?? 'default'}>
            {statusLabelMap[result.status] ?? result.status}
          </Tag>
        )}
        {result.content && (
          <Paragraph style={{ whiteSpace: 'pre-wrap' }} copyable>
            {result.content}
          </Paragraph>
        )}
        {Array.isArray(result.notes) && result.notes.length > 0 && (
          <Collapse
            size="small"
            items={[
              {
                key: 'notes',
                label: `Notes (${result.notes.length})`,
                children: (
                  <Space direction="vertical">
                    {result.notes.map((note, idx) => (
                      <Paragraph key={idx} style={{ whiteSpace: 'pre-wrap', marginBottom: 8 }}>
                        {note}
                      </Paragraph>
                    ))}
                  </Space>
                ),
              },
            ]}
          />
        )}
        {result.metadata && Object.keys(result.metadata).length > 0 && (
          <Paragraph
            code
            copyable
            style={{ maxHeight: 200, overflow: 'auto' }}
          >
            {JSON.stringify(result.metadata, null, 2)}
          </Paragraph>
        )}
      </Space>
    );
  };

  const contextMetaContent = renderContextMeta();

  return (
    <Drawer
      width={480}
      title={
        activeTask
          ? (
            <Space direction="vertical" size={0}>
          <Title level={5} style={{ margin: 0 }}>
                {activeTask.name}
              </Title>
              <Text type="secondary">Task ID: {activeTask.id}</Text>
            </Space>
            )
          : 'Task details'
      }
      open={isTaskDrawerOpen}
      onClose={closeTaskDrawer}
      destroyOnClose={false}
      maskClosable
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            disabled={!currentPlanId || !selectedTaskId}
            loading={tasksLoading || resultLoading}
          >
            Refresh
          </Button>
          <Button
            icon={<CopyOutlined />}
            onClick={handleCopyTask}
            disabled={!activeTask}
          >
            Copy
          </Button>
        </Space>
      }
    >
      {!currentPlanId ? (
        <Empty description="No plan bound to the current session" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : !selectedTaskId ? (
        <Empty description="Select a task to view details" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : tasksLoading && !activeTask ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 0' }}>
          <Spin tip="Loading task information..." />
        </div>
      ) : !activeTask ? (
        <Empty description="Task not found; it may have been deleted" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <section>
            <Title level={5}>Basic info</Title>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="Task type">
                {activeTask.task_type ?? 'Unknown'}
              </Descriptions.Item>
              <Descriptions.Item label="Status">
                <Tag color={statusColorMap[activeTask.status ?? 'pending'] ?? 'default'}>
                  {statusLabelMap[activeTask.status ?? 'pending'] ??
                    activeTask.status ??
                    'Unknown'}
                </Tag>
              </Descriptions.Item>
              {activeTask.parent_id ? (
                <Descriptions.Item label="Parent task">
                  <Button
                    type="link"
                    size="small"
                    onClick={() => handleDependencyClick(activeTask.parent_id!)}
                  >
                    Task #{activeTask.parent_id}
                  </Button>
                </Descriptions.Item>
              ) : (
                <Descriptions.Item label="Parent task">None</Descriptions.Item>
              )}
              <Descriptions.Item label="Depth">
                {activeTask.depth ?? 0}
              </Descriptions.Item>
            </Descriptions>
          </section>

          <section>
            <Title level={5}>Task details</Title>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <div>
                <Text type="secondary">Instruction</Text>
                <Paragraph
                  style={{ whiteSpace: 'pre-wrap' }}
                  copyable
                  ellipsis={{ rows: 6, expandable: true, symbol: 'Expand' }}
                >
                  {activeTask.instruction || 'No description'}
                </Paragraph>
              </div>
              <div>
                <Text type="secondary">Dependencies</Text>
                {renderDependencies()}
              </div>
            </Space>
          </section>

          <section>
            <Title level={5}>Context</Title>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              {activeTask.context_combined ? (
                <Paragraph
                  style={{ whiteSpace: 'pre-wrap' }}
                  copyable
                  ellipsis={{ rows: 6, expandable: true, symbol: 'Expand' }}
                >
                  {activeTask.context_combined}
                </Paragraph>
              ) : (
                <Text type="secondary">No context summary</Text>
              )}
              {renderContextSections()}
              {contextMetaContent}
            </Space>
          </section>

          {recentToolResults.length > 0 && (
            <section>
              <Title level={5}>Recent search summaries</Title>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                {recentToolResults.map((result, index) => (
                  <ToolResultCard
                    key={`${result.name ?? 'tool'}_${index}`}
                    payload={result}
                    defaultOpen={index === 0}
                  />
                ))}
              </Space>
            </section>
          )}

          <section>
            <Title level={5}>Metadata</Title>
            {activeTask.metadata && Object.keys(activeTask.metadata).length > 0 ? (
              <Paragraph
                code
                copyable
                style={{ maxHeight: 200, overflow: 'auto' }}
              >
                {JSON.stringify(activeTask.metadata, null, 2)}
              </Paragraph>
            ) : (
              <Text type="secondary">No metadata</Text>
            )}
          </section>

          <section>
            <Title level={5}>Execution result</Title>
            {renderExecutionResult()}
          </section>
        </Space>
      )}
    </Drawer>
  );
};

export default TaskDetailDrawer;

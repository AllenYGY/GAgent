import * as React from 'react';
import { Card, Button, Space, Tag, Typography, Tooltip, Alert, Divider } from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DownOutlined,
  UpOutlined,
  FileTextOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

import { ENV } from '@/config/env';
import { planTreeApi } from '@api/planTree';
import type { ActionLogEntry, DecompositionJobStatus, JobLogEvent } from '@/types';
import { dispatchPlanSyncEvent } from '@utils/planSyncEvents';

dayjs.extend(relativeTime);

const { Text, Paragraph } = Typography;

const MAX_RENDER_LOGS = 200;
const FINAL_STATUSES = new Set(['succeeded', 'failed']);

const levelColorMap: Record<string, string> = {
  debug: 'default',
  info: 'blue',
  success: 'success',
  warning: 'orange',
  warn: 'orange',
  error: 'red',
};

const statusMeta: Record<
  string,
  {
    color: string;
    label: string;
    icon: React.ReactNode;
  }
> = {
  queued: {
    color: 'default',
    label: 'Queued',
    icon: <PauseCircleOutlined />,
  },
  running: {
    color: 'processing',
    label: 'Running',
    icon: <SyncOutlined spin />,
  },
  succeeded: {
    color: 'success',
    label: 'Completed',
    icon: <CheckCircleOutlined />,
  },
  failed: {
    color: 'error',
    label: 'Failed',
    icon: <CloseCircleOutlined />,
  },
};

const jobTypeMeta: Record<
  string,
  {
    label: string;
    color: string;
  }
> = {
  plan_decompose: {
    label: 'Task decomposition log',
    color: 'blue',
  },
  plan_execute: {
    label: 'Plan execution log',
    color: 'green',
  },
  chat_action: {
    label: 'Action execution log',
    color: 'purple',
  },
  default: {
    label: 'Background job log',
    color: 'geekblue',
  },
};

type StreamMessage =
  | { type: 'snapshot'; job: DecompositionJobStatus }
  | { type: 'heartbeat'; job: Partial<DecompositionJobStatus> & { job_id: string; status: string } }
  | {
      type: 'event';
      job_id: string;
      status?: string;
      event?: JobLogEvent;
      result?: Record<string, any>;
      error?: string | null;
      stats?: Record<string, any>;
      job_type?: string | null;
      metadata?: Record<string, any>;
    };

const parseStreamData = (raw: MessageEvent<any>): StreamMessage | null => {
  try {
    const payload = JSON.parse(raw.data);
    if (!payload) return null;
    if (payload.type === 'snapshot') {
      return payload as StreamMessage;
    }
    if (payload.type === 'heartbeat') {
      return payload as StreamMessage;
    }
    payload.type = 'event';
    return payload as StreamMessage;
  } catch (error) {
    console.warn('Unable to parse SSE message:', error);
    return null;
  }
};

interface JobLogPanelProps {
  jobId: string;
  initialJob?: DecompositionJobStatus | null;
  targetTaskName?: string | null;
  planId?: number | null;
  jobType?: string | null;
}

const JobLogPanel: React.FC<JobLogPanelProps> = ({ jobId, initialJob, targetTaskName, planId, jobType: initialJobType }) => {
  const [logs, setLogs] = React.useState<JobLogEvent[]>(initialJob?.logs ?? []);
  const [actionLogs, setActionLogs] = React.useState<ActionLogEntry[]>(initialJob?.action_logs ?? []);
  const [status, setStatus] = React.useState<string>(initialJob?.status ?? 'queued');
  const [stats, setStats] = React.useState<Record<string, any>>(initialJob?.stats ?? {});
  const [result, setResult] = React.useState<Record<string, any> | null>(initialJob?.result ?? null);
  const [error, setError] = React.useState<string | null>(initialJob?.error ?? null);
  const [expanded, setExpanded] = React.useState(true);
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = React.useState<string | null>(initialJob?.finished_at ?? initialJob?.started_at ?? initialJob?.created_at ?? null);
  const [missingJob, setMissingJob] = React.useState(false);
  const [jobType, setJobType] = React.useState<string>(initialJob?.job_type ?? initialJobType ?? 'plan_decompose');
  const [jobMetadata, setJobMetadata] = React.useState<Record<string, any>>(initialJob?.metadata ?? {});
  const [resolvedPlanId, setResolvedPlanId] = React.useState<number | null>(planId ?? initialJob?.plan_id ?? null);

  const sourceRef = React.useRef<EventSource | null>(null);
  const pollerRef = React.useRef<number | null>(null);
  const autoCollapsedRef = React.useRef(false);
  const statusRef = React.useRef<string>(initialJob?.status ?? 'queued');
  const actionCursorRef = React.useRef<string | null>(initialJob?.action_cursor ?? null);
  const completionNotifiedRef = React.useRef(false);

  const applySnapshot = React.useCallback((snapshot: DecompositionJobStatus | null) => {
    if (!snapshot) return;
    setStatus(snapshot.status);
    statusRef.current = snapshot.status;
    setStats(snapshot.stats ?? {});
    setResult(snapshot.result ?? null);
    setError(snapshot.error ?? null);
    if (snapshot.job_type) {
      setJobType(snapshot.job_type || 'plan_decompose');
    }
    if (snapshot.metadata && typeof snapshot.metadata === 'object') {
      setJobMetadata(snapshot.metadata);
    }
    if (snapshot.plan_id !== undefined && snapshot.plan_id !== null) {
      setResolvedPlanId(snapshot.plan_id);
    }
    if (Array.isArray(snapshot.logs)) {
      setLogs(snapshot.logs.slice(-MAX_RENDER_LOGS));
    }
    if (Array.isArray(snapshot.action_logs)) {
      setActionLogs(snapshot.action_logs);
    }
    if (snapshot.action_cursor !== undefined) {
      actionCursorRef.current = snapshot.action_cursor ?? null;
    }
    setLastUpdatedAt(snapshot.finished_at ?? snapshot.started_at ?? snapshot.created_at ?? null);
  }, []);

  const appendLogEvent = React.useCallback((event: JobLogEvent | undefined) => {
    if (!event) return;
    setLogs((prev) => {
      const next = [...prev, event];
      if (next.length > MAX_RENDER_LOGS) {
        return next.slice(-MAX_RENDER_LOGS);
      }
      return next;
    });
  }, []);

  const closeStream = React.useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  const stopPolling = React.useCallback(() => {
    if (pollerRef.current !== null) {
      window.clearInterval(pollerRef.current);
      pollerRef.current = null;
    }
  }, []);

  const startPolling = React.useCallback(() => {
    if (pollerRef.current !== null) return;
    pollerRef.current = window.setInterval(async () => {
      try {
        const snapshot = await planTreeApi.getJobStatus(jobId);
        applySnapshot(snapshot);
        if (FINAL_STATUSES.has(snapshot.status)) {
          stopPolling();
        }
      } catch (err) {
        const isNotFoundError = err instanceof Error && /not found/i.test(err.message || '');
        if (isNotFoundError) {
          setMissingJob(true);
          stopPolling();
        } else {
          console.error('Failed to poll job status:', err);
        }
      }
    }, 5000);
  }, [applySnapshot, jobId, stopPolling]);

  React.useEffect(() => {
    applySnapshot(initialJob ?? null);
  }, [applySnapshot, initialJob, jobId]);

  React.useEffect(() => {
    if (FINAL_STATUSES.has(status) && !autoCollapsedRef.current) {
      autoCollapsedRef.current = true;
      const timer = window.setTimeout(() => {
        setExpanded(false);
      }, 1800);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [status]);

  React.useEffect(() => {
    statusRef.current = status;
  }, [status]);

  React.useEffect(() => {
    completionNotifiedRef.current = false;
  }, [jobId]);

  React.useEffect(() => {
    if (!FINAL_STATUSES.has(status) || completionNotifiedRef.current) {
      return;
    }
    const planIdForEvent =
      resolvedPlanId ??
      (typeof jobMetadata?.plan_id === 'number' ? jobMetadata.plan_id : null) ??
      null;
    const planTitle =
      typeof jobMetadata?.plan_title === 'string' ? jobMetadata.plan_title : null;
    dispatchPlanSyncEvent(
      {
        type: 'plan_jobs_completed',
        plan_id: planIdForEvent,
        plan_title: planTitle,
        job_id: jobId,
        job_type: jobType ?? null,
        status,
      },
      {
        jobId,
        jobType: jobType ?? null,
        status,
        source: 'job.log',
      }
    );
    completionNotifiedRef.current = true;
  }, [jobId, jobMetadata, jobType, resolvedPlanId, status]);

  React.useEffect(() => {
    if (!jobId) {
      return undefined;
    }

    let cancelled = false;

    const isNotFoundError = (err: unknown) =>
      err instanceof Error && /not found/i.test(err.message || '');

    const init = async () => {
      try {
        const snapshot = await planTreeApi.getJobStatus(jobId);
        if (cancelled) {
          return;
        }
        setMissingJob(false);
        applySnapshot(snapshot);
      } catch (err) {
        if (cancelled) return;
        if (isNotFoundError(err)) {
          setMissingJob(true);
          closeStream();
          stopPolling();
          return;
        }
        console.error('Failed to load job status:', err);
        // fall back to polling
      }

      const streamUrl = `${ENV.API_BASE_URL}/jobs/${jobId}/stream`;
      try {
        const source = new EventSource(streamUrl);
        sourceRef.current = source;
        setIsStreaming(true);

        source.onmessage = (event) => {
          const parsed = parseStreamData(event);
          if (!parsed) return;

          if (parsed.type === 'snapshot') {
            applySnapshot(parsed.job);
            return;
          }

          if (parsed.type === 'heartbeat') {
            setStatus(parsed.job.status);
            statusRef.current = parsed.job.status;
            setStats(parsed.job.stats ?? {});
            if (parsed.job.job_type) {
              setJobType(parsed.job.job_type || 'plan_decompose');
            }
            if (parsed.job.metadata) {
              setJobMetadata(parsed.job.metadata as Record<string, any>);
            }
            if (parsed.job.plan_id !== undefined && parsed.job.plan_id !== null) {
              setResolvedPlanId(parsed.job.plan_id);
            }
            return;
          }

          if (parsed.status) {
            setStatus(parsed.status);
            statusRef.current = parsed.status;
          }
          if (parsed.stats) {
            setStats(parsed.stats);
          }
          if (parsed.result) {
            setResult(parsed.result);
          }
          if (parsed.error) {
            setError(parsed.error);
          }
          if (parsed.job_type) {
            setJobType(parsed.job_type || 'plan_decompose');
          }
          if (parsed.metadata) {
            setJobMetadata(parsed.metadata);
          }
          appendLogEvent(parsed.event);
          setLastUpdatedAt(new Date().toISOString());

          if (parsed.status && FINAL_STATUSES.has(parsed.status)) {
            closeStream();
          }
        };

        source.onerror = () => {
          if (FINAL_STATUSES.has(statusRef.current)) {
            closeStream();
            return;
          }
          console.warn('SSE connection interrupted; switching to polling.');
          closeStream();
          startPolling();
        };
      } catch (err) {
        console.warn('Failed to initialise SSE; falling back to polling:', err);
        startPolling();
      }
    };

    init();

    return () => {
      cancelled = true;
      closeStream();
      stopPolling();
    };
  }, [appendLogEvent, applySnapshot, closeStream, jobId, startPolling, stopPolling]);

  const statusInfo = statusMeta[status] || statusMeta.queued;

  const jobTypeInfo = React.useMemo(() => jobTypeMeta[jobType] ?? jobTypeMeta.default, [jobType]);

  const headerTitle = React.useMemo(() => {
    return (
      <Space size="small">
        <Tag color={statusInfo.color} style={{ marginRight: 0 }}>
          <Space size={4}>
            {statusInfo.icon}
            <span>{statusInfo.label}</span>
          </Space>
        </Tag>
        <Tag color={jobTypeInfo.color} style={{ marginRight: 0 }}>
          {jobTypeInfo.label}
        </Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>
          #{jobId.slice(0, 8)}
        </Text>
      </Space>
    );
  }, [jobId, statusInfo, jobTypeInfo]);

  const lastUpdatedText = React.useMemo(() => {
    if (!lastUpdatedAt) return null;
    return dayjs(lastUpdatedAt).fromNow();
  }, [lastUpdatedAt]);

  const renderLogMetadata = (metadata: Record<string, any> | undefined) => {
  if (!metadata || Object.keys(metadata).length === 0) return null;
  const pretty = JSON.stringify(metadata, null, 2);
  return (
    <div
      style={{
        background: '#f7f7f7',
        padding: 8,
        borderRadius: 4,
        marginTop: 4,
        maxHeight: 180,
        overflow: 'auto',
      }}
    >
      <pre
        style={{
          fontSize: 12,
          margin: 0,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {pretty}
      </pre>
    </div>
    );
  };

  const renderActionLogs = () => {
    if (!actionLogs.length) {
      return null;
    }
    return (
      <div style={{ width: '100%' }}>
        <Divider plain style={{ margin: '12px 0' }}>
          Action execution log
        </Divider>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          {actionLogs.map((entry) => {
            const statusKey = (entry.status || '').toLowerCase();
            const statusInfo = statusMeta[statusKey] || statusMeta.queued;
            const descriptor = entry.action_name ? `${entry.action_kind}/${entry.action_name}` : entry.action_kind;
            const timestamp = entry.created_at ?? entry.updated_at;
            return (
              <div key={`action_${entry.sequence}`} style={{ fontSize: 12, borderLeft: '2px solid #f0f0f0', paddingLeft: 8 }}>
                <Space size="small">
                  <Tag color={statusInfo.color} style={{ marginRight: 0 }}>
                    {statusInfo.icon}
                    <span style={{ marginLeft: 4 }}>{statusInfo.label}</span>
                  </Tag>
                  <Text strong>
                    Step {entry.sequence}: {descriptor}
                  </Text>
                </Space>
                {entry.message && (
                  <div style={{ marginTop: 4 }}>
                    <Text>{entry.message}</Text>
                  </div>
                )}
                {timestamp && (
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    {dayjs(timestamp).format('HH:mm:ss')}
                  </div>
                )}
                {entry.details && renderLogMetadata(entry.details as Record<string, any>)}
              </div>
            );
          })}
        </Space>
      </div>
    );
  };

  const renderLogs = () => {
    if (missingJob) {
      return (
        <Alert
          type="warning"
          message="Unable to load logs"
          description="The background job has been cleared or no longer exists."
          showIcon
        />
      );
    }
    if (!logs.length) {
      return (
        <Text type="secondary" style={{ fontSize: 12 }}>
          No logs available yet.
        </Text>
      );
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {logs.map((log, index) => {
          const color = levelColorMap[log.level?.toLowerCase()] ?? 'default';
          return (
            <div key={`${log.timestamp ?? 'log'}_${index}`} style={{ lineHeight: 1.4 }}>
              <Space size="small" align="start">
                <Tag color={color} style={{ marginRight: 0 }}>
                  {log.level?.toUpperCase() ?? 'INFO'}
                </Tag>
                <div>
                  <Text style={{ fontWeight: 500 }}>{log.message}</Text>
                  <div style={{ fontSize: 12, color: '#999' }}>
                    {log.timestamp ? dayjs(log.timestamp).format('HH:mm:ss') : ''}
                  </div>
                  {renderLogMetadata(log.metadata as Record<string, any>)}
                </div>
              </Space>
            </div>
          );
        })}
      </div>
    );
  };

  const renderResultSummary = () => {
    if (!result) return null;
    if (jobType === 'plan_decompose') {
      const createdTasks = Array.isArray(result.created_tasks) ? result.created_tasks : [];
      const stoppedReason = result.stopped_reason;
      return (
        <div style={{ marginTop: 12 }}>
          <Divider plain style={{ margin: '12px 0' }}>
            Execution summary
          </Divider>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Space size="small">
              <FileTextOutlined />
              <Text>New subtasks: {createdTasks.length}</Text>
            </Space>
            {stoppedReason && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                Stop reason: {stoppedReason}
              </Text>
            )}
          </Space>
        </div>
      );
    }

    if (jobType === 'chat_action') {
      const steps = Array.isArray(result.steps) ? (result.steps as any[]) : [];
      const failedSteps = steps.filter((step) => step?.success === false);
      const succeededSteps = steps.filter((step) => step?.success === true);
      const firstFailure = failedSteps[0];
      return (
        <div style={{ marginTop: 12 }}>
          <Divider plain style={{ margin: '12px 0' }}>
            Action summary
          </Divider>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Space size="small">
              <FileTextOutlined />
              <Text>Total actions: {steps.length}</Text>
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Succeeded: {succeededSteps.length}, Failed: {failedSteps.length}
            </Text>
            {firstFailure && (
              <Text type="danger" style={{ fontSize: 12 }}>
                First failed action: {firstFailure?.action?.name ?? '-'} — {firstFailure?.message ?? 'Execution failed'}
              </Text>
            )}
          </Space>
        </div>
      );
    }

    return null;
  };

  return (
    <Card
      size="small"
      style={{ marginTop: 12 }}
      title={headerTitle}
      extra={
        <Space size="small">
          <Tooltip title={isStreaming ? 'Live streaming' : 'Fetching via polling'}>
            {isStreaming ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
          </Tooltip>
          <Button
            type="link"
            size="small"
            icon={expanded ? <UpOutlined /> : <DownOutlined />}
            onClick={() => setExpanded((prev) => !prev)}
          >
            {expanded ? 'Collapse' : 'Expand'}
          </Button>
        </Space>
      }
      styles={{
        body: expanded
          ? { paddingTop: 12, paddingBottom: 12 }
          : { paddingTop: 0, paddingBottom: 0 },
      }}
    >
      {expanded && (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Space size="small">
              <Text type="secondary" style={{ fontSize: 12 }}>
                Target task:
              </Text>
              <Text>{targetTaskName ?? '-'}</Text>
            </Space>
            {resolvedPlanId !== null && resolvedPlanId !== undefined ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                Plan ID: {resolvedPlanId}
              </Text>
            ) : planId !== undefined && planId !== null ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                Plan ID: {planId}
              </Text>
            ) : null}
            {jobMetadata?.session_id && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                Session ID: {jobMetadata.session_id}
              </Text>
            )}
            {lastUpdatedText && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                Last update: {lastUpdatedText}
              </Text>
            )}
          </Space>

          {error && (
            <Alert
              type="error"
              message="Background execution failed"
              description={error}
              showIcon
            />
          )}

          {renderActionLogs()}
          {renderLogs()}
          {renderResultSummary()}

          {Object.keys(stats || {}).length > 0 && (
            <div style={{ fontSize: 12, color: '#999' }}>
              <Divider plain style={{ margin: '12px 0' }}>
                Statistics
              </Divider>
              <Paragraph
                copyable={{
                  text: JSON.stringify(stats, null, 2),
                }}
                style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
              >
                {JSON.stringify(stats, null, 2)}
              </Paragraph>
            </div>
          )}
        </Space>
      )}
    </Card>
  );
};

export default JobLogPanel;

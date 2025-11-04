import React from 'react';
import { Alert, Card, Empty, Space, Spin, Tag, Typography } from 'antd';
import type { SimulationRun, SimulationActionSpec } from '@/types';

const { Text, Paragraph } = Typography;
const DEFAULT_GOAL_TEXT = "Refine the currently bound plan to better achieve the user's objectives.";

interface SimulatedTranscriptProps {
  run: SimulationRun | null;
  loading?: boolean;
  error?: string | null;
}

const actionLabel = (action: SimulationActionSpec) => `${action.kind}/${action.name}`;

const formatParameters = (action: SimulationActionSpec) => {
  const params = action.parameters ?? {};
  if (!Object.keys(params).length) {
    return '{}';
  }
  try {
    return JSON.stringify(params, null, 2);
  } catch (error) {
    return String(params);
  }
};

const verdictTag = (alignment: string | undefined) => {
  switch (alignment) {
    case 'aligned':
      return <Tag color="green">Aligned</Tag>;
    case 'misaligned':
      return <Tag color="red">Misaligned</Tag>;
    case 'unclear':
      return <Tag color="orange">Unclear</Tag>;
    default:
      return <Tag>Pending</Tag>;
  }
};

const SimulatedTranscript: React.FC<SimulatedTranscriptProps> = ({ run, loading, error }) => {
  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 16 }}>
        <Alert type="error" message="Simulated user mode error" description={error} />
      </div>
    );
  }

  if (!run) {
    return (
      <div style={{ padding: 40 }}>
        <Empty description="No simulation run started yet." />
      </div>
    );
  }

  const lastTurnGoal = run.turns.length > 0 ? run.turns[run.turns.length - 1].goal : null;
  const goalText = run.config.improvement_goal || lastTurnGoal || DEFAULT_GOAL_TEXT;

  return (
    <div className="simulated-transcript">
      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title="Simulated Run Summary"
        extra={<Tag color="blue">{run.status.toUpperCase()}</Tag>}
      >
        <Space direction="vertical" size={4}>
          <Text>
            <strong>Run ID:</strong> {run.run_id}
          </Text>
          <Text>
            <strong>Goal:</strong> {goalText}
          </Text>
          <Text>
            <strong>Turns:</strong> {run.turns.length} / {run.config.max_turns}
          </Text>
          <Text>
            <strong>Remaining:</strong> {run.remaining_turns}
          </Text>
          {run.error && (
            <Alert
              type="error"
              message="Run encountered an error"
              description={run.error}
              showIcon
            />
          )}
        </Space>
      </Card>

      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {run.turns.map((turn) => (
          <Card
            key={turn.index}
            size="small"
            title={`Turn ${turn.index}`}
            extra={turn.judge ? verdictTag(turn.judge.alignment) : verdictTag(undefined)}
          >
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <div>
                <Text strong>Simulated user</Text>
                <Paragraph style={{ marginBottom: 4 }}>{turn.simulated_user.message}</Paragraph>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
                  Goal: {turn.goal || goalText}
                </Text>
                {turn.simulated_user.desired_action && (
                  <Card size="small" type="inner" title="Desired ACTION">
                    <Paragraph style={{ marginBottom: 0 }}>
                      <Text strong>{actionLabel(turn.simulated_user.desired_action)}</Text>
                    </Paragraph>
                    <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                      {formatParameters(turn.simulated_user.desired_action)}
                    </pre>
                  </Card>
                )}
              </div>

              <div>
                <Text strong>Chat agent</Text>
                <Paragraph style={{ marginBottom: 4 }}>{turn.chat_agent.reply}</Paragraph>
                {turn.chat_agent.actions.length > 0 ? (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    {turn.chat_agent.actions.map((action, idx) => (
                      <Card
                        key={`${turn.index}-chat-${idx}`}
                        size="small"
                        type="inner"
                        title={`Action ${idx + 1}: ${actionLabel(action)}`}
                      >
                        <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{formatParameters(action)}</pre>
                      </Card>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">No actions proposed.</Text>
                )}
              </div>

              <div>
                <Text strong>Judge verdict</Text>
                {turn.judge ? (
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Text>{turn.judge.explanation}</Text>
                    {typeof turn.judge.confidence === 'number' && (
                      <Text type="secondary">Confidence: {turn.judge.confidence.toFixed(2)}</Text>
                    )}
                  </Space>
                ) : (
                  <Text type="secondary">Awaiting judgement.</Text>
                )}
              </div>
            </Space>
          </Card>
        ))}
      </Space>
    </div>
  );
};

export default SimulatedTranscript;

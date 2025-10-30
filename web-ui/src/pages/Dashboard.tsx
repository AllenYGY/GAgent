import React from 'react';
import { Row, Col, Card, Statistic, Progress, Space, Typography, Button, message } from 'antd';
import {
  PlayCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  RobotOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { useSystemStore } from '@store/system';
import { useTasksStore } from '@store/tasks';
import { usePlanTasks } from '@hooks/usePlans';
import { useChatStore } from '@store/chat';
import TreeVisualization from '@components/dag/TreeVisualization';
import { ENV } from '@/config/env';

const { Title, Text } = Typography;

const Dashboard: React.FC = () => {
  const { systemStatus } = useSystemStore();
  const { tasks, getTaskStats } = useTasksStore();
  const { currentWorkflowId, currentSession, currentPlanId } = useChatStore((state) => ({
    currentWorkflowId: state.currentWorkflowId,
    currentSession: state.currentSession,
    currentPlanId: state.currentPlanId,
  }));

  const { data: planTasks = [] } = usePlanTasks({ planId: currentPlanId ?? undefined });

  // Normalize stats from different backend formats
  const processStats = (rawStats: any) => {
    if (!rawStats) return { total: 0, pending: 0, running: 0, completed: 0, failed: 0 };
    
    // When backend returns the newer schema
    if (rawStats.by_status) {
      return {
        total: rawStats.total || 0,
        pending: rawStats.by_status.pending || 0,
        running: rawStats.by_status.running || 0,
        completed: rawStats.by_status.done || rawStats.by_status.completed || 0,
        failed: rawStats.by_status.failed || 0,
      };
    }
    
    // Legacy schema fallback
    return {
      total: rawStats.total || 0,
      pending: rawStats.pending || 0,
      running: rawStats.running || 0,
      completed: rawStats.completed || 0,
      failed: rawStats.failed || 0,
    };
  };

  const statsSource = planTasks.length > 0
    ? {
        total: planTasks.length,
        pending: planTasks.filter((task) => task.status === 'pending').length,
        running: planTasks.filter((task) => task.status === 'running').length,
        completed: planTasks.filter((task) => task.status === 'completed').length,
        failed: planTasks.filter((task) => task.status === 'failed').length,
      }
    : getTaskStats();
  const stats = processStats(statsSource);

  return (
    <div>
      {/* Page title */}
      <div className="content-header">
        <Title level={3} style={{ margin: 0 }}>
          📊 Dashboard
        </Title>
        <Text type="secondary">
          AI Task Orchestration – real-time monitoring and control
        </Text>
      </div>

      <div className="content-body">
        {/* System stats cards */}
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="Total tasks"
                value={stats.total}
                prefix={<DatabaseOutlined />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
          
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="Pending"
                value={stats.pending}
                prefix={<ClockCircleOutlined />}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>
          
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="Running"
                value={stats.running}
                prefix={<PlayCircleOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="Completed"
                value={stats.completed}
                prefix={<CheckCircleOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
              {stats.failed > 0 && (
                <div style={{ marginTop: 8 }}>
                  <Text type="danger">
                    <ExclamationCircleOutlined /> {stats.failed} failed
                  </Text>
                </div>
              )}
            </Card>
          </Col>
        </Row>

        {/* System health */}
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} lg={12}>
            <Card title="🔥 System status" size="small">
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Text>API connection</Text>
                    <Text strong style={{ color: systemStatus.api_connected ? '#52c41a' : '#ff4d4f' }}>
                      {systemStatus.api_connected ? 'Connected' : 'Disconnected'}
                    </Text>
                  </div>
                  <Progress
                    percent={systemStatus.api_connected ? 100 : 0}
                    status={systemStatus.api_connected ? 'success' : 'exception'}
                    showInfo={false}
                    size="small"
                  />
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Text>Database</Text>
                    <Text strong style={{ 
                      color: systemStatus.database_status === 'connected' ? '#52c41a' : '#ff4d4f' 
                    }}>
                      {systemStatus.database_status === 'connected' ? 'Healthy' : 'Unavailable'}
                    </Text>
                  </div>
                  <Progress
                    percent={systemStatus.database_status === 'connected' ? 100 : 0}
                    status={systemStatus.database_status === 'connected' ? 'success' : 'exception'}
                    showInfo={false}
                    size="small"
                  />
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Text>CPU load</Text>
                    <Text strong>
                      {systemStatus.system_load.cpu}% CPU
                    </Text>
                  </div>
                  <Progress
                    percent={systemStatus.system_load.cpu}
                    status={systemStatus.system_load.cpu > 80 ? 'exception' : 'success'}
                    showInfo={false}
                    size="small"
                  />
                </div>
              </Space>
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card title="📈 API throughput" size="small">
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <Statistic
                  title="Requests per minute"
                  value={systemStatus.system_load.api_calls_per_minute}
                  suffix="req/min"
                  prefix={<RobotOutlined />}
                />
                
                <div>
                  <Text type="secondary">
                    💡 System is using the real GLM API (no mock mode).
                  </Text>
                </div>

                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Memory usage: {systemStatus.system_load.memory}%
                  </Text>
                  <Progress
                    percent={systemStatus.system_load.memory}
                    size="small"
                    showInfo={false}
                    style={{ marginTop: 4 }}
                  />
                </div>
              </Space>
            </Card>
          </Col>
        </Row>

        {/* DAG visualisation */}
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Card 
              title="🎯 Task orchestration map" 
              size="small"
              extra={
                <Button
                  onClick={async () => {
                    console.log('🔄 Testing PlanTree API manually...');
                    if (!currentPlanId) {
                      message.warning('No plan is bound; cannot request PlanTree data.');
                      return;
                    }
                    try {
                      const response = await fetch(`${ENV.API_BASE_URL}/plans/${currentPlanId}/tree`);
                      if (!response.ok) {
                        throw new Error(`PlanTree request failed: ${response.status}`);
                      }
                      const data = await response.json();
                      console.log('✅ PlanTree node count:', Object.keys(data.nodes || {}).length);
                    } catch (error) {
                      console.error('❌ PlanTree API debug failed:', error);
                      message.error('PlanTree API debug failed. Check backend services.');
                    }
                  }}
                >
                  Debug API
                </Button>
              }
            >
              <TreeVisualization />
            
            </Card>
          </Col>
        </Row>
      </div>
    </div>
  );
};

export default Dashboard;

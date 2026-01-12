import React from 'react';
import { Layout, Tooltip, Space, Typography } from 'antd';
import {
  RobotOutlined,
  ApiOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { useSystemStore } from '@store/system';
import { useTasksStore } from '@store/tasks';

const { Header } = Layout;
const { Text } = Typography;

const AppHeader: React.FC = () => {
  const { systemStatus, apiConnected } = useSystemStore();
  const { activeTasks, hasTasks } = useTasksStore((state) => {
    const count = state.tasks.reduce((total, task) => {
      if (task.status === 'pending' || task.status === 'running') {
        return total + 1;
      }
      return total;
    }, 0);
    return { activeTasks: count, hasTasks: state.tasks.length > 0 };
  });
  const activeTaskCount = hasTasks ? activeTasks : systemStatus.active_tasks;

  return (
    <Header className="app-header">
      <div className="app-logo">
        <RobotOutlined className="logo-icon" />
        <span>Research Agent</span>
      </div>
      
      <div className="app-header-actions">
        {/* System status indicators */}
        <Space size="large">
          <Tooltip title={`API connection: ${apiConnected ? 'connected' : 'disconnected'}`}>
            <div className="system-status">
              <ApiOutlined style={{ marginRight: 4 }} />
              <div className={`status-indicator ${apiConnected ? '' : 'disconnected'}`} />
              <Text style={{ color: 'white', fontSize: 12 }}>
                {apiConnected ? 'API connected' : 'API disconnected'}
              </Text>
            </div>
          </Tooltip>

          <Tooltip title={`Database: ${systemStatus.database_status}`}>
            <div className="system-status">
              <DatabaseOutlined style={{ marginRight: 4 }} />
              <div className={`status-indicator ${
                systemStatus.database_status === 'connected' ? '' : 
                systemStatus.database_status === 'error' ? 'disconnected' : 'warning'
              }`} />
              <Text style={{ color: 'white', fontSize: 12 }}>
                Database {systemStatus.database_status === 'connected' ? 'healthy' : 'unhealthy'}
              </Text>
            </div>
          </Tooltip>

          <Tooltip title="Active tasks">
            <div className="system-status">
              <Text style={{ color: 'white', fontSize: 12 }}>
                Active tasks: {activeTaskCount}
              </Text>
            </div>
          </Tooltip>

        </Space>

      </div>
    </Header>
  );
};

export default AppHeader;

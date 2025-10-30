import React from 'react';
import { Layout, Button, Badge, Tooltip, Space, Typography } from 'antd';
import {
  RobotOutlined,
  ApiOutlined,
  DatabaseOutlined,
  BellOutlined,
  SettingOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { useSystemStore } from '@store/system';
import { useChatStore } from '@store/chat';

const { Header } = Layout;
const { Text } = Typography;

const AppHeader: React.FC = () => {
  const { systemStatus, apiConnected } = useSystemStore();
  const { toggleChatPanel, chatPanelVisible } = useChatStore();

  return (
    <Header className="app-header">
      <div className="app-logo">
        <RobotOutlined className="logo-icon" />
        <span>AI Task Orchestration System</span>
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
                Active tasks: {systemStatus.active_tasks}
              </Text>
            </div>
          </Tooltip>

          <Tooltip title="API calls per minute">
            <div className="system-status">
              <Text style={{ color: 'white', fontSize: 12 }}>
                API: {systemStatus.system_load.api_calls_per_minute}/min
              </Text>
            </div>
          </Tooltip>
        </Space>

        {/* Action buttons */}
        <Space>
          <Tooltip title="Notifications">
            <Badge count={0} size="small">
              <Button 
                type="text" 
                icon={<BellOutlined />} 
                style={{ color: 'white' }}
              />
            </Badge>
          </Tooltip>

          <Tooltip title={chatPanelVisible ? 'Hide chat panel' : 'Show chat panel'}>
            <Button 
              type="text" 
              icon={<MessageOutlined />} 
              style={{ color: 'white' }}
              onClick={toggleChatPanel}
            />
          </Tooltip>

          <Tooltip title="System settings">
            <Button 
              type="text" 
              icon={<SettingOutlined />} 
              style={{ color: 'white' }}
            />
          </Tooltip>
        </Space>
      </div>
    </Header>
  );
};

export default AppHeader;

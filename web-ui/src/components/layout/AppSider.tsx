import React from 'react';
import { Button, Layout, Menu, Tooltip } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  NodeIndexOutlined,
  ProjectOutlined,
  DatabaseOutlined,
  MessageOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';

const { Sider } = Layout;

interface AppSiderProps {
  collapsed: boolean;
  onToggle: () => void;
}

interface MenuItem {
  key: string;
  icon: React.ReactNode;
  label: string;
  path: string;
}

const menuItems: MenuItem[] = [
  {
    key: 'dashboard',
    icon: <DashboardOutlined />,
    label: 'Dashboard',
    path: '/dashboard',
  },
  {
    key: 'chat',
    icon: <MessageOutlined />,
    label: 'AI Chat',
    path: '/chat',
  },
  {
    key: 'tasks',
    icon: <NodeIndexOutlined />,
    label: 'Task Management',
    path: '/tasks',
  },
  {
    key: 'plans',
    icon: <ProjectOutlined />,
    label: 'Plan Management',
    path: '/plans',
  },
  {
    key: 'memory',
    icon: <DatabaseOutlined />,
    label: 'Memory Vault',
    path: '/memory',
  },
];

const AppSider: React.FC<AppSiderProps> = ({ collapsed, onToggle }) => {
  const navigate = useNavigate();
  const location = useLocation();

  // Determine active menu item from the current path
  const selectedKeys = [location.pathname.slice(1) || 'dashboard'];

  const handleMenuClick = (item: { key: string }) => {
    const menuItem = menuItems.find(m => m.key === item.key);
    if (menuItem) {
      navigate(menuItem.path);
    }
  };

  return (
    <Sider
      width={200}
      collapsedWidth={64}
      collapsed={collapsed}
      trigger={null}
      className="app-sider"
    >
      <div
        style={{
          display: 'flex',
          justifyContent: collapsed ? 'center' : 'flex-end',
          padding: '8px 12px',
        }}
      >
        <Tooltip title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <Button
            type="text"
            size="small"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={onToggle}
            style={{ color: 'white' }}
          />
        </Tooltip>
      </div>
      <Menu
        mode="inline"
        selectedKeys={selectedKeys}
        className="sider-menu"
        theme="dark"
        onClick={handleMenuClick}
        inlineCollapsed={collapsed}
        items={menuItems.map(item => ({
          key: item.key,
          icon: item.icon,
          label: item.label,
        }))}
      />
    </Sider>
  );
};

export default AppSider;

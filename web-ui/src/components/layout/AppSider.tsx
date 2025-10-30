import React from 'react';
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  NodeIndexOutlined,
  ProjectOutlined,
  SettingOutlined,
  BarChartOutlined,
  ToolOutlined,
  BookOutlined,
  DatabaseOutlined,
  MessageOutlined,
} from '@ant-design/icons';

const { Sider } = Layout;

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
  {
    key: 'analytics',
    icon: <BarChartOutlined />,
    label: 'Analytics',
    path: '/analytics',
  },
  {
    key: 'tools',
    icon: <ToolOutlined />,
    label: 'Toolbox',
    path: '/tools',
  },
  {
    key: 'templates',
    icon: <BookOutlined />,
    label: 'Templates',
    path: '/templates',
  },
  {
    key: 'system',
    icon: <SettingOutlined />,
    label: 'System Settings',
    path: '/system',
  },
];

const AppSider: React.FC = () => {
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
    <Sider width={200} className="app-sider">
      <Menu
        mode="inline"
        selectedKeys={selectedKeys}
        className="sider-menu"
        theme="dark"
        onClick={handleMenuClick}
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

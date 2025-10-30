import React from 'react';
import { Layout } from 'antd';
import ChatSidebar from './ChatSidebar';
import ChatMainArea from './ChatMainArea';
import DAGSidebar from './DAGSidebar';
import TaskDetailDrawer from '@components/tasks/TaskDetailDrawer';

const ChatLayout: React.FC = () => {
  return (
    <>
      <Layout style={{
        height: 'calc(100vh - 64px)', // Subtract header height
        overflow: 'hidden',
        margin: '-24px', // Offset parent Content padding
      }}>
        {/* Left conversation list */}
        <Layout.Sider 
          width={280} 
          style={{ 
            background: '#f8f9fa',
            borderRight: '1px solid #e5e7eb'
          }}
        >
          <ChatSidebar />
        </Layout.Sider>

        {/* Main chat area */}
        <Layout.Content 
          style={{ 
            background: 'white',
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0 // Prevent flex children overflow
          }}
        >
          <ChatMainArea />
        </Layout.Content>

        {/* Right-hand DAG visualization */}
        <Layout.Sider 
          width={400} 
          style={{ 
            background: 'white',
            borderLeft: '1px solid #e5e7eb'
          }}
          reverseArrow
        >
          <DAGSidebar />
        </Layout.Sider>
      </Layout>
      <TaskDetailDrawer />
    </>
  );
};

export default ChatLayout;

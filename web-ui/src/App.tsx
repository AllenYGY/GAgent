import { useEffect, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { App as AntdApp, Layout } from 'antd';
import { useSystemStore } from '@store/system';
import { checkApiHealth } from '@api/client';
import AppHeader from '@components/layout/AppHeader';
import AppSider from '@components/layout/AppSider';
import ErrorBoundary from '@components/common/ErrorBoundary';
import ChatLayout from '@components/layout/ChatLayout';
import Dashboard from '@pages/Dashboard';
import Tasks from '@pages/Tasks';
import Plans from '@pages/Plans';
import Memory from '@pages/Memory';
import System from '@pages/System';
import { ENV } from '@/config/env';

function App() {
  const { message } = AntdApp.useApp();
  const { setSystemStatus, setApiConnected, refreshApiCallRate } = useSystemStore();
  const [siderCollapsed, setSiderCollapsed] = useState(false);

  // Initialize system status checks
  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      console.error('Unhandled error:', event.error || event.message);
      message.error(`Frontend runtime error: ${event.message || 'Unknown error'}`, 6);
    };
    const handleRejection = (event: PromiseRejectionEvent) => {
      const reason = (event.reason && (event.reason.message || event.reason.toString())) || 'Unknown reason';
      console.error('Unhandled rejection:', event.reason);
      message.error(`Unhandled frontend exception: ${reason}`, 6);
    };

    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleRejection);

    const initializeApp = async () => {
      console.log('🚀 Initializing Research Agent...');
      console.log('⚡ Running in PRODUCTION mode - using REAL APIs (No Mock)');

      try {
        // Add a slight delay to ensure components finish mounting
        await new Promise(resolve => setTimeout(resolve, 500));

        const healthData = await checkApiHealth();

        console.log('🏥 Health check result:', healthData);

        setApiConnected(healthData.api_connected);
        setSystemStatus({
          api_connected: healthData.api_connected,
          database_status: healthData.api_connected ? 'connected' : 'disconnected',
          active_tasks: 0,
          total_plans: 0,
          system_load: {
            cpu: 0,
            memory: 0,
            api_calls_per_minute: 0,
          },
        });

        if (healthData.api_connected) {
          message.success('🎉 System connected successfully! All services are operational.', 5);
          console.log('✅ GLM API Status:', healthData.llm_status);
        } else {
          console.error('❌ API connection failed');
          message.error(`❌ Backend connection failed. Please confirm the service is running at ${ENV.API_BASE_URL}`, 10);
          setApiConnected(false);
        }
      } catch (error) {
        console.error('❌ App initialization failed:', error);
        message.error('❌ App initialization failed. Please check network connectivity and backend services.', 10);
        setApiConnected(false);
        setSystemStatus({
          api_connected: false,
          database_status: 'disconnected',
          active_tasks: 0,
          total_plans: 0,
          system_load: {
            cpu: 0,
            memory: 0,
            api_calls_per_minute: 0,
          },
        });
      }
    };

    initializeApp();

    return () => {
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleRejection);
    };
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      refreshApiCallRate();
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [refreshApiCallRate]);

  return (
    <ErrorBoundary>
      <Layout style={{ minHeight: '100vh' }}>
        <AppHeader />
        <Layout>
          <AppSider
            collapsed={siderCollapsed}
            onToggle={() => setSiderCollapsed((prev) => !prev)}
          />
          <Layout.Content style={{ padding: '24px', background: '#f0f2f5' }}>
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<ErrorBoundary><Dashboard /></ErrorBoundary>} />
                <Route path="/chat" element={<ErrorBoundary><ChatLayout /></ErrorBoundary>} />
                <Route path="/tasks" element={<ErrorBoundary><Tasks /></ErrorBoundary>} />
                <Route path="/plans" element={<ErrorBoundary><Plans /></ErrorBoundary>} />
                <Route path="/memory" element={<ErrorBoundary><Memory /></ErrorBoundary>} />
                <Route path="/system" element={<ErrorBoundary><System /></ErrorBoundary>} />
              </Routes>
            </ErrorBoundary>
          </Layout.Content>
        </Layout>
      </Layout>
    </ErrorBoundary>
  );
}

export default App;

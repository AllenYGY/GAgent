import React, { useRef, useEffect } from 'react';
import { App as AntdApp, Input, Button, Space, Typography, Avatar, Divider, Tooltip, Select, Switch, Empty, Tag } from 'antd';
import {
  SendOutlined,
  PaperClipOutlined,
  ReloadOutlined,
  ClearOutlined,
  RobotOutlined,
  UserOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { useChatStore } from '@store/chat';
import { useTasksStore } from '@store/tasks';
import { useSimulationStore } from '@store/simulation';
import ChatMessage from './ChatMessage';
import type { SimulationRunStatus } from '@/types';

const { TextArea } = Input;
const { Title, Text } = Typography;

const ChatPanel: React.FC = () => {
  const { message } = AntdApp.useApp();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<any>(null);

  const {
    messages,
    inputText,
    isProcessing,
    isTyping,
    chatPanelVisible,
    setInputText,
    sendMessage,
    clearMessages,
    retryLastMessage,
    currentSession,
    defaultSearchProvider,
    setDefaultSearchProvider,
    isUpdatingProvider,
  } = useChatStore();

  const { selectedTask, currentPlan } = useTasksStore();
  const {
    enabled: simulatedModeEnabled,
    isLoading: simulationLoading,
    currentRun: simulationRun,
    error: simulationError,
    pollingRunId,
    transcript: simulationTranscript,
    lastUpdatedAt,
    setEnabled: setSimulationEnabled,
    cancelRun: cancelSimulationRun,
    refreshRun: refreshSimulationRun,
  } = useSimulationStore((state) => ({
    enabled: state.enabled,
    isLoading: state.isLoading,
    currentRun: state.currentRun,
    error: state.error,
    pollingRunId: state.pollingRunId,
    transcript: state.transcript,
    lastUpdatedAt: state.lastUpdatedAt,
    setEnabled: state.setEnabled,
    cancelRun: state.cancelRun,
    refreshRun: state.refreshRun,
  }));
  const hasSimulationTranscript = simulationTranscript.length > 0;
  const showSimulationView = simulatedModeEnabled || hasSimulationTranscript;
  const displayedMessages = messages;
  const simulationInProgress = showSimulationView && (simulationLoading || Boolean(pollingRunId));

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayedMessages.length, simulatedModeEnabled]);

  // Send message
  const handleSendMessage = async () => {
    if (!inputText.trim() || isProcessing || simulatedModeEnabled) return;

    const metadata = {
      task_id: selectedTask?.id,
      plan_title: currentPlan || undefined,
    };

    await sendMessage(inputText.trim(), metadata);
  };

  // Handle keyboard shortcuts
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (simulatedModeEnabled) {
        e.preventDefault();
        return;
      }
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Track input changes
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
  };

  // Quick actions
  const handleQuickAction = (action: string) => {
    const quickMessages = {
      create_plan: 'Please create a new plan.',
      list_tasks: 'Show all current tasks.',
      system_status: 'Show the system status.',
      help: 'What can you do?',
    };

    const message = quickMessages[action as keyof typeof quickMessages];
    if (message) {
      setInputText(message);
      inputRef.current?.focus();
    }
  };

  const handleProviderChange = async (value: string | undefined) => {
    try {
      await setDefaultSearchProvider((value as 'builtin' | 'perplexity') ?? null);
    } catch (error) {
      console.error('Failed to switch search provider:', error);
      message.error('Failed to switch search provider. Please try again later.');
    }
  };

  const handleSimulationToggle = async (checked: boolean) => {
    if (!checked && simulationRun) {
      try {
        await cancelSimulationRun();
      } catch (error) {
        message.warning('Unable to stop the active simulation; please try again.');
      }
    }
    setSimulationEnabled(checked);
  };

  const handleSimulationRefresh = async () => {
    if (!simulationRun) {
      return;
    }
    try {
      await refreshSimulationRun(simulationRun.run_id);
    } catch (error) {
      console.error('Failed to refresh simulation status:', error);
    }
  };

  const statusColorMap: Record<SimulationRunStatus, string> = {
    idle: 'default',
    running: 'geekblue',
    finished: 'green',
    cancelled: 'volcano',
    error: 'red',
  };

  const renderSimulationBanner = () => {
    if (!showSimulationView) {
      return null;
    }
    const status = simulationRun?.status ?? 'idle';
    const statusTagColor = statusColorMap[status as SimulationRunStatus] ?? 'default';
    const statusLabel = status.toUpperCase();

    const formatTimestamp = (value: Date | null | undefined) => {
      if (!value) {
        return null;
      }
      const date = value instanceof Date ? value : new Date(value);
      if (Number.isNaN(date.getTime())) {
        return null;
      }
      return date.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    };

    const lastUpdatedLabel = formatTimestamp(lastUpdatedAt);

    return (
      <div
        style={{
          marginBottom: 12,
          padding: '8px 12px',
          background: '#f5f5f5',
          border: '1px solid #e8e8e8',
          borderRadius: 8,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <Space size={8} wrap align="center">
            <Tag color={statusTagColor} style={{ marginRight: 0 }}>
              {statusLabel}
            </Tag>
            {simulationRun && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                Turns {simulationRun.turns.length}/{simulationRun.config.max_turns} · Remaining{' '}
                {simulationRun.remaining_turns}
              </Text>
            )}
            {pollingRunId && simulationInProgress && (
              <Tag color="geekblue" style={{ marginRight: 0 }}>
                Auto-refreshing
              </Tag>
            )}
            {lastUpdatedLabel && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                Last update {lastUpdatedLabel}
              </Text>
            )}
          </Space>
          <Space size={8}>
            <Tooltip title="Refresh simulation status">
              <Button
                size="small"
                type="text"
                icon={<ReloadOutlined />}
                onClick={handleSimulationRefresh}
                loading={simulationLoading}
                disabled={!simulationRun}
              />
            </Tooltip>
            {simulationRun && (
              <Tooltip title="Stop simulation">
                <Button
                  size="small"
                  type="text"
                  danger
                  onClick={() => handleSimulationToggle(false)}
                  disabled={simulationLoading}
                >
                  Stop
                </Button>
              </Tooltip>
            )}
          </Space>
        </div>
        {simulationError && (
          <Text type="danger" style={{ fontSize: 12, marginTop: 6, display: 'block' }}>
            {simulationError}
          </Text>
        )}
      </div>
    );
  };

  const providerOptions = [
    { label: 'Built-in search', value: 'builtin' },
    { label: 'Perplexity search', value: 'perplexity' },
  ];

  const providerValue = defaultSearchProvider ?? undefined;

  if (!chatPanelVisible) {
    return null;
  }

  return (
    <div className="chat-panel">
      {/* Chat header */}
      <div className="chat-header">
        <Space align="center">
          <Avatar icon={<RobotOutlined />} size="small" />
          <div>
            <Title level={5} style={{ margin: 0 }}>
              AI Task Orchestration Assistant
            </Title>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isProcessing ? 'Thinking...' : isTyping ? 'Typing...' : 'Online'}
            </Text>
          </div>
        </Space>

        <Space>
          <Tooltip title="Simulated user mode">
            <Switch
              size="small"
              checked={simulatedModeEnabled}
              onChange={handleSimulationToggle}
            />
          </Tooltip>
          <Tooltip title="Clear conversation">
            <Button
              type="text"
              size="small"
              icon={<ClearOutlined />}
              onClick={clearMessages}
            />
          </Tooltip>
        </Space>
      </div>

      {/* Message list */}
      <div className="chat-messages">
        {renderSimulationBanner()}
        {displayedMessages.length === 0 ? (
          showSimulationView ? (
            simulationInProgress ? (
              <div style={{ textAlign: 'center', padding: '24px 16px', color: '#999' }}>
                <Text>Running simulated user loop…</Text>
              </div>
            ) : (
              <div style={{ padding: '40px 20px' }}>
                <Empty description="Start the simulation to see messages." />
              </div>
            )
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: '#999' }}>
              <MessageOutlined style={{ fontSize: 32, marginBottom: 16 }} />
              <div>
                <Text>Hello! I'm your AI task orchestration assistant.</Text>
              </div>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  I can help you create plans, manage tasks, and orchestrate workflows.
                </Text>
              </div>
              
              {/* Quick action shortcuts */}
              <div style={{ marginTop: 16 }}>
                <Space direction="vertical" size="small">
                  <Button
                    size="small"
                    type="link"
                    onClick={() => handleQuickAction('create_plan')}
                  >
                    📋 Create a new plan
                  </Button>
                  <Button
                    size="small"
                    type="link"
                    onClick={() => handleQuickAction('list_tasks')}
                  >
                    📝 View task list
                  </Button>
                  <Button
                    size="small"
                    type="link"
                    onClick={() => handleQuickAction('system_status')}
                  >
                    📊 System status
                  </Button>
                  <Button
                    size="small"
                    type="link"
                    onClick={() => handleQuickAction('help')}
                  >
                    ❓ Help
                  </Button>
                </Space>
              </div>
            </div>
          )
        ) : (
          <>
            {displayedMessages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            
            {/* Processing indicator */}
            {isProcessing && (
              <div className="message assistant">
                <div className="message-avatar assistant">
                  <RobotOutlined />
                </div>
                <div className="message-content">
                  <div className="message-bubble">
                    <Text>Thinking...</Text>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
        {showSimulationView && simulationInProgress && displayedMessages.length > 0 && (
          <div className="message assistant">
            <div className="message-avatar assistant">
              <RobotOutlined />
            </div>
            <div className="message-content">
              <div className="message-bubble">
                <Text>Running simulation…</Text>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Context banner */}
      {currentPlan && (
        <>
          <Divider style={{ margin: '8px 0' }} />
          <div style={{ padding: '0 16px 8px', fontSize: 12, color: '#666' }}>
            Current plan: {currentPlan}
          </div>
        </>
      )}

      {/* Composer */}
      <div className="chat-input-area">
        <div className="chat-input-main">
          <TextArea
            ref={inputRef}
            value={inputText}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder={
              simulatedModeEnabled
                ? 'Simulated mode active. Use simulation controls to run turns.'
                : 'Type a message... (Shift+Enter for newline, Enter to send)'
            }
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={isProcessing || simulatedModeEnabled}
            style={{ flex: 1 }}
          />
          <div className="chat-input-side">
            <Select
              size="small"
              value={providerValue}
              placeholder="Choose a web search provider"
              options={providerOptions}
              allowClear
              onChange={handleProviderChange}
              disabled={!currentSession || isProcessing}
              loading={isUpdatingProvider}
              style={{ width: '100%' }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSendMessage}
              disabled={!inputText.trim() || isProcessing || simulatedModeEnabled}
              loading={isProcessing}
              style={{ width: '100%' }}
            />
          </div>
        </div>

        <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between' }}>
          <Space size="small">
            <Tooltip title="Attachment">
              <Button 
                type="text" 
                size="small" 
                icon={<PaperClipOutlined />}
                disabled
              />
            </Tooltip>
          </Space>

          <Space size="small">
            <Tooltip title="Retry">
              <Button
                type="text"
                size="small"
                icon={<ReloadOutlined />}
                onClick={retryLastMessage}
                disabled={isProcessing || messages.length === 0}
              />
            </Tooltip>
          </Space>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;

import React, { useRef, useEffect } from 'react';
import { App as AntdApp, Card, Input, Button, Space, Typography, Avatar, Divider, Tooltip, Select } from 'antd';
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
import ChatMessage from './ChatMessage';

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

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Send message
  const handleSendMessage = async () => {
    if (!inputText.trim() || isProcessing) return;

    const metadata = {
      task_id: selectedTask?.id,
      plan_title: currentPlan || undefined,
    };

    await sendMessage(inputText.trim(), metadata);
  };

  // Handle keyboard shortcuts
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
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
        {messages.length === 0 ? (
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
        ) : (
          <>
            {messages.map((message) => (
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
            placeholder="Type a message... (Shift+Enter for newline, Enter to send)"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={isProcessing}
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
              disabled={!inputText.trim() || isProcessing}
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

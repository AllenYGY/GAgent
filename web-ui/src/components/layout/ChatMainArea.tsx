import React, { useRef, useEffect, useMemo } from 'react';
import {
  App as AntdApp,
  Input,
  Button,
  Space,
  Typography,
  Avatar,
  Divider,
  Empty,
  Alert,
  Tag,
  Tooltip,
  Switch,
  Select,
} from 'antd';
import {
  SendOutlined,
  PaperClipOutlined,
  RobotOutlined,
  UserOutlined,
  MessageOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { useChatStore } from '@store/chat';
import { useTasksStore } from '@store/tasks';
import ChatMessage from '@components/chat/ChatMessage';

const { TextArea } = Input;
const { Title, Text } = Typography;

const ChatMainArea: React.FC = () => {
  const { message } = AntdApp.useApp();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<any>(null);

  const {
    messages,
    inputText,
    isProcessing,
    currentSession,
    currentPlanTitle,
    currentTaskName,
    memoryEnabled,
    relevantMemories,
    setInputText,
    sendMessage,
    startNewSession,
    loadSessions,
    loadChatHistory,
    toggleMemory,
    defaultSearchProvider,
    setDefaultSearchProvider,
    isUpdatingProvider,
    pendingPlanCreation,
  } = useChatStore();

  const { selectedTask, currentPlan } = useTasksStore();
  const planCreationPending = useMemo(() => {
    if (!pendingPlanCreation) {
      return null;
    }
    const sessionId =
      currentSession?.session_id ?? currentSession?.id ?? null;
    if (!pendingPlanCreation.sessionId || pendingPlanCreation.sessionId === sessionId) {
      return pendingPlanCreation;
    }
    return null;
  }, [currentSession, pendingPlanCreation]);

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Initialise the session: try to recover from backend first
  useEffect(() => {
    (async () => {
      if (currentSession) {
        return;
      }
      try {
        await loadSessions();
        const selected = useChatStore.getState().currentSession;
        if (selected) {
          await loadChatHistory(selected.id);
          return;
        }
        const session = startNewSession('AI Task Orchestration Assistant');
        await loadChatHistory(session.id);
      } catch (err) {
        console.warn('[ChatMainArea] Failed to initialise session; creating a new one:', err);
        const session = startNewSession('AI Task Orchestration Assistant');
        await loadChatHistory(session.id);
      }
    })();
  }, [currentSession, loadSessions, loadChatHistory, startNewSession]);

  // Send message
  const handleSendMessage = async () => {
    if (!inputText.trim() || isProcessing) return;

    const metadata = {
      task_id: selectedTask?.id ?? undefined,
      plan_title: currentPlan || currentPlanTitle || undefined,
      task_name: selectedTask?.name ?? currentTaskName ?? undefined,
    };

    await sendMessage(inputText.trim(), metadata);
    inputRef.current?.focus();
  };

  const handleProviderChange = async (value: string | undefined) => {
    try {
      await setDefaultSearchProvider((value as 'builtin' | 'perplexity') ?? null);
    } catch (err) {
      console.error('[ChatMainArea] Failed to change search provider:', err);
      message.error('Failed to change search provider. Please try again later.');
    }
  };

  const providerOptions = [
    { label: 'Built-in search', value: 'builtin' },
    { label: 'Perplexity search', value: 'perplexity' },
  ];

  const providerValue = defaultSearchProvider ?? undefined;

  // Keyboard shortcut: submit on Enter
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Quick actions
  const quickActions = [
    { text: 'Create a new plan', action: () => setInputText('Please create a new plan.') },
    { text: 'View task status', action: () => setInputText('Show the status of all current tasks.') },
    { text: 'System help', action: () => setInputText('What can you do?') },
  ];

  // Welcome screen for empty sessions
  const renderWelcome = () => (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      padding: '0 40px',
      textAlign: 'center',
    }}>
      <Avatar
        size={64}
        icon={<RobotOutlined />}
        style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          marginBottom: 16,
        }}
      />

      <Title level={3} style={{ marginBottom: 12, color: '#1f2937' }}>
        AI Task Orchestration Assistant
      </Title>

      <Text
        style={{
          fontSize: 14,
          color: '#6b7280',
          marginBottom: 24,
          lineHeight: 1.5,
        }}
      >
        I can help you create plans, break tasks down, and orchestrate execution so complex projects become manageable.
      </Text>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 280 }}>
        {quickActions.map((action, index) => (
          <Button
            key={index}
            size="middle"
            style={{
              height: 40,
              borderRadius: 8,
              border: '1px solid #e5e7eb',
              background: 'white',
              boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-start',
              paddingLeft: 16,
            }}
            onClick={action.action}
          >
            <MessageOutlined style={{ marginRight: 10, color: '#6366f1', fontSize: 14 }} />
            <span style={{ color: '#374151', fontWeight: 500, fontSize: 14 }}>{action.text}</span>
          </Button>
        ))}
      </div>

      <Divider style={{ margin: '24px 0', width: '100%' }} />

      <Text type="secondary" style={{ fontSize: 13 }}>
        💡 Describe what you need in natural language and I will figure out how to help.
      </Text>
    </div>
  );

  return (
    <div style={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column',
      background: 'white',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 20px',
        borderBottom: '1px solid #f0f0f0',
        background: 'white',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Avatar size={32} icon={<RobotOutlined />} style={{ background: '#52c41a' }} />
            <div>
              <Text strong style={{ fontSize: 16 }}>
                {currentSession?.title || 'AI Task Orchestration Assistant'}
              </Text>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 2 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {isProcessing ? 'Thinking...' : 'Online'}
                </Text>
                {messages.length > 0 && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Messages: {messages.length}
                  </Text>
                )}
              </div>
            </div>
          </div>

          {/* Context details and memory toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Memory toggle */}
            <Tooltip title={memoryEnabled ? 'Memory augmentation enabled' : 'Memory augmentation disabled'}>
              <Space size="small">
                <DatabaseOutlined style={{ color: memoryEnabled ? '#52c41a' : '#d9d9d9', fontSize: 16 }} />
                <Switch
                  checked={memoryEnabled}
                  onChange={toggleMemory}
                  size="small"
                  checkedChildren="Memory"
                  unCheckedChildren="Memory"
                />
              </Space>
            </Tooltip>
          </div>
        </div>
      </div>

      {/* Message list */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        background: '#fafbfc',
      }}>
        {messages.length === 0 ? (
          renderWelcome()
        ) : (
          <div style={{
            padding: '16px 20px',
            maxWidth: 800,
            margin: '0 auto',
            width: '100%',
          }}>
            {/* Related memory banner */}
            {relevantMemories.length > 0 && (
              <Alert
                message={`🧠 Found ${relevantMemories.length} related memories`}
                description={
                  <Space wrap>
                    {relevantMemories.map(m => (
                      <Tag key={m.id} color="blue">
                        {m.keywords.slice(0, 2).join(', ')} ({(m.similarity! * 100).toFixed(0)}%)
                      </Tag>
                    ))}
                  </Space>
                }
                type="info"
                closable
                style={{ marginBottom: 16 }}
                onClose={() => useChatStore.getState().setRelevantMemories([])}
              />
            )}

            {planCreationPending && (
              <Alert
                message="Plan creation in progress"
                description={
                  planCreationPending.title
                    ? `Creating "${planCreationPending.title}" in the background. Tasks will appear shortly.`
                    : 'Creating the plan in the background. Tasks will appear shortly.'
                }
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {messages.map((message) => (
              <div key={message.id} style={{ marginBottom: 16 }}>
                <ChatMessage message={message} />
              </div>
            ))}
            
            {/* Processing indicator */}
            {isProcessing && (
              <div style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 12,
                marginBottom: 16,
              }}>
                <Avatar 
                  size={32} 
                  icon={<RobotOutlined />} 
                  style={{ background: '#52c41a' }} 
                />
                <div style={{
                  background: 'white',
                  padding: '12px 16px',
                  borderRadius: '12px 12px 12px 4px',
                  border: '1px solid #e5e7eb',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div className="typing-indicator">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                    <Text type="secondary">Thinking...</Text>
                  </div>
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{
        padding: '12px 20px',
        borderTop: '1px solid #f0f0f0',
        background: 'white',
        flexShrink: 0,
      }}>
        <div style={{ maxWidth: 840, margin: '0 auto' }}>
          <div
            style={{
              display: 'flex',
              gap: 12,
              alignItems: 'stretch',
            }}
          >
            <TextArea
              ref={inputRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Describe your request... (Shift+Enter for newline, Enter to send)"
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={isProcessing}
              style={{
                resize: 'none',
                borderRadius: 12,
                fontSize: 14,
                flex: 1,
              }}
            />
            <div
              style={{
                width: 220,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              <Select
                size="small"
                value={providerValue}
                placeholder="Choose a web search provider"
                options={providerOptions}
                allowClear
                onChange={handleProviderChange}
                disabled={isProcessing}
                loading={isUpdatingProvider}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSendMessage}
                disabled={!inputText.trim() || isProcessing}
                loading={isProcessing}
                style={{
                  height: 'auto',
                  borderRadius: 12,
                  paddingLeft: 16,
                  paddingRight: 16,
                }}
              >
                Send
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatMainArea;

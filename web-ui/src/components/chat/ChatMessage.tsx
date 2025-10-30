import React, { useState } from 'react';
import { Avatar, Typography, Space, Button, Tooltip, message as antMessage } from 'antd';
import {
  UserOutlined,
  RobotOutlined,
  InfoCircleOutlined,
  CopyOutlined,
  ReloadOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { ChatMessage as ChatMessageType, ToolResultPayload } from '@/types';
import { useChatStore } from '@store/chat';
import ReactMarkdown from 'markdown-to-jsx';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ToolResultCard from './ToolResultCard';
import JobLogPanel from './JobLogPanel';
import type { DecompositionJobStatus } from '@/types';

const { Text } = Typography;

interface ChatMessageProps {
  message: ChatMessageType;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const { type, content, timestamp, metadata } = message;
  const { saveMessageAsMemory } = useChatStore();
  const [isSaving, setIsSaving] = useState(false);

  // Copy message content
  const handleCopy = () => {
    navigator.clipboard.writeText(content);
  };

  // Save message as memory
  const handleSaveAsMemory = async () => {
    try {
      setIsSaving(true);
      await saveMessageAsMemory(message);
      antMessage.success('✅ Saved to memory');
    } catch (error) {
      console.error('Failed to save memory:', error);
      antMessage.error('❌ Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  // Format timestamp
  const formatTime = (date: Date) => {
    return new Date(date).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Render avatar
  const renderAvatar = () => {
    const avatarProps = {
      size: 32 as const,
      style: { flexShrink: 0 },
    };

    switch (type) {
      case 'user':
        return (
          <Avatar 
            {...avatarProps}
            icon={<UserOutlined />}
            style={{ ...avatarProps.style, backgroundColor: '#1890ff' }}
          />
        );
      case 'assistant':
        return (
          <Avatar 
            {...avatarProps}
            icon={<RobotOutlined />}
            style={{ ...avatarProps.style, backgroundColor: '#52c41a' }}
          />
        );
      case 'system':
        return (
          <Avatar 
            {...avatarProps}
            icon={<InfoCircleOutlined />}
            style={{ ...avatarProps.style, backgroundColor: '#faad14' }}
          />
        );
      default:
        return null;
    }
  };

  // Custom code block
  const CodeBlock = ({ children, className }: { children: string; className?: string }) => {
    const language = className?.replace('lang-', '') || 'text';
    
    return (
      <SyntaxHighlighter
        style={tomorrow}
        language={language}
        PreTag="div"
        customStyle={{
          margin: '8px 0',
          borderRadius: '6px',
          fontSize: '13px',
        }}
      >
        {children}
      </SyntaxHighlighter>
    );
  };

  // Render message body
  const renderContent = () => {
    if (type === 'system') {
      return (
        <Text type="secondary" style={{ fontStyle: 'italic' }}>
          {content}
        </Text>
      );
    }

    return (
      <ReactMarkdown
        options={{
          overrides: {
            code: {
              component: CodeBlock,
            },
            pre: {
              component: ({ children }: { children: React.ReactNode }) => (
                <div>{children}</div>
              ),
            },
            p: {
              props: {
                style: { margin: '0 0 8px 0', lineHeight: 1.6 },
              },
            },
            ul: {
              props: {
                style: { margin: '8px 0', paddingLeft: '20px' },
              },
            },
            ol: {
              props: {
                style: { margin: '8px 0', paddingLeft: '20px' },
              },
            },
            blockquote: {
              props: {
                style: {
                  borderLeft: '4px solid #d9d9d9',
                  paddingLeft: '12px',
                  margin: '8px 0',
                  color: '#666',
                  fontStyle: 'italic',
                },
              },
            },
          },
        }}
      >
        {content}
      </ReactMarkdown>
    );
  };

  // Render metadata
  const renderMetadata = () => {
    if (!metadata) return null;

    const planTitle = metadata.plan_title;
    const planId = metadata.plan_id;
    if (!planTitle && (planId === undefined || planId === null)) {
      return null;
    }

    return (
      <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
        <div>
          Linked plan:
          {planTitle ? ` ${planTitle}` : ''}
          {planId !== undefined && planId !== null ? ` (#${planId})` : ''}
        </div>
      </div>
    );
  };

  const renderToolResults = () => {
    const toolResults = Array.isArray(metadata?.tool_results)
      ? (metadata?.tool_results as ToolResultPayload[])
      : [];
    if (!toolResults.length) {
      return null;
    }
    return (
      <Space direction="vertical" size="middle" style={{ width: '100%', marginTop: 12 }}>
        {toolResults.map((result, index) => (
          <ToolResultCard key={`${result.name ?? 'tool'}_${index}`} payload={result} defaultOpen={index === 0} />
        ))}
      </Space>
    );
  };

  const renderActionSummary = () => {
    const summaryItems = Array.isArray(metadata?.actions_summary)
      ? (metadata?.actions_summary as Array<Record<string, any>>)
      : [];
    if (!summaryItems.length) {
      return null;
    }
    return (
      <div style={{ marginTop: 12 }}>
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Text strong>Action summary</Text>
          <div>
            {summaryItems.map((item, index) => {
              const order = typeof item.order === 'number' ? item.order : index + 1;
              const success = item.success;
              const icon = success === true ? '✅' : success === false ? '⚠️' : '⏳';
              const kind = typeof item.kind === 'string' ? item.kind : 'action';
              const name = typeof item.name === 'string' && item.name ? `/${item.name}` : '';
              const messageText =
                typeof item.message === 'string' && item.message.trim().length > 0
                  ? ` - ${item.message}`
                  : '';
              return (
                <div key={`${order}_${kind}_${name}`} style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>
                  <Text>
                    {icon} Step {order}: {kind}
                    {name}
                    {messageText}
                  </Text>
                </div>
              );
            })}
          </div>
        </Space>
      </div>
    );
  };

  const renderJobLogPanel = () => {
    if (!metadata || metadata.type !== 'job_log') {
      return null;
    }
    const jobMetadata = (metadata.job as DecompositionJobStatus | null) ?? null;
    const jobId: string | undefined = metadata.job_id ?? jobMetadata?.job_id;
    if (!jobId) {
      return null;
    }
    return (
      <JobLogPanel
        jobId={jobId}
        initialJob={jobMetadata}
        targetTaskName={metadata.target_task_name ?? null}
        planId={metadata.plan_id ?? null}
        jobType={metadata.job_type ?? jobMetadata?.job_type ?? null}
      />
    );
  };

  return (
    <div className={`message ${type}`}>
      {renderAvatar()}
      
      <div className="message-content">
        <div className="message-bubble">
          {renderContent()}
          {renderActionSummary()}
          {renderToolResults()}
          {renderJobLogPanel()}
          {renderMetadata()}
        </div>
        
        <div className="message-time">
          <Space size="small">
            <Text type="secondary" style={{ fontSize: 12 }}>
              {formatTime(timestamp)}
            </Text>
            
            {type !== 'system' && (
              <Space size={4}>
                <Tooltip title="Copy">
                  <Button
                    type="text"
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={handleCopy}
                    style={{ fontSize: 10, padding: '0 4px' }}
                  />
                </Tooltip>

                <Tooltip title="Save to memory">
                  <Button
                    type="text"
                    size="small"
                    icon={<DatabaseOutlined />}
                    onClick={handleSaveAsMemory}
                    loading={isSaving}
                    style={{ fontSize: 10, padding: '0 4px' }}
                  />
                </Tooltip>

                {type === 'assistant' && (
                  <Tooltip title="Regenerate">
                    <Button
                      type="text"
                      size="small"
                      icon={<ReloadOutlined />}
                      style={{ fontSize: 10, padding: '0 4px' }}
                    />
                  </Tooltip>
                )}
              </Space>
            )}
          </Space>
        </div>
      </div>
    </div>
  );
};

export default ChatMessage;

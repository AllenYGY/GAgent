import React, { useState } from 'react';
import {
  Avatar,
  Button,
  Dropdown,
  Input,
  List,
  MenuProps,
  Modal,
  Tag,
  Typography,
  Tooltip,
  message,
} from 'antd';
import {
  PlusOutlined,
  SearchOutlined,
  MessageOutlined,
  MoreOutlined,
  EditOutlined,
  DeleteOutlined,
  ExportOutlined,
  ExclamationCircleOutlined,
  InboxOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useChatStore } from '@store/chat';
import { ChatSession } from '@/types';

const { Text } = Typography;
const { Search } = Input;

const TITLE_SOURCE_HINT: Record<string, string> = {
  plan: 'Generated from the plan title',
  plan_task: 'Generated from plan and task context',
  heuristic: 'Generated from recent conversation content',
  llm: 'Summarised by the model',
  default: 'Default title – consider regenerating',
  local: 'Temporary title – consider regenerating',
  user: 'User-defined title',
};

const ChatSidebar: React.FC = () => {
  const {
    sessions,
    currentSession,
    setCurrentSession,
    startNewSession,
    deleteSession,
    loadChatHistory,
    autotitleSession,
  } = useChatStore();

  const [searchQuery, setSearchQuery] = useState('');

  // Filter conversations by search query
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredSessions = sessions.filter((session) => {
    if (!normalizedQuery) {
      return true;
    }
    const title = session.title?.toLowerCase?.() ?? '';
    const planTitle = session.plan_title?.toLowerCase?.() ?? '';
    return title.includes(normalizedQuery) || planTitle.includes(normalizedQuery);
  });

  // Create a new conversation
  const handleNewChat = () => {
    const newSession = startNewSession();
    setCurrentSession(newSession);
  };

  // Switch to a conversation
  const handleSelectSession = async (session: ChatSession) => {
    // Switch session locally first
    setCurrentSession(session);
    
    // Load history from backend if needed
    if (session.messages.length === 0 && session.session_id) {
      console.log('🔄 [ChatSidebar] Loading conversation history:', session.session_id);
      try {
        await loadChatHistory(session.session_id);
      } catch (err) {
        console.warn('Failed to load conversation history:', err);
      }
    }
  };

  const handleArchiveSession = async (session: ChatSession) => {
    try {
      await deleteSession(session.id, { archive: true });
      message.success('Conversation archived');
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error);
      message.error(`Failed to archive conversation: ${errMsg}`);
    }
  };

  const performDeleteSession = async (session: ChatSession) => {
    try {
      await deleteSession(session.id);
      message.success('Conversation deleted');
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error);
      message.error(`Failed to delete conversation: ${errMsg}`);
      throw error;
    }
  };

  const confirmDeleteSession = (session: ChatSession) => {
    Modal.confirm({
      title: 'Delete conversation',
      icon: <ExclamationCircleOutlined />, 
      content: `This will permanently delete "${session.title || session.id}". Continue?`,
      okText: 'Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: () => performDeleteSession(session),
    });
  };

  const handleSessionMenuAction = async (session: ChatSession, key: string) => {
    if (key !== 'autotitle') {
      return;
    }

    const sessionId = session.session_id ?? session.id;
    if (!sessionId) {
      return;
    }

    try {
      const result = await autotitleSession(sessionId, { force: true });
      if (!result) {
        return;
      }
      if (result.updated) {
        message.success(`Title updated to "${result.title}"`);
      } else {
        message.info('Title unchanged.');
      }
    } catch (error) {
      console.error('Failed to regenerate title:', error);
      message.error('Failed to regenerate the title. Please try again later.');
    }
  };

  // Conversation menu entries
  const getSessionMenuItems = (session: ChatSession): MenuProps['items'] => {
    const items: MenuProps['items'] = [
      {
        key: 'rename',
        label: 'Rename',
        icon: <EditOutlined />,
      },
      {
        key: 'autotitle',
        label: 'Regenerate title',
        icon: <ReloadOutlined />,
      },
      {
        key: 'export',
        label: 'Export conversation',
        icon: <ExportOutlined />,
      },
    ];

    if (session.is_active !== false) {
      items.push({
        key: 'archive',
        label: 'Archive conversation',
        icon: <InboxOutlined />,
        onClick: async (_info: any) => {
          _info?.domEvent?.stopPropagation?.();
          await handleArchiveSession(session);
        },
      });
    }

    items.push({ type: 'divider' });
    items.push({
      key: 'delete',
      label: 'Delete conversation',
      icon: <DeleteOutlined />,
      danger: true,
      onClick: (_info: any) => {
        _info?.domEvent?.stopPropagation?.();
        confirmDeleteSession(session);
      },
    });

    return items;
  };

  // Format timestamps for listing
  const formatTime = (date?: Date | null) => {
    if (!date) {
      return '';
    }
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return date.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
      });
    } else if (days === 1) {
      return 'Yesterday';
    } else if (days < 7) {
      return `${days} days ago`;
    }
    return date.toLocaleDateString();
  };

  return (
    <div style={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column',
      padding: '16px 12px'
    }}>
      {/* Header – create conversation */}
      <div style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleNewChat}
          style={{ 
            width: '100%',
            height: 40,
            borderRadius: 8,
            fontWeight: 500,
          }}
        >
          New conversation
        </Button>
      </div>

      {/* Search box */}
      <div style={{ marginBottom: 16 }}>
        <Search
          placeholder="Search conversations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            borderRadius: 8,
          }}
          prefix={<SearchOutlined style={{ color: '#9ca3af' }} />}
        />
      </div>

      {/* Conversation list */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <List
          style={{ height: '100%', overflow: 'auto' }}
          dataSource={filteredSessions}
          renderItem={(session) => {
            const lastTimestamp =
              session.last_message_at ?? session.updated_at ?? session.created_at;
            const titleHint = session.isUserNamed
              ? 'User-defined title'
              : session.titleSource && TITLE_SOURCE_HINT[session.titleSource]
              ? TITLE_SOURCE_HINT[session.titleSource]
              : undefined;

            return (
              <List.Item
                style={{
                  padding: '8px 12px',
                  margin: '4px 0',
                  borderRadius: 8,
                  background: currentSession?.id === session.id ? '#e3f2fd' : 'transparent',
                border: currentSession?.id === session.id ? '1px solid #2196f3' : '1px solid transparent',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onClick={() => handleSelectSession(session)}
              onMouseEnter={(e) => {
                if (currentSession?.id !== session.id) {
                  e.currentTarget.style.background = '#f5f5f5';
                }
              }}
              onMouseLeave={(e) => {
                if (currentSession?.id !== session.id) {
                  e.currentTarget.style.background = 'transparent';
                }
              }}
            >
              <div
                style={{ width: '100%', display: 'flex', alignItems: 'flex-start', gap: 12 }}
              >
                <Avatar 
                  size={32} 
                  icon={<MessageOutlined />} 
                  style={{ 
                    background: currentSession?.id === session.id ? '#2196f3' : '#f0f0f0',
                    color: currentSession?.id === session.id ? 'white' : '#999',
                    flexShrink: 0,
                  }}
                />
                
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 4,
                      gap: 8,
                    }}
                  >
                    <Tooltip title={titleHint} placement="topLeft">
                      <Text
                        strong={currentSession?.id === session.id}
                        ellipsis
                        style={{
                          fontSize: 14,
                          color: currentSession?.id === session.id ? '#1976d2' : '#333',
                          flex: 1,
                        }}
                      >
                        {session.title || `Session ${session.id.slice(-8)}`}
                      </Text>
                    </Tooltip>
                    
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {formatTime(lastTimestamp)}
                    </Text>

                    <Dropdown
                      menu={{
                        items: getSessionMenuItems(session),
                        onClick: ({ key, domEvent }) => {
                          domEvent?.stopPropagation();
                          void handleSessionMenuAction(session, String(key));
                        },
                      }}
                      trigger={['click']}
                      placement="bottomRight"
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<MoreOutlined />}
                        onClick={(e) => e.stopPropagation()}
                        style={{ 
                          marginLeft: 4,
                          opacity: 0.6,
                          flexShrink: 0,
                        }}
                      />
                    </Dropdown>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <Text
                      type="secondary"
                      ellipsis
                      style={{ fontSize: 12, color: '#6b7280', flex: 1 }}
                    >
                      {session.plan_title || 'No plan linked'}
                    </Text>
                    {session.is_active === false && <Tag color="gold">Archived</Tag>}
                  </div>
                </div>
              </div>
              </List.Item>
            );
          }}
        />
      </div>

      {/* Footer stats */}
      {sessions.length > 0 && (
        <div style={{ 
          marginTop: 16, 
          padding: '12px 16px',
          background: '#f8f9fa',
          borderRadius: 8,
          textAlign: 'center'
        }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Total conversations: {sessions.length}
          </Text>
        </div>
      )}
    </div>
  );
};

export default ChatSidebar;

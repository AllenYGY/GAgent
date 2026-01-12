import React, { useState } from 'react';
import {
  Avatar,
  Button,
  Checkbox,
  Dropdown,
  Input,
  List,
  MenuProps,
  Modal,
  Switch,
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
  RollbackOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useChatStore } from '@store/chat';
import { chatApi, ConversationExportFormat } from '@api/chat';
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

const sanitizeFileName = (value: string, fallback: string): string => {
  const trimmed = (value ?? '').trim();
  const candidate = trimmed || fallback;
  const safe = candidate
    .replace(/[^A-Za-z0-9._-]+/g, '_')
    .replace(/^[._-]+|[._-]+$/g, '');
  return (safe || fallback).slice(0, 60);
};

const formatExportTimestamp = (date: Date): string => {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(
    date.getHours()
  )}${pad(date.getMinutes())}`;
};

const buildFallbackFilename = (
  session: ChatSession,
  format: ConversationExportFormat
): string => {
  const baseTitle = session.title || session.plan_title || session.session_id || session.id;
  const fallback = session.session_id
    ? `session_${session.session_id.slice(-8)}`
    : 'conversation';
  const safeTitle = sanitizeFileName(baseTitle, fallback);
  const timestamp = formatExportTimestamp(new Date());
  return `conversation_${safeTitle}_${timestamp}.${format}`;
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
    renameSession,
    bulkDeleteSessions,
    setSessionActive,
  } = useChatStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameValue, setRenameValue] = useState('');
  const [renameTarget, setRenameTarget] = useState<ChatSession | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [showArchivedOnly, setShowArchivedOnly] = useState(false);

  // Filter conversations by search query
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredSessions = sessions.filter((session) => {
    if (showArchivedOnly) {
      return session.is_active === false;
    }
    if (session.is_active === false && session.id !== currentSession?.id) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    const title = session.title?.toLowerCase?.() ?? '';
    const planTitle = session.plan_title?.toLowerCase?.() ?? '';
    return title.includes(normalizedQuery) || planTitle.includes(normalizedQuery);
  });
  const archivedCount = sessions.filter((session) => session.is_active === false).length;
  const visibleSessionIds = filteredSessions.map(
    (session) => session.session_id ?? session.id
  );
  const allVisibleSelected =
    visibleSessionIds.length > 0 &&
    visibleSessionIds.every((id) => selectedSessionIds.includes(id));
  const someVisibleSelected =
    visibleSessionIds.some((id) => selectedSessionIds.includes(id)) &&
    !allVisibleSelected;

  // Create a new conversation
  const handleNewChat = () => {
    const newSession = startNewSession();
    setCurrentSession(newSession);
  };

  // Switch to a conversation
  const handleSelectSession = async (session: ChatSession) => {
    if (selectionMode) {
      const sessionKey = session.session_id ?? session.id;
      setSelectedSessionIds((prev) =>
        prev.includes(sessionKey)
          ? prev.filter((id) => id !== sessionKey)
          : [...prev, sessionKey]
      );
      return;
    }

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

  const handleUnarchiveSession = async (session: ChatSession) => {
    const sessionId = session.session_id ?? session.id;
    if (!sessionId) {
      return;
    }
    try {
      await setSessionActive(sessionId, true);
      message.success('Conversation restored');
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error);
      message.error(`Failed to restore conversation: ${errMsg}`);
    }
  };

  const handleExportSession = async (
    session: ChatSession,
    format: ConversationExportFormat
  ) => {
    const sessionId = session.session_id ?? session.id;
    if (!sessionId) {
      message.error('Missing session id for export.');
      return;
    }

    try {
      const { blob, filename, contentType } = await chatApi.exportSession(
        sessionId,
        format
      );
      const downloadName = filename ?? buildFallbackFilename(session, format);
      const downloadBlob =
        blob.type || !contentType ? blob : new Blob([blob], { type: contentType });
      const url = URL.createObjectURL(downloadBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = downloadName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      message.success(`Exported conversation as ${format.toUpperCase()}.`);
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error);
      message.error(`Failed to export conversation: ${errMsg}`);
    }
  };

  const clearSelectionMode = () => {
    setSelectionMode(false);
    setSelectedSessionIds([]);
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedSessionIds((prev) => {
        const merged = new Set([...prev, ...visibleSessionIds]);
        return Array.from(merged);
      });
      return;
    }
    setSelectedSessionIds((prev) =>
      prev.filter((id) => !visibleSessionIds.includes(id))
    );
  };

  const handleBulkDelete = async () => {
    if (selectedSessionIds.length === 0) {
      message.info('Select at least one conversation.');
      return;
    }

    Modal.confirm({
      title: `Delete ${selectedSessionIds.length} conversation(s)`,
      icon: <ExclamationCircleOutlined />,
      content: 'This will permanently delete the selected conversations. Continue?',
      okText: 'Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          const result = await bulkDeleteSessions(selectedSessionIds);
          const deletedCount = result.deleted?.length ?? 0;
          const missingCount = result.missing?.length ?? 0;
          if (deletedCount > 0) {
            message.success(`Deleted ${deletedCount} conversation(s).`);
          }
          if (missingCount > 0) {
            message.warning(`${missingCount} conversation(s) were not found.`);
          }
          clearSelectionMode();
        } catch (error) {
          const errMsg = error instanceof Error ? error.message : String(error);
          message.error(`Failed to delete conversations: ${errMsg}`);
        }
      },
    });
  };

  const openRenameModal = (session: ChatSession) => {
    setRenameTarget(session);
    setRenameValue(session.title || '');
    setRenameModalOpen(true);
  };

  const closeRenameModal = () => {
    setRenameModalOpen(false);
    setRenameTarget(null);
    setRenameValue('');
    setIsRenaming(false);
  };

  const handleRenameConfirm = async () => {
    if (!renameTarget) {
      return;
    }
    const trimmed = renameValue.trim();
    if (!trimmed) {
      message.error('Title cannot be empty.');
      return;
    }
    const sessionId = renameTarget.session_id ?? renameTarget.id;
    if (!sessionId) {
      message.error('Missing session id.');
      return;
    }

    setIsRenaming(true);
    try {
      await renameSession(sessionId, trimmed);
      message.success('Conversation renamed.');
      closeRenameModal();
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error);
      message.error(`Failed to rename conversation: ${errMsg}`);
      setIsRenaming(false);
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
    if (key === 'rename') {
      openRenameModal(session);
      return;
    }

    if (key === 'autotitle') {
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
      return;
    }

    if (key.startsWith('export-')) {
      const format = key.replace('export-', '') as ConversationExportFormat;
      await handleExportSession(session, format);
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
        children: [
          {
            key: 'export-md',
            label: 'Export as Markdown',
          },
          {
            key: 'export-json',
            label: 'Export as JSON',
          },
          {
            key: 'export-txt',
            label: 'Export as TXT',
          },
        ],
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
    } else {
      items.push({
        key: 'unarchive',
        label: 'Restore conversation',
        icon: <RollbackOutlined />,
        onClick: async (_info: any) => {
          _info?.domEvent?.stopPropagation?.();
          await handleUnarchiveSession(session);
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
      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        {selectionMode ? (
          <>
            <Button
              danger
              onClick={() => void handleBulkDelete()}
              disabled={selectedSessionIds.length === 0}
              style={{ flex: 1, height: 40, borderRadius: 8, fontWeight: 500 }}
            >
              Delete selected ({selectedSessionIds.length})
            </Button>
            <Button
              onClick={clearSelectionMode}
              style={{ height: 40, borderRadius: 8 }}
            >
              Cancel
            </Button>
          </>
        ) : (
          <>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleNewChat}
              style={{ 
                flex: 1,
                height: 40,
                borderRadius: 8,
                fontWeight: 500,
              }}
            >
              New Conversation
            </Button>
            <Button
              onClick={() => setSelectionMode(true)}
              disabled={sessions.length === 0}
              style={{ height: 40, borderRadius: 8 }}
            >
              Select
            </Button>
          </>
        )}
      </div>

      {/* Search box */}
      <div style={{ marginBottom: selectionMode ? 8 : 16 }}>
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
      <div style={{ marginBottom: selectionMode ? 8 : 12, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Switch
          size="small"
          checked={showArchivedOnly}
          onChange={(checked) => setShowArchivedOnly(checked)}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          Archived only
        </Text>
        {archivedCount > 0 && (
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
            {archivedCount} archived
          </Text>
        )}
      </div>
      {selectionMode && (
        <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Checkbox
            indeterminate={someVisibleSelected}
            checked={allVisibleSelected}
            onChange={(event) => handleSelectAll(event.target.checked)}
          >
            Select all
          </Checkbox>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {selectedSessionIds.length} selected
          </Text>
        </div>
      )}

      {/* Conversation list */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <List
          style={{ height: '100%', overflow: 'auto' }}
          dataSource={filteredSessions}
          renderItem={(session) => {
            const lastTimestamp =
              session.last_message_at ?? session.updated_at ?? session.created_at;
            const sessionKey = session.session_id ?? session.id;
            const isSelected = selectedSessionIds.includes(sessionKey);
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
                  background: selectionMode && isSelected
                    ? '#fff7e6'
                    : currentSession?.id === session.id
                    ? '#e3f2fd'
                    : 'transparent',
                  border:
                    currentSession?.id === session.id
                      ? '1px solid #2196f3'
                      : '1px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
                onClick={() => handleSelectSession(session)}
                onMouseEnter={(e) => {
                  if (selectionMode || isSelected) {
                    return;
                  }
                  if (currentSession?.id !== session.id) {
                    e.currentTarget.style.background = '#f5f5f5';
                  }
                }}
                onMouseLeave={(e) => {
                  if (selectionMode || isSelected) {
                    return;
                  }
                  if (currentSession?.id !== session.id) {
                    e.currentTarget.style.background = 'transparent';
                  }
                }}
              >
              <div
                style={{ width: '100%', display: 'flex', alignItems: 'flex-start', gap: 12 }}
              >
                {selectionMode && (
                  <Checkbox
                    checked={isSelected}
                    onChange={() => {
                      setSelectedSessionIds((prev) =>
                        prev.includes(sessionKey)
                          ? prev.filter((id) => id !== sessionKey)
                          : [...prev, sessionKey]
                      );
                    }}
                    onClick={(event) => event.stopPropagation()}
                    style={{ marginTop: 6 }}
                  />
                )}
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
                      disabled={selectionMode}
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
      <Modal
        title="Rename conversation"
        open={renameModalOpen}
        onOk={handleRenameConfirm}
        onCancel={closeRenameModal}
        okText="Save"
        cancelText="Cancel"
        confirmLoading={isRenaming}
        destroyOnClose
      >
        <Input
          placeholder="Enter a new title"
          value={renameValue}
          onChange={(event) => setRenameValue(event.target.value)}
          onPressEnter={() => {
            void handleRenameConfirm();
          }}
          maxLength={200}
          autoFocus
        />
      </Modal>
    </div>
  );
};

export default ChatSidebar;

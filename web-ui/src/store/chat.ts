import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import {
  ActionStatusResponse,
  ChatActionStatus,
  ChatActionSummary,
  ChatMessage,
  ChatResponseMetadata,
  ChatResponsePayload,
  ChatSession,
  ChatSessionSummary,
  ChatSessionAutoTitleResult,
  Memory,
  PlanSyncEventDetail,
  ToolResultPayload,
  WebSearchProvider,
} from '@/types';
import { SessionStorage } from '@/utils/sessionStorage';
import { useTasksStore } from '@store/tasks';
import { memoryApi } from '@api/memory';
import { chatApi } from '@api/chat';
import { ENV } from '@/config/env';
import {
  collectToolResultsFromActions,
  collectToolResultsFromMetadata,
  collectToolResultsFromSteps,
  mergeToolResults,
} from '@utils/toolResults';
import {
  coercePlanId,
  coercePlanTitle,
  derivePlanSyncEventsFromActions,
  dispatchPlanSyncEvent,
  extractPlanIdFromActions,
  extractPlanTitleFromActions,
} from '@utils/planSyncEvents';

const isActionStatus = (value: any): value is ChatActionStatus => {
  return value === 'pending' || value === 'running' || value === 'completed' || value === 'failed';
};

const parseDate = (value?: string | null): Date | null => {
  if (!value) {
    return null;
  }
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return null;
  }
  return new Date(timestamp);
};

const summaryToChatSession = (summary: ChatSessionSummary): ChatSession => {
  const rawName = summary.name?.trim();
  const title =
    rawName ||
    (summary.plan_title && summary.plan_title.trim()) ||
    `Session ${summary.id.slice(0, 8)}`;
  const titleSource =
    summary.name_source ??
    (rawName ? (summary.is_user_named ? 'user' : null) : null);
  const isUserNamed =
    summary.is_user_named === undefined || summary.is_user_named === null
      ? null
      : Boolean(summary.is_user_named);
  const createdAt = parseDate(summary.created_at) ?? new Date();
  const updatedAt = parseDate(summary.updated_at) ?? createdAt;
  const lastMessageAt = parseDate(summary.last_message_at);

  return {
    id: summary.id,
    title,
    messages: [],
    created_at: createdAt,
    updated_at: updatedAt,
    workflow_id: null,
    session_id: summary.id,
    plan_id: summary.plan_id ?? null,
    plan_title: summary.plan_title ?? null,
    current_task_id: summary.current_task_id ?? null,
    current_task_name: summary.current_task_name ?? null,
    last_message_at: lastMessageAt,
    is_active: summary.is_active,
    defaultSearchProvider: summary.settings?.default_search_provider ?? null,
    titleSource,
    isUserNamed,
  };
};

const derivePlanContextFromMessages = (
  messages: ChatMessage[]
): { planId: number | null | undefined; planTitle: string | null | undefined } => {
  let planId: number | null | undefined = undefined;
  let planTitle: string | null | undefined = undefined;

  for (let idx = messages.length - 1; idx >= 0; idx -= 1) {
    const metadata = messages[idx]?.metadata;
    if (!metadata) {
      continue;
    }

    if (planId === undefined && Object.prototype.hasOwnProperty.call(metadata, 'plan_id')) {
      const candidate = coercePlanId((metadata as any).plan_id);
      if (candidate !== undefined) {
        planId = candidate ?? null;
      }
    }

    if (planTitle === undefined && Object.prototype.hasOwnProperty.call(metadata, 'plan_title')) {
      const candidate = coercePlanTitle((metadata as any).plan_title);
      if (candidate !== undefined) {
        planTitle = candidate ?? null;
      }
    }

    if (planId !== undefined && planTitle !== undefined) {
      break;
    }
  }

  return { planId, planTitle };
};

const pendingAutotitleSessions = new Set<string>();
const autoTitleHistory = new Map<string, { planId: number | null }>();

interface ChatState {
  // Chat data
  currentSession: ChatSession | null;
  sessions: ChatSession[];
  messages: ChatMessage[];
  currentWorkflowId: string | null;

  // Current context
  currentPlanId: number | null;
  currentPlanTitle: string | null;
  currentTaskId: number | null;
  currentTaskName: string | null;
  defaultSearchProvider: WebSearchProvider | null;
  
  // Input state
  inputText: string;
  isTyping: boolean;
  isProcessing: boolean;
  isUpdatingProvider: boolean;
  
  // UI state
  chatPanelVisible: boolean;
  chatPanelWidth: number;

  // Memory related state
  memoryEnabled: boolean;
  relevantMemories: Memory[];

  // Actions
  setCurrentSession: (session: ChatSession | null) => void;
  addSession: (session: ChatSession) => void;
  removeSession: (sessionId: string) => void;
  deleteSession: (sessionId: string, options?: { archive?: boolean }) => Promise<void>;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (messageId: string, updates: Partial<ChatMessage>) => void;
  removeMessage: (messageId: string) => void;
  clearMessages: () => void;
  
  // Input actions
  setInputText: (text: string) => void;
  setIsTyping: (typing: boolean) => void;
  setIsProcessing: (processing: boolean) => void;
  
  // UI actions
  toggleChatPanel: () => void;
  setChatPanelVisible: (visible: boolean) => void;
  setChatPanelWidth: (width: number) => void;

  // Context actions
  setChatContext: (context: { planId?: number | null; planTitle?: string | null; taskId?: number | null; taskName?: string | null }) => void;
  clearChatContext: () => void;
  setCurrentWorkflowId: (workflowId: string | null) => void;

  // Memory actions
  toggleMemory: () => void;
  setMemoryEnabled: (enabled: boolean) => void;
  setRelevantMemories: (memories: Memory[]) => void;
  saveMessageAsMemory: (message: ChatMessage, memoryType?: string, importance?: string) => Promise<void>;

  loadSessions: () => Promise<void>;
  autotitleSession: (
    sessionId: string,
    options?: { force?: boolean; strategy?: string | null }
  ) => Promise<ChatSessionAutoTitleResult | null>;
  
  // Quick actions
  sendMessage: (content: string, metadata?: ChatMessage['metadata']) => Promise<void>;
  retryLastMessage: () => Promise<void>;
  startNewSession: (title?: string) => ChatSession;
  restoreSession: (sessionId: string, title?: string) => Promise<ChatSession>;
  loadChatHistory: (sessionId: string) => Promise<void>;
  setDefaultSearchProvider: (provider: WebSearchProvider | null) => Promise<void>;
}

export const useChatStore = create<ChatState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    currentSession: null,
    sessions: [],
    messages: [],
    currentWorkflowId: null,
    currentPlanId: null,
    currentPlanTitle: null,
    currentTaskId: null,
    currentTaskName: null,
    defaultSearchProvider: null,
    inputText: '',
    isTyping: false,
    isProcessing: false,
    isUpdatingProvider: false,
    chatPanelVisible: true,
    chatPanelWidth: 400,
    memoryEnabled: true, // Enable memory by default
    relevantMemories: [],

    // Set current session
    setCurrentSession: (session) => {
      const sessionPlanId = session?.plan_id ?? null;
      const sessionPlanTitle = session?.plan_title ?? null;
      const sessionTaskId = session?.current_task_id ?? null;
      const sessionTaskName = session?.current_task_name ?? null;
      const provider = session?.defaultSearchProvider ?? null;

      set({
        currentSession: session,
        currentWorkflowId: session?.workflow_id ?? null,
        messages: session ? session.messages : [],
        currentPlanId: sessionPlanId,
        currentPlanTitle: sessionPlanTitle,
        currentTaskId: sessionTaskId,
        currentTaskName: sessionTaskName,
        defaultSearchProvider: provider,
      });
      
      if (session) {
        SessionStorage.setCurrentSessionId(session.id);
      } else {
        SessionStorage.clearCurrentSessionId();
      }
    },

    // Add session
    addSession: (session) => {
      const normalized: ChatSession = {
        ...session,
        defaultSearchProvider: session.defaultSearchProvider ?? null,
      };
      set((state) => {
        const exists = state.sessions.some((s) => s.id === normalized.id);
        const newSessions = exists
          ? state.sessions.map((s) => (s.id === normalized.id ? normalized : s))
          : [...state.sessions, normalized];
        SessionStorage.setAllSessionIds(newSessions.map((s) => s.id));
        return { sessions: newSessions };
      });
    },

    // Remove session
    removeSession: (sessionId) => {
      autoTitleHistory.delete(sessionId);
      pendingAutotitleSessions.delete(sessionId);
      set((state) => {
        const newSessions = state.sessions.filter(s => s.id !== sessionId);
        // Update localStorage
        const allSessionIds = newSessions.map(s => s.id);
        SessionStorage.setAllSessionIds(allSessionIds);
        // Clear current session id if the active session was removed
        if (state.currentSession?.id === sessionId) {
          SessionStorage.clearCurrentSessionId();
        }
        return {
          sessions: newSessions,
          currentSession: state.currentSession?.id === sessionId ? null : state.currentSession,
          messages: state.currentSession?.id === sessionId ? [] : state.messages,
          defaultSearchProvider:
            state.currentSession?.id === sessionId ? null : state.defaultSearchProvider,
        };
      });
    },

    deleteSession: async (sessionId, options) => {
      const archive = options?.archive ?? false;
      try {
        await chatApi.deleteSession(
          sessionId,
          archive ? { archive: true } : undefined
        );
      } catch (error) {
        console.error('Failed to delete session:', error);
        throw error;
      }

      if (archive) {
        set((state) => {
          const updatedSessions = state.sessions.map((session) =>
            session.id === sessionId ? { ...session, is_active: false } : session
          );
          const updatedCurrent =
            state.currentSession?.id === sessionId
              ? { ...state.currentSession, is_active: false }
              : state.currentSession;
          return {
            sessions: updatedSessions,
            currentSession: updatedCurrent,
          };
        });
        dispatchPlanSyncEvent(
          {
            type: 'session_archived',
            session_id: sessionId,
            plan_id: null,
          },
          { source: 'chat.session' }
        );
        return;
      }

      const wasCurrent = get().currentSession?.id === sessionId;
      get().removeSession(sessionId);

      if (wasCurrent) {
        const tasksStore = useTasksStore.getState();
        tasksStore.setTasks([]);
        tasksStore.clearTaskResultCache();
        tasksStore.closeTaskDrawer();

        const remainingSessions = get().sessions;
        const fallbackSession =
          remainingSessions.find((session) => session.is_active) ??
          remainingSessions[0] ??
          null;

        if (fallbackSession) {
          get().setCurrentSession(fallbackSession);
          try {
            await get().loadChatHistory(fallbackSession.id);
          } catch (historyError) {
            console.warn('Failed to load fallback session history:', historyError);
          }
        } else {
          set({
            currentPlanId: null,
            currentPlanTitle: null,
            currentTaskId: null,
            currentTaskName: null,
            currentWorkflowId: null,
            messages: [],
          });
        }
      }

      dispatchPlanSyncEvent(
        {
          type: 'session_deleted',
          session_id: sessionId,
          plan_id: null,
        },
        { source: 'chat.session' }
      );
    },

    // Add message
    addMessage: (message) => set((state) => {
      const newMessages = [...state.messages, message];
      
      // Update current session
      let updatedSession = state.currentSession;
      if (updatedSession) {
        updatedSession = {
          ...updatedSession,
          messages: newMessages,
          updated_at: new Date(),
        };
      }

      // Update session list
      const updatedSessions = state.sessions.map(session =>
        session.id === updatedSession?.id ? updatedSession : session
      );

      return {
        messages: newMessages,
        currentSession: updatedSession,
        sessions: updatedSessions,
      };
    }),

    // Update message
    updateMessage: (messageId, updates) => set((state) => {
      const updatedMessages = state.messages.map(msg =>
        msg.id === messageId ? { ...msg, ...updates } : msg
      );

      // Update current session
      let updatedSession = state.currentSession;
      if (updatedSession) {
        updatedSession = {
          ...updatedSession,
          messages: updatedMessages,
          updated_at: new Date(),
        };
      }

      return {
        messages: updatedMessages,
        currentSession: updatedSession,
      };
    }),

    // Remove message
    removeMessage: (messageId) => set((state) => ({
      messages: state.messages.filter(msg => msg.id !== messageId),
    })),

    // Clear messages
    clearMessages: () => set({ messages: [] }),

    // Set chat context
    setChatContext: ({ planId, planTitle, taskId, taskName }) => {
      set((state) => {
        const nextPlanId = planId !== undefined ? planId : state.currentPlanId;
        const nextPlanTitle = planTitle !== undefined ? planTitle : state.currentPlanTitle;
        const nextTaskId = taskId !== undefined ? taskId : state.currentTaskId;
        const nextTaskName = taskName !== undefined ? taskName : state.currentTaskName;

        if (
          state.currentPlanId === nextPlanId &&
          state.currentPlanTitle === nextPlanTitle &&
          state.currentTaskId === nextTaskId &&
          state.currentTaskName === nextTaskName
        ) {
          return state;
        }

        const planIdValue = nextPlanId ?? null;
        const planTitleValue = nextPlanTitle ?? null;

        const updatedSession = state.currentSession
          ? {
              ...state.currentSession,
              plan_id: planIdValue,
              plan_title: planTitleValue,
            }
          : null;

        const updatedSessions = updatedSession
          ? state.sessions.map((session) =>
              session.id === updatedSession.id ? updatedSession : session
            )
          : state.sessions;

        return {
          currentPlanId: planIdValue,
          currentPlanTitle: planTitleValue,
          currentTaskId: nextTaskId ?? null,
          currentTaskName: nextTaskName ?? null,
          currentSession: updatedSession,
          sessions: updatedSessions,
        };
      });
    },

    clearChatContext: () =>
      set((state) => {
        const updatedSession = state.currentSession
          ? { ...state.currentSession, plan_id: null, plan_title: null }
          : null;
        const sessions = updatedSession
          ? state.sessions.map((session) =>
              session.id === updatedSession.id ? updatedSession : session
            )
          : state.sessions;

        return {
          currentPlanId: null,
          currentPlanTitle: null,
          currentTaskId: null,
          currentTaskName: null,
          currentSession: updatedSession,
          sessions,
        };
      }),

    // Set current workflow
    setCurrentWorkflowId: (workflowId) => {
      const state = get();
      if (state.currentWorkflowId === workflowId) {
        return;
      }

      const currentSession = state.currentSession
        ? { ...state.currentSession, workflow_id: workflowId ?? undefined }
        : null;
      const sessions = state.sessions.map((session) =>
        session.id === currentSession?.id
          ? { ...session, workflow_id: workflowId ?? undefined }
          : session
      );

      try {
        const { setCurrentWorkflowId } = useTasksStore.getState();
        setCurrentWorkflowId(workflowId ?? null);
      } catch (err) {
        console.warn('Unable to sync workflow id to tasks store:', err);
      }

      set({
        currentWorkflowId: workflowId ?? null,
        currentSession,
        sessions,
      });
    },

    // Set input text
    setInputText: (text) => set({ inputText: text }),

    // Set typing indicator
    setIsTyping: (typing) => set({ isTyping: typing }),

    // Set processing state
    setIsProcessing: (processing) => set({ isProcessing: processing }),

    // Toggle chat panel visibility
    toggleChatPanel: () => set((state) => ({
      chatPanelVisible: !state.chatPanelVisible,
    })),

    // Set chat panel visibility
    setChatPanelVisible: (visible) => set({ chatPanelVisible: visible }),

    // Set chat panel width
    setChatPanelWidth: (width) => set({ chatPanelWidth: width }),

    // Send message
    sendMessage: async (content, metadata) => {
      const {
        currentPlanTitle,
        currentPlanId,
        currentTaskId,
        currentTaskName,
        currentWorkflowId,
        currentSession,
        memoryEnabled,
        defaultSearchProvider,
      } = get();
      const mergedMetadata = {
        ...metadata,
        plan_id: metadata?.plan_id ?? currentPlanId ?? undefined,
        plan_title: metadata?.plan_title ?? currentPlanTitle ?? undefined,
        task_id: metadata?.task_id ?? currentTaskId ?? undefined,
        task_name: metadata?.task_name ?? currentTaskName ?? undefined,
        workflow_id: metadata?.workflow_id ?? currentWorkflowId ?? undefined,
      };

      const userMessage: ChatMessage = {
        id: `msg_${Date.now()}_user`,
        type: 'user',
        content,
        timestamp: new Date(),
        metadata: mergedMetadata,
      };
      get().addMessage(userMessage);
      set({ isProcessing: true, inputText: '' });

      let enhancedContent = content;
      let memories: Memory[] = [];

      if (memoryEnabled) {
        try {
          const memoryResult = await memoryApi.queryMemory({
            search_text: content,
            limit: 3,
            min_similarity: 0.6,
          });
          memories = memoryResult.memories;
          set({ relevantMemories: memories });
          if (memories.length > 0) {
            const memoryContext = memories
              .map((m) => `[Memory ${(m.similarity! * 100).toFixed(0)}%] ${m.content}`)
              .join('\n');
            enhancedContent = `Related memories:\n${memoryContext}\n\nUser question: ${content}`;
          }
        } catch (error) {
          console.error('Memory RAG query failed:', error);
        }
      }

      try {
        const providerToUse =
          defaultSearchProvider ??
          currentSession?.defaultSearchProvider ??
          null;
        const messages = get().messages;
        const recentMessages = messages.slice(-10).map((msg) => ({
          role: msg.type,
          content: msg.content,
          timestamp: msg.timestamp.toISOString(),
        }));

        const chatRequest = {
          task_id: mergedMetadata.task_id,
          plan_title: mergedMetadata.plan_title,
          plan_id: mergedMetadata.plan_id,
          workflow_id: mergedMetadata.workflow_id,
          session_id: currentSession?.session_id,
          history: recentMessages,
          mode: 'assistant' as const,
          default_search_provider: providerToUse ?? undefined,
          metadata: providerToUse ? { default_search_provider: providerToUse } : undefined,
        };

        const result: ChatResponsePayload = await chatApi.sendMessage(
          enhancedContent,
          chatRequest
        );
        const stateSnapshot = get();
        const actions = (result.actions ?? []) as ChatActionSummary[];

        const metadataHasPlanId = (
          result.metadata && Object.prototype.hasOwnProperty.call(result.metadata, 'plan_id')
        );
        const metadataPlanId = metadataHasPlanId ? coercePlanId(result.metadata?.plan_id) : undefined;
        const planIdFromActions = extractPlanIdFromActions(actions);
        const resolvedPlanId =
          metadataHasPlanId
            ? (metadataPlanId ?? null)
            : (
                planIdFromActions
                ?? coercePlanId(mergedMetadata.plan_id)
                ?? stateSnapshot.currentPlanId
                ?? null
              );

        const metadataHasPlanTitle = (
          result.metadata && Object.prototype.hasOwnProperty.call(result.metadata, 'plan_title')
        );
        const metadataPlanTitle = metadataHasPlanTitle ? coercePlanTitle(result.metadata?.plan_title) : undefined;
        const actionsPlanTitle = extractPlanTitleFromActions(actions);
        const resolvedPlanTitle =
          metadataHasPlanTitle
            ? (metadataPlanTitle ?? null)
            : (
                coercePlanTitle(mergedMetadata.plan_title)
                ?? (
                  actionsPlanTitle !== undefined
                    ? coercePlanTitle(actionsPlanTitle) ?? null
                    : undefined
                )
                ?? stateSnapshot.currentPlanTitle
                ?? null
              );

        const resolvedTaskId =
          result.metadata?.task_id
          ?? mergedMetadata.task_id
          ?? stateSnapshot.currentTaskId
          ?? null;
        const resolvedTaskName = mergedMetadata.task_name ?? stateSnapshot.currentTaskName ?? null;
        const resolvedWorkflowId =
          result.metadata?.workflow_id
          ?? mergedMetadata.workflow_id
          ?? stateSnapshot.currentWorkflowId
          ?? null;

        const initialStatus = isActionStatus(result.metadata?.status)
          ? (result.metadata?.status as ChatActionStatus)
          : (actions.length > 0 ? 'pending' : 'completed');

        const assistantMessageId = `msg_${Date.now()}_assistant`;
        const assistantMetadata: ChatResponseMetadata = {
          ...(result.metadata ?? {}),
          plan_id: resolvedPlanId ?? null,
          plan_title: resolvedPlanTitle ?? null,
          task_id: resolvedTaskId ?? null,
          workflow_id: resolvedWorkflowId ?? null,
          actions,
          action_list: actions,
          status: initialStatus,
        };

        const initialToolResults = collectToolResultsFromMetadata(result.metadata?.tool_results);
        if (initialToolResults.length > 0) {
          assistantMetadata.tool_results = initialToolResults;
        }

        const assistantMessage: ChatMessage = {
          id: assistantMessageId,
          type: 'assistant',
          content: result.response,
          timestamp: new Date(),
          metadata: assistantMetadata,
        };

        get().addMessage(assistantMessage);
        set({ isProcessing: false });

        set((state) => {
          const planIdValue = resolvedPlanId ?? state.currentPlanId ?? null;
          const planTitleValue = resolvedPlanTitle ?? state.currentPlanTitle ?? null;
          const taskIdValue = resolvedTaskId ?? state.currentTaskId ?? null;
          const workflowValue = resolvedWorkflowId ?? state.currentWorkflowId ?? null;
          const updatedSession = state.currentSession
            ? {
                ...state.currentSession,
                plan_id: planIdValue,
                plan_title: planTitleValue,
                current_task_id: taskIdValue,
                current_task_name:
                  resolvedTaskName ?? state.currentSession.current_task_name ?? null,
                workflow_id: workflowValue,
              }
            : null;
          const updatedSessions = updatedSession
            ? state.sessions.map((session) =>
                session.id === updatedSession.id ? updatedSession : session
              )
            : state.sessions;

          return {
            currentPlanId: planIdValue,
            currentPlanTitle: planTitleValue,
            currentTaskId: taskIdValue,
            currentTaskName: resolvedTaskName ?? state.currentTaskName ?? null,
            currentWorkflowId: workflowValue,
            currentSession: updatedSession,
            sessions: updatedSessions,
          };
        });

        const sessionAfter = get().currentSession ?? stateSnapshot.currentSession ?? null;
        if (sessionAfter) {
          const sessionKey = sessionAfter.session_id ?? sessionAfter.id;
          const history = sessionKey ? autoTitleHistory.get(sessionKey) : undefined;
          const planIdSnapshot = sessionAfter.plan_id ?? null;
          const shouldAttemptAutoTitle =
            !!sessionKey &&
            sessionAfter.isUserNamed !== true &&
            (!history || history.planId !== planIdSnapshot);

          if (shouldAttemptAutoTitle) {
            const userMessages = sessionAfter.messages.filter((msg) => msg.type === 'user');
            const hasContext = planIdSnapshot !== null || userMessages.length > 0;
            if (hasContext) {
              void get()
                .autotitleSession(sessionKey)
                .catch((error) => console.warn('Failed to auto-title session:', error));
            }
          }
        }

        if (resolvedWorkflowId !== stateSnapshot.currentWorkflowId) {
          get().setCurrentWorkflowId(resolvedWorkflowId ?? null);
        }

        if (assistantMetadata.agent_workflow) {
          window.dispatchEvent(
            new CustomEvent('tasksUpdated', {
              detail: {
                type: 'agent_workflow_created',
                workflow_id: assistantMetadata.workflow_id,
                total_tasks: assistantMetadata.total_tasks,
                dag_structure: assistantMetadata.dag_structure,
                plan_id: resolvedPlanId ?? null,
              },
            })
          );
        }

        if (assistantMetadata.session_id) {
          const state = get();
          const newSessionId = assistantMetadata.session_id as string;
          const current = state.currentSession
            ? { ...state.currentSession, session_id: newSessionId }
            : null;
          const sessions = state.sessions.map((s) =>
            s.id === current?.id ? { ...s, session_id: newSessionId } : s
          );
          set({ currentSession: current, sessions });
          SessionStorage.setCurrentSessionId(newSessionId);
        }

        const trackingId =
          typeof assistantMetadata.tracking_id === 'string'
            ? assistantMetadata.tracking_id
            : undefined;

        if (!trackingId) {
          const planEvents = derivePlanSyncEventsFromActions(result.actions, {
            fallbackPlanId: resolvedPlanId ?? stateSnapshot.currentPlanId ?? null,
            fallbackPlanTitle: resolvedPlanTitle ?? stateSnapshot.currentPlanTitle ?? null,
          });
          if (planEvents.length > 0) {
            const sessionForEvent = get().currentSession ?? stateSnapshot.currentSession ?? null;
            for (const eventDetail of planEvents) {
              dispatchPlanSyncEvent(eventDetail, {
                source: 'chat.sync',
                sessionId: sessionForEvent?.session_id ?? null,
              });
            }
          }
        }

        try {
          const { currentSession: cs, currentWorkflowId: cw, currentPlanId: planIdForEvent } = get();
          window.dispatchEvent(
            new CustomEvent('tasksUpdated', {
              detail: {
                type: 'chat_message_processed',
                session_id: cs?.session_id ?? null,
                workflow_id: cw ?? null,
                plan_id: resolvedPlanId ?? planIdForEvent ?? null,
              },
            })
          );
        } catch (e) {
          console.warn('Failed to dispatch tasksUpdated event:', e);
        }

        const sessionForPatch = get().currentSession;
        if (!assistantMetadata.tracking_id && sessionForPatch) {
          void (async () => {
            try {
              await chatApi.updateSession(sessionForPatch.session_id ?? sessionForPatch.id, {
                plan_id: resolvedPlanId ?? null,
                plan_title: resolvedPlanTitle ?? null,
                current_task_id: resolvedTaskId ?? null,
                current_task_name: resolvedTaskName ?? null,
                is_active: true,
              });
            } catch (patchError) {
              console.warn('Failed to synchronise session info:', patchError);
            }
          })();
        }

        const waitForActionCompletion = async (
          trackingId: string
        ): Promise<ActionStatusResponse | null> => {
          const timeoutMs = 120_000;
          const intervalMs = 2_500;
          const start = Date.now();
          let lastStatus: ActionStatusResponse | null = null;
          while (Date.now() - start < timeoutMs) {
            try {
              const status = await chatApi.getActionStatus(trackingId);
              lastStatus = status;
              if (status.status === 'completed' || status.status === 'failed') {
                return status;
              }
            } catch (pollError) {
              console.warn('Failed to poll action status:', pollError);
              break;
            }
            await new Promise((resolve) => setTimeout(resolve, intervalMs));
          }
          return lastStatus;
        };

        if (trackingId) {
          void (async () => {
            const status = await waitForActionCompletion(trackingId);
            const currentMessages = get().messages;
            const messageAtUpdate =
              currentMessages.find((msg) => msg.id === assistantMessageId) ??
              assistantMessage;
            const existingMetadata: ChatResponseMetadata = {
              ...((messageAtUpdate.metadata as ChatResponseMetadata | undefined) ?? assistantMetadata ?? {}),
            };

            if (!status || (status.status !== 'completed' && status.status !== 'failed')) {
              const timeoutErrors = [
                ...(existingMetadata.errors ?? []),
                'The background action did not finish within 120 seconds; please refresh the plan view later.',
              ];
              get().updateMessage(assistantMessageId, {
                metadata: {
                  ...existingMetadata,
                  status: 'failed',
                  errors: timeoutErrors,
                },
              });
              return;
            }

            const finalActions = status.actions ?? existingMetadata.actions ?? [];
            const finalPlanIdCandidate =
              coercePlanId(status.plan_id) ??
              coercePlanId(status.result?.bound_plan_id) ??
              extractPlanIdFromActions(finalActions) ??
              resolvedPlanId ??
              null;

            const stepList = Array.isArray(status.result?.steps)
              ? (status.result?.steps as Array<Record<string, any>>)
              : [];
            let planTitleFromSteps: string | null | undefined;
            for (const step of stepList) {
              const details = step?.details;
              if (!details || typeof details !== 'object') {
                continue;
              }
              const candidate =
                coercePlanTitle((details as any).title) ??
                coercePlanTitle((details as any).plan_title);
              if (candidate !== undefined) {
                planTitleFromSteps = candidate ?? null;
                break;
              }
            }
            const finalPlanTitle =
              planTitleFromSteps ??
              coercePlanTitle(status.result?.plan_title) ??
              resolvedPlanTitle ??
              null;

            const finalErrors = status.errors ?? [];
            const updatedMetadata: ChatResponseMetadata = {
              ...existingMetadata,
              status: status.status,
              plan_id: finalPlanIdCandidate ?? null,
              plan_title: finalPlanTitle ?? null,
              tracking_id: trackingId,
              actions: finalActions,
              action_list: finalActions,
              errors: finalErrors,
              result: status.result,
              finished_at: status.finished_at ?? existingMetadata.finished_at,
            };

            const toolResultsFromExisting = collectToolResultsFromMetadata(
              existingMetadata.tool_results
            );
            const toolResultsFromResult = collectToolResultsFromMetadata(
              status.result?.tool_results
            );
            const toolResultsFromSteps = collectToolResultsFromSteps(stepList);
            const toolResultsFromActions = collectToolResultsFromActions(finalActions);
            const mergedToolResults = mergeToolResults(
              mergeToolResults(toolResultsFromExisting, toolResultsFromResult),
              mergeToolResults(toolResultsFromSteps, toolResultsFromActions)
            );
            if (mergedToolResults.length > 0) {
              updatedMetadata.tool_results = mergedToolResults;
            } else {
              delete updatedMetadata.tool_results;
            }

            const contentWithStatus =
              status.status === 'failed' && finalErrors.length
                ? `${messageAtUpdate.content}\n\n⚠️ Background execution failed: ${finalErrors.join('; ')}`
                : messageAtUpdate.content;

            get().updateMessage(assistantMessageId, {
              content: contentWithStatus,
              metadata: updatedMetadata,
            });

            set((state) => {
              const planIdValue = finalPlanIdCandidate ?? state.currentPlanId ?? null;
              const planTitleValue = finalPlanTitle ?? state.currentPlanTitle ?? null;
              const updatedSession = state.currentSession
                ? {
                    ...state.currentSession,
                    plan_id: planIdValue,
                    plan_title: planTitleValue,
                  }
                : null;
              const updatedSessions = updatedSession
                ? state.sessions.map((session) =>
                    session.id === updatedSession.id ? updatedSession : session
                  )
                : state.sessions;

              return {
                currentPlanId: planIdValue,
                currentPlanTitle: planTitleValue,
                currentSession: updatedSession,
                sessions: updatedSessions,
              };
            });

            const sessionAfter = get().currentSession ?? stateSnapshot.currentSession ?? null;

            const asyncEvents = derivePlanSyncEventsFromActions(finalActions, {
              fallbackPlanId: finalPlanIdCandidate ?? sessionAfter?.plan_id ?? null,
              fallbackPlanTitle: finalPlanTitle ?? sessionAfter?.plan_title ?? null,
            });

            const eventsToDispatch =
              asyncEvents.length > 0
                ? asyncEvents
                : finalPlanIdCandidate != null
                ? [
                    {
                      type: 'task_changed',
                      plan_id: finalPlanIdCandidate,
                      plan_title: finalPlanTitle ?? sessionAfter?.plan_title ?? null,
                    } as PlanSyncEventDetail,
                  ]
                : [];

            if (eventsToDispatch.length > 0) {
              for (const eventDetail of eventsToDispatch) {
                dispatchPlanSyncEvent(eventDetail, {
                  trackingId,
                  source: 'chat.async',
                  status: status.status,
                  sessionId:
                    assistantMetadata.session_id ??
                    sessionAfter?.session_id ??
                    currentSession?.session_id ??
                    null,
                });
              }
            }

            if (sessionAfter) {
              try {
                await chatApi.updateSession(sessionAfter.session_id ?? sessionAfter.id, {
                  plan_id: finalPlanIdCandidate ?? null,
                  plan_title: finalPlanTitle ?? null,
                  is_active: status.status === 'completed',
                });
              } catch (patchError) {
                console.warn('Failed to synchronise session info:', patchError);
              }
            }
          })();
        }
      } catch (error) {
        console.error('Failed to send message:', error);
        set({ isProcessing: false });
        const errorMessage: ChatMessage = {
          id: `msg_${Date.now()}_assistant`,
          type: 'assistant',
          content:
            'Sorry, I cannot process your request right now. Possible reasons:\n\n1. Backend services are not fully started\n2. The LLM API is not configured\n3. Network connectivity issues\n\nPlease verify the backend status or try again later.',
          timestamp: new Date(),
        };
        get().addMessage(errorMessage);
      }
    },
    // Retry the last user message
    retryLastMessage: async () => {
      const { messages } = get();
      const lastUserMessage = [...messages].reverse().find(msg => msg.type === 'user');
      
      if (lastUserMessage) {
        await get().sendMessage(lastUserMessage.content, lastUserMessage.metadata);
      }
    },

    // Start a new session (always generates a new ID)
    startNewSession: (title) => {
      const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const providerPreference = get().defaultSearchProvider ?? null;
      autoTitleHistory.delete(sessionId);
      const session: ChatSession = {
        id: sessionId,
        title: title || `Conversation ${new Date().toLocaleString()}`,
        messages: [],
        created_at: new Date(),
        updated_at: new Date(),
        workflow_id: null,
        session_id: sessionId,
        plan_id: null,
        plan_title: null,
        current_task_id: null,
        current_task_name: null,
        last_message_at: null,
        is_active: true,
        defaultSearchProvider: providerPreference,
        titleSource: 'local',
        isUserNamed: false,
      };

      console.log('🆕 Created new session:', {
        frontendSessionId: session.id,
        backendSessionId: session.session_id,
        title: session.title,
      });

      get().addSession(session);
      get().setCurrentSession(session);
      set({ currentWorkflowId: null });
      
      // Persist the current session id and all session ids
      SessionStorage.setCurrentSessionId(sessionId);

      return session;
    },

    // Restore an existing session (used after refresh)
    restoreSession: async (sessionId, title) => {
      let session = get().sessions.find((s) => s.id === sessionId) || null;

      if (!session) {
        await get().loadSessions();
        session = get().sessions.find((s) => s.id === sessionId) || null;
      }

      if (!session) {
        const providerPreference = get().defaultSearchProvider ?? null;
        autoTitleHistory.delete(sessionId);
        session = {
          id: sessionId,
          title: title || `Conversation ${new Date().toLocaleString()}`,
          messages: [],
          created_at: new Date(),
          updated_at: new Date(),
          workflow_id: null,
          session_id: sessionId,
          plan_id: null,
          plan_title: null,
          current_task_id: null,
          current_task_name: null,
          last_message_at: null,
          is_active: true,
          defaultSearchProvider: providerPreference,
          titleSource: 'local',
          isUserNamed: false,
        };
        get().addSession(session);
      }

      get().setCurrentSession(session);
      SessionStorage.setCurrentSessionId(sessionId);

      await get().loadChatHistory(sessionId);

      const refreshedSession = get().currentSession;
      if (refreshedSession && refreshedSession.id === sessionId) {
        return refreshedSession;
      }

      return refreshedSession || session;
    },

    // Load chat history
    loadChatHistory: async (sessionId: string) => {
      try {
        console.log('📖 Loading chat history:', sessionId);
        const response = await fetch(`${ENV.API_BASE_URL}/chat/history/${sessionId}?limit=100`);
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.messages && data.messages.length > 0) {
          console.log(`✅ Loaded ${data.messages.length} historical messages`);
          
          // Convert backend messages into frontend format
      const messages: ChatMessage[] = data.messages.map((msg: any, index: number) => {
        const metadata =
          msg.metadata && typeof msg.metadata === 'object'
            ? (msg.metadata as Record<string, any>)
            : {};
        const toolResults = collectToolResultsFromMetadata(metadata.tool_results);
        if (toolResults.length > 0) {
          metadata.tool_results = toolResults;
        }
        return {
          id: `${sessionId}_${index}`,
          type: (msg.role || 'assistant') as 'user' | 'assistant' | 'system',
          content: msg.content,
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
              metadata,
            };
          });
          
          // Update message list
          set({ messages });
          
          const planContext = derivePlanContextFromMessages(messages);

          set((state) => {
            const targetSession = state.sessions.find((s) => s.id === sessionId);
            if (!targetSession) {
              return {};
            }

            const planIdValue =
              planContext.planId !== undefined
                ? planContext.planId ?? null
                : targetSession.plan_id ?? null;
            const planTitleValue =
              planContext.planTitle !== undefined
                ? planContext.planTitle ?? null
                : targetSession.plan_title ?? null;

            const lastMessage = messages[messages.length - 1];
            const updatedSession: ChatSession = {
              ...targetSession,
              messages,
              updated_at: new Date(),
              plan_id: planIdValue,
              plan_title: planTitleValue,
              last_message_at: lastMessage ? lastMessage.timestamp : targetSession.last_message_at ?? null,
            };

            const sessions = state.sessions.map((s) =>
              s.id === sessionId ? updatedSession : s
            );

            const isCurrent = state.currentSession?.id === sessionId;

            return {
              sessions,
              currentSession: isCurrent ? updatedSession : state.currentSession,
              currentPlanId: isCurrent ? planIdValue ?? null : state.currentPlanId,
              currentPlanTitle: isCurrent ? planTitleValue ?? null : state.currentPlanTitle,
            };
          });
        } else {
          console.log('📭 No historical messages available');
        }
      } catch (error) {
        console.error('Failed to load chat history:', error);
        throw error;
      }
    },

    // Memory helpers
    toggleMemory: () => set((state) => ({ memoryEnabled: !state.memoryEnabled })),

    setMemoryEnabled: (enabled) => set({ memoryEnabled: enabled }),

    setRelevantMemories: (memories) => set({ relevantMemories: memories }),

    saveMessageAsMemory: async (message, memoryType = 'conversation', importance = 'medium') => {
      try {
        console.log('💾 Saving message to memory:', { content: message.content.substring(0, 50) });

        await memoryApi.saveMemory({
          content: message.content,
          memory_type: memoryType as any,
          importance: importance as any,
          tags: ['chat', 'manual_saved'],
          context: `Conversation saved at ${new Date().toLocaleString()}`,
          related_task_id: message.metadata?.task_id
        });

        console.log('✅ Message saved to memory');
      } catch (error) {
        console.error('❌ Failed to save memory:', error);
        throw error;
      }
    },

    setDefaultSearchProvider: async (provider) => {
      const normalized: WebSearchProvider | null = provider ?? null;
      const prevProvider = get().defaultSearchProvider ?? null;
      if (normalized === prevProvider) {
        return;
      }

      const currentSession = get().currentSession;
      const sessionKey = currentSession?.session_id ?? currentSession?.id ?? null;

      set((state) => ({
        defaultSearchProvider: normalized,
        isUpdatingProvider: currentSession ? true : false,
        currentSession: currentSession
          ? { ...currentSession, defaultSearchProvider: normalized }
          : currentSession,
        sessions: currentSession
          ? state.sessions.map((session) =>
              session.id === sessionKey
                ? { ...session, defaultSearchProvider: normalized }
                : session
            )
          : state.sessions,
      }));

      if (!currentSession) {
        set({ isUpdatingProvider: false });
        return;
      }

      try {
        if (!sessionKey) {
          set({ isUpdatingProvider: false });
          return;
        }

        await chatApi.updateSession(sessionKey, {
          settings: { default_search_provider: normalized },
        });
      } catch (error) {
        console.error('Failed to update default search provider:', error);
        set((state) => ({
          defaultSearchProvider: prevProvider,
          isUpdatingProvider: false,
          currentSession: state.currentSession
            ? { ...state.currentSession, defaultSearchProvider: prevProvider }
            : state.currentSession,
          sessions: state.sessions.map((session) =>
            session.id === sessionKey
              ? { ...session, defaultSearchProvider: prevProvider }
              : session
          ),
        }));
        throw error;
      }

      set((state) => ({
        isUpdatingProvider: false,
        defaultSearchProvider: normalized,
        currentSession: state.currentSession
          ? { ...state.currentSession, defaultSearchProvider: normalized }
          : state.currentSession,
        sessions: state.sessions.map((session) =>
          session.id === sessionKey
            ? { ...session, defaultSearchProvider: normalized }
            : session
        ),
      }));
    },

    autotitleSession: async (sessionId, options = {}) => {
      const sessionKey = sessionId?.trim();
      if (!sessionKey) {
        return null;
      }

      if (pendingAutotitleSessions.has(sessionKey)) {
        return null;
      }

      pendingAutotitleSessions.add(sessionKey);

      const payload: { force?: boolean; strategy?: string | null } = {};
      if (options.force) {
        payload.force = true;
      }
      if (options.strategy !== undefined) {
        payload.strategy = options.strategy;
      }

      try {
        const result = await chatApi.autotitleSession(sessionKey, payload);
        set((state) => {
          const updateSession = (session: ChatSession): ChatSession => {
            const matchId = session.session_id ?? session.id;
            if (matchId !== sessionKey) {
              return session;
            }

            const next: ChatSession = {
              ...session,
              title: result.title ?? session.title,
              titleSource: result.source ?? session.titleSource ?? null,
            };

            if (result.skipped_reason === 'user_named') {
              next.isUserNamed = true;
            } else if (result.source === 'user') {
              next.isUserNamed = true;
            } else if (result.updated) {
              next.isUserNamed = false;
            }

            return next;
          };

          const currentSession = state.currentSession
            ? updateSession(state.currentSession)
            : state.currentSession;

          return {
            currentSession,
            sessions: state.sessions.map(updateSession),
          };
        });

        const sessionsAfter = get().sessions;
        const target = sessionsAfter.find((session) => {
          const matchId = session.session_id ?? session.id;
          return matchId === sessionKey;
        });
        if (target) {
          autoTitleHistory.set(sessionKey, { planId: target.plan_id ?? null });
        }

        return result;
      } catch (error) {
        console.warn('Failed to generate session title automatically:', error);
        throw error;
      } finally {
        pendingAutotitleSessions.delete(sessionKey);
      }
    },

    loadSessions: async () => {
      try {
        const response = await chatApi.getSessions({ limit: 100, offset: 0 });
        const summaries = response.sessions ?? [];
        const existingSessions = get().sessions;
        const existingMap = new Map(existingSessions.map((s) => [s.id, s]));

        const normalized = summaries.map((summary) => {
          const base = summaryToChatSession(summary);
          const existing = existingMap.get(summary.id);
          if (!existing) {
            return base;
          }
          return {
            ...base,
            messages: existing.messages,
            workflow_id: existing.workflow_id ?? base.workflow_id,
            created_at: existing.created_at ?? base.created_at,
            updated_at: base.updated_at,
          };
        });

        for (const session of normalized) {
          const sessionKey = session.session_id ?? session.id;
          if (!sessionKey) {
            continue;
          }
          const source = session.titleSource ?? null;
          if (source && source !== 'default' && source !== 'local') {
            autoTitleHistory.set(sessionKey, { planId: session.plan_id ?? null });
          }
        }

        set({ sessions: normalized });
        SessionStorage.setAllSessionIds(normalized.map((s) => s.id));

        const storedId = SessionStorage.getCurrentSessionId();
        const nextSession =
          (storedId && normalized.find((s) => s.id === storedId)) ||
          normalized[0] ||
          null;

        if (nextSession) {
          get().setCurrentSession(nextSession);
        } else {
          set({
            currentSession: null,
            messages: [],
            currentPlanId: null,
            currentPlanTitle: null,
            currentTaskId: null,
            currentTaskName: null,
            currentWorkflowId: null,
            defaultSearchProvider: null,
          });
          SessionStorage.clearCurrentSessionId();
        }
      } catch (error) {
        console.error('Failed to load session list:', error);
        throw error;
      }
    },
  }))
);

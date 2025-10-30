import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { PlanResultItem, PlanSyncEventDetail, Task } from '@/types';
import { queryClient } from '@/queryClient';
import { isPlanSyncEventDetail } from '@utils/planSyncEvents';

// Temporary type definition to avoid build errors
interface TaskStats {
  total: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
}

interface DAGNode {
  id: string;
  label: string;
  color?: string;
  shape?: string;
}

interface DAGEdge {
  from: string;
  to: string;
  color?: string;
  label?: string;
}

interface TasksState {
  // Task data
  tasks: Task[];
  selectedTask: Task | null;
  selectedTaskId: number | null;
  taskStats: TaskStats | null;
  currentPlan: string | null;
  currentWorkflowId: string | null;
  isTaskDrawerOpen: boolean;
  taskResultCache: Record<number, PlanResultItem | null>;
  
  // DAG visualization data
  dagNodes: DAGNode[];
  dagEdges: DAGEdge[];
  dagLayout: 'hierarchical' | 'force' | 'circular';
  
  // Filtering and search
  filters: {
    status: string[];
    task_type: string[];
    search_query: string;
  };
  
  // Actions
  setTasks: (tasks: Task[]) => void;
  addTask: (task: Task) => void;
  updateTask: (id: number, updates: Partial<Task>) => void;
  removeTask: (id: number) => void;
  setSelectedTask: (task: Task | null) => void;
  openTaskDrawer: (task: Task | null) => void;
  openTaskDrawerById: (taskId: number) => void;
  closeTaskDrawer: () => void;
  setTaskResult: (taskId: number, result: PlanResultItem | null) => void;
  clearTaskResultCache: (taskId?: number) => void;
  setCurrentPlan: (planTitle: string | null) => void;
  setCurrentWorkflowId: (workflowId: string | null) => void;
  setTaskStats: (stats: TaskStats | null) => void;
  
  // DAG helpers
  setDagData: (nodes: DAGNode[], edges: DAGEdge[]) => void;
  updateNodePosition: (nodeId: string, position: { x: number; y: number }) => void;
  setDagLayout: (layout: TasksState['dagLayout']) => void;
  
  // Filter helpers
  setFilters: (filters: Partial<TasksState['filters']>) => void;
  clearFilters: () => void;
  
  // Derived values
  getFilteredTasks: () => Task[];
  getTaskStats: () => {
    total: number;
    pending: number;
    running: number;
    completed: number;
    failed: number;
  };
}

export const useTasksStore = create<TasksState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    tasks: [],
    selectedTask: null,
    selectedTaskId: null,
    taskStats: null,
    currentPlan: null,
    currentWorkflowId: null,
    isTaskDrawerOpen: false,
    taskResultCache: {},
    dagNodes: [],
    dagEdges: [],
    dagLayout: 'hierarchical',
    filters: {
      status: [],
      task_type: [],
      search_query: '',
    },

    // Set task list
    setTasks: (tasks) => {
      set(() => {
        const { nodes, edges } = generateDagData(tasks);
        const rootTask = tasks.find((task) => task.task_type === 'root');
        const selectedId = get().selectedTaskId;
        const matchedSelection =
          selectedId != null ? tasks.find((task) => task.id === selectedId) ?? null : null;
        const nextSelectedTask = matchedSelection ?? null;
        const nextSelectedId = matchedSelection ? selectedId : null;
        return {
          tasks,
          dagNodes: nodes,
          dagEdges: edges,
          currentPlan: rootTask?.name ?? null,
          selectedTask: nextSelectedTask,
          selectedTaskId: nextSelectedId,
        };
      });
    },

    // Add task
    addTask: (task) => set((state) => {
      const tasks = [...state.tasks, task];
      const { nodes, edges } = generateDagData(tasks);
      return { tasks, dagNodes: nodes, dagEdges: edges };
    }),

    // Update task
    updateTask: (id, updates) => set((state) => {
      const tasks = state.tasks.map((task) =>
        task.id === id ? { ...task, ...updates } : task
      );
      const { nodes, edges } = generateDagData(tasks);
      const isSelected = state.selectedTaskId === id;
      return { 
        tasks, 
        dagNodes: nodes, 
        dagEdges: edges,
        selectedTask: isSelected && state.selectedTask
          ? { ...state.selectedTask, ...updates }
          : state.selectedTask,
      };
    }),

    // Remove task
    removeTask: (id) => set((state) => {
      const tasks = state.tasks.filter((task) => task.id !== id);
      const { nodes, edges } = generateDagData(tasks);
      const removingSelected = state.selectedTaskId === id;
      return { 
        tasks, 
        dagNodes: nodes, 
        dagEdges: edges,
        selectedTask: removingSelected ? null : state.selectedTask,
        selectedTaskId: removingSelected ? null : state.selectedTaskId,
      };
    }),

    // Set selected task
    setSelectedTask: (task) =>
      set({
        selectedTask: task,
        selectedTaskId: task?.id ?? null,
      }),

    openTaskDrawer: (task) =>
      set((state) => {
        if (!task) {
          return {
            isTaskDrawerOpen: false,
            selectedTask: null,
            selectedTaskId: null,
          };
        }
        return {
          isTaskDrawerOpen: true,
          selectedTask: task,
          selectedTaskId: task.id,
        };
      }),

    openTaskDrawerById: (taskId) =>
      set((state) => {
        const task =
          state.tasks.find((item) => item.id === taskId) ??
          (state.selectedTask?.id === taskId ? state.selectedTask : null);
        return {
          isTaskDrawerOpen: true,
          selectedTask: task ?? null,
          selectedTaskId: taskId,
        };
      }),

    closeTaskDrawer: () =>
      set({
        isTaskDrawerOpen: false,
        selectedTaskId: null,
      }),

    setTaskResult: (taskId, result) =>
      set((state) => {
        const nextCache = { ...state.taskResultCache };
        if (result == null) {
          delete nextCache[taskId];
        } else {
          nextCache[taskId] = result;
        }
        return { taskResultCache: nextCache };
      }),

    clearTaskResultCache: (taskId) =>
      set((state) => {
        if (typeof taskId === 'number') {
          if (!(taskId in state.taskResultCache)) {
            return {};
          }
          const nextCache = { ...state.taskResultCache };
          delete nextCache[taskId];
          return { taskResultCache: nextCache };
        }
        if (Object.keys(state.taskResultCache).length === 0) {
          return {};
        }
        return { taskResultCache: {} };
      }),

    // Set current plan
    setCurrentPlan: (planTitle) => set({ currentPlan: planTitle }),

    setCurrentWorkflowId: (workflowId) => set({ currentWorkflowId: workflowId }),

    setTaskStats: (stats) => set({ taskStats: stats }),

    // Set DAG data
    setDagData: (nodes, edges) => set({ dagNodes: nodes, dagEdges: edges }),

    // Update node position
    updateNodePosition: (nodeId, position) => set((state) => ({
      dagNodes: state.dagNodes.map((node) =>
        node.id === nodeId ? { ...node, ...position } : node
      ),
    })),

    // Set DAG layout
    setDagLayout: (layout) => set({ dagLayout: layout }),

    // Set filters
    setFilters: (filters) => set((state) => ({
      filters: { ...state.filters, ...filters },
    })),

    // Clear filters
    clearFilters: () => set({
      filters: {
        status: [],
        task_type: [],
        search_query: '',
      },
    }),

    // Get filtered tasks
    getFilteredTasks: () => {
      const { tasks, filters } = get();
      return tasks.filter((task) => {
        // Filter by status
        if (filters.status.length > 0 && !filters.status.includes(task.status)) {
          return false;
        }
        
        // Filter by type
        if (filters.task_type.length > 0 && !filters.task_type.includes(task.task_type)) {
          return false;
        }
        
        // Filter by search query
        if (filters.search_query) {
          const query = filters.search_query.toLowerCase();
          return task.name.toLowerCase().includes(query);
        }
        
        return true;
      });
    },

    // Get task statistics
    getTaskStats: () => {
      const tasks = get().tasks;
      return {
        total: tasks.length,
        pending: tasks.filter(t => t.status === 'pending').length,
        running: tasks.filter(t => t.status === 'running').length,
        completed: tasks.filter(t => t.status === 'completed').length,
        failed: tasks.filter(t => t.status === 'failed').length,
      };
    },
  }))
);

// Helper to generate DAG visualization data
function generateDagData(tasks: Task[]): { nodes: DAGNode[]; edges: DAGEdge[] } {
  const nodes: DAGNode[] = tasks.map((task) => ({
    id: task.id.toString(),
    label: task.name.replace(/^\[.*?\]\s*/, ''), // Remove plan prefix
    group: task.task_type,
    status: task.status,
    level: task.depth,
  }));

  const edges: DAGEdge[] = [];
  
  // Generate edges based on parent_id
  tasks.forEach((task) => {
    if (task.parent_id) {
      edges.push({
        from: task.parent_id.toString(),
        to: task.id.toString(),
        label: 'contains',
        color: '#1890ff',
      });
    }
  });

  return { nodes, edges };
}

const invalidatePlanCollections = () => {
  queryClient.invalidateQueries({ queryKey: ['planTree', 'summaries'], exact: false });
  queryClient.invalidateQueries({ queryKey: ['planTree', 'titles'], exact: false });
  void queryClient.refetchQueries({
    queryKey: ['planTree', 'summaries'],
    exact: false,
    type: 'active',
  });
  void queryClient.refetchQueries({
    queryKey: ['planTree', 'titles'],
    exact: false,
    type: 'active',
  });
};

const matchesPlanScopedKey = (queryKey: unknown, planId: number) => {
  if (!Array.isArray(queryKey) || queryKey.length < 2) {
    return false;
  }
  if (queryKey[0] !== 'planTree') {
    return false;
  }
  const scope = queryKey[1];
  switch (scope) {
    case 'tasks':
    case 'results':
    case 'execution':
    case 'taskResult':
    case 'full':
    case 'subgraph':
      return queryKey[2] === planId;
    default:
      return false;
  }
};

const invalidatePlanScopedQueries = (planId: number) => {
  const predicate = ({ queryKey }: { queryKey: unknown }) =>
    matchesPlanScopedKey(queryKey, planId);
  queryClient.invalidateQueries({
    predicate: ({ queryKey }) => matchesPlanScopedKey(queryKey, planId),
  });
  void queryClient.refetchQueries({
    predicate,
    type: 'active',
  });
};

const removePlanScopedQueries = (planId: number) => {
  queryClient.removeQueries({
    predicate: ({ queryKey }) => matchesPlanScopedKey(queryKey, planId),
  });
};

declare global {
  interface Window {
    __gaPlanSyncListenerRegistered__?: boolean;
  }
}

if (typeof window !== 'undefined' && !window.__gaPlanSyncListenerRegistered__) {
  const handlePlanSyncEvent = (event: CustomEvent<PlanSyncEventDetail>) => {
    const detail = event.detail;
    if (!isPlanSyncEventDetail(detail)) {
      return;
    }
    switch (detail.type) {
      case 'plan_created':
      case 'plan_updated': {
        invalidatePlanCollections();
        if (detail.plan_id != null) {
          invalidatePlanScopedQueries(detail.plan_id);
        }
        break;
      }
      case 'plan_deleted': {
        invalidatePlanCollections();
        if (detail.plan_id != null) {
          removePlanScopedQueries(detail.plan_id);
        }
        break;
      }
      case 'task_changed':
      case 'plan_jobs_completed': {
        if (detail.plan_id != null) {
          invalidatePlanScopedQueries(detail.plan_id);
        }
        break;
      }
      default:
        break;
    }
  };

  window.addEventListener('tasksUpdated', handlePlanSyncEvent as EventListener);
  window.__gaPlanSyncListenerRegistered__ = true;
}

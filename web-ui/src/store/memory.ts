import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import type { Memory, MemoryStats } from '@/types';

interface MemoryState {
  // Data state
  memories: Memory[];
  selectedMemory: Memory | null;
  stats: MemoryStats | null;

  // Filter state
  filters: {
    search_query: string;
    memory_types: string[];
    importance_levels: string[];
    min_similarity: number;
  };

  // Loading state
  loading: boolean;
  error: string | null;

  // Actions
  setMemories: (memories: Memory[]) => void;
  addMemory: (memory: Memory) => void;
  updateMemory: (id: string, updates: Partial<Memory>) => void;
  removeMemory: (id: string) => void;
  setSelectedMemory: (memory: Memory | null) => void;
  setStats: (stats: MemoryStats | null) => void;
  setFilters: (filters: Partial<MemoryState['filters']>) => void;
  clearFilters: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Derived values
  getFilteredMemories: () => Memory[];
}

export const useMemoryStore = create<MemoryState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    memories: [],
    selectedMemory: null,
    stats: null,
    filters: {
      search_query: '',
      memory_types: [],
      importance_levels: [],
      min_similarity: 0.6,
    },
    loading: false,
    error: null,

    // Set memory list
    setMemories: (memories) => set({ memories }),

    // Add memory
    addMemory: (memory) => set((state) => ({
      memories: [memory, ...state.memories],
    })),

    // Update memory
    updateMemory: (id, updates) => set((state) => ({
      memories: state.memories.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
      selectedMemory: state.selectedMemory?.id === id
        ? { ...state.selectedMemory, ...updates }
        : state.selectedMemory,
    })),

    // Remove memory
    removeMemory: (id) => set((state) => ({
      memories: state.memories.filter((m) => m.id !== id),
      selectedMemory: state.selectedMemory?.id === id ? null : state.selectedMemory,
    })),

    // Set selected memory
    setSelectedMemory: (memory) => set({ selectedMemory: memory }),

    // Set statistics
    setStats: (stats) => set({ stats }),

    // Set filters
    setFilters: (filters) => set((state) => ({
      filters: { ...state.filters, ...filters },
    })),

    // Clear filters
    clearFilters: () => set({
      filters: {
        search_query: '',
        memory_types: [],
        importance_levels: [],
        min_similarity: 0.6,
      },
    }),

    // Set loading state
    setLoading: (loading) => set({ loading }),

    // Set error state
    setError: (error) => set({ error }),

    // Get filtered memories
    getFilteredMemories: () => {
      const { memories, filters } = get();
      return memories.filter((memory) => {
        // Filter by search query
        if (filters.search_query) {
          const query = filters.search_query.toLowerCase();
          const matchContent = memory.content.toLowerCase().includes(query);
          const matchKeywords = memory.keywords.some(k => k.toLowerCase().includes(query));
          const matchTags = memory.tags.some(t => t.toLowerCase().includes(query));
          if (!matchContent && !matchKeywords && !matchTags) {
            return false;
          }
        }

        // Filter by memory type
        if (filters.memory_types.length > 0 && !filters.memory_types.includes(memory.memory_type)) {
          return false;
        }

        // Filter by importance
        if (filters.importance_levels.length > 0 && !filters.importance_levels.includes(memory.importance)) {
          return false;
        }

        // Filter by similarity
        if (memory.similarity !== undefined && memory.similarity < filters.min_similarity) {
          return false;
        }

        return true;
      });
    },
  }))
);

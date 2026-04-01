import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { vi } from 'vitest';
import ToolResultCard from '../ToolResultCard';
import { useChatStore } from '@store/chat';

describe('ToolResultCard', () => {
  beforeEach(() => {
    useChatStore.setState({
      sendMessage: vi.fn().mockResolvedValue(undefined),
    } as any);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders search results when successful', () => {
    render(
      <ToolResultCard
        defaultOpen
        payload={{
          name: 'web_search',
          summary: 'Web search completed',
          result: {
            query: 'latest AI trends',
            success: true,
            response: 'Here is today\'s roundup of AI developments.',
            results: [
              {
                title: 'AI Weekly',
                url: 'https://example.com',
                source: 'Example News',
                snippet: 'Summary snippet',
              },
            ],
          },
        }}
      />
    );

    expect(screen.getByText('Web search completed')).toBeInTheDocument();
    expect(screen.getByText(/Query:/)).toBeInTheDocument();
    expect(screen.getByText('AI Weekly')).toBeInTheDocument();
  });

  it('shows retry button when search fails', async () => {
    const sendMessage = useChatStore.getState().sendMessage as unknown as ReturnType<typeof vi.fn>;
    render(
      <ToolResultCard
        defaultOpen
        payload={{
          name: 'web_search',
          summary: 'Web search failed',
          result: {
            query: 'latest AI trends',
            success: false,
            error: 'Request timed out',
          },
        }}
      />
    );

    expect(screen.getByText('Request timed out')).toBeInTheDocument();
    const retryButton = screen.getByRole('button', { name: 'Retry search' });
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledTimes(1);
    });
  });

  it('renders graph_rag response and trace fields', () => {
    render(
      <ToolResultCard
        defaultOpen
        payload={{
          name: 'graph_rag',
          summary: 'Knowledge-graph search completed',
          result: {
            query: 'batch effect',
            success: true,
            backend: 'multirag',
            mode: 'hybrid',
            response: '回答：这是最终融合结果。',
            trace: {
              final_path: 'merged',
              graphrag: 'fallback_graph',
              vectorrag: 'used',
            },
          },
        }}
      />
    );

    expect(screen.getByText('Knowledge-graph search completed')).toBeInTheDocument();
    expect(screen.getByText('回答：这是最终融合结果。')).toBeInTheDocument();
    expect(screen.getByText('Backend: multirag')).toBeInTheDocument();
    expect(screen.getByText('Mode: hybrid')).toBeInTheDocument();
    expect(screen.getByText('Final path: merged')).toBeInTheDocument();
  });
});

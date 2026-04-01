import { describe, expect, it } from 'vitest';
import {
  collectToolResultsFromActions,
  collectToolResultsFromMetadata,
  collectToolResultsFromSteps,
  mergeToolResults,
} from './toolResults';

describe('toolResults utilities', () => {
  it('collects tool results from steps', () => {
    const steps = [
      {
        action: { kind: 'plan_operation', name: 'create_plan' },
        details: {},
      },
      {
        action: {
          kind: 'tool_operation',
          name: 'web_search',
          parameters: { query: 'latest ai news' },
        },
        success: true,
        details: {
          summary: 'Search complete',
          result: {
            query: 'latest ai news',
            success: true,
            response: 'Top highlights...',
            results: [
              { title: 'AI Weekly', url: 'https://example.com', source: 'Example', snippet: '...' },
            ],
          },
        },
      },
    ];
    const payloads = collectToolResultsFromSteps(steps);
    expect(payloads).toHaveLength(1);
    expect(payloads[0].name).toBe('web_search');
    expect(payloads[0].result?.query).toBe('latest ai news');
    expect(payloads[0].result?.results).toHaveLength(1);
  });

  it('merges tool results without duplicates', () => {
    const existing = collectToolResultsFromMetadata([
      {
        name: 'web_search',
        summary: 'Search complete',
        result: { query: 'q1', success: true },
      },
    ]);
    const additional = collectToolResultsFromMetadata([
      {
        name: 'web_search',
        summary: 'Search complete',
        result: { query: 'q1', success: true },
      },
      {
        name: 'web_search',
        summary: 'Second search',
        result: { query: 'q2', success: false, error: 'timeout' },
      },
    ]);

    const merged = mergeToolResults(existing, additional);
    expect(merged).toHaveLength(2);
    expect(merged[0].result?.query).toBe('q1');
    expect(merged[1].result?.query).toBe('q2');
  });

  it('collects from action payloads', () => {
    const actions = [
      {
        kind: 'tool_operation',
        name: 'web_search',
        parameters: { query: 'abc' },
        details: { result: { query: 'abc', success: true } },
      },
    ];
    const payloads = collectToolResultsFromActions(actions as any);
    expect(payloads).toHaveLength(1);
    expect(payloads[0].result?.query).toBe('abc');
  });

  it('preserves springer result fields', () => {
    const payloads = collectToolResultsFromMetadata([
      {
        name: 'springer_nature',
        summary: 'Springer Nature meta search',
        result: {
          api: 'meta',
          query: 'batch effect',
          record_count: 2,
          records_preview: [{ title: 'Paper A' }, { title: 'Paper B' }],
          fallback_reason: 'basic_plan_simplified,field_constraints_removed',
          original_query: 'batch effect sort:date',
        },
      },
    ]);

    expect(payloads).toHaveLength(1);
    expect(payloads[0].result?.record_count).toBe(2);
    expect(payloads[0].result?.api).toBe('meta');
    expect(payloads[0].result?.records_preview).toHaveLength(2);
    expect(payloads[0].result?.fallback_reason).toBe('basic_plan_simplified,field_constraints_removed');
  });

  it('preserves graph_rag multirag fields', () => {
    const payloads = collectToolResultsFromMetadata([
      {
        name: 'graph_rag',
        summary: 'Knowledge-graph search finished',
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
      },
    ]);

    expect(payloads).toHaveLength(1);
    expect(payloads[0].result?.backend).toBe('multirag');
    expect(payloads[0].result?.mode).toBe('hybrid');
    expect(payloads[0].result?.trace?.final_path).toBe('merged');
  });
});

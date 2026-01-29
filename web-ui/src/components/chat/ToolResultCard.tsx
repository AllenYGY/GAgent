import React, { useMemo, useState } from 'react';
import { Alert, Button, Collapse, List, Space, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { ToolResultItem, ToolResultPayload } from '@/types';
import { useChatStore } from '@store/chat';

const { Paragraph, Text } = Typography;

interface ToolResultCardProps {
  payload: ToolResultPayload;
  defaultOpen?: boolean;
}

const ToolResultCard: React.FC<ToolResultCardProps> = ({ payload, defaultOpen = false }) => {
  const [introVisible, setIntroVisible] = useState(true);
  const [retryLoading, setRetryLoading] = useState(false);

  const sendMessage = useChatStore((state) => state.sendMessage);

    const {
      toolName,
      introMessage,
      header,
      query,
      searchItems,
      springerRecords,
      springerRecordCount,
      springerApi,
      springerFallbackReason,
      springerOriginalQuery,
      triples,
      responseText,
      promptText,
      errorText,
      success,
      providerLabel,
      fallbackLabel,
      metadata,
      subgraph,
      isWebSearch,
      isSpringer,
    } = useMemo(() => {
      const toolValue = typeof payload.name === 'string' && payload.name ? payload.name : 'tool';
      const isWeb = toolValue === 'web_search';
      const isGraph = toolValue === 'graph_rag';
      const isSpringerTool = toolValue === 'springer_nature';

    const providerValue =
      isWeb && typeof payload.result?.provider === 'string'
        ? payload.result.provider
        : isWeb && typeof payload.parameters?.provider === 'string'
          ? payload.parameters.provider
          : undefined;
    const fallbackValue =
      isWeb && typeof payload.result?.fallback_from === 'string'
        ? payload.result.fallback_from
        : undefined;
    const labelMap: Record<string, string> = {
      builtin: 'Built-in',
      perplexity: 'Perplexity',
    };
    const providerLabelText = providerValue ? labelMap[providerValue] ?? providerValue : undefined;
    const fallbackLabelText = fallbackValue ? labelMap[fallbackValue] ?? fallbackValue : undefined;

    const successState = payload.result?.success !== false;
    let headerText =
      payload.summary ??
      (successState ? 'Tool run completed' : 'Tool run failed—please try again later.');
    let intro = 'The tool call has finished processing.';
      if (isWeb) {
        headerText =
          payload.summary ??
          (successState ? 'Web search completed' : 'Web search failed—please try again later.');
        intro = 'Web search executed to retrieve up-to-date references.';
      } else if (isGraph) {
        headerText =
          payload.summary ??
          (successState ? 'Knowledge-graph search completed' : 'Knowledge-graph search failed.');
        intro = 'Knowledge-graph query executed.';
      } else if (isSpringerTool) {
        headerText =
          payload.summary ??
          (successState ? 'Springer Nature search completed' : 'Springer Nature search failed.');
        intro = 'Springer Nature query executed.';
      }
    const normalizedQuery =
      payload.result?.query ??
      (typeof payload.parameters?.query === 'string' ? payload.parameters.query : undefined);
    const springerApiValue =
      typeof payload.result?.api === 'string'
        ? payload.result.api
        : typeof payload.parameters?.api === 'string'
          ? payload.parameters.api
          : undefined;
    const resultItems =
      isWeb && Array.isArray(payload.result?.results) && payload.result?.results?.length
        ? payload.result?.results.filter(Boolean)
        : [];
    const springerPreview =
      Array.isArray(payload.result?.records_preview) && payload.result?.records_preview.length > 0
        ? payload.result.records_preview
        : [];
    const springerRecordCountValue =
      typeof payload.result?.record_count === 'number' ? payload.result.record_count : undefined;
    const springerFallbackValue =
      typeof payload.result?.fallback_reason === 'string'
        ? payload.result.fallback_reason
        : undefined;
    const springerOriginalQueryValue =
      typeof payload.result?.original_query === 'string'
        ? payload.result.original_query
        : undefined;
    const response =
      typeof payload.result?.response === 'string' && payload.result.response.trim().length > 0
        ? payload.result.response
        : typeof payload.result?.answer === 'string' && payload.result.answer.trim().length > 0
          ? payload.result.answer
          : undefined;
    const error =
      typeof payload.result?.error === 'string' && payload.result.error.trim().length > 0
        ? payload.result.error
        : undefined;

    return {
      toolName: toolValue,
      introMessage: intro,
      header: headerText,
      query: normalizedQuery,
      searchItems: resultItems,
      springerRecords: springerPreview,
      springerRecordCount: springerRecordCountValue,
      springerApi: springerApiValue,
      springerFallbackReason: springerFallbackValue,
      springerOriginalQuery: springerOriginalQueryValue,
      responseText: response,
      promptText: isGraph && typeof payload.result?.prompt === 'string' ? payload.result.prompt : undefined,
      errorText: error,
      success: successState,
      providerLabel: providerLabelText,
      fallbackLabel: fallbackLabelText,
      metadata: isGraph && payload.result?.metadata && typeof payload.result.metadata === 'object'
        ? payload.result.metadata
        : undefined,
      triples: isGraph && Array.isArray(payload.result?.triples) ? payload.result.triples : [],
      subgraph: isGraph && payload.result?.subgraph && typeof payload.result.subgraph === 'object'
        ? payload.result.subgraph
        : undefined,
      isWebSearch: isWeb,
      isSpringer: isSpringerTool,
    };
  }, [payload]);

  const handleRetry = async () => {
    if (!isWebSearch) {
      return;
    }
    if (!query) {
      return;
    }
    try {
      setRetryLoading(true);
      const prompt = `Please call the web_search tool again to search for "${query}" and summarise the latest findings.`;
      await sendMessage(prompt, { tool_retry: true, retry_query: query });
    } finally {
      setRetryLoading(false);
    }
  };

  const handleCollapseChange = (keys: string | string[]) => {
    if (keys && (Array.isArray(keys) ? keys.length > 0 : true)) {
      setIntroVisible(false);
    }
  };

  const springerFallbackMap: Record<string, string> = {
    basic_plan_simplified: 'Query normalized for basic plan support.',
    field_constraints_removed: 'Field constraints removed due to access limits.',
  };

  const collapseItems = [
    {
      key: 'result',
      label: (
        <Space>
          <Tag color={success ? (toolName === 'graph_rag' ? 'purple' : 'green') : 'red'}>
            {toolName}
          </Tag>
          {providerLabel && <Tag color="blue">{providerLabel}</Tag>}
          <Text>{header}</Text>
        </Space>
      ),
      children: (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {providerLabel && (
            <Text type="secondary">
              Source: {providerLabel}
              {fallbackLabel ? ` (fallback from ${fallbackLabel})` : ''}
            </Text>
          )}
          {query && (
            <Text type="secondary">
              Query: <Text code>{query}</Text>
            </Text>
          )}
          {isSpringer && springerApi && (
            <Text type="secondary">API: {springerApi}</Text>
          )}
          {isSpringer && typeof springerRecordCount === 'number' && (
            <Text type="secondary">Records: {springerRecordCount}</Text>
          )}
          {isSpringer && springerOriginalQuery && (
            <Text type="secondary">
              Original query: <Text code>{springerOriginalQuery}</Text>
            </Text>
          )}
          {isSpringer && springerFallbackReason && (
            <Text type="secondary">
              Note:{' '}
              {springerFallbackReason
                .split(',')
                .map((reason) => springerFallbackMap[reason] ?? reason)
                .join(' ')}
            </Text>
          )}
          {responseText && (
            <Paragraph style={{ marginBottom: 8, whiteSpace: 'pre-wrap' }}>
              {responseText}
            </Paragraph>
          )}
          {promptText && (
            <Paragraph style={{ marginBottom: 8, whiteSpace: 'pre-wrap' }}>
              {promptText}
            </Paragraph>
          )}
          {metadata && (
            <Text type="secondary">
              Triple count: {metadata.triple_count ?? '-'}, hops: {metadata.hops ?? '-'}
            </Text>
          )}
          {searchItems.length > 0 && (
            <List<ToolResultItem>
              size="small"
              dataSource={searchItems}
              renderItem={(item, index) => (
                <List.Item key={`${item?.url ?? index}`}>
                  <Space direction="vertical" size={2}>
                    {item?.title && (
                      <Text strong>
                        {item.url ? (
                          <a href={item.url} target="_blank" rel="noopener noreferrer">
                            {item.title}
                          </a>
                        ) : (
                          item.title
                        )}
                      </Text>
                    )}
                    {item?.source && (
                      <Text type="secondary">Source: {item.source}</Text>
                    )}
                    {item?.snippet && (
                      <Text style={{ whiteSpace: 'pre-wrap' }}>{item.snippet}</Text>
                    )}
                  </Space>
                </List.Item>
              )}
            />
          )}
          {springerRecords.length > 0 && (
            <List<Record<string, any>>
              size="small"
              dataSource={springerRecords}
              renderItem={(record, index) => {
                const title =
                  typeof record?.title === 'string'
                    ? record.title
                    : typeof record?.title?.[0] === 'string'
                      ? record.title[0]
                      : undefined;
                const doi = typeof record?.doi === 'string' ? record.doi : undefined;
                const publication =
                  typeof record?.publicationName === 'string'
                    ? record.publicationName
                    : typeof record?.journalTitle === 'string'
                      ? record.journalTitle
                      : typeof record?.publicationTitle === 'string'
                        ? record.publicationTitle
                        : typeof record?.publisher === 'string'
                          ? record.publisher
                          : undefined;
                const date =
                  typeof record?.publicationDate === 'string'
                    ? record.publicationDate
                    : typeof record?.onlineDate === 'string'
                      ? record.onlineDate
                      : typeof record?.publicationYear === 'string'
                        ? record.publicationYear
                        : undefined;
                const url =
                  typeof record?.url === 'string'
                    ? record.url
                    : Array.isArray(record?.url) && record.url.length > 0
                      ? typeof record.url[0] === 'string'
                        ? record.url[0]
                        : record.url[0]?.value ?? record.url[0]?.url
                      : undefined;

                const metaParts = [
                  doi ? `DOI: ${doi}` : null,
                  publication ? `Source: ${publication}` : null,
                  date ? `Date: ${date}` : null,
                ].filter(Boolean);

                return (
                  <List.Item key={`${doi ?? title ?? index}`}>
                    <Space direction="vertical" size={2}>
                      <Text strong>
                        {url ? (
                          <a href={url} target="_blank" rel="noopener noreferrer">
                            {title ?? `Record ${index + 1}`}
                          </a>
                        ) : (
                          title ?? `Record ${index + 1}`
                        )}
                      </Text>
                      {metaParts.length > 0 && (
                        <Text type="secondary">{metaParts.join(' • ')}</Text>
                      )}
                    </Space>
                  </List.Item>
                );
              }}
            />
          )}
          {triples && triples.length > 0 && (
            <List<Record<string, any>>
              size="small"
              dataSource={triples}
              renderItem={(item, index) => (
                <List.Item key={index}>
                  <Space direction="vertical" size={2}>
                    <Text strong>
                      {item.entity1} --[{item.relation}]→ {item.entity2}
                    </Text>
                    <Text type="secondary">
                      Type: {item.entity1_type ?? 'unknown'} → {item.entity2_type ?? 'unknown'}
                    </Text>
                    {item.pdf_name && (
                      <Text type="secondary">Source PDF: {item.pdf_name}</Text>
                    )}
                  </Space>
                </List.Item>
              )}
            />
          )}
          {subgraph && (
            <Alert
              type="info"
              showIcon
              message="Returned a knowledge-graph subgraph; view it in the graph panel for deeper analysis."
            />
          )}
          {!success && (
            <Alert
              type="error"
              showIcon
              message={errorText ?? 'Search failed. Please try again later.'}
            />
          )}
          {!success && query && isWebSearch && (
            <Button
              type="link"
              icon={<ReloadOutlined />}
              onClick={handleRetry}
              loading={retryLoading}
              style={{ paddingLeft: 0 }}
            >
              Retry search
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="tool-result-card">
      {introVisible && (
        <Alert
          showIcon
          type="info"
          message={introMessage}
          style={{ marginBottom: 8 }}
        />
      )}
      <Collapse
        size="small"
        defaultActiveKey={defaultOpen ? ['result'] : []}
        onChange={handleCollapseChange}
        ghost
        items={collapseItems}
      />
    </div>
  );
};

export default ToolResultCard;

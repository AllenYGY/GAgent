# MultiRAG API

本文档描述独立 MultiRAG 后端服务当前对外提供的 HTTP JSON 接口。

## 概览

- 协议：HTTP
- 数据格式：`application/json`
- 鉴权方式：`X-API-Key`
- 当前接口：
  - `GET /api/health`
  - `POST /api/query`

Base URL 示例：

```text
http://119.147.24.196:8002
```

如果后续接入域名、Nginx 或 HTTPS，只需要替换 Base URL，接口路径和请求格式不变。

## 鉴权

`GET /api/health` 不需要鉴权。  
`POST /api/query` 必须携带请求头：

```http
X-API-Key: <SERVER_API_KEY>
```

说明：

- `SERVER_API_KEY` 是 MultiRAG 服务自身的访问密钥
- 不应与其他系统或模型服务的密钥复用

## 1. 健康检查

### 请求

```http
GET /api/health
```

### cURL 示例

```bash
curl http://119.147.24.196:8002/api/health
```

### 成功响应示例

```json
{
  "success": true,
  "backend": "multirag",
  "qwen_configured": true,
  "server_api_key_configured": true,
  "allowed_origins": [],
  "query_timeout_seconds": 300,
  "files": {
    "working_dir": {
      "path": "/home/zczhao/lightrag_project/lightrag_workdir",
      "exists": true
    },
    "graph_store": {
      "path": "/home/zczhao/lightrag_project/lightrag_workdir/graph_chunk_entity_relation.graphml",
      "exists": true
    },
    "vector_index": {
      "path": "/home/zczhao/lightrag_project/vrag.index",
      "exists": true
    },
    "vector_meta": {
      "path": "/home/zczhao/lightrag_project/vrag.pkl",
      "exists": true
    }
  },
  "optional_files": {
    "solo_queries": {
      "path": "/home/zczhao/lightrag_project/lightrag_workdir/solo_queries.jsonl",
      "exists": true
    }
  }
}
```

### 状态码

- `200`：服务健康
- `503`：关键配置缺失、索引文件缺失或服务不可用

## 2. 查询接口

### 请求

```http
POST /api/query
Content-Type: application/json
X-API-Key: <SERVER_API_KEY>
```

请求体：

```json
{
  "query": "what is BACTERIOPHAGE",
  "mode": "hybrid"
}
```

### 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `query` | `string` | 是 | 用户问题，不能为空 |
| `mode` | `string` | 否 | 查询模式，默认 `hybrid` |

### `mode` 可选值

| 值 | 说明 |
| --- | --- |
| `hybrid` | 默认模式，结合局部与全局上下文 |
| `local` | 更偏局部实体相关上下文 |
| `global` | 更偏全局摘要与概览 |
| `naive` | 更接近传统 RAG 检索方式 |

### cURL 示例

英文查询：

```bash
curl -X POST http://119.147.24.196:8002/api/query \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_SERVER_API_KEY' \
  -d '{"query":"what is BACTERIOPHAGE","mode":"hybrid"}'
```

中文查询：

```bash
curl -X POST http://119.147.24.196:8002/api/query \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_SERVER_API_KEY' \
  -d '{"query":"噬菌体和水产养殖有什么关系","mode":"hybrid"}'
```

生物信息学示例：

```bash
curl -X POST http://119.147.24.196:8002/api/query \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_SERVER_API_KEY' \
  -d '{"query":"生物信息学里有哪些常见的 batch effect 去除方法？","mode":"global"}'
```

### 成功响应示例

```json
{
  "success": true,
  "backend": "multirag",
  "mode": "hybrid",
  "result": "回答： ...",
  "trace": {
    "final_path": "merged",
    "graphrag": "fallback_graph",
    "vectorrag": "used"
  }
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | `boolean` | 是否成功 |
| `backend` | `string` | 固定为 `multirag` |
| `mode` | `string` | 实际使用的模式 |
| `result` | `string` | 最终回答文本 |
| `trace` | `object` | 本次查询走过的检索路径信息 |

### `trace` 字段说明

#### `trace.graphrag`

| 值 | 说明 |
| --- | --- |
| `native_graph` | 原生 GraphRAG 查询成功 |
| `fallback_graph` | 原生图查询未命中后，fallback 图检索成功 |
| `graph_no_result` | GraphRAG 未提供有效结果 |

#### `trace.vectorrag`

| 值 | 说明 |
| --- | --- |
| `used` | 本次使用了 VectorRAG |
| `unused` | 本次未使用 VectorRAG |

#### `trace.final_path`

| 值 | 说明 |
| --- | --- |
| `merged` | GraphRAG 和 VectorRAG 共同参与最终回答 |
| `vector_only` | 仅 VectorRAG 参与最终回答 |
| `native_graph` | 仅原生 GraphRAG 结果参与最终回答 |
| `fallback_graph` | 仅 fallback 图结果参与最终回答 |
| `no_local_context` | 本地检索都不可用，退化为直接模型回答 |

## 错误响应

错误响应格式：

```json
{
  "success": false,
  "error": "错误说明"
}
```

常见状态码：

| 状态码 | 说明 |
| --- | --- |
| `400` | 请求体不是 JSON、`query` 为空、`mode` 非法 |
| `401` | `X-API-Key` 无效 |
| `413` | 请求体超过大小限制 |
| `429` | 触发限流 |
| `500` | 服务内部异常 |
| `503` | 查询超时、索引缺失、上游模型失败或关键配置缺失 |

## 请求限制

当前默认限制：

- 请求体最大：`8192` 字节
- 查询超时：`300` 秒

## 当前实现说明

- 当前回答链路是：GraphRAG + VectorRAG + 最终融合
- `trace.graphrag = fallback_graph` 并不一定表示异常，可能只是原生图查询未命中后自动进入 fallback 图路径
- `result` 始终是最终融合后的回答，而不是单一路径的原始输出

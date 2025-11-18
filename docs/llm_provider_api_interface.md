# LLM Provider API Interface

本项目的 `LLMClient` 统一使用 OpenAI Chat Completions 兼容协议。所有脚本都会在启动时 `load_dotenv(override=True)`，因此 `.env` 中的最新配置会覆盖 shell 中已有的 `export`。若终端里还留有旧的 `*_API_KEY`，请运行 `unset` 再执行脚本。

## 1. 快速入门

```python
from openai import OpenAI
client = OpenAI(
    api_key=os.environ["QWEN_API_KEY"],
    base_url=os.environ["QWEN_API_URL"],
)
resp = client.chat.completions.create(
    model=os.environ["QWEN_MODEL"],
    messages=[{"role": "user", "content": "Summarize the solar system."}],
)
print(resp.choices[0].message.content)
```

## 2. Provider 变量一览

| Provider | 必需环境变量 | 默认 Base URL | 备注 |
| --- | --- | --- | --- |
| GLM | `GLM_API_KEY`, `GLM_API_URL`, `GLM_MODEL` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | 默认模型 `glm-4.6` |
| Qwen | `QWEN_API_KEY`, `QWEN_API_URL`, `QWEN_MODEL` | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` | 常用 `qwen3-max` |
| Perplexity | `PERPLEXITY_API_KEY`, `PERPLEXITY_API_URL`, `PERPLEXITY_MODEL` | `https://api.perplexity.ai/chat/completions` | 默认不参与批量评估 |
| Doubao | `DOUBAO_API_KEY`, `DOUBAO_API_URL`, `DOUBAO_MODEL` | `https://ark.cn-beijing.volces.com/api/v3` | 客户端会自动补 `/chat/completions` |
| Moonshot/Kimi | `MOONSHOT_API_KEY`, `MOONSHOT_API_URL`, `MOONSHOT_MODEL` | `https://api.moonshot.cn/v1` | 兼容 `kimi-k2-turbo-preview`/`kimi-latest` |
| DeepSeek | `DEEPSEEK_API_KEY`, `DEEPSEEK_API_URL`, `DEEPSEEK_MODEL` | `https://api.deepseek.com` | 支持 `deepseek-chat`、`deepseek-reasoner` |
| Grok/xAI | `GROK_API_KEY`, `GROK_API_URL`, `GROK_MODEL` | `https://api.x.ai/v1` | 适合自定义更长 timeout |
| Gemini | `GEMINI_API_KEY`, `GEMINI_API_URL`, `GEMINI_MODEL` | `https://generativelanguage.googleapis.com/v1beta/openai` | 若不想测试请 `unset` 相关变量 |

## 3. Provider 示例

### GLM
```python
client = OpenAI(
    api_key=os.environ["GLM_API_KEY"],
    base_url=os.environ.get("GLM_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
)
resp = client.chat.completions.create(
    model=os.environ.get("GLM_MODEL", "glm-4.6"),
    messages=[{"role": "user", "content": "Describe the CRE research plan."}],
)
print(resp.choices[0].message.content)
```

### Qwen
```python
client = OpenAI(
    api_key=os.environ["QWEN_API_KEY"],
    base_url=os.environ.get("QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
)
resp = client.chat.completions.create(
    model=os.environ.get("QWEN_MODEL", "qwen3-max"),
    messages=[{"role": "user", "content": "Explain carbapenem resistance."}],
)
print(resp.choices[0].message.content)
```

### Doubao / Volcengine
```python
client = OpenAI(
    api_key=os.environ["DOUBAO_API_KEY"],
    base_url=os.environ.get("DOUBAO_API_URL", "https://ark.cn-beijing.volces.com/api/v3"),
)
resp = client.chat.completions.create(
    model=os.environ.get("DOUBAO_MODEL", "doubao-seed-1-6-251015"),
    messages=[{"role": "user", "content": "Give me a policy-ready summary."}],
)
print(resp.choices[0].message.content)
```

### Moonshot / Kimi
```python
client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url=os.environ.get("MOONSHOT_API_URL", "https://api.moonshot.cn/v1"),
)
resp = client.chat.completions.create(
    model=os.environ.get("MOONSHOT_MODEL", "kimi-k2-turbo-preview"),
    messages=[{"role": "user", "content": "太阳系有哪些行星？"}],
)
print(resp.choices[0].message.content)
```

### DeepSeek
```python
client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com"),
)
resp = client.chat.completions.create(
    model=os.environ.get("DEEPSEEK_MODEL", "deepseek-reasoner"),
    messages=[{"role": "user", "content": "What is a phage cocktail?"}],
)
print(resp.choices[0].message.content)
```

### Grok / xAI
```python
import httpx
client = OpenAI(
    api_key=os.environ["GROK_API_KEY"],
    base_url=os.environ.get("GROK_API_URL", "https://api.x.ai/v1"),
    timeout=httpx.Timeout(600.0),
)
resp = client.chat.completions.create(
    model=os.environ.get("GROK_MODEL", "grok-4"),
    messages=[{"role": "user", "content": "Solve 2 + 2."}],
)
print(resp.choices[0].message.content)
```

### Gemini
```python
client = OpenAI(
    api_key=os.environ["GEMINI_API_KEY"],
    base_url=os.environ.get("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
)
resp = client.chat.completions.create(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    messages=[{"role": "user", "content": "Explain how LLMs work."}],
)
print(resp.choices[0].message.content)
```

### Perplexity（可选）
```python
client = OpenAI(
    api_key=os.environ["PERPLEXITY_API_KEY"],
    base_url=os.environ.get("PERPLEXITY_API_URL", "https://api.perplexity.ai/chat/completions"),
)
resp = client.chat.completions.create(
    model=os.environ.get("PERPLEXITY_MODEL", "sonar-reasoning-pro"),
    messages=[{"role": "user", "content": "Describe the solar system."}],
)
print(resp.choices[0].message.content)
```

## 4. 验证与调试

- 只测指定模型：`python scripts/verify_llm_connectivity.py --providers glm,qwen`
- 对全部模型并行评估计划：省略 `--provider` 即会并行运行（默认跳过 Perplexity），输出 `plan_scores_<provider>.csv`。
- 常见错误：`404 url.not_found` 多因 Base URL 缺 `/chat/completions`；`503 The model is overloaded`（Gemini）需稍等或改模型；若看到 `[WARN] Skipping provider ... because no API key is configured`，说明 `.env` 或 shell 中缺少对应密钥。

#!/usr/bin/env python3
import argparse
import json
import os
import sys
from urllib import error, request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.llm import PROVIDER_CONFIGS, _compose_endpoint, _first_env_value


def _resolve_value(arg_value, env_names, default_value):
    if arg_value:
        return arg_value
    env_value = _first_env_value(env_names)
    if env_value:
        return env_value
    return default_value


def _build_headers(provider: str, api_key: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if provider == "openrouter":
        referer = os.getenv("OPENROUTER_SITE_URL")
        title = os.getenv("OPENROUTER_SITE_NAME")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
    return headers


def _redact_headers(headers):
    redacted = dict(headers)
    if "Authorization" in redacted:
        redacted["Authorization"] = "Bearer ***"
    return redacted


def main():
    parser = argparse.ArgumentParser(description="Minimal LLM connectivity test.")
    parser.add_argument("--provider", required=True, help="LLM provider name (e.g. openrouter, grok).")
    parser.add_argument("--model", default="", help="Model override.")
    parser.add_argument("--url", default="", help="Base URL override (without /chat/completions).")
    parser.add_argument("--prompt", default="ping", help="Prompt to send.")
    args = parser.parse_args()

    provider = args.provider.lower()
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        print(f"[ERR] Unsupported provider: {provider}", file=sys.stderr)
        sys.exit(2)

    api_key = _resolve_value(None, config.get("api_key_env"), None)
    if not api_key:
        print(f"[ERR] Missing API key env: {config.get('api_key_env')}", file=sys.stderr)
        sys.exit(2)

    base_url = _resolve_value(args.url, config.get("url_env"), config.get("default_url"))
    model = _resolve_value(args.model, config.get("model_env"), config.get("default_model"))
    endpoint = _compose_endpoint(base_url, config.get("endpoint_path"))

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": args.prompt}],
            }
        ],
    }
    headers = _build_headers(provider, api_key)

    print(f"[INFO] provider={provider}")
    print(f"[INFO] endpoint={endpoint}")
    print(f"[INFO] model={model}")
    print(f"[INFO] headers={json.dumps(_redact_headers(headers), ensure_ascii=False)}")

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as resp:
            resp_text = resp.read().decode("utf-8")
            print(f"[OK] status={resp.status}")
            print(resp_text)
            sys.exit(0)
    except error.HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        print(f"[ERR] HTTP {e.code}: {msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERR] Request failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse, json, os
from urllib import error, request

CFG = {
    "chatgpt": ("OPENAI_API_KEY", "gpt-4.1-mini", "https://api.openai.com/v1", "oai"),
    "gemini": ("GEMINI_API_KEY", "gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta", "gemini"),
    "kimi": ("MOONSHOT_API_KEY", "kimi-k2.5", "https://api.moonshot.cn/v1", "oai"),
    "qwen": ("DASHSCOPE_API_KEY", "qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1", "oai"),
    "deepseek": ("DEEPSEEK_API_KEY", "deepseek-chat", "https://api.deepseek.com", "oai"),
    "grok": ("XAI_API_KEY", "grok-3-mini", "https://api.x.ai/v1", "oai"),
    "claude": ("ANTHROPIC_API_KEY", "claude-3-7-sonnet-latest", "https://api.anthropic.com/v1", "claude"),
}


class LLMError(RuntimeError): pass


def _post(url, headers, body):
    req = request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=300) as r: return json.loads(r.read().decode("utf-8"))
    except error.HTTPError as e: raise LLMError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}") from e
    except error.URLError as e: raise LLMError(f"请求失败: {e}") from e


def _text(x):
    if isinstance(x, str): return x
    if isinstance(x, list): return "\n".join(filter(None, map(_text, x)))
    if isinstance(x, dict): return _text(x.get("text", x.get("content", x.get("parts", ""))))
    return ""


class LLMRunner:
    def __init__(self, provider, model=None, api_key=None, base_url=None):
        env, default_model, default_base, kind = CFG[provider]
        self.kind, self.model = kind, model or default_model
        self.api_key, self.base = api_key or os.getenv(env, ""), (base_url or default_base).rstrip("/")
        if not self.api_key: raise LLMError(f"{provider} 缺少 API key，请传 --api-key 或设置环境变量 {env}。")

    def run(self, prompt, system_prompt=None):
        raw = {"oai": self._oai, "gemini": self._gemini, "claude": self._claude}[self.kind](prompt, system_prompt)
        return {"response_text": self._extract(raw), "raw_response": raw}

    def _oai(self, prompt, system_prompt):
        msg = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [{"role": "user", "content": prompt}]
        return _post(f"{self.base}/chat/completions", {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, {"model": self.model, "messages": msg})

    def _gemini(self, prompt, system_prompt):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system_prompt: body["system_instruction"] = {"parts": [{"text": system_prompt}]}
        return _post(f"{self.base}/models/{self.model}:generateContent", {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, body)

    def _claude(self, prompt, system_prompt):
        body = {"model": self.model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
        if system_prompt: body["system"] = system_prompt
        return _post(f"{self.base}/messages", {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, body)

    def _extract(self, raw):
        if self.kind == "gemini": return _text(raw.get("candidates", [{}])[0].get("content", {}).get("parts", []))
        if self.kind == "claude": return _text(raw.get("content", []))
        return _text(raw.get("choices", [{}])[0].get("message", {}).get("content", ""))


def _args():
    x = argparse.ArgumentParser(description="LLM 工具脚本：只接收 prompt 并调用指定 LLM。")
    x.add_argument("--provider", choices=list(CFG), default="kimi")
    x.add_argument("--prompt", required=True)
    x.add_argument("--system-prompt")
    x.add_argument("--model"); x.add_argument("--api-key"); x.add_argument("--base-url")
    return x.parse_args()


def main():
    a = _args()
    print(LLMRunner(a.provider, a.model, a.api_key, a.base_url).run(a.prompt, a.system_prompt)["response_text"])


if __name__ == "__main__": main()

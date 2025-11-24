# LLM Providers & Configuration

Available providers include:

- `openrouter` (default)
- Generic OpenAI-compatible: `openai-http` (custom endpoints), `ollama` (local), `llama-cpp` (local)
- Convenience aliases: `deepseek`, `qwen`, `kimi`, `glm`, `modelscope`, `gemini`

## Quick start

```
copilot> /llm list
copilot> /llm use deepseek
copilot> /llm key deepseek sk-...     # set API key for this session
copilot> /config                      # verify provider settings
```

Notes:
- OpenAI-compatible providers read `base_url`, `api_key`, `model`, and optional headers from the session config or environment. For convenience aliases we default to:
    - deepseek: base https://api.deepseek.com, model `deepseek-chat`
    - qwen (DashScope): base https://dashscope.aliyuncs.com (path `/compatible-mode/v1/chat/completions`), model `qwen-turbo`
    - kimi (Moonshot): base https://api.moonshot.cn, model `moonshot-v1-8k`
    - glm (ZhipuAI): base https://open.bigmodel.cn (path `/api/paas/v4/chat/completions`), model `glm-4`
    - llama-cpp: base http://localhost:8080 (llama.cpp server with `--api`), model `llama`
    - modelscope: base https://api-inference.modelscope.cn, model `deepseek-ai/DeepSeek-R1-Distill-Llama-8B`
        - gemini: base https://generativelanguage.googleapis.com/v1beta/openai, path `/chat/completions`, model `gemini-2.5-flash` (see https://ai.google.dev/gemini-api/docs/openai for setup)
            - Model listing (`/v1beta/openai/models`) requires the same API key in the Authorization header, so provide it before calling `/llm list`.
- You can switch providers anytime with `/llm use <name>`.
- Colors are enabled by default; toggle with `/colors on|off`.

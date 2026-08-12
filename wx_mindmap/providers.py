"""
wx-mindmap · AI 供应商预设

内置几个主流 OpenAI 兼容 AI 的默认 Base URL / Model / 获取key的官方地址。
用户选一个 → 填自己的 key 就能用，不写死、不限制。
用户也可以完全自定义 URL+Model 接任何 OpenAI 兼容服务（含本地 Ollama）。
所有 key 只在用户本机用，绝不进输出/上传/打包。
"""
from __future__ import annotations

# name, 默认BaseURL, 默认Model, 官方获取key页面, 是否视觉能力(可看图)
PROVIDERS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key_url": "https://platform.deepseek.com/api_keys",
        "vision": False,
        "desc": "文字强、便宜，但不支持视觉（看不了图/视频）。",
    },
    {
        "id": "qwen",
        "name": "通义千问 (qwen)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "key_url": "https://bailian.console.aliyun.com",
        "vision": True,
        "desc": "阿里云百炼，支持视觉（qwen-vl-plus 可看图）。",
    },
    {
        "id": "zhipu",
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "vision": True,
        "desc": "智谱清言，GLM-4V 支持视觉。",
    },
    {
        "id": "moonshot",
        "name": "Moonshot (Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "key_url": "https://platform.moonshot.cn/console/api-keys",
        "vision": False,
        "desc": "Kimi，长文本强，部分模型支持视觉。",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_url": "https://platform.openai.com/api-keys",
        "vision": True,
        "desc": "GPT 系列，能力全面，国内访问可能需魔法。",
    },
    {
        "id": "ollama",
        "name": "Ollama (本地)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b",
        "key_url": "https://ollama.com",
        "vision": False,
        "desc": "本地免费模型，key 随便填（如 ollama），数据不出本机。",
    },
    {
        "id": "doubao",
        "name": "豆包 (火山方舟)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-seed-2-1-pro-260628",
        "key_url": "https://console.volcengine.com/ark",
        "vision": True,
        "desc": "字节豆包（火山方舟），支持视觉。key 形如 ark-xxxx。注意：模型需在火山方舟控制台开通，且可能有限额(429)。",
    },
    {
        "id": "custom",
        "name": "自定义 (任意 OpenAI 兼容)",
        "base_url": "",
        "model": "",
        "key_url": "",
        "vision": True,
        "desc": "自己填 Base URL + 模型 + Key，可接任意 OpenAI 兼容服务（含本地 Ollama、中转站等）。",
    },
]

# 默认第一个（DeepSeek）
DEFAULT_PROVIDER = PROVIDERS[0]

# 通过 id 取
BY_ID = {p["id"]: p for p in PROVIDERS}

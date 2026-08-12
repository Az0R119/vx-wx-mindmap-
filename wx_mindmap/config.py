# -*- coding: utf-8 -*-
"""wx-mindmap 本地配置持久化（记住上次设置，下次打开自动加载）。

明文存本机用户目录一份 JSON：API key / 模型供应商 / 主题 / 群类型等。
方便程度优先（与网页版 localStorage 同级），不加密。
安全提示：key 存本机明文，不要在公用电脑上使用本功能。
文件名：.wxmindmap_config.json
"""

import os
import json

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".wxmindmap_config.json")

# 可持久化的字段白名单（只存这些，避免存无关临时数据）
_FIELDS = [
    "provider",       # 供应商名（如 DeepSeek/豆包）
    "base_url",       # Base URL
    "model",          # 模型名
    "api_key",        # API Key（明文）
    "vision_provider",
    "vision_base",
    "vision_model",
    "vision_key",
    "theme",          # 深色/浅色/极简
    "user_hint",      # 群类型/关注点
    "compress",       # 是否压缩
]


def load() -> dict:
    """读本地配置；无则返回空 dict。"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save(values: dict) -> bool:
    """保存配置（只保留白名单字段）。返回是否成功。"""
    try:
        keep = {k: values.get(k) for k in _FIELDS if k in values and values.get(k) is not None}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def clear_key() -> None:
    """仅清空 key（不留敏感的明文）。保留其他配置。"""
    try:
        data = load()
        data.pop("api_key", None)
        data.pop("vision_key", None)
        save(data)
    except Exception:
        pass

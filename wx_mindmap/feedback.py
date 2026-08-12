# -*- coding: utf-8 -*-
"""wx-mindmap 反馈闭环（L2 个人记忆 + 社区改进点拉取）。

- 本机记住用户偏好（群类型/主题/近期反馈）→ 下次自动注入
- 出图后让用户点 👍/👎 + 一句原因 → 匿名上传到 Cloudflare Worker
- 启动时拉取 /improvements → 社区改进点注入 prompt（一个反馈惠及所有人）
反馈只含匿名字段，绝不包含聊天内容。
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional

# 后端地址（部署的 Cloudflare Worker，测试可用）
BACKEND_URL = "https://wxmindmap.1464768276.workers.dev"

# 本机偏好文件路径（L2 个人记忆）
PREF_PATH = os.path.join(os.path.expanduser("~"), ".wxmindmap_prefs.json")


def _read_prefs() -> Dict:
    try:
        with open(PREF_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_prefs(prefs: Dict) -> None:
    try:
        with open(PREF_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def remember_pref(key: str, value: str) -> None:
    """L2：记住一条偏好（如上次的群类型/主题/反馈），供下次生成时提示。"""
    try:
        p = _read_prefs()
        p[key] = value
        p["updated_at"] = int(time.time())
        _write_prefs(p)
    except Exception:
        pass


def get_personal_hint() -> str:
    """取本机积累的个人偏好，拼成提示注入 prompt；无则空串。"""
    try:
        p = _read_prefs()
        hints = []
        if p.get("group_type"):
            hints.append("用户上次群的类型是【" + str(p["group_type"]) + "】")
        if p.get("focus"):
            hints.append("用户上次关注【" + str(p["focus"]) + "】")
        if p.get("recent_dislike"):
            hints.append("用户上次反馈不满意点【" + str(p["recent_dislike"]) + "】")
        return "；".join(hints)
    except Exception:
        return ""


def submit_feedback(mood: str, reason: str, group_type: str = "",
                    version: str = "", backend: str = BACKEND_URL) -> Dict:
    """匿名上传一条反馈（不含聊天内容）。异步调用，失败不影响主流程。
    同时本地记住这条偏好。"""
    # 本地记住
    if mood == "dislike":
        remember_pref("recent_dislike", reason)
    if group_type:
        remember_pref("group_type", group_type)

    def _send():
        try:
            import urllib.request
            payload = json.dumps({
                "mood": mood,
                "reason": reason[:300],
                "groupType": group_type[:30],
                "version": version[:20],
            }).encode("utf-8")
            req = urllib.request.Request(
                backend.replace("/feedback", "").rstrip("/") + "/feedback",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15)
        except Exception:
            pass  # 上传失败静默——反馈是可选的，不能让用户卡住
    try:
        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        pass
    return {"ok": True}


def fetch_improvements(backend: str = BACKEND_URL, timeout: float = 10.0) -> List[str]:
    """拉取社区改进点（所有用户反馈汇总）。失败返回 []。"""
    try:
        import urllib.request
        url = backend.replace("/improvements", "").rstrip("/") + "/improvements"
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        # 只拿高频改进点（top dislike reasons）
        pts = data.get("improvementPoints", [])
        lines = []
        for pt in pts[:5]:
            kw = str(pt.get("keyword", "")).strip()
            n = int(pt.get("count", 0))
            if kw:
                lines.append(f"{kw}（{n} 人提过）")
        return lines
    except Exception:
        return []


def build_community_hint(backend: str = BACKEND_URL) -> str:
    """把社区改进点 + 个人偏好拼成语气可读的提示，供注入 prompt。"""
    parts = []
    personal = get_personal_hint()
    if personal:
        parts.append(personal)
    community = fetch_improvements(backend)
    if community:
        parts.append("社区用户普遍偏好改进：" + "、".join(community))
    return "；".join(parts)

"""
wx-mindmap · 解析模块

从 WeChatDataAnalysis 导出的 zip（WCE / memotrace 格式）里，
把所有消息、发送者、类型、时间提取出来，返回结构化的消息列表。

零 token：纯本地解析，不调任何模型。
"""
from __future__ import annotations

import html as ihtml
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional


# 消息类型: data-render-type 的值
TEXT_KINDS = {"text", "emoji"}

# 加入群聊 / 系统消息 特征（丢弃）
_SYSTEM_MARKS = ["加入群聊", "$from$", "$adder$", "invited", "added", "quotations",
                 "撤回了一条消息", "拍了拍", "以上是", "消息记录", "开启了朋友验证"]


@dataclass
class WxMessage:
    ts: int                 # unix 秒
    date: str               # "2026-08-04"
    time_str: str           # "2026-08-04 16:10:08"
    sender: str             # 昵称
    kind: str               # text | image | video | file | link | system | ...
    body: str = ""          # 文本内容（非文本消息为空，但保留类型标记）


@dataclass
class WxChat:
    display_name: str
    username: str
    is_group: bool
    exported_at: str = ""
    message_count: int = 0
    messages: List[WxMessage] = field(default_factory=list)


def _clean(s: str) -> str:
    """去掉 HTML 标签并反转义，得到纯文本。"""
    s = re.sub(r"<[^>]+>", "", s)
    return ihtml.unescape(s).strip()


def read_chat(zf: zipfile.ZipFile, meta_path: str, page_paths: List[str]) -> WxChat:
    """给定一个会话的 meta.json 路径 + 所有 page-*.js 路径，返回 WxChat。"""
    meta = json.loads(zf.read(meta_path).decode("utf-8"))
    chat = WxChat(
        display_name=meta.get("displayName", ""),
        username=meta.get("username", ""),
        is_group=bool(meta.get("isGroup", False)),
        exported_at=meta.get("exportedAt", ""),
        message_count=int(meta.get("messageCount", 0)),
    )

    for page in sorted(page_paths):
        try:
            data = zf.read(page).decode("utf-8", errors="replace")
        except Exception:
            continue
        _parse_page(chat, data)
    return chat


def _parse_page(chat: WxChat, data: str) -> None:
    """解析消息，追加进 chat.messages。
    兼容两种导出格式：旧版 page-*.js(`const html=...` 包裹) 与新版 messages.html(直接就是 HTML)。
    """
    # 取出 const html = "..." 的字符串原文（旧格式）；新版 messages.html 直接是 HTML，走兜底
    m = re.search(r'const html = "(.*?)";', data, re.S)
    if m:
        try:
            page_html = json.loads('"' + m.group(1) + '"')
        except Exception:
            page_html = m.group(1)  # 兜底：原样用
    else:
        # 新版 messages.html：body 里就是完整 HTML，直接解析
        page_html = data
        # 去掉 <body>...</body> 之外的 head/style/script，保留消息主体
        bm = re.search(r'<body[^>]*>(.*?)</body>', page_html, re.S)
        if bm:
            page_html = bm.group(1)
        # 去掉残留的 <script>...</script> / <style>...</style>（可能混在 body 里）
        page_html = re.sub(r'<script[^>]*>.*?</script>', '', page_html, flags=re.S)
        page_html = re.sub(r'<style[^>]*>.*?</style>', '', page_html, flags=re.S)

    # 按消息 div 切分（lookahead，保留分隔符）
    blocks = re.split(
        r'(?=<div class="mb-6"[^>]*data-wce-create-time)', page_html
    )
    for blk in blocks:
        if "data-wce-create-time" not in blk:
            continue
        # 时间戳 & 渲染类型
        ts_m = re.search(r'data-wce-create-time="([0-9]+)"', blk)
        ttl = re.search(r'title="([^"]+)"', blk)
        rt = re.search(r'data-render-type="([^"]+)"', blk)
        ts = int(ts_m.group(1)) if ts_m else 0
        time_str = ttl.group(1) if ttl else ""
        date = time_str[:10]
        kind = rt.group(1) if rt else "text"

        # 发送者：text-left(收) / text-right(发)
        sm = re.search(r'text-(?:left|right)">([^<]+?)</div>', blk)
        sender = _clean(sm.group(1)) if sm else "(系统)"

        # 正文：msg-bubble
        bm = re.search(
            r'class="[^"]*msg-bubble[^"]*">(.*?)</div>\s*</div>\s*</div>\s*</div>',
            blk, re.S,
        )
        body = _clean(bm.group(1)) if bm else _clean(blk)

        # 丢弃系统/加入/撤回噪音；非文本消息保留类型标记、正文可为空
        if kind in TEXT_KINDS:
            if not body:
                continue
            if body == sender or body.startswith(sender[:4]):
                continue
            if any(mark in body for mark in _SYSTEM_MARKS):
                continue
        elif kind in ("system",):
            continue

        chat.messages.append(WxMessage(
            ts=ts, date=date, time_str=time_str,
            sender=sender or "(匿名)", kind=kind, body=body,
        ))


def load_export(zip_path: str, max_chats: Optional[int] = None) -> List[WxChat]:
    """从整个导出 zip 加载所有会话。返回 WxChat 列表。"""
    zf = zipfile.ZipFile(zip_path)
    conv_root = "conversations/"
    # 收集每个会话的 meta.json + page
    chats_map = {}
    for n in zf.namelist():
        if not n.startswith(conv_root):
            continue
        parts = n.split("/")
        if len(parts) < 3:
            continue
        conv = parts[1]
        if conv.endswith(".js"):
            continue
        chats_map.setdefault(conv, {"meta": None, "pages": []})
        if n.endswith("meta.json"):
            chats_map[conv]["meta"] = n
        elif n.endswith("messages.html"):
            # 新版导出：单文件 messages.html 含全部消息
            chats_map[conv]["pages"].append(n)
        elif "pages/" in n and n.endswith(".js"):
            chats_map[conv]["pages"].append(n)

    chats = []
    for conv, info in chats_map.items():
        if not info["meta"] or not info["pages"]:
            continue
        chat = read_chat(zf, info["meta"], info["pages"])
        chats.append(chat)
        if max_chats and len(chats) >= max_chats:
            break
    return chats


def transcripts(chat: WxChat) -> List[str]:
    """生成本工具内部用的纯文本行（AI 提炼时喂给模型用）。"""
    out = []
    for ms in chat.messages:
        tag = {"image": "[图]", "video": "[视频]", "file": "[文件]",
               "link": "[链接]", "emoji": ""}.get(ms.kind, "")
        out.append(f"[{ms.time_str}] {ms.sender}: {tag}{ms.body}")
    return out

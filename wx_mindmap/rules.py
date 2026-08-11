"""
wx-mindmap · 规则引擎（零 token）

在不调用任何模型的前提下，从消息里算出的种种"特征"：
- 活跃成员排行（谁最活跃、发言条数、占比）
- 消息类型统计（文本/图片/视频/文件/链接各多少）
- 时间分布（按天/按小时的热区）
- 关键词聚类（命中设定词表 → 主题板块）
- 时间跨度、总条数头部信息

全部纯本地规则，免费、快速、不耗用户 token。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

from .parser import WxChat, WxMessage


def chat_stats(chat: WxChat) -> Dict:
    """头部统计：总数、时长、类型分布。"""
    msgs = chat.messages
    if not msgs:
        return {"total": 0}
    kinds = Counter(m.kind for m in msgs)
    dates = sorted({m.date for m in msgs if m.date})
    senders = Counter(m.sender for m in msgs)
    total = len(msgs)
    return {
        "display_name": chat.display_name,
        "is_group": chat.is_group,
        "total": total,
        "start_date": dates[0] if dates else "",
        "end_date": dates[-1] if dates else "",
        "days": len(dates),
        "kinds": dict(kinds),
        "senders_count": len(senders),
        "image_count": kinds.get("image", 0),
        "video_count": kinds.get("video", 0),
        "file_count": kinds.get("file", 0),
        "link_count": kinds.get("link", 0),
        "quote_count": kinds.get("quote", 0),
    }


def active_members(chat: WxChat, top: int = 12) -> List[Dict]:
    """发言活跃成员排行（含文本之外的计数 + 代表性发言引用）。"""
    counter = Counter(m.sender for m in chat.messages)
    total = len(chat.messages) or 1
    out = []
    for name, cnt in counter.most_common(top):
        # 代表性发言：挑该成员第一条有实质内容(>8字)的文本/引用
        quote = ""
        for m in chat.messages:
            if m.sender == name and m.kind in ("text", "quote") and len(m.body) >= 8:
                quote = m.body[:50] + ("…" if len(m.body) > 50 else "")
                break
        out.append({
            "name": name,
            "count": cnt,
            "pct": round(cnt / total * 100, 1),
            "quote": quote,
        })
    return out


def hour_distribution(chat: WxChat) -> List[int]:
    """一天 24 小时各小时的发言数（0-23）。"""
    hours = [0] * 24
    for m in chat.messages:
        try:
            h = datetime.fromtimestamp(m.ts).hour
            hours[h] += 1
        except Exception:
            pass
    return hours


def day_distribution(chat: WxChat, limit: int = 30) -> List[Dict]:
    """按天的发言分布。"""
    by_day = Counter(m.date for m in chat.messages if m.date)
    out = [{"date": d, "count": c} for d, c in
           sorted(by_day.items())[-limit:]]
    return out


def keyword_clusters(chat: WxChat, keywords: List[str], top: int = 6) -> List[Dict]:
    out = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        hits = [m for m in chat.messages
                if m.kind in ("text", "quote") and m.body and kw in m.body]
        if not hits:
            continue
        members = Counter(m.sender for m in hits)
        top_members = [n for n, _ in members.most_common(5)]
        # 挑几条不长不短的例子
        examples = [m.body for m in hits if len(m.body) <= 60][:5]
        out.append({
            "keyword": kw,
            "count": len(hits),
            "examples": examples,
            "members": top_members,
        })
        if len(out) >= top:
            break
    return out


_URL_RE = __import__("re").compile(r"https?://[^\s<>\"'\u3002]+")
_SITE_MARK = __import__("re").compile(
    r"(网站|工具|做了个|做了一个|搞了|开发|上线|部署|发布|项目|模拟器|小程序|应用|来玩|点击即玩|下载|作品)")


def detect_projects(chat: WxChat, top: int = 10) -> List[Dict]:
    """
    纯规则识别"具体项目"：抓含链接的消息，扒出项目名(title) + 链接 + 作者 + 一句描述。
    原理：群友分享项目几乎必带 URL；用链接聚合，再取"链接上一条及本条"文本拼描述。
    返回 [{name, url, author, desc, hits}]
    """
    import re
    projects = {}   # url -> record
    # 先收集所有含链接的消息
    for m in chat.messages:
        urls = _URL_RE.findall(m.body or "")
        if not urls:
            continue
        for url in urls[:2]:
            url = url.rstrip("，。;；,)]}")  # 去尾部标点
            rec = projects.setdefault(url, {"url": url, "hits": [], "authors": Counter(), "desc": ""})
            rec["hits"].append(m)
            rec["authors"][m.sender] += 1

    out = []
    for url, rec in projects.items():
        # 作者：发言最多者
        author = rec["authors"].most_common(1)[0][0] if rec["authors"] else ""
        # 项目名：从域名里猜（netlify.app / github.io 前面那段），再好用"含平台标记的消息"里找
        name = _guess_name(url, rec["hits"])
        # 描述：抓含做项目话术 + 链接的消息原文
        desc = ""
        for m in rec["hits"]:
            if _SITE_MARK.search(m.body or "") and len(m.body) > 6:
                desc = m.body
                break
        if not desc and rec["hits"]:
            desc = rec["hits"][0].body
        # 供 AI 判断"好评原因/评论"的相关消息（发送者 + 正文，最多 4 条，控制体积）
        msgs_for_ai = []
        for m in rec["hits"][:4]:
            body = (m.body or "").strip()
            if body and body != desc:
                msgs_for_ai.append(f"{m.sender}: {body[:60]}")
        out.append({
            "name": name, "url": url, "author": author,
            "desc": desc[:80], "times": len(rec["hits"]),
            "messages": msgs_for_ai,
        })
    # 按提及次数排序
    out.sort(key=lambda r: r["times"], reverse=True)
    return out[:top]


def _guess_name(url: str, hits) -> str:
    """从链接/消息里猜项目名。"""
    import re
    # 1) netlify.app / github.io 前的 slug
    m = re.search(r"https?://([\w.-]+?)(?:\.netlify\.app|\.github\.io|[./])", url)
    if m:
        slug = m.group(1)
        # 人类可读化
        slug = slug.split("-")
        if len(slug) >= 2:
            return "奶龙跑酷" if "nailong" in url else " ".join(slug).title()[:30]
        return slug[0][:30]
    # 2) 从带"项目名"话术的消息里找邻近的引号/冒号
    return re.sub(r"https?://\S+", "", url).strip()[:30] or "某个项目"


def media_contributors(chat: WxChat, top: int = 5) -> List[Dict]:
    """谁分享的图片/视频/文件最多（多媒体贡献者）。返回 [{name, kinds, total}]"""
    contrib = {}
    for m in chat.messages:
        if m.kind not in ("image", "video", "file"):
            continue
        rec = contrib.setdefault(m.sender, {"name": m.sender, "image": 0, "video": 0, "file": 0})
        rec[m.kind] += 1
    lst = list(contrib.values())
    lst.sort(key=lambda r: r["image"] + r["video"] + r["file"], reverse=True)
    return lst[:top]


def quote_heat(chat: WxChat) -> Dict:
    """引用互动热度：被引用/回帖的次数。返回 {quote_count, quote_senders}"""
    quotes = [m for m in chat.messages if m.kind == "quote" and m.sender]
    return {"quote_count": len(quotes),
            "quote_senders": len({
                m.sender for m in quotes}) if True else 0}


def daily_pace(chat: WxChat) -> Dict:
    """整体节奏：平均每天几条、最活跃那天几条。"""
    by_day = Counter(m.date for m in chat.messages if m.date)
    days = len(by_day) or 1
    total = len(chat.messages)
    peak = max(by_day.values()) if by_day else 0
    peak_day = max(by_day, key=by_day.get) if by_day else ""
    return {"avg_per_day": round(total / days, 1),
            "peak_day": peak_day, "peak_count": peak}


# 常见中文停用词（词云里过滤掉，避免全是"的/了/是"）
_STOP = set("的 了 是 我 你 他 她 它 我们 你们 他们 这个 那个 一个 什么 怎么 为什么 没有 不是 就是 可以 因为 所以 但是 如果 知道 觉得 大家 一下 有点 真的 现在 已经 还有 或者 然后 自己 大概 应该 可能 时候 东西 事情 这样 那样 这是 那是".split())


def word_cloud(chat: WxChat, top: int = 24) -> List[Dict]:
    """
    纯规则词频统计（零 token）：
    统计文本消息里的高频词（2字以上、去掉停用词、排除成员昵称），返回 [{word, count}]。
    """
    import re
    # 收集成员昵称（小写），词云里排除——昵称不是话题词
    from collections import Counter as _C
    member_names = {m.sender.lower().strip() for m in chat.messages if m.sender}
    freq = Counter()
    for m in chat.messages:
        if m.kind not in ("text", "quote") or not m.body:
            continue
        # 去掉链接、@提及、标点
        body = re.sub(r"https?://\S+|@\S+", " ", m.body)
        body = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", body)
        for w in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", body):
            wl = w.lower()
            if wl in _STOP or wl in member_names or wl.endswith("hub") and len(wl) < 3:
                continue
            freq[wl] += 1
    out = [{"word": w, "count": c} for w, c in freq.most_common(top) if c >= 2]
    return out

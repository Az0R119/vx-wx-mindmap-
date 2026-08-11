"""
wx-mindmap · AI 提炼模块（通用多模型适配器）

对标现在 agent 团队的做法：用户填「API 地址 + Key + 模型名」就能接任意
OpenAI 兼容服务 —— DeepSeek / 豆包 / 通义 / Kimi / 本地 Ollama 等全兼容。
不限制用户的 AI 提供商。

- 文字提炼：3 条精华 / 观点分歧 / 行动项（读取 zip 里的文字消息）
- 视觉描述：把图片/视频帧发给你选的视觉模型，让"看内容"也成为可能
任何失败一律返回空（上层降级为纯本地规则版），绝不崩、绝不泄露 key。
"""
from __future__ import annotations

import json
import base64
import urllib.request
import urllib.error
from typing import Dict, List, Optional


DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
# 常用视觉模型提示（用户可任意改）
VISION_MODEL_HINT = "如 DeepSeek 无视觉请填：Doubao-vision / qwen-vl-plus / kimi-vl 等"


def _call_chat(messages: List[Dict], api_key: str, base: str, model: str,
               timeout: int = 120) -> str:
    """调任意 OpenAI 兼容的 chat/completions（支持多模态 content 数组）。"""
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        # 不设 max_tokens —— 让模型用默认上限，避免输出被截断
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------- 文字提炼
# 把"生成思维导图的模板感觉"写成 AI 可执行的风格指令（用户启用 API 时生效）
MINDMAP_STYLE = """请按以下风格组织要点，让思维导图精致耐看：
1. 每条要点前带一个贴合内容的 emoji（如 🚀💰🧠🔧🎬），不要所有条目用同一个。
2. 对重要要点，把最核心的 1-3 个关键词用 <b>加粗</b> 标出（对应模板的"关键词 emphasis"）。
3. 区分重要度：RARELY 用"【重要】"标注最关键、影响最大的 1-2 条；其余为常规。这会在图上显示成红/蓝不同高亮。
4. 语言简洁、口语化、像群聊里总结的语气，别写成论文。
5. 不要编造聊天里没有的内容，仅基于给的材料概括。"""

_PROMPT_MAP = {
    "essence": (
        "以下是某微信群的部分聊天记录。请提炼出最值得关注的 3 条核心信息/结论，"
        "每条一句话。\n"
        + MINDMAP_STYLE + "\n\n"
        "直接输出 3 条，用编号 1. 2. 3. 列出。\n\n"),
    "disputes": (
        "以下是某微信群的部分聊天记录。请找出群里观点对立/有分歧的话题点，"
        "每点一句话（若没有分歧请只输出“无明显分歧”）。\n"
        + MINDMAP_STYLE + "\n\n"),
    "actions": (
        "以下是某微信群的部分聊天记录。请找出大家提到的待办、约定、行动项，"
        "每项一句话（若没有请只输出“无明显行动项”）。\n"
        + MINDMAP_STYLE + "\n\n"),
}


def summarize_text(transcript: List[str], mode: str, api_key: str,
                   base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL) -> List[str]:
    """文字提炼。mode: essence/disputes/actions。失败返回 []。"""
    if not api_key or mode not in _PROMPT_MAP:
        return []
    lines = transcript
    if len(lines) > 400:
        lines = lines[:400]
    messages = [
        {"role": "user",
         "content": _PROMPT_MAP[mode] + "\n".join(lines)}
    ]
    try:
        raw = _call_chat(messages, api_key, base, model)
    except Exception:
        return []
    return _parse_items(raw)


def _parse_items(raw: str) -> List[str]:
    items = []
    for ln in raw.splitlines():
        ln = ln.strip().lstrip("1234567890.、 -")
        if ln and ln != "无" and "无明显" not in ln and len(ln) < 200:
            items.append(ln)
        if len(items) >= 5:
            break
    return items


# ---------------------------------------------------------------- 视觉描述
def describe_image(image_path: str, api_key: str,
                   base: str, model: str,
                   question: str = "简要描述这张图的内容，1-2 句话。") -> str:
    """把一张本地图片发给视觉模型，返回文字描述。成功返回描述，失败返回 ''。"""
    if not api_key:
        return ""
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ],
    }]
    try:
        return _call_chat(messages, api_key, base, model)
    except Exception:
        return ""


# 兼容旧调用名
def summarize(transcript, mode, api_key, base=DEFAULT_BASE, model=DEFAULT_MODEL):
    return summarize_text(transcript, mode, api_key, base, model)


def enrich_projects_reviews(projects: List[Dict], api_key: str,
                            base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL) -> Dict:
    if not api_key or not projects:
        return {}
    # 把项目 + 相关消息压缩成一段喂给模型
    lines = []
    for p in projects[:10]:
        name = p.get("name", "项目")
        author = p.get("author", "未知")
        msgs = p.get("messages", []) or []
        snippet = "；".join(msgs[:3]) if msgs else (p.get("desc", "") or "")[:50]
        if not snippet:
            snippet = "（无可见讨论）"
        lines.append(f"- {name}（作者:{author}）讨论:{snippet}")
    block = "\n".join(lines)
    prompt = (
        "以下是某微信群里被提到的项目及其相关讨论。请对每个项目给出：\n"
        "1. why_good：一句话说明它为什么好/被关注（根据讨论推断；若无明显好评写'群内有提及'）\n"
        "2. comments：1-2 条可能的评价短句（模仿群里语气）\n"
        "严格按 JSON 数组输出，形如 [{\"name\":\"项目名\",\"why_good\":\"...\",\"comments\":[\"...\"]}]\n"
        "只输出 JSON，不要多余解释。\n\n"
        f"{block}"
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        raw = _call_chat(messages, api_key, base, model, timeout=120)
    except Exception:
        return {}
    # 解析 JSON（容错：截取 [ ] 之间的部分）
    import json as _json
    import re as _re
    m = _re.search(r"\[.*\]", raw, _re.S)
    if not m:
        return {}
    try:
        arr = _json.loads(m.group(0))
    except Exception:
        return {}
    result = {}
    for item in arr if isinstance(arr, list) else []:
        if isinstance(item, dict) and item.get("name"):
            result[item["name"]] = {
                "good": str(item.get("why_good", "") or ""),
                "comments": [c for c in item.get("comments", []) if c][:3],
            }
    return result


# ---------------------------------------------------------------- AI 版结构生成（挣脱规则，prompt 驱动）
# AI 版灵魂 prompt：把最早模板（《依门2030AI群思维导图》九宫格项目 / 支线结构 / 评论互动 / emoji / 重要度）的
# "生成感觉" 写成 AI 可执行的指令。用户启用 API 时，AI 读消息自己决定板块结构，不走死规则。
AI_PAGE_STYLE = """生成一个深色科技风的微信群聊「思维导图」总结页，把群聊精华整理成一个可点击收放的网页。

顶部有四个数据小徽章：📝 条消息 · 👥 位群友 · 📅 天跨度 · 🚀 项目。

页面板块（注意：🚀 群友项目摆在整个导图最上面，最醒目）：
  🚀 群友做的项目（第一块，最靠上）
  🤖 AI·计算机·科技
  🔧 问题 & 解决方案
  💡 群友的奇思妙想
  👥 活跃群友画像
  📊 数据洞察

视觉/交互亮点：
- 配色分级：每块一个主题色（紫、青、绿、橙、红、蓝），配图标和渐变文字标题
- 思维导图树状结构：子节点用竖线+横线连接
- 智能标签：每个节点带彩色小标签（项目/人物/技术/想法/问题/方案/金融/AI）
- 重要程度仅用颜色区分：🔴红框=重要，🟠橙框=中等，🔵蓝框=常规（不要任何中文"重要/中等"字样）
- 评论区还原：项目卡片下面带圆形头像的群友原话评论
- 可折叠：点标题栏展开/收起（▸ 旋转）

【表情要求】每条要点配一个与之内容高度相关的 emoji（讲游戏就🎮、讲钱就💰、讲模型就🤖、讲想法就💡、讲问题就⚠️…），禁止所有要点用同一个表情。

【项目要求】每个项目要给出：作者、3-6 条"饱受好评的理由"（每条用 <理由关键词> 加粗 + 简短说明）、2-3 条评论区群友原话好评。

【活跃群友画像要求】"活跃群友画像"板块必须充实：按贡献度分"核心贡献者"和"积极参与者"两组，每个成员给出：头像 emoji、人物标签（如"技术大佬/段子手/投资专家/项目作者"）、以及一句描述 TA 是谁/做了什么（对标免费版的画像深度，不能只罗列名字）。

内容要充实、不空屏、不编造。"""


def ai_generate_structure(transcript: List[str], api_key: str,
                          base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL,
                          known_projects: List[Dict] = None) -> Dict:
    """
    AI 版核心：让 AI 读消息，返回一份完整的板块结构（挣脱死规则，prompt 驱动）。
    known_projects：免费版规则抓到的项目/工具（带链接），AI 必须把它们全部列入项目板块，
    确保 AI 版项目覆盖面 ≥ 免费版（取长补短，不遗漏）。
    返回 {
      "title": 一句话概括这群在聊什么,
      "sections": [ { "icon", "title", "points": [{"text","take"}] } ],
      "projects": [ {"name","author","why_good","comments"[...]} ],
    }
    任何失败返回 {}（上层降级为免费规则版，不崩）。
    """
    if not api_key:
        return {}
    lines = transcript
    if len(lines) > 300:
        lines = lines[:300]
    schema_example = (
        '{"title":"整群一句话概括",'
        '"sections":[{"icon":"🚀","title":"群友做的项目","accent":"#a78bfa",'
        '"subs":[{"title":"小板块标题","points":[{"text":"要点","emoji":"🎮","level":1,"tag":"项目"}]}]}],'
        '"projects":[{"name":"项目名","author":"作者",'
        '"reasons":["饱受好评理由1","饱受好评理由2","饱受好评理由3"],'
        '"comments":["群友原话好评1","好评2"]}]}'
    )
    # 已知工具清单：免费版规则抓的项目，AI 必须全覆盖
    known_block = ""
    if known_projects:
        lines_list = []
        for p in known_projects[:20]:
            nm = str(p.get("name", "?"))
            au = str(p.get("author", "")) or "?"
            ur = str(p.get("url", "")) or ""
            lines_list.append("- " + nm + " (作者: " + au + ") " + ur)
        known_block = "【已知工具清单（必须全部列入 projects，一个都不能漏）】\n" + "\n".join(lines_list) + "\n\n"

    prompt = (
        "以下是某微信群的聊天记录。请按给定风格产出思维导图内容。\n"
        + AI_PAGE_STYLE + "\n\n"
        "严格返回 JSON，结构如下（不要多余文字）：\n"
        + schema_example + "\n"
        "【必读】sections 仍 6 个，但第一个必须是🚀群友做的项目/工具(最靠上)；其余5个按序。"
        "每条 points 必须带 emoji 字段(与该要点内容相关,不可全同)；points.level 用 1(红)/2(橙)/3(蓝)；"
        "points.tag 用：项目/人物/技术/想法/问题/方案/金融/AI 之一。"
        "projects[] 必须完整覆盖下方【已知工具清单】里的每一个，一个都不能漏；"
        "对每个工具给出 author、3-6 条饱受好评理由(reasons)、2-3 条群友原话好评(comments)。"
        "若已知工具清单为空，则从聊天记录里自己找项目。\n\n"
        + known_block
        + "聊天记录：\n" + "\n".join(lines)
    )
    messages = [{"role": "user", "content": prompt}]
    import os as _os, tempfile as _tf
    _dbg = _os.path.join(_tf.gettempdir(), "wxmindmap_ai_debug.log")
    try:
        raw = _call_chat(messages, api_key, base, model, timeout=180)
        # 记录 AI 原始返回（完整不截断），方便排查
        with open(_dbg, "w", encoding="utf-8") as f:
            f.write("=== AI 原始返回 ===\n" + raw)
        return _parse_structure(raw)
    except Exception as e:
        with open(_dbg, "w", encoding="utf-8") as f:
            import traceback as _tb
            f.write("=== AI 调用异常 ===\n" + repr(e) + "\n" + _tb.format_exc())
        return {}


def _parse_structure(raw: str) -> Dict:
    """容错解析 AI 返回的大板块(含小板块) JSON。"""
    import json as _json, re as _re, os as _os, tempfile as _tf
    _dbg = _os.path.join(_tf.gettempdir(), "wxmindmap_ai_debug.log")
    if not raw or not raw.strip():
        return {}
    text = _re.sub(r"```(?:json)?", "", raw).strip()
    result = {"title": "", "sections": [], "projects": []}
    data = None
    err = ""
    # 1) 整体加载
    try:
        data = _json.loads(text)
    except Exception as e1:
        # 2) 去掉围栏, 剥离多余说明, 找第一个{到匹配} 
        m = _re.search(r"\{.*\}", text, _re.S)
        if m:
            try:
                data = _json.loads(m.group(0))
            except Exception as e2:
                err = f"整体:{e1} | 正则:{e2}"
        else:
            err = f"整体:{e1} | 无大括号"
    if not isinstance(data, dict):
        with open(_dbg, "a", encoding="utf-8") as f:
            f.write("\n\n[解析失败记录] " + err + "\n已解析对象类型:" + str(type(data)))
        return result
    # 成功 — 清一条成功日志
    with open(_dbg, "a", encoding="utf-8") as f:
        f.write("\n[解析成功] sections=" + str(len(data.get("sections", []) or [])) +
                " projects=" + str(len(data.get("projects", []) or [])))
    result["title"] = str(data.get("title", ""))
    # 兼容两套 schema：旧的 sections[{id,title,points}] 与新的 sections[{icon,title,subs[{title,points}]}]
    sections = []
    for s in data.get("sections", []) or []:
        if not isinstance(s, dict):
            continue
        icon = str(s.get("icon", "•"))
        stitle = str(s.get("title", ""))
        accent = str(s.get("accent", "#a78bfa"))
        subs = s.get("subs")
        if isinstance(subs, list) and subs:
            sub_list = []
            for sb in subs:
                if not isinstance(sb, dict):
                    continue
                points = []
                for p in sb.get("points", []) or []:
                    if isinstance(p, dict) and p.get("text"):
                        points.append({
                            "text": str(p["text"]),
                            "emoji": str(p.get("emoji", "")),
                            "level": p.get("level", 1 if p.get("important") else 3),
                            "tag": str(p.get("tag", "")),
                        })
                sub_list.append({"title": str(sb.get("title", "")), "points": points})
            sections.append({"icon": icon, "title": stitle, "accent": accent, "subs": sub_list})
        else:
            points = []
            for p in s.get("points", []) or []:
                if isinstance(p, dict) and p.get("text"):
                    points.append({
                        "text": str(p["text"]),
                        "level": p.get("level", 1 if p.get("important") else 3),
                        "tag": str(p.get("tag", "")),
                    })
            sections.append({"icon": icon, "title": stitle, "accent": accent,
                             "subs": [{"title": "", "points": points}]})
    projects = []
    for p in data.get("projects", []) or []:
        if not isinstance(p, dict):
            continue
        # reasons（多条好评）兼容旧的 why_good（单条）
        reasons = [str(r) for r in (p.get("reasons") or []) if r]
        if not reasons and p.get("why_good"):
            reasons = [str(p.get("why_good"))]
        projects.append({"name": str(p.get("name", "")), "author": str(p.get("author", "")),
                         "reasons": reasons,
                         "comments": [c for c in (p.get("comments") or []) if c][:3]})
    result["sections"] = sections
    result["projects"] = projects
    # —— 强制：标题含"项目/工具/作品"的板块排最前（置顶，不管 AI 返回顺序）——
    proj_secs = []
    others = []
    for s in sections:
        t = s.get("title", "")
        if ("项目" in t) or ("工具" in t) or ("作品" in t) or ("实践" in t):
            proj_secs.append(s)
        else:
            others.append(s)
    result["sections"] = proj_secs + others
    return result

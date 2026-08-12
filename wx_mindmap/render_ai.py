"""
wx-mindmap · AI 版独立渲染
==========================
这是跟免费版（render.py）完全独立的渲染代码 —— 用户启用 API 且 AI 成功生成结构后，
走这一个模板。清爽浅色 + 渐变现代信息图风，板块由 AI 语义驱动，不是死规则计数。

与免费版是两个文件、两种生图逻辑、两套 CSS，彻底分开。
"""
from __future__ import annotations

import html as _html
from typing import Dict, List


def _esc(s) -> str:
    return _html.escape(str(s))


def _render_point(p: Dict) -> str:
    """一条要点：重要度三档(红/橙/蓝) + <关键词>加粗 + 智能标签。无中文干扰字。"""
    text = p.get("text", "")
    level = p.get("level", 1 if p.get("important") else 3)
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 3
    if level not in (1, 2, 3):
        level = 3
    safe = _esc(text)
    import re
    safe = re.sub(r"&lt;([^&]+)&gt;", r"<b>\1</b>", safe)
    # 智能标签
    tag = p.get("tag", "")
    tag_html = ""
    if tag:
        tag_html = f'<span class="tagx tag-{_esc(tag)}">{_esc(tag)}</span>'
    # 用 AI 配的内容相关 emoji；若平台不含则退回重要度颜色图标
    emoji = p.get("emoji", "")
    icon = {1: "🔴", 2: "🟠", 3: "🔵"}.get(level, "🔵") if not emoji else emoji
    return (f'<div class="pt imp-{level}"><span class="pt-ic">{icon}</span>'
            f'<div class="pt-tx">{safe}{tag_html}</div></div>')


def render_ai_page(chat_name: str, ai: Dict, stats: Dict,
                   version_tag="AI版", free_data: Dict = None,
                   qa_base: str = "", qa_model: str = "") -> str:
    """
    AI 版渲染。ai 来自 ai_generate_structure() 的返回。
    stats：chat_stats，用于顶部统计。
    wordcloud：可选词云数据，纯展示不干扰 AI。
    qa_base/qa_model：用于"问 AI"自由输入的 OpenAI 兼容端点（key 用户现场填）。
    """
    ai = ai or {}
    title = ai.get("title") or f"{chat_name} 群聊分析"
    sections = ai.get("sections", []) or []
    projects = ai.get("projects", []) or []
    free_data = free_data or {}
    wordcloud = free_data.get("wordcloud") or []
    cloud_html = _render_ai_cloud(wordcloud) if wordcloud else ""
    # 免费版也有的硬数据板块：活跃度 + 猜您想问
    active_html = _render_ai_active(free_data.get("active_members") or [])
    faq_html = _render_ai_faq(free_data)
    # "问 AI"自由输入区块（base/model 嵌入，key 现场填）
    qa_html = _render_ai_qa(qa_base or "", qa_model or "")

    # 顶部四个数据小徽章（stat 数据，非 AI 生成）
    n_projects = len(projects)
    stat_html = (
        f'<div class="stat"><div class="sn">{stats.get("total",0)}</div>'
        f'<div class="sl">条消息</div></div>'
        f'<div class="stat"><div class="sn">{stats.get("senders_count",0)}</div>'
        f'<div class="sl">位群友</div></div>'
        f'<div class="stat"><div class="sn">{stats.get("days",0)}</div>'
        f'<div class="sl">天跨度</div></div>'
        f'<div class="stat"><div class="sn">{n_projects}</div>'
        f'<div class="sl">项目</div></div>'
    )

    # 板块（AI 语义板块：大板块 → 小板块 → 要点 三级，可折叠）
    # 跳过标题含"项目/工具/作品"的板块——这些由下面更全的"🚀群友项目"九宫格独立展示，避免重复
    secs = ""
    shown = 0
    for s in sections:
        st = s.get("title", "")
        if ("项目" in st) or ("工具" in st) or ("作品" in st) or ("实践" in st):
            continue
        subs_html = ""
        for sb in s.get("subs", []) or []:
            sub_title = sb.get("title", "")
            pts = "".join(_render_point(p) for p in sb.get("points", []) if p.get("text"))
            sub_head = (f'<div class="sub-h" style="border-color:{s.get("accent","#a78bfa")};">'
                        f'{_esc(sub_title)}</div>' if sub_title else '')
            subs_html += f'<div class="sub-b">{sub_head}{pts}</div>'
        secs += (f'<details class="sec" open><summary class="sec-h">'
                 f'<span class="sec-i">{_esc(s.get("icon","•"))}</span>'
                 f'<h3>{_esc(st)}</h3>'
                 f'<span class="arrow">▸</span></summary>'
                 f'<div class="sec-b">{subs_html}</div></details>')
        shown += 1
    # 如果没有非项目板块，则空（项目板块已被九宫格覆盖）
    if not shown and not projects:
        secs = '<details class="sec" open><summary class="sec-h"><span class="sec-i">🤖</span><h3>AI 未能生成板块</h3><span class="arrow">▸</span></summary><div class="sec-b"><div class="pt imp-3"><span class="pt-ic">🔵</span><div class="pt-tx">AI 未能生成板块，请检查 key 或稍后再试。</div></div></div></details>'

    # 项目九宫格（AI 写的好评/评论）
    if projects:
        cards = ""
        for p in projects:
            comments = "".join(
                f'<div class="cmt-i"><span class="cmt-a">💬</span>'
                f'<span class="cmt-t">{_esc(c)}</span></div>'
                for c in p.get("comments", [])[:3])
            author = f'<span class="p-auth">{_esc(p.get("author",""))}</span>' if p.get("author") else ""
            # 多条饱受好评理由
            reasons = p.get("reasons", []) or []
            good_html = ""
            if reasons:
                items = "".join(
                    f'<li>👍 <span class="p-good-i">{_esc(r)}</span></li>' for r in reasons[:6])
                good_html = (f'<div class="p-good"><strong>饱受好评原因：</strong>'
                             f'<ul class="p-good-list">{items}</ul></div>')
            cards += (f'<div class="pcard"><div class="p-top">🚀 <span class="p-name">'
                      f'{_esc(p.get("name","项目"))}</span>{author}</div>'
                      f'{good_html}'
                      f'<div class="p-cmts">{comments}</div></div>')
        proj_html = (f'<div class="ra-sec-t"><span>🚀 群友项目</span></div>'
                     f'<div class="pgrid">{cards}</div>')
    else:
        proj_html = ""

    # —— AI 版纯由 AI 产出，不注入本地规则数据（活跃/词云/时间支撑区全部由 AI 在 6 大块里决定）——

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(chat_name)} · AI 版思维导图</title>
<style>
  * {{margin:0;padding:0;box-sizing:border-box;}}
  body {{font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    background:#0a0e1a;color:#dbe4ff;min-height:100vh;padding:30px 20px 70px;}}
  .wrap {{max-width:1150px;margin:0 auto;}}

  .hero {{background:linear-gradient(135deg,#1a1030,#2a1a4a 55%,#0e2a4a);border:1px solid #3a2a66;
    border-radius:20px;padding:30px 34px;box-shadow:0 12px 40px rgba(88,60,255,.18);}}
  .hero h1 {{font-size:28px;font-weight:800;background:linear-gradient(90deg,#a78bfa,#22d3ee,#34d399);
    -webkit-background-clip:text;background-clip:text;color:transparent;}}
  .hero .sub {{opacity:.8;margin-top:8px;font-size:14px;color:#a5b8e0;}}
  .hero .tag {{display:inline-block;background:rgba(124,58,237,.15);border:1px solid rgba(167,139,250,.35);
    padding:3px 14px;border-radius:999px;font-size:12px;color:#c4b5fd;margin-top:14px;}}
  .stats {{display:flex;gap:12px;margin-top:20px;flex-wrap:wrap;}}
  .stat {{background:rgba(20,28,48,.6);border:1px solid #2a3a5a;border-radius:12px;padding:10px 20px;
    min-width:86px;text-align:center;}}
  .stat .sn {{font-size:22px;font-weight:800;color:#fff;}}
  .stat .sl {{font-size:11px;opacity:.6;color:#9fb0d8;}}

  .insight {{background:#101629;border:1px solid #2a3a5a;border-left:4px solid #a78bfa;
    border-radius:14px;padding:18px 24px;margin-top:22px;}}
  .insight .it {{font-size:12px;font-weight:700;color:#a78bfa;letter-spacing:.5px;margin-bottom:6px;}}
  .insight .ib {{font-size:16px;font-weight:600;color:#e8eeff;line-height:1.6;}}

  /* 每块主题色 */
  .sec {{background:#101629;border:1px solid #27324d;border-radius:16px;margin-top:18px;
    overflow:hidden;box-shadow:0 6px 24px rgba(0,0,0,.25);}}
  .sec-h {{display:flex;align-items:center;gap:12px;padding:16px 22px;cursor:pointer;border-bottom:1px solid #1e2a44;}}
  .sec-h h3 {{font-size:17px;font-weight:800;}}
  .sec-i {{font-size:22px;}}
  .arrow {{margin-left:auto;color:#7c8aab;transition:.25s;font-size:14px;}}
  .sec[open] .arrow {{transform:rotate(90deg);}}
  .sec-b {{padding:16px 22px 20px;display:flex;flex-direction:column;gap:14px;}}
  .sub-b {{display:flex;flex-direction:column;gap:8px;}}
  .sub-h {{font-size:14px;font-weight:700;padding-left:12px;border-left:3px solid;margin:4px 0 2px;}}

  /* 树状结构：竖线+横线连接 */
  .pt {{display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:10px;
    font-size:14px;line-height:1.6;margin-left:14px;position:relative;}}
  .pt::before {{content:"";position:absolute;left:-14px;top:0;bottom:0;width:2px;background:#2a3a5a;}}
  .pt::after {{content:"";position:absolute;left:-14px;top:18px;width:10px;height:2px;background:#2a3a5a;}}
  .pt .pt-ic {{flex-shrink:0;width:20px;}}
  .pt .pt-tx {{color:#c9d6f2;}}
  .pt-tx b {{color:#e0aaff;font-weight:700;}}

  /* 智能标签 */
  .tagx {{display:inline-block;font-size:10px;padding:1px 7px;border-radius:999px;margin-left:6px;vertical-align:1px;}}
  .tag-project{{background:#7c3aed33;color:#c4b5fd;border:1px solid #7c3aed66}}
  .tag-person{{background:#22d3ee22;color:#67e8f9;border:1px solid #22d3ee55}}
  .tag-tech{{background:#34d39922;color:#6ee7b7;border:1px solid #34d39955}}
  .tag-idea{{background:#f59e0b22;color:#fbbf24;border:1px solid #f59e0b55}}
  .tag-problem{{background:#f43f5e22;color:#fda4af;border:1px solid #f43f5e55}}
  .tag-solution{{background:#8b5cf622;color:#c4b5fd;border:1px solid #8b5cf655}}
  .tag-finance{{background:#f59e0b22;color:#fbbf24;border:1px solid #f59e0b55}}
  .tag-ai{{background:#ec489922;color:#f9a8d4;border:1px solid #ec489955}}

  /* 重要度：红/橙/蓝 */
  .pt.imp-1 {{background:rgba(244,63,94,.08);border:1px solid #f43f5e;}}
  .pt.imp-1 .pt-tx {{color:#ffc4cf;}}
  .pt-lbl-1 {{margin-left:6px;font-size:9px;padding:1px 6px;border-radius:4px;background:#f43f5e;color:#fff;}}
  .pt.imp-2 {{background:rgba(245,158,11,.06);border:1px solid #f59e0b;}}
  .pt-lbl-2 {{margin-left:6px;font-size:9px;padding:1px 6px;border-radius:4px;background:#f59e0b;color:#111;}}
  .pt.imp-3 {{border:1px solid #3346la;background:rgba(96,165,250,.05);}}
  .pt-lbl-3 {{margin-left:6px;font-size:9px;padding:1px 6px;border-radius:4px;background:#3b82f6;color:#fff;}}

  /* 词云 */
  .scloud {{margin-top:14px;background:#101629;border:1px solid #27324d;border-radius:16px;
    padding:22px;box-shadow:0 6px 24px rgba(0,0,0,.25);}}
  .scloud .t {{font-size:17px;font-weight:800;color:#f1f5ff;margin-bottom:16px;}}
  .cw {{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:6px 14px;min-height:130px;}}
  .cw span {{font-weight:700;}}

  /* 活跃成员卡片 */
  .a-group {{margin-bottom:4px;}}
  .a-gtitle {{font-size:14px;font-weight:700;color:#b388ff;margin:10px 0 8px;padding-left:6px;border-left:3px solid #7c4dff;}}
  .a-gbody {{display:flex;flex-direction:column;gap:8px;}}
  .a-card {{background:#0d1424;border:1px solid #2a3a5a;border-radius:10px;padding:10px 14px;}}
  .a-head {{display:flex;align-items:center;gap:8px;font-size:13px;}}
  .a-medal {{flex-shrink:0;}}
  .m-name {{font-weight:700;color:#f1f5ff;}}
  .a-cnt {{margin-left:auto;color:#9fb0d8;font-size:12px;}}
  .a-quote {{margin-top:6px;background:rgba(124,77,255,.08);border-left:3px solid #7c4dff;
    border-radius:0 8px 8px 0;padding:6px 10px;font-size:12px;color:#c9d6f2;line-height:1.5;}}
  .a-q-t {{color:#b388ff;font-weight:600;}}

  /* 猜您想问 */
  .faq-list {{display:flex;flex-direction:column;gap:8px;}}
  .faq-item-details {{background:#0d1424;border:1px solid #2a3a5a;border-radius:12px;overflow:hidden;}}
  .faq-item-details summary {{display:flex;align-items:center;gap:8px;padding:12px 16px;cursor:pointer;
    font-size:14px;color:#dbe4ff;list-style:none;}}
  .faq-item-details summary::-webkit-details-marker {{display:none;}}
  .faq-item-details .arrow {{transition:.2s;color:#7c8aab;}}
  .faq-item-details[open] .arrow {{transform:rotate(90deg);}}
  .faq-body {{padding:0 16px 14px;color:#9fb0d8;font-size:13px;}}

  /* 问 AI 自由输入 */
  .qa-in {{display:block;width:100%;background:#0d1424;border:1px solid #2a3a5a;border-radius:10px;
    color:#dbe4ff;padding:11px 14px;font-size:14px;margin-bottom:8px;}}
  .qa-in:focus {{outline:none;border-color:#7c4dff;}}
  .qa-keyrow {{display:flex;gap:8px;}}
  .qa-k {{flex:2;}}
  .qa-m {{flex:1;}}
  .qa-b {{flex:2;}}
  .qa-btn {{display:block;width:100%;background:linear-gradient(90deg,#7c4dff,#22d3ee);border:none;
    color:#fff;font-size:15px;font-weight:700;padding:12px;border-radius:10px;cursor:pointer;margin-top:2px;}}
  .qa-btn:disabled {{opacity:.6;cursor:wait;}}
  .qa-ans {{margin-top:10px;background:#0d1424;border:1px solid #2a3a5a;border-left:4px solid #7c4dff;
    border-radius:10px;padding:12px 14px;color:#dbe4ff;font-size:14px;line-height:1.6;white-space:pre-wrap;}}

  .ra-sec-t {{font-size:19px;font-weight:800;margin-top:26px;padding-left:4px;
    background:linear-gradient(90deg,#a78bfa,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent;}}
  .pgrid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin-top:14px;}}
  @media(max-width:680px){{.pgrid{{grid-template-columns:1fr;}}}}
  .pcard {{background:#141b33;border:1px solid #2a3a5a;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.2);}}
  .p-top {{font-size:15px;font-weight:700;color:#f1f5ff;display:flex;align-items:center;gap:8px;flex-wrap:wrap;}}
  .p-auth {{background:rgba(124,58,237,.2);color:#c4b5fd;font-size:11px;padding:2px 9px;border-radius:999px;font-weight:600;}}
  .p-good {{font-size:13px;color:#9fb0d8;margin-top:9px;line-height:1.5;}}
  .p-cmts {{margin-top:12px;border-top:1px dashed #2a3a5a;padding-top:10px;display:flex;flex-direction:column;gap:9px;}}
  .cmt-i {{display:flex;gap:9px;align-items:flex-start;font-size:12px;color:#a5b8e0;}}
  .cmt-a {{width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#a78bfa,#22d3ee);
    display:flex;align-items:center;justify-content:center;font-size:9px;flex-shrink:0;color:#0a0e1a;}}

  .foot {{text-align:center;color:#9ca3af;font-size:11px;margin-top:36px;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>🧠 {_esc(chat_name)}</h1>
    <div class="sub">{_esc(title)}</div>
    <span class="tag">AI 版 · 由 AI 解析生成</span>
    <div class="stats">{stat_html}</div>
  </div>

  <div class="insight">
    <div class="it">✨ AI 核心洞察</div>
    <div class="ib">{_esc(title)}</div>
  </div>

  {proj_html}

  {secs}

  {cloud_html}

  {active_html}

  {faq_html}

  {qa_html}

  <div class="foot">wx-mindmap · AI 版 · 由你配置的模型生成 · 本地处理</div>
</div>
</body>
</html>"""


def _render_ai_support(fd: Dict) -> str:
    """数据支撑区：活跃成员 + 时间热区（规则硬数据，AI 版也保留，不空屏）。"""
    parts = []
    # 活跃成员
    am = fd.get("active_members", []) or []
    if am:
        rows = ""
        mx = (am[0].get("count", 1) or 1)
        for m in am[:8]:
            cnt = m.get("count", 0)
            w = int(cnt / mx * 100) if mx else 0
            rows += (f'<div class="mem-r"><span class="mn">{_esc(m.get("name",""))}</span>'
                     f'<div class="mb"><div class="mf" style="width:{w}%"></div></div>'
                     f'<span class="mc">{cnt}</span></div>')
        parts.append(('    <div class="sup-card"><div class="sup-t">🏆 群内活跃成员</div>'
                      '<div class="mem-bar">' + rows + '</div></div>'))
    # 时间热区
    hours = fd.get("hour_dist", []) or []
    if hours:
        mxh = max(hours) or 1
        cells = "".join(
            f'<div class="hcell" style="height:{int(h/mxh*100)+4}px" title="{i}点 {h}条"></div>'
            for i, h in enumerate(hours))
        parts.append(('    <div class="sup-card"><div class="sup-t">⏰ 各时段活跃度</div>'
                      '<div class="hours">' + cells + '</div></div>'))
    if not parts:
        return ""
    joined = "".join(parts)
    return '    <div class="ra-sec-t"><span>📊 数据一览</span></div><div class="support-c">' + joined + '</div>'


def _render_ai_cloud(words: List[Dict]) -> str:
    """词云：不重复压紧嵌合——每个词出现一次，按词频定字号，用 flex-wrap 让词紧凑铺满、
    嵌合排布（不是中心放射），视觉像经典词云（词与词紧挨、大小分明）。"""
    if not words:
        return ""
    words = sorted(words, key=lambda w: w["count"], reverse=True)[:36]
    mx = max(w["count"] for w in words) or 1
    n = max(1, len(words))
    colors = ["#a78bfa", "#22d3ee", "#34d399", "#fbbf24", "#f87171", "#60a5fa", "#e879f9", "#fdba74"]
    items = []
    for i, w in enumerate(words):
        ratio = w["count"] / mx
        size = 0.9 + ratio * 1.9   # 0.9 ~ 2.8rem, 频率越高越大
        color = colors[i % len(colors)]
        # 轻微旋转微调(不是乱转), 增强"自然堆叠"感
        items.append(
            f'<span class="cw-i" style="font-size:{size:.2f}rem;color:{color};'
            f'padding:2px 6px;display:inline-block;line-height:1.15;">{_esc(w["word"])}</span>')
    joined = "".join(items)
    return ('    <div class="scloud"><div class="t">☁️ 群聊词云</div>'
            '<div class="cw" style="display:flex;flex-wrap:wrap;justify-content:center;'
            'align-items:center;align-content:center;gap:4px 10px;min-height:220px;">' 
            + joined + '</div></div>')


def _render_ai_active(am: List[Dict]) -> str:
    """活跃群友卡片列表（对标免费版）：分 核心主力/积极参与/其他成员 三组，
    每个成员 = 昵称 + 条数/占比 + ta说 气泡。不做柱状图。"""
    if not am:
        return ""
    medals = ["🥇", "🥈", "🥉"]
    groups = [
        ("🏆 核心主力 · 发言最多", am[:3]),
        ("👥 积极参与", am[3:8]),
        ("👥 其他成员", am[8:14]),
    ]
    all_rows = ""
    for gtitle, members in groups:
        if not members:
            continue
        rows = ""
        for i, m in enumerate(members):
            med = medals[i] if gtitle.startswith("🏆") else ("◆" if i < 2 else "·")
            quote_html = ""
            if m.get("quote"):
                quote_html = (f'<div class="a-quote"><span class="a-q-t">ta说：</span>'
                              f'{_esc(m["quote"])}</div>')
            rows += (f'<div class="a-card"><div class="a-head"><span class="a-medal">{med}</span>'
                     f'<span class="m-name">{_esc(m.get("name",""))}</span>'
                     f'<span class="a-cnt">{m.get("count",0)}条 · {m.get("pct",0)}%</span></div>'
                     f'{quote_html}</div>')
        all_rows += (f'<div class="a-group"><div class="a-gtitle">{gtitle}</div>'
                     f'<div class="a-gbody">{rows}</div></div>')
    return ('    <div class="scloud"><div class="t">👥 活跃群友</div>'
            '<div class="a-list">' + all_rows + '</div></div>')


def _render_ai_qa(base: str, model: str) -> str:
    """"问 AI"自由输入区块：用户输入问题 + 填自己的 key → 调 OpenAI 兼容 API 回答。
    base/model 已由用户在选择 provider 时配置，嵌入网页；key 现场填不进 HTML。"""
    if not base:
        return ""
    import html as _h
    b = _h.escape(base)
    m = _h.escape(model or "")
    jscode = r'''
async function askAI(){
  const q=document.getElementById('wmq').value.trim();
  const k=document.getElementById('wmk').value.trim();
  const ans=document.getElementById('wma');
  const btn=document.getElementById('wmbtn');
  if(!q){ans.textContent='请先输入问题';return;}
  if(!k){ans.textContent='请填写你的 API Key';return;}
  btn.disabled=true;btn.textContent='思考中…';ans.textContent='';
  try{
    const url=document.getElementById('wmb').value.replace(/\/+$/,'')+'/chat/completions';
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+k},
      body:JSON.stringify({model:document.getElementById('wmm').value,messages:[{role:'user',content:q}],temperature:0.5})});
    if(!r.ok){const e=await r.text().catch(()=>'');ans.textContent='❌ '+r.status+' '+e.slice(0,150);return;}
    const d=await r.json();
    ans.textContent=(d.choices&&d.choices[0]&&d.choices[0].message&&d.choices[0].message.content)||'（无内容）';
  }catch(e){ans.textContent='❌ 请求失败：'+e.message;}
  btn.disabled=false;btn.textContent='提问';
}
'''
    return (
        '    <div class="scloud"><div class="t">🗣️ 问 AI（自由提问）</div>'
        '<input id="wmq" class="qa-in" placeholder="输入你想问群聊/内容的任何问题…">'
        '<div class="qa-keyrow"><input id="wmk" class="qa-in qa-k" type="password" '
        f'placeholder="你的 API Key（浏览器调用，不保存）"><input id="wmm" class="qa-in qa-m" value="{m}">'
        f'<input id="wmb" class="qa-in qa-b" value="{b}"></div>'
        '<button id="wmbtn" class="qa-btn" onclick="askAI()">提问 🚀</button>'
        '<div id="wma" class="qa-ans"></div>'
        '<script>' + jscode + '</scr' + 'ipt>'
        '</div>'
    )


def _render_ai_faq(fd: Dict) -> str:
    """猜您想问：可点折叠的增量问答（免费版硬数据，AI 版保留）。"""
    items = []
    # Q1 多媒体
    total = fd.get("total")
    img = fd.get("image_count", 0); vid = fd.get("video_count", 0); fl = fd.get("file_count", 0)
    if img or vid:
        items.append(('<div class="faq-item-details"><summary><span class="arrow">▸</span>'
                      '📷 群里发了多少图片/视频？</summary>'
                      f'<div class="faq-body">共 {img} 张图片、{vid} 个视频、{fl} 个文件。</div></div>'))
    # Q2 谁最活跃（已在上方柱状图）
    items.append(('<div class="faq-item-details"><summary><span class="arrow">▸</span>'
                  '🗓 群聊持续多久、平均每天多少条？</summary>'
                  f'<div class="faq-body">共 {fd.get("days",0)} 天、{fd.get("total",0)} 条消息，'
                  f'平均每天约 {fd.get("avg_per_day","?")} 条。</div></div>'))
    if not items:
        return ""
    return ('    <div class="scloud"><div class="t">💬 猜您想问</div>'
            '<div class="faq-list">' + "".join(items) + '</div></div>')

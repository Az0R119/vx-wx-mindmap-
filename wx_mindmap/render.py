"""
wx-mindmap · 排版渲染模块

把规则引擎/AI 提炼的结果，渲染成"上次那种"可折叠深色思维导图 HTML。
沿用已验证的模板手法：深色主题 + 头部 + 大板块(可折叠 details) + 小板块(竖排) + 要点，
也支持浅色/极简主题切换（纯 CSS 变量）。

零 token：纯字符串拼接生成 HTML，不联网。
"""
from __future__ import annotations

import html as ihtml
from typing import Dict, List


# —— 主题色板（CSS 变量组）——
THEMES = {
    "dark": {
        "bg": "#101026", "container": "#1c1c35", "card": "#13132a",
        "card_border": "#3a3a6a", "line": "#2a2a50",
        "t_blue": "#6cb4ff", "t_green": "#5fe0c0", "t_pink": "#d9a6ff",
        "name": "#efe9ff", "body": "#b8b3d6", "link": "#8ab4ff",
        "tag": "#5fe0c0", "quote": "#cdc7ec", "footer": "#8a86ac",
        "imp_hi": "#d85d5d", "imp_lo": "#6cb4ff",
    },
    "light": {
        "bg": "#f4f5fb", "container": "#ffffff", "card": "#ffffff",
        "card_border": "#d9deef", "line": "#e3e8f5",
        "t_blue": "#2272cc", "t_green": "#14a37f", "t_pink": "#8b3fbf",
        "name": "#1c2438", "body": "#4a5570", "link": "#2272cc",
        "tag": "#14a37f", "quote": "#5a6478", "footer": "#9aa2b8",
        "imp_hi": "#d04848", "imp_lo": "#2272cc",
    },
    "minimal": {
        "bg": "#ffffff", "container": "#f7f7f7", "card": "#ffffff",
        "card_border": "#e2e2e2", "line": "#ebebeb",
        "t_blue": "#333333", "t_green": "#111111", "t_pink": "#555555",
        "name": "#000000", "body": "#444444", "link": "#1a5fb4",
        "tag": "#000000", "quote": "#555555", "footer": "#999",
        "imp_hi": "#b00020", "imp_lo": "#1a5fb4",
    },
}


def _esc(s) -> str:
    return ihtml.escape(str(s))


def render_mindmap(chat_name: str, stats: Dict, opts: Dict,
                   version_tag: str = "") -> str:
    """
    渲染完整 HTML。
    opts 应含:
      active_members: list[dict]  (name/count/pct)
      hour_dist:      list[int] 24
      day_dist:       list[dict] (date/count)
      clusters:       list[dict] (keyword/count/examples/members)
      ai:             dict {mode: [items]}  (可能为空)
      theme:          str dark|light|minimal
      video_section:  list[str]  视频相关提示(可空)
    """
    theme = THEMES.get(opts.get("theme", "dark"), THEMES["dark"])
    css = _build_css(theme)

    # 头部
    total = stats.get("total", 0)
    start, end = stats.get("start_date", ""), stats.get("end_date", "")
    sub = f"{start} ~ {end} · 共 {total} 条消息"
    if stats.get("senders_count"):
        sub += f" · {stats['senders_count']} 位成员"

    # —— 板块1：概述（统计卡）——
    s_overview = _render_overview(stats, theme)

    # —— 板块2：活跃成员 ——
    s_active = _render_active(opts.get("active_members", []), theme)

    # —— 板块2.5：群友项目（规则自动识别,零token）——
    s_proj = _render_projects(opts.get("projects", []), theme)

    # —— 板块3：话题 / 关键词聚类 ——
    s_topic = _render_clusters(opts.get("clusters", []), theme)

    # —— 板块4：时间热区 ——
    s_time = _render_time(opts.get("hour_dist", []), opts.get("day_dist", []), theme)

    # —— 板块5：AI 提炼（可选）——
    s_ai = _render_ai(opts.get("ai", {}), theme)

    # —— 板块6：多媒体 / 视频（零 token 也能提）——
    s_media = _render_media(stats, theme)

    # —— 板块6.5：AI 视觉识别（用户填视觉模型的 key 才启用）——
    s_vis = _render_vision(opts.get("vision_descs", []), theme)

    # —— 板块6.6：词云（零 token，纯规则词频）——
    s_cloud = _render_wordcloud(opts.get("wordcloud", []), theme)

    # —— 底部：猜您想问（可点折叠，默认关，点击展开）——
    s_faq = _render_faq(opts, stats, theme)

    sections = filter(None, [
        s_overview, s_active, s_proj, s_topic, s_time, s_ai, s_media, s_vis, s_cloud,
    ])

    # 把 sections 拼成 body，然后接上 FAQ
    body = "".join(sections) + (s_faq or "")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(chat_name)} 思维导图</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span class="a">{_esc(chat_name)}</span><span class="b"> 思维导图</span></h1>
    <div class="sub">{_esc(sub)}</div>
    <div class="hint">本页由 wx-mindmap 生成 · {_esc(version_tag or "免费版")}{_ai_note(opts.get('ai', {}))}</div>
  </header>
  {body}
  <footer>wx-mindmap · 自动生成 · 本地处理，隐私安全</footer>
</div>
</body>
</html>"""
    return html


def _ai_note(ai: Dict) -> str:
    return " · AI 提炼已启用" if ai else ""


# ---------------------------------------------------------------- 板块渲染
def _overview_card(title, icon, value, note=""):
    return (f'<div class="oc"><div class="oi">{icon}</div><div class="ov">{value}</div>'
            f'<div class="on">{note}</div></div>')


def _render_overview(stats, theme) -> str:
    cells = []
    total = stats.get("total", 0)
    cells.append(_overview_card("消息总数", "💬", total))
    cells.append(_overview_card("发言成员", "👥", stats.get("senders_count", 0)))
    cells.append(_overview_card("活跃天数", "📅", stats.get("days", 0)))
    cells.append(_overview_card("图片", "🖼", stats.get("image_count", 0)))
    cells.append(_overview_card("视频", "🎬", stats.get("video_count", 0)))
    cells.append(_overview_card("文件", "📎", stats.get("file_count", 0)))
    grid = "".join(cells)
    return f'<details class="section" open><summary>📊 群数据概览 <span class="count">{total}</span><span class="arrow">▸</span></summary><div class="mini"><div class="ov-grid">{grid}</div></div></details>'


def _render_active(active, theme) -> str:
    if not active:
        return ""
    # —— 按重要程度分成小板块 ——
    # 小板块1: 核心主力(前3)  小板块2: 积极参与(4-7)  小板块3: 其他(8+)
    groups = [
        ("🥇 核心主力 · 发言最多", active[:3], "imp-hi"),
        ("🙌 积极参与", active[3:7], "imp-lo"),
        ("👥 其他成员", active[7:], "imp-lo"),
    ]
    subs = []
    for title, members, imp in groups:
        if not members:
            continue
        rows = []
        for i, m in enumerate(members):
            bar_w = min(100, m["pct"] * 3)
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "·"
            quote_html = ""
            if m.get("quote"):
                quote_html = (f'<div class="quotebox"><b>ta说：</b>'
                              f'{_esc(m["quote"])}</div>')
            rows.append(
                f'<li class="{imp}"><span class="lem">{medal}</span>'
                f'<div class="m-info"><span class="m-name">{_esc(m["name"])}</span>'
                f'<span class="m-cnt">{m["count"]}条 · {m["pct"]}%</span>'
                f'{quote_html}'
                f'<span class="m-bar"><i style="width:{bar_w}%"></i></span></div></li>'
            )
        subs.append(
            f'<div class="b2"><div class="tt">{title}</div>'
            f'<ul class="ulist">{"" . join(rows)}</ul></div>')
    return (f'<details class="section" open><summary>🏆 活跃成员 '
            f'<span class="count">{len(active)}位</span><span class="arrow">▸</span>'
            f'</summary><div class="mini">{"".join(subs)}</div></details>')


def _render_projects(projects, theme) -> str:
    """群友项目卡 — 对标上次模板的"项目九宫格"：卡片带作者徽章+简介+链接+摘录+提及成员。
    本地规则版：good-list(好感原因)/comments(评论) 需语义判断，这里用"代表性消息摘录"和
    "提及成员"填空（只有接了 AI 才升级成真正的好评原因+评论区）。"""
    if not projects:
        return ""
    cards = []
    for p in projects:
        name = _esc(p.get("name") or "项目")
        url = p.get("url") or ""
        desc = p.get("desc") or ""
        times = p.get("times", 1)
        author = p.get("author") or ""
        # 作者徽章（person-badge 风格）
        author_html = f'<span class="person-badge">{_esc(author)}</span>' if author else ""
        # 简介（meta）
        meta_html = f'<div class="meta">{_esc(desc[:50])}</div>' if desc else ""
        # 链接（link）
        link_html = ""
        if url:
            link_html = (f'<span class="link">🔗 <a href="{_esc(url)}" target="_blank">'
                         f'{_esc(url[:52])}</a></span>')
        # good-list：有 AI 好评原因用 AI，否则用本地摘录
        good_html = ""
        why_good = p.get("why_good")
        if why_good:
            good_html = (f'<ul class="good-list"><li>👍 <span class="gl-txt">'
                         f'{_esc(why_good)}</span></li></ul>')
        elif desc:
            good_html = (f'<ul class="good-list"><li>💬 <span class="gl-txt">'
                         f'{_esc(desc[:70])}</span></li></ul>')
        # 评论区：有 AI 评论用 AI 的评论区，否则本地"提及次数"
        cmt_html = ""
        reviews = p.get("reviews") or []
        if reviews:
            cmt_list = ""
            for r in reviews[:3]:
                cmt_list += (f'<div class="cmt"><div class="avatar">💬</div>'
                             f'<div class="cmt-box"><div class="txt">{_esc(r)}</div>'
                             f'</div></div>')
            cmt_html = f'<div class="comments">{cmt_list}</div>'
        else:
            cmt_html = (f'<div class="comments"><div class="cmt"><div class="avatar">💬</div>'
                        f'<div class="cmt-box"><div class="who"><b>{_esc(author or "群友")}</b>'
                        f' · 提及 {times} 次</div></div></div></div>')
        cards.append(
            f'<div class="pcard"><h3>🚀 {name} {author_html}</h3>'
            f'{meta_html}{link_html}{good_html}{cmt_html}</div>')
    return (f'<details class="section" open><summary>🚀 群友项目 · 九宫格 '
            f'<span class="count">{len(projects)}个</span><span class="arrow">▸</span>'
            f'</summary><div class="pgrid">{"".join(cards)}</div></details>')


def _render_clusters(clusters, theme) -> str:
    if not clusters:
        return ""
    # 为每话题生成"小板块"：标题 = emoji + 关键词, 要点 = 例子(带emoji+红蓝重要度)
    cards = []
    for idx, c in enumerate(clusters):
        kw = c["keyword"]
        COUNT = c["count"]
        # 重要度：消息多的=重要红, 少的=普通蓝
        imp = "imp-hi" if COUNT >= 5 else "imp-lo"
        # 小板块标题: 🧩 关键词 [条数]
        members = " ".join(f'<span class="pbadge">{_esc(n)}</span>'
                           for n in c.get("members", []))
        # 每要点: emoji + 文本, 用模板的要点样式
        eg_emojis = ["💬", "🗣", "📌", "✍️", "👀", "💡"]
        points = ""
        for j, ex in enumerate(c.get("examples", [])[:6]):
            emo = eg_emojis[j % len(eg_emojis)]
            # 示例若 >40 字截断
            short = ex if len(ex) <= 42 else ex[:42] + "…"
            points += (f'<li class="{imp}"><span class="lem">{emo}</span>'
                       f'<span class="keg">{_esc(short)}</span></li>')
        cards.append(
            f'<div class="b2"><div class="tt">🔖 {_esc(kw)} '
            f'<span class="tagc">{COUNT}条</span></div>'
            f'<ul class="ulist">{points}</ul>'
            f'<div class="ppl">{members}</div></div>')
    return (f'<details class="section" open><summary>🔖 话题关键词 '
            f'<span class="count">{len(clusters)}类</span><span class="arrow">▸</span>'
            f'</summary><div class="mini">{"".join(cards)}</div></details>')


def _render_time(hours, days, theme) -> str:
    if not hours:
        return ""
    # 24小时热区：找出峰值时段
    mx = max(hours) or 1
    hour_cells = []
    labels = ["00","01","02","03","04","05","06","07","08","09","10","11",
              "12","13","14","15","16","17","18","19","20","21","22","23"]
    for h, v in enumerate(hours):
        hgt = int(v / mx * 100)
        hour_cells.append(
            f'<div class="hcell"><div class="hbar" style="height:{max(3,hgt)}%"></div>'
            f'<div class="hl">{labels[h]}</div></div>')
    # 峰值时段描述
    top3 = sorted(range(24), key=lambda h: hours[h], reverse=True)[:3]
    peak = "、".join(f"{labels[h]}点" for h in sorted(top3))
    grid = "".join(hour_cells)
    day_summary = " · ".join(
        f"{d['date'][5:]} {d['count']}条" for d in days[-7:]) if days else ""
    return (f'<details class="section"><summary>⏰ 时间热区 <span class="count">峰在{peak}</span>'
            f'<span class="arrow">▸</span></summary><div class="mini">'
            f'<div class="hours">{grid}</div>'
            f'<div class="days">{_esc(day_summary)}</div></div></details>')


def _render_ai(ai: Dict, theme) -> str:
    if not ai:
        return ""
    titles = {
        "essence": ("✨", "AI 提炼 · 3 条精华"),
        "disputes": ("⚔️", "观点分歧"),
        "actions": ("✅", "待办 / 行动项"),
    }
    blocks = []
    for mode, items in ai.items():
        if not items:
            continue
        icon, title = titles.get(mode, ("🤖", "AI 提炼"))
        lis_items = []
        for x in items:
            # 带【重要】的要点 → 红高亮（重要度），其余蓝色
            if "【重要】" in x:
                x_clean = x.replace("【重要】", "").strip()
                lis_items.append(
                    f'<li class="imp-hi"><span class="lem">🔴</span>'
                    f'<span class="keg"><b>{_esc(x_clean)}</b></span></li>')
            else:
                lis_items.append(
                    f'<li class="imp-lo"><span class="lem">◈</span>'
                    f'<span class="keg">{_esc(x)}</span></li>')
        lis = "".join(lis_items)
        blocks.append(
            f'<div class="b2 ai"><div class="tt">{icon} {title}</div>'
            f'<ul class="ulist">{lis}</ul></div>')
    if not blocks:
        return ""
    return (f'<details class="section" open><summary>🤖 AI 提炼 <span class="count">'
            f'增强模式</span><span class="arrow">▸</span></summary><div class="mini">'
            f'{"".join(blocks)}</div></details>')


def _render_faq(opts, stats, theme) -> str:
    """「猜您想问」折叠问答区 — 只放主板块没展开的信息增量，不重复。"""
    items = []

    # Q1: 发了多少图/视频/文件/链接？（主板块只说总数，这里拆分细项）
    v = stats.get("video_count", 0)
    img = stats.get("image_count", 0)
    f = stats.get("file_count", 0)
    lk = stats.get("link_count", 0)
    if v or img or f or lk:
        rows = []
        for emo, n, label in [("🖼", img, "图片"), ("🎬", v, "视频"),
                              ("📎", f, "文件"), ("🔗", lk, "链接")]:
            rows.append(
                f'<li class="imp-lo"><span class="lem">{emo}</span>'
                f'<span class="keg">{label} {n} 个/张</span></li>')
        items.append((
            "一共发了多少图片、视频、文件？",
            f'<ul class="ulist">{"".join(rows)}</ul>'))

    # Q2: 谁最爱分享素材/文件（多媒体贡献者）？
    mc = opts.get("media_contributors", [])
    if mc:
        rows = []
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        for i, m in enumerate(mc[:5]):
            total = m["image"] + m["video"] + m["file"]
            rows.append(
                f'<li class="imp-lo"><span class="lem">{medals[i]}</span>'
                f'<span class="keg">{_esc(m["name"])} · 共 {total} 个'
                f'（图{m["image"]} 视{m["video"]} 文{m["file"]}）</span></li>')
        items.append((
            "谁最爱在群里分享图片/视频？",
            f'<ul class="ulist">{"".join(rows)}</ul>'))

    # Q3: 引用/互动热度 + 整体节奏
    qh = opts.get("quote_heat", {})
    dv = opts.get("daily_pace", {})
    if qh or dv:
        lines = []
        if qh.get("quote_count"):
            lines.append(f'<li class="imp-lo"><span class="lem">💬</span>'
                         f'<span class="keg">被引用/回帖共 {qh["quote_count"]} 条'
                         f'，{qh["quote_senders"]} 人参与互动</span></li>')
        if dv.get("avg_per_day"):
            peak_txt = ""
            if dv.get("peak_count"):
                peak_txt = f'，{dv["peak_day"]} 最多（{dv["peak_count"]} 条）'
            lines.append(f'<li class="imp-lo"><span class="lem">📅</span>'
                         f'<span class="keg">平均每天约 {dv["avg_per_day"]} 条{peak_txt}'
                         f'</span></li>')
        if lines:
            items.append((
                "群里的互动热度和节奏怎么样？",
                f'<ul class="ulist">{"".join(lines)}</ul>'))

    if not items:
        return ""
    faqs = "".join(
        f'<details class="faq-item"><summary>{q} <span class="arrow">▸</span></summary>'
        f'<div class="faq-body">{a}</div></details>'
        for q, a in items)
    return (f'<div class="faq"><h2 class="faq-title">🤔 猜您想问</h2>'
            f'<p class="faq-note">点一下即可展开答案 · 全部本地规则，不耗 token</p>{faqs}</div>')


def _render_vision(descs, theme) -> str:
    """AI 视觉识别结果板块（用户填了视觉模型的 key 且启用识别才会显示）。"""
    if not descs:
        return ""
    items = "".join(
        f'<li class="imp-lo"><span class="lem">🖼</span>'
        f'<span class="keg"><b>{_esc(d["file"])}</b> — {_esc(d["desc"])}</span></li>'
        for d in descs[:10])
    return (f'<details class="section"><summary>🔍 AI 看图 <span class="count">'
            f'{len(descs)}张</span><span class="arrow">▸</span></summary>'
            f'<div class="mini"><ul class="ulist">{items}</ul>'
            f'<div class="eg">用你配置的视觉模型识别图片内容（按需启用，省 token）。</div>'
            f'</div></details>')


def _render_wordcloud(words, theme) -> str:
    """词云板块：放射状——最高频词居中最大，向外一圈圈变小（零 token）。"""
    if not words:
        return ""
    # 排序：最高频在最前 → 中心
    words = sorted(words, key=lambda w: w["count"], reverse=True)[:28]
    mx = max(w["count"] for w in words) or 1
    colors = ["var(--t-blue)", "var(--t-green)", "var(--t-pink)",
              "#ffd54f", "#80deea", "#ce93d8", "#aed581", "#ffab91"]
    # 用 flex 居中放射：核心词大、外层小；用随机轻微旋转/位移营造"云"感
    items = []
    for i, w in enumerate(words):
        ratio = w["count"] / mx
        # 第1个词=最大，往后递减；字号 2.6rem → 1.0rem
        size = 2.6 - (i / len(words)) * 1.6
        import random as _r
        rot = _r.randint(-8, 8)
        items.append(
            f'<span class="cw-item" style="font-size:{size:.2f}rem;color:{colors[i%len(colors)]};'
            f'transform:rotate({rot}deg);order:{len(words)-i}">{_esc(w["word"])}</span>')
    cloud = "".join(items)
    return (f'<details class="section"><summary>☁️ 群聊词云 <span class="count">'
            f'{len(words)}词</span><span class="arrow">▸</span></summary>'
            f'<div class="ccloud">{cloud}</div></details>')


def _render_media(stats, theme) -> str:
    v = stats.get("video_count", 0)
    img = stats.get("image_count", 0)
    f = stats.get("file_count", 0)
    if not (v or img or f):
        return ""
    parts = []
    if image := img:
        parts.append(f"🖼 图片 {image} 张")
    if video := v:
        parts.append(f"🎬 视频 {video} 个")
    if fil := f:
        parts.append(f"📎 文件 {fil} 个")
    note = f'<div class="eg">本群共分享了 {len(parts) and "".join(parts)}；如需识别视频/图片内容，可开启 AI 提炼（自带 key）。</div>'
    return (f'<details class="section"><summary>🎬 多媒体 <span class="count">'
            f'{v+img+f}个</span><span class="arrow">▸</span></summary><div class="mini">{note}</div></details>')


# ---------------------------------------------------------------- CSS
def _build_css(t: Dict) -> str:
    return f"""
:root{{--bg:{t['bg']};--container:{t['container']};--card:{t['card']};
--card-border:{t['card_border']};--line:{t['line']};
--t-blue:{t['t_blue']};--t-green:{t['t_green']};--t-pink:{t['t_pink']};
--name:{t['name']};--body:{t['body']};--link:{t['link']};--tag:{t['tag']};
--quote:{t['quote']};--footer:{t['footer']};}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--body);
font-family:"Segoe UI","Microsoft YaHei UI","PingFang SC",sans-serif;
min-height:100vh;padding:36px 18px 60px;}}
.wrap{{max-width:1180px;margin:0 auto;}}
header{{text-align:center;margin-bottom:26px;}}
header h1{{font-size:26px;font-weight:800;letter-spacing:1px;}}
header h1 .a{{color:var(--t-blue);}}header h1 .b{{color:var(--t-green);}}
header .sub{{margin-top:8px;font-size:13px;opacity:.8;}}
header .hint{{margin-top:6px;font-size:11px;opacity:.55;}}

details.section{{background:var(--container);border:1px solid var(--line);
border-radius:14px;margin-bottom:16px;overflow:hidden;}}
details.section summary{{cursor:pointer;list-style:none;display:flex;align-items:center;
justify-content:space-between;padding:13px 20px;font-size:17px;font-weight:700;
color:var(--t-pink);}}
details.section summary::-webkit-details-marker{{display:none;}}
details.section summary .count{{background:#26264a;color:var(--t-green);
border:1px solid rgba(90,220,180,.25);padding:2px 12px;border-radius:999px;
font-size:11px;font-weight:600;}}
details.section summary .arrow{{color:#8883b8;font-size:13px;transition:transform .2s;}}
details.section[open] summary{{border-bottom:1px solid var(--line);}}
details.section[open] summary .arrow{{transform:rotate(90deg);}}
.mini{{display:flex;flex-direction:column;gap:12px;padding:16px 20px;}}

.ov-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;}}
.oc{{background:var(--card);border:1px solid var(--card-border);border-radius:10px;
padding:12px;text-align:center;}}
.oc .oi{{font-size:20px;}}.oc .ov{{font-size:20px;font-weight:800;color:var(--name);margin-top:2px;}}
.oc .on{{font-size:11px;color:var(--footer);}}

.mem-list{{display:flex;flex-direction:column;gap:6px;}}
.mem{{display:flex;align-items:center;gap:10px;font-size:13px;padding:7px 10px;
background:var(--card);border:1px solid var(--card-border);border-radius:8px;}}
.m-left{{display:flex;align-items:center;gap:10px;flex:0 0 auto;max-width:62%;}}
.m-medal{{width:20px;text-align:center;flex-shrink:0;}}
.m-info{{display:flex;flex-direction:column;gap:2px;min-width:0;}}
.m-name{{font-weight:700;color:var(--name);}}
.m-cnt{{color:var(--t-blue);font-size:11px;}}
.m-bar{{flex:1;height:8px;background:rgba(90,220,180,.12);border-radius:6px;overflow:hidden;min-width:40px;}}
.m-bar i{{display:block;height:100%;background:var(--t-blue);opacity:.7;border-radius:6px;}}
.quotebox{{font-size:11px;color:var(--quote);background:rgba(124,107,255,.08);
border-left:2px solid var(--t-pink);padding:3px 8px;border-radius:4px;margin-top:3px;max-width:320px;}}
.quotebox b{{color:var(--t-pink);font-weight:600;}}

.b2{{background:var(--card);border:1px solid var(--card-border);border-radius:10px;padding:12px 14px;}}
.b2 .tt{{font-size:14px;font-weight:700;color:var(--t-green);display:flex;align-items:center;gap:7px;margin-bottom:8px;flex-wrap:wrap;}}
.b2 ul{{list-style:none;}}.b2 li{{font-size:12.8px;line-height:1.6;color:var(--body);padding:3px 0;}}
.b2 li b{{color:var(--t-pink);margin-right:4px;}}
.eg{{font-size:12px;color:var(--quote);line-height:1.5;padding:2px 0;}}
.pbadge{{color:var(--tag);font-size:10px;background:rgba(90,220,180,.1);border:1px solid rgba(90,220,180,.2);padding:1px 7px;border-radius:5px;}}
.ppl{{margin-top:8px;display:flex;gap:4px;flex-wrap:wrap;}}
.tagc{{font-size:10px;color:var(--t-blue);border:1px solid var(--line);padding:0 7px;border-radius:999px;}}

/* 要点列表：每条 emoji + 文本，红蓝重要度 */
.ulist{{display:flex;flex-direction:column;gap:4px;}}
.ulist li{{display:flex;align-items:flex-start;gap:7px;padding:4px 8px;border-radius:6px;line-height:1.5;font-size:12.8px;}}
.ulist .lem{{flex-shrink:0;color:var(--t-pink);}}
.ulist .keg{{color:var(--body);}}
.imp-hi{{background:rgba(216,93,93,.12);border-left:3px solid var(--imp-hi);}}
.imp-hi .keg{{color:#ffd5d0;}}
.imp-lo{{background:rgba(108,180,255,.08);border-left:3px solid var(--imp-lo);}}
.imp-lo .keg{{color:#d3e6ff;}}
.mem{{border-left:4px solid var(--line);}}
.mem.imp-hi{{border-left-color:var(--imp-hi);background:rgba(216,93,93,.10);}}
.mem.imp-lo{{border-left-color:var(--imp-lo);background:rgba(108,180,255,.06);}}

.pgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;}}
@media(max-width:700px){{.pgrid{{grid-template-columns:1fr;}}}}
.pcard{{background:var(--card);border:1px solid var(--card-border);border-radius:12px;
padding:14px 16px;display:flex;flex-direction:column;gap:7px;}}
.pcard h3{{font-size:14px;font-weight:700;color:var(--name);display:flex;align-items:center;gap:6px;flex-wrap:wrap;}}
.pcard .person-badge{{color:var(--tag);font-size:10px;background:rgba(90,220,180,.1);border:1px solid rgba(90,220,180,.2);padding:1px 8px;border-radius:999px;}}
.pcard .meta{{color:var(--footer);font-size:11px;line-height:1.4;}}
.pcard .link{{color:var(--link);font-size:11px;word-break:break-all;}}
.pcard .link a{{color:var(--link);text-decoration:none;}}
.pcard .good-list{{list-style:none;margin:2px 0 0;}}
.pcard .good-list li{{font-size:12px;color:var(--body);line-height:1.5;padding:2px 0;}}
.pcard .gl-txt{{color:var(--quote);}}
/* 评论区（模板 cmt 结构） */
.pcard .comments{{margin-top:4px;border-top:1px dashed var(--line);padding-top:7px;}}
.pcard .cmt{{display:flex;gap:7px;align-items:flex-start;}}
.pcard .cmt .avatar{{width:22px;height:22px;border-radius:50%;background:linear-gradient(135deg,#7c4dff,#00e5ff);display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0;}}
.pcard .cmt-box{{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:8px;padding:5px 9px;flex:1;font-size:11px;}}
.pcard .cmt-box .who{{font-size:10px;color:#9aa;margin-bottom:2px;}}
.pcard .cmt-box .who b{{color:#b388ff;}}
.pcard .cmt-box .txt{{color:var(--body);line-height:1.5;}}

.hours{{display:flex;align-items:flex-end;gap:3px;height:110px;}}
.hcell{{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%;}}
.hbar{{width:100%;background:var(--t-green);opacity:.7;border-radius:2px;}}
.hl{{font-size:8px;color:var(--footer);margin-top:2px;}}
.days{{font-size:11px;color:var(--footer);margin-top:8px;}}

.ai .tt{{color:var(--t-pink);}}
.ai li{{font-size:13px;}}
footer{{text-align:center;color:var(--footer);font-size:11px;margin-top:26px;opacity:.7;}}

/* —— 猜您想问 FAQ —— */
.faq{{margin-top:26px;background:var(--container);border:1px solid var(--line);border-radius:14px;padding:16px 20px;}}
.faq-title{{font-size:16px;font-weight:800;color:var(--t-pink);margin-bottom:2px;}}
.faq-note{{font-size:11px;color:var(--footer);margin-bottom:12px;}}
.faq-item{{border:1px solid var(--card-border);border-radius:8px;background:var(--card);margin-bottom:8px;overflow:hidden;}}
.faq-item summary{{cursor:pointer;list-style:none;padding:10px 14px;font-size:13px;font-weight:600;color:var(--t-green);display:flex;justify-content:space-between;align-items:center;}}
.faq-item summary::-webkit-details-marker{{display:none;}}
.faq-item[open] summary{{border-bottom:1px solid var(--line);}}
.faq-item .arrow{{color:#8883b8;font-size:12px;transition:transform .2s;}}
.faq-item[open] .arrow{{transform:rotate(90deg);}}
.faq-body{{padding:12px 14px;font-size:12.5px;}}
.faq-body .hours{{height:80px;}}

/* —— 词云：核心词居中大、外层词小，云感 —— */
.ccloud{{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;
gap:6px 14px;padding:20px 10px;min-height:180px;}}
.cw-item{{font-weight:700;line-height:1.2;padding:2px 5px;text-shadow:0 1px 2px rgba(0,0,0,.3);}}
"""

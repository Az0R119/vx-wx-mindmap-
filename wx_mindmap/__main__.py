"""
wx-mindmap · 主程序（命令行 / 可直接双击运行）

把 WeChatDataAnalysis 导出的 zip，变成一张「按上次模板排版」的思维导图 HTML。

默认：零 token，纯本地规则生成（活跃成员 / 话题 / 时间 / 多媒体统计）。
可选：AI 提炼（3 条精华 / 分歧 / 行动项）——需要用户自带自己的 API key。
      key 只在本机使用，从不写入输出、从不上传、从不分发。
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from typing import Optional

from .parser import load_export, transcripts
from .rules import (chat_stats, active_members, hour_distribution, day_distribution,
                    keyword_clusters, detect_projects, media_contributors,
                    quote_heat, daily_pace, word_cloud)
from .render import render_mindmap
from .ai import summarize


# 内置常用话题词表（用户可 --keywords 覆盖）
DEFAULT_KEYWORDS = ["AI", "编程", "代码", "工具", "项目", "课程", "作业",
                    "考试", "游戏", "金融", "量化", "视频", "音乐", "比赛"]


def _ask(question: str, default="n") -> bool:
    """CLI 交互，返回 True/False。默认 n（安全起见 AI 默认关）。"""
    while True:
        ans = input(f"{question}（y/n，默认 {default}）: ").strip().lower() or default
        if ans in ("y", "n"):
            return ans == "y"


def run_summary(zip_path: str, out_html: Optional[str] = None,
                compress: bool = False,
                keywords=None, top=12, cluster_top=6, project_top=10,
                theme="dark", ai_modes=None,
                api_key="", api_base="https://api.deepseek.com", model="deepseek-chat",
                vision_key="", vision_base="", vision_model="", describe_images=False,
                max_vision=8, user_hint="") -> dict:
    """高层流水线：zip → (可选压缩) → 解析 → 规则 → (可选 文字AI) → (可选 视觉AI) → 出图."""
    import os as _os
    import shutil as _shutil
    import tempfile as _tmp

    warnings = []
    work_zip = zip_path

    # —— 可选：压缩图片（省后续喂图 token）——
    if compress:
        try:
            from .compress import compress_zip_images
            tmp_zip = _os.path.join(_tmp.gettempdir(),
                                    "wx_summary_compress_" + _os.path.basename(zip_path))
            st = compress_zip_images(zip_path, tmp_zip)
            work_zip = tmp_zip
            if st["compressed"]:
                warnings.append(f"已压缩 {st['compressed']} 张图片（省后续 token）")
        except Exception as e:
            warnings.append(f"压缩跳过（{e}）")

    # —— 解析 ——
    chats = load_export(work_zip, max_chats=1)
    if not chats:
        raise RuntimeError("zip 里没解析到会话，请确认是 WeChatDataAnalysis 导出的 zip")
    chat = chats[0]
    stats = chat_stats(chat)

    # —— 规则 → opts ——
    opts = {
        "active_members": active_members(chat, top=top),
        "hour_dist": hour_distribution(chat),
        "day_dist": day_distribution(chat),
        "clusters": keyword_clusters(chat, keywords or DEFAULT_KEYWORDS, top=cluster_top),
        "projects": detect_projects(chat, top=project_top),
        "media_contributors": media_contributors(chat),
        "quote_heat": quote_heat(chat),
        "daily_pace": daily_pace(chat),
        "wordcloud": word_cloud(chat),
        "ai": {},
        "theme": theme,
        "user_hint": user_hint or "",
    }

    # —— 可选 AI 文字提炼 ——
    if ai_modes and api_key:
        try:
            tr = transcripts(chat)
            for mode in ai_modes:
                items = summarize(tr, mode, api_key, base=api_base, model=model)
                if items:
                    opts["ai"][mode] = items
            if not opts["ai"]:
                warnings.append("AI 文字提炼未成功，已用纯本地规则版")
        except Exception as e:
            warnings.append(f"AI 文字提炼跳过（{e}）")

    # —— 可选 AI 批量升级项目卡（一次调用，生成好评原因+评论区）——
    if api_key and opts.get("projects"):
        try:
            from .ai import enrich_projects_reviews
            _reviews = enrich_projects_reviews(opts["projects"], api_key,
                                               base=api_base, model=model)
            if _reviews:
                # 把 AI 好评注入每个项目
                for pr in opts["projects"]:
                    rv = _reviews.get(pr.get("name")) or _reviews.get(pr.get("url"))
                    if rv:
                        pr["why_good"] = rv.get("good", "")
                        pr["reviews"] = rv.get("comments", [])
            else:
                warnings.append("AI 项目好评未生成（key/模型/网络？），项目卡用本地版")
        except Exception as e:
            warnings.append(f"AI 项目好评跳过（{e}）")

    # —— 可选 AI 视觉识别（默认关，省 token；用户勾选"识别图片"才启用）——
    if describe_images and vision_key and vision_base and vision_model:
        try:
            from .ai import describe_image
            from zipfile import ZipFile as _Zf
            media_descs = []
            zf = _Zf(zip_path)
            # 找 assets 里的图片（media/ 下的，最多 max_vision 张）
            img_candidates = [n for n in zf.namelist()
                              if n.lower().endswith((".jpg", ".jpeg", ".png"))
                              and "media/" in n][:max_vision]
            import tempfile as _tp, os as _os
            _tmp_dir = _tp.mkdtemp(prefix="wx_vis_")
            try:
                import base64 as _b64
                counted = 0
                for name in img_candidates:
                    raw = zf.read(name)
                    # 只取较大的图，跳过头像/表情（去重噪音）
                    if len(raw) < 8000:
                        continue
                    _p = _os.path.join(_tmp_dir, _os.path.basename(name))
                    with open(_p, "wb") as f:
                        f.write(raw)
                    desc = describe_image(_p, vision_key, vision_base, vision_model,
                                          "用一句话简洁描述这张图的内容")
                    if desc:
                        media_descs.append({"file": name.split("/")[-1], "desc": desc[:80]})
                        counted += 1
                    if counted >= max_vision:
                        break
            finally:
                import shutil as _sh
                _sh.rmtree(_tmp_dir, ignore_errors=True)
            if media_descs:
                opts["vision_descs"] = media_descs
            else:
                warnings.append("视觉识别未返回结果（key/模型/网络？），已跳过")
        except Exception as e:
            warnings.append(f"视觉识别跳过（{e}）")

    # —— 判断版本：有 AI 结构 → AI版（独立渲染代码）；否则免费版 ——
    ai_struct = None
    if api_key:
        try:
            from .ai import ai_generate_structure, generate_section_plan
            tr = transcripts(chat)
            user_hint = (opts.get("user_hint") or "").strip()
            # Step1：让 AI 先判定这个群该有哪些板块（专属板块方案；家庭群出家庭板块，不再硬编码 IT）
            # 有无用户提示都走一遍——没提示时 AI 按聊天内容自行判断群类型
            plan = {}
            from .ai import generate_section_plan as _gsp
            try:
                plan = _gsp(tr, api_key, base=api_base, model=model, user_hint=user_hint)
            except Exception:
                plan = {}
            # Step2/3：板块方案 + 用户输入 + 原风格注入，正式出图
            ai_struct = ai_generate_structure(tr, api_key, base=api_base, model=model,
                                              known_projects=opts.get("projects"),
                                              user_hint=user_hint, section_plan=plan)
            if ai_struct and ai_struct.get("sections"):
                warnings.append(f"✅ AI 版：AI 生成 {len(ai_struct['sections'])} 个板块"
                                + (f"（群类型：{plan.get('群类型','')}）" if plan and plan.get("群类型") else ""))
            else:
                warnings.append("⚠️ AI 未返回有效板块（已退回免费版）。请检查 key / 模型 / AI 返回格式")
        except Exception as e:
            warnings.append(f"❌ AI 调用失败，已退回免费版（{e}）")

    if ai_struct and ai_struct.get("sections"):
        # —— AI 版：独立渲染代码 ——
        # 兜底：把免费版规则抓到的、但 AI 漏掉的项目补齐（保证项目一个不少）
        try:
            ai_projects = {p["name"] for p in ai_struct.get("projects", [])}
            for rp in opts.get("projects", []):
                nm = rp.get("name")
                if nm and nm not in ai_projects:
                    ai_struct.setdefault("projects", []).append({
                        "name": nm, "author": rp.get("author", ""),
                        "reasons": [str(rp.get("desc", "") or "")] if rp.get("desc") else [],
                        "comments": [f"群友分享了 {nm}"]})
        except Exception:
            pass
        from .render_ai import render_ai_page
        html = render_ai_page(chat.display_name, ai_struct, stats,
                              version_tag="AI版", free_data=opts,
                              qa_base=api_base, qa_model=model)
        version_tag = "AI版"
    else:
        # —— 免费规则版 ——
        has_ai = bool(opts.get("ai")) or any(p.get("why_good") for p in opts.get("projects", []))
        version_tag = "AI版" if has_ai else "免费版"
        render_mindmap_local = render_mindmap  # noqa
        html = render_mindmap(chat.display_name, stats, opts, version_tag=version_tag)

    if out_html is None:
        base = _os.path.splitext(_os.path.basename(zip_path))[0]
        out_html = _os.path.join(_os.path.dirname(_os.path.abspath(zip_path)),
                                 f"{base}_消息总结_{version_tag}.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)

    # —— 清理临时压缩 zip ——
    if work_zip != zip_path:
        try:
            _os.remove(work_zip)
        except OSError:
            pass

    return {
        "out_file": out_html,
        "chat_name": chat.display_name,
        "message_count": len(chat.messages),
        "senders_count": stats.get("senders_count", 0),
        "warnings": warnings,
    }


def build_opts(chat, args) -> dict:
    """收集所有规则数据 + 可选 AI 结果。纯规则部分永不失败。"""
    stats = chat_stats(chat)
    opts = {
        "active_members": active_members(chat, top=args.top),
        "hour_dist": hour_distribution(chat),
        "day_dist": day_distribution(chat),
        "clusters": keyword_clusters(chat, args.keywords, top=args.cluster_top),
        "projects": detect_projects(chat, top=args.project_top),
        "media_contributors": media_contributors(chat),
        "quote_heat": quote_heat(chat),
        "daily_pace": daily_pace(chat),
        "wordcloud": word_cloud(chat),
        "ai": {},
        "theme": args.theme,
    }

    # —— 可选：AI 提炼（用户自带 key）——
    if args.ai:
        key = os.environ.get(args.api_key_env, "").strip() or args.api_key
        key = key.strip() if key else ""
        if key:
            print("已检测到 API key，开始 AI 提炼…（失败则自动降级，不影响主图）")
            transcript = transcripts(chat)
            for mode in args.ai:
                items = summarize(transcript, mode, key,
                                  base=args.api_base, model=args.model)
                if items:
                    opts["ai"][mode] = items
            if not opts["ai"]:
                print("  ⚠️ AI 提炼未成功（key 无效/网络/超量），已自动跳过，主图为纯本地版。")
        else:
            print("  ⚠️ 未提供 API key（--api-key 或环境变量），跳过 AI 提炼，走纯本地规则版。")
    return opts


def run(zip_path: str, out_path: str, args) -> str:
    chats = load_export(zip_path, max_chats=args.chat)
    if not chats:
        raise RuntimeError("zip 里没有解析到会话（确认是 WeChatDataAnalysis 导出的 zip）")
    chat = chats[0]
    print(f"已解析：{chat.display_name} · {len(chat.messages)} 条消息 · "
          f"{chat_stats(chat)['senders_count']} 位成员")
    opts = build_opts(chat, args)
    html = render_mindmap(chat.display_name, chat_stats(chat), opts)
    if out_path is None:
        base = os.path.splitext(os.path.basename(zip_path))[0]
        out_path = os.path.join(os.path.dirname(os.path.abspath(zip_path)),
                                f"{base}_思维导图.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="wx-mindmap",
        description="微信导出 zip → 思维导图 HTML（默认零 token 本地规则；可选自带 key 的 AI 提炼）",
    )
    p.add_argument("input", help="WeChatDataAnalysis 导出的 zip 路径")
    p.add_argument("output", nargs="?", default=None, help="输出 HTML 路径（默认 <原名>_思维导图.html）")
    p.add_argument("--chat", type=int, default=1, help="处理第几个会话(默认取第一个)")
    p.add_argument("--top", type=int, default=12, help="活跃成员展示前 N 人")
    p.add_argument("--keywords", nargs="*", default=DEFAULT_KEYWORDS,
                   help="关键词/话题词表，用于聚类")
    p.add_argument("--cluster-top", type=int, default=6, help="最多聚类几个话题")
    p.add_argument("--project-top", type=int, default=10, help="最多列出几个识别出的项目")
    p.add_argument("--theme", choices=["dark", "light", "minimal"], default="dark",
                   help="主题色（默认深色，像上次那份）")
    # —— AI 选项（默认全关；开启需自带 key）——
    p.add_argument("--ai", nargs="*",
                   choices=["essence", "disputes", "actions"], default=None,
                   help="启用哪些 AI 提炼：essence=3条精华 disputes=分歧 actions=行动项")
    p.add_argument("--api-key", default="", help="你的 API key（默认从环境变量读，不写进文件/输出）")
    p.add_argument("--api-key-env", default="DEEPSEEK_API_KEY",
                   help="从哪个环境变量读 key（不要硬编码 key 到命令行）")
    p.add_argument("--api-base", default="https://api.deepseek.com", help="OpenAI 兼容端点")
    p.add_argument("--model", default="deepseek-chat", help="模型名")
    args = p.parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"错误：找不到文件 {args.input}")
        return 1

    if not args.api_key and not os.environ.get(args.api_key_env):
        if args.ai:
            print("提示：AI 提炼需要你自己的 API key。")
            print(f"  方式一：--api-key <key>\n  方式二：设置环境变量 {args.api_key_env}")
            print("  （不填也能用，只是没有 AI 提炼那部分）")
            if _ask("继续用纯本地规则生成导向图？", default="y"):
                args.ai = None

    try:
        out = run(args.input, args.output, args)
    except Exception as e:
        print(f"出错：{e}")
        return 1

    print(f"✅ 思维导图已生成：{out}")
    if _ask("立即在浏览器打开？", default="y"):
        webbrowser.open("file:///" + out.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    # 无参数：打开图形界面；有参数：走命令行
    if len(sys.argv) <= 1:
        try:
            from .gui import main as gui_main
            sys.exit(gui_main())
        except Exception as e:
            print(f"图形界面启动失败（{e}），可改用命令行：python -m wx_mindmap <zip>")
            sys.exit(1)
    sys.exit(main())

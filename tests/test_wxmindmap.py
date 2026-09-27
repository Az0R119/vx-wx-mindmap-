# -*- coding: utf-8 -*-
"""wx-mindmap 回归测试：三种导出格式解析 + 免费版出图不崩。

用例数据是真实微信导出 zip，放不进仓库。用环境变量指路径：
    WXM_TEST_DIR="C:/Users/ZhuanZ/Desktop/05微信导出"
不设或文件缺失 → 该用例 skip（不报红）。

跑法：
    unset PYTHONPATH && ./.venv/Scripts/python.exe -m unittest discover tests -v
或直接：
    unset PYTHONPATH && ./.venv/Scripts/python.exe tests/test_wxmindmap.py
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wx_mindmap.parser import load_export, transcripts          # noqa: E402
from wx_mindmap import rules                                     # noqa: E402
from wx_mindmap.render import render_mindmap                     # noqa: E402

# 数据目录：默认猜用户桌面，可用环境变量覆盖
TEST_DIR = os.environ.get(
    "WXM_TEST_DIR",
    os.path.join(os.path.expanduser("~"), "Desktop", "05微信导出"),
)
OLD_ZIP = os.path.join(TEST_DIR, "1.zip")            # 旧格式 pages/page-*.js
NEW_ZIP = os.path.join(TEST_DIR, "wechat_chat_export_wxid_424b2k4yed8r22_20260812_181425_ce0d3120aedd.zip")


def _need(path):
    if not os.path.exists(path):
        raise unittest.SkipTest("缺测试数据: " + path)


class TestParser(unittest.TestCase):
    """两种导出格式都要能解析——改 parser 最容易把另一种格式改坏。"""

    def test_old_format(self):
        """旧格式(const html= 包裹的 page-*.js)解析出消息。"""
        _need(OLD_ZIP)
        chats = load_export(OLD_ZIP)
        self.assertTrue(chats, "旧格式没解析出会话")
        total = sum(len(c.messages) for c in chats)
        self.assertGreater(total, 100, f"旧格式消息数异常: {total}")

    def test_new_format(self):
        """新版格式(单文件 messages.html)解析出消息 + 昵称/正文都有。"""
        _need(NEW_ZIP)
        chats = load_export(NEW_ZIP)
        self.assertTrue(chats, "新版格式没解析出会话(报'没找到会话'就是这个挂了)")
        msgs = chats[0].messages
        self.assertGreater(len(msgs), 5, f"新版消息数异常: {len(msgs)}")
        # 至少一条有昵称 + 正文（防正则只抓壳不抓内容）
        self.assertTrue(any(m.sender and m.body for m in msgs), "新版消息缺 sender/body")

    def test_transcripts(self):
        """transcripts() 产出可直接喂 AI 的行。"""
        _need(NEW_ZIP)
        lines = transcripts(load_export(NEW_ZIP)[0])
        self.assertTrue(lines and all(isinstance(x, str) for x in lines))


class TestFreeRender(unittest.TestCase):
    """免费版出图：不崩 + HTML 标签平衡（div 不平衡是历史高发 bug）。"""

    def _render(self, zip_path):
        _need(zip_path)
        chat = load_export(zip_path)[0]
        stats = rules.chat_stats(chat)
        # 与 __main__.py 的 opts 保持一致（少字段 render 会崩）
        opts = {
            "active_members": rules.active_members(chat),
            "hour_dist": rules.hour_distribution(chat),
            "day_dist": rules.day_distribution(chat),
            "clusters": rules.keyword_clusters(chat, ["项目", "工具"], top=6),
            "projects": rules.detect_projects(chat),
            "media_contributors": rules.media_contributors(chat),
            "quote_heat": rules.quote_heat(chat),
            "daily_pace": rules.daily_pace(chat),
            "wordcloud": rules.word_cloud(chat),
            "ai": {},
            "theme": "dark",
        }
        return render_mindmap(chat.display_name, stats, opts, version_tag="免费版")

    def test_new_format_renders(self):
        html = self._render(NEW_ZIP)
        self.assertIn("<html", html.lower())
        self.assertGreater(len(html), 2000, "出图太短，八成中途崩了")

    def test_div_balanced(self):
        """div 开闭数必须相等——历史 bug 都出在这。"""
        html = self._render(NEW_ZIP)
        opens = len(re.findall(r"<div\b", html))
        closes = len(re.findall(r"</div>", html))
        self.assertEqual(opens, closes, f"div 不平衡: {opens} 开 / {closes} 闭")


class TestFeedbackBuckets(unittest.TestCase):
    """worker 归桶逻辑：同义说法必须合并。node 跑 JS，缺 node 则 skip。"""

    WORKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "backend", "feedback_worker.js")

    def test_buckets_merge_synonyms(self):
        import json
        import shutil
        import subprocess
        import tempfile

        if not shutil.which("node"):
            raise unittest.SkipTest("没装 node")
        if not os.path.exists(self.WORKER):
            raise unittest.SkipTest("缺 feedback_worker.js")

        js = r'''
const src = require("fs").readFileSync(process.argv[2], "utf8");
eval(src.slice(src.indexOf("const BUCKETS")).replace(/export default[\s\S]*$/, ""));
const recs = [
  {mood:"dislike", reason:"板块太多了"},
  {mood:"dislike", reason:"板块有点杂，想精简"},
  {mood:"dislike", reason:"要点太长了"},
  {mood:"dislike", reason:"啊这"},          // 归不进桶 → 丢弃
];
const s = summarize(recs);
const b = s.improvementPoints.find(p => p.keyword === "板块太多太杂");
process.stdout.write(JSON.stringify({
  merged: b ? b.count : 0,
  points: s.improvementPoints.length,
}));
'''
        with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False,
                                         encoding="utf-8") as f:
            f.write(js)
            tmp = f.name
        try:
            out = subprocess.run(["node", tmp, self.WORKER], capture_output=True,
                                 text=True, encoding="utf-8", timeout=30).stdout
            data = json.loads(out)
        finally:
            os.remove(tmp)
        self.assertEqual(data["merged"], 2, "两种'板块多'的说法没合并成一个桶")
        self.assertEqual(data["points"], 2, f"归桶的桶数不对: {data['points']}(应为2)")


if __name__ == "__main__":
    unittest.main(verbosity=2)

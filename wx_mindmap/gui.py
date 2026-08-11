"""
微信消息总结 · 图形界面

双击即用：选 WeChatDataAnalysis 导出的 zip → 可选压缩图片 / 可选 AI 提炼（自带 key）
→ 选主题 → 点「生成思维导图」→ 输出 HTML 并打开。

AI 提炼的 key 只在本机使用、不进输出/上传；不填 key 也能用（纯本地规则版）。
"""
from __future__ import annotations

import os
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .compress import HAVE_PIL
from .__main__ import run_summary
from . import __version__


class WeChatSummaryApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"微信消息总结 · v{__version__}")
        self.root.geometry("720x860")
        self.root.minsize(620, 680)
        # 居中显示，避免底部按钮被顶出屏幕
        self.root.update_idletasks()
        try:
            self.root.eval('tk::PlaceWindow . center')
        except Exception:
            pass

        self.zip_var = tk.StringVar()
        self.compress_on = tk.BooleanVar(value=False)
        self.ai_prefix = tk.StringVar(value="AI 提炼（可选，需自带 API key）")
        self.ai_on = tk.BooleanVar(value=False)
        self.key_var = tk.StringVar()
        self.theme = tk.StringVar(value="深色")
        self.status = tk.StringVar(value="选择 WeChatDataAnalysis 导出的 zip，点生成")
        self.busy = False

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 14, "pady": 8}

        # —— 步骤1 选择 zip ——
        f1 = ttk.LabelFrame(self.root, text="① 选择微信导出 zip（WeChatDataAnalysis 导出）")
        f1.pack(fill="x", **pad)
        row = ttk.Frame(f1); row.pack(fill="x", padx=8, pady=8)
        ttk.Entry(row, textvariable=self.zip_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="浏览…", command=self._pick).pack(side="left", padx=(8,0))

        # —— 步骤2 选项 ——
        f2 = ttk.LabelFrame(self.root, text="② 选项（默认即可）")
        f2.pack(fill="x", **pad)
        opt_row = ttk.Frame(f2); opt_row.pack(fill="x", padx=8, pady=6)
        ttk.Checkbutton(opt_row, text="压缩 zip 里的图片（省后续喂图 token）",
                        variable=self.compress_on).pack(side="left")
        ttk.Label(opt_row, text="    主题:").pack(side="left", padx=(12,4))
        ttk.Combobox(opt_row, textvariable=self.theme, width=6,
                     values=["深色","浅色","极简"], state="readonly").pack(side="left")
        ttk.Label(f2, text="不压缩也行——出图读的是文字，压缩只为省后续喂视觉模型的 token。",
                  foreground="#888").pack(anchor="w", padx=10)

        # —— 步骤3 AI 提炼（可选,通用供应商选择）——
        f3 = ttk.LabelFrame(self.root, text="③ AI 提炼（可选 · 选个 AI 填 key 就能用，不限制提供商）")
        f3.pack(fill="x", **pad)
        ttk.Checkbutton(f3, text="启用 AI 提炼（3条精华 / 观点分歧 / 行动项）",
                        variable=self.ai_on).pack(anchor="w", padx=10, pady=(6,0))

        # 供应商下拉：选主流 AI 自动填 URL/Model
        prov_row = ttk.Frame(f3); prov_row.pack(fill="x", padx=10, pady=(3,0))
        ttk.Label(prov_row, text="选择 AI:").pack(side="left")
        self.provider_var = tk.StringVar(value="DeepSeek")
        from .providers import PROVIDERS
        self._providers = PROVIDERS
        prov_names = [p["name"] for p in PROVIDERS]
        prov_cb = ttk.Combobox(prov_row, textvariable=self.provider_var, values=prov_names,
                               state="readonly", width=16)
        prov_cb.bind("<<ComboboxSelected>>", self._on_provider_changed)
        prov_cb.pack(side="left", padx=(6,0))
        ttk.Label(prov_row, text="  获取 key:").pack(side="left", padx=(8,0))
        self.key_url_lbl = ttk.Label(prov_row, text="", foreground="#4da6ff")
        self.key_url_lbl.pack(side="left")
        # 该供应商是否支持视觉
        self.vision_lbl = ttk.Label(f3, text="", foreground="#888")
        self.vision_lbl.pack(anchor="w", padx=10)

        # key 输入
        key_row = ttk.Frame(f3); key_row.pack(fill="x", padx=10, pady=(3,0))
        ttk.Label(key_row, text="API Key:").pack(side="left")
        self.key_entry = ttk.Entry(key_row, textvariable=self.key_var, show="*", width=32)
        self.key_entry.pack(side="left", padx=(6,0))
        self.show_key_btn = ttk.Button(key_row, text="👁", width=3, command=self._toggle_show_key)
        self.show_key_btn.pack(side="left", padx=(4,0))

        # 地址 + 模型
        url_row = ttk.Frame(f3); url_row.pack(fill="x", padx=10, pady=(3,0))
        ttk.Label(url_row, text="Base URL:").pack(side="left")
        self.base_var = tk.StringVar()
        ttk.Entry(url_row, textvariable=self.base_var, width=30).pack(side="left", padx=(6,0))
        ttk.Label(url_row, text="  模型:").pack(side="left", padx=(8,0))
        self.model_var = tk.StringVar()
        ttk.Entry(url_row, textvariable=self.model_var, width=20).pack(side="left", padx=(6,0))

        # 测试连接
        ttk.Button(f3, text="测试连接", command=self._test_conn).pack(anchor="w", padx=10, pady=(4,2))
        self.conn_lbl = ttk.Label(f3, text="", foreground="#888")
        self.conn_lbl.pack(anchor="w", padx=10)

        # 说明
        ttk.Label(f3, text="选内置的 AI 只需填 key；也可自己改 URL+模型接任意 OpenAI 兼容服务，甚至本地 Ollama。key 只在本机用，不进 HTML/上传。",
                  foreground="#888", wraplength=600, justify="left").pack(anchor="w", padx=10, pady=(2,6))

        # —— 视觉识别（独立视觉模型，默认关省 token）——
        self.vision_on = tk.BooleanVar(value=False)
        vision_ck = ttk.Checkbutton(f3, text="识别图片内容（可选 · 用独立的视觉模型，默认不烧 token）",
                                    variable=self.vision_on)
        vision_ck.pack(anchor="w", padx=10, pady=(4,0))
        self._build_vision_row(f3)

        self._on_provider_changed()  # 初始化默认供应商显示

        # —— 进度状态 ——
        self.status_lbl = ttk.Label(self.root, textvariable=self.status, foreground="#333")
        self.status_lbl.pack(fill="x", padx=16)

        # —— 生成按钮 ——
        bottom = ttk.Frame(self.root); bottom.pack(fill="x", side="bottom", padx=14, pady=12)
        self.btn_go = ttk.Button(bottom, text="生成思维导图 🚀", command=self._go)
        self.btn_go.pack(side="right")
        ttk.Label(bottom, text="输出在 zip 同目录：<原名>_消息总结.html",
                  foreground="#666").pack(side="left")

    # (key 框始终可见，无需 toggle；保留空方法以防旧引用)  
    # —— AI 供应商相关 ——
    def _build_vision_row(self, parent):
        """视觉模型的独立配置行（默认关省 token）。"""
        vis = ttk.Frame(parent); vis.pack(fill="x", padx=20, pady=(2,4))
        ttk.Label(vis, text="视觉 AI:").pack(side="left")
        # 只列有视觉能力的供应商
        vision_names = [p["name"] for p in self._providers if p["vision"]]
        if not vision_names:
            vision_names = [p["name"] for p in self._providers]
        self.vision_provider_var = tk.StringVar(value=vision_names[0] if vision_names else "")
        vcb = ttk.Combobox(vis, textvariable=self.vision_provider_var, values=vision_names,
                           state="readonly", width=14)
        vcb.bind("<<ComboboxSelected>>", lambda e: self._on_vision_changed())
        vcb.pack(side="left", padx=(6,0))
        ttk.Label(vis, text="key:").pack(side="left", padx=(8,0))
        self.vision_key_var = tk.StringVar()
        ttk.Entry(vis, textvariable=self.vision_key_var, show="*", width=16).pack(side="left", padx=(4,0))
        self.vision_base_var = tk.StringVar()
        self.vision_model_var = tk.StringVar()
        self._on_vision_changed()

    def _get_vision_provider(self):
        from .providers import PROVIDERS
        name = self.vision_provider_var.get()
        for p in PROVIDERS:
            if p["name"] == name:
                return p
        return None

    def _on_vision_changed(self, *_):
        p = self._get_vision_provider()
        if p:
            self.vision_base_var.set(p["base_url"])
            self.vision_model_var.set(p["model"])

    def _get_provider(self):
        name = self.provider_var.get()
        for p in self._providers:
            if p["name"] == name:
                return p
        return None

    def _on_provider_changed(self, *_):
        p = self._get_provider()
        if not p:
            return
        self.base_var.set(p["base_url"])
        self.model_var.set(p["model"])
        self.key_url_lbl.config(text=p["key_url"])
        self.vision_lbl.config(
            text=("✅ 支持视觉（可识图/视频）" if p["vision"] else "⚠️ 该模型无视觉（识图需要视觉模型）"),
            foreground=("#3fae6a" if p["vision"] else "#c98a2d"))

    def _toggle_show_key(self):
        if self.key_entry.cget("show") == "*":
            self.key_entry.config(show="")
            self.show_key_btn.config(text="🙈")
        else:
            self.key_entry.config(show="*")
            self.show_key_btn.config(text="👁")

    def _test_conn(self):
        api_key = self.key_var.get().strip()
        if not api_key:
            messagebox.showwarning("未填 key", "请先填 API Key 再测试")
            return
        base = self.base_var.get().strip()
        model = self.model_var.get().strip()
        self.conn_lbl.config(text="测试中…", foreground="#888")
        threading.Thread(
            target=self._test_conn_work, args=(api_key, base, model),
            daemon=True).start()

    def _test_conn_work(self, key, base, model):
        try:
            from .ai import _call_chat
            _call_chat([{"role": "user", "content": "ping"}], key, base, model, timeout=25)
            self.root.after(0, lambda: self.conn_lbl.config(
                text="✅ 连接成功，key 有效", foreground="#3fae6a"))
        except Exception as e:
            self.root.after(0, lambda: self.conn_lbl.config(
                text=f"❌ 失败：{str(e)[:60]}", foreground="#d04848"))

    def _pick(self):
        if self.busy: return
        f = filedialog.askopenfilename(title="选择微信导出 zip",
                filetypes=[("Zip", "*.zip"), ("所有文件", "*.*")])
        if f:
            self.zip_var.set(f)

    def _go(self):
        if self.busy: return
        src = self.zip_var.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror("未选文件", "请先选择微信导出的 zip 文件"); return
        self.busy = True
        self.btn_go.config(state="disabled", text="处理中…")
        self.status.set("开始处理…")
        threading.Thread(target=self._work, args=(src,), daemon=True).start()

    def _work(self, src):
        try:
            res = run_summary(
                src,
                compress=self.compress_on.get(),
                keywords=None,
                theme={"深色":"dark","浅色":"light","极简":"minimal"}.get(self.theme.get(), "dark"),
                ai_modes=["essence","disputes","actions"] if self.ai_on.get() else None,
                api_key=self.key_var.get().strip() or os.environ.get("DEEPSEEK_API_KEY",""),
                api_base=self.base_var.get().strip() or "https://api.deepseek.com",
                model=self.model_var.get().strip() or "deepseek-chat",
                describe_images=self.vision_on.get(),
                vision_key=self.vision_key_var.get().strip() or "",
                vision_base=self.vision_base_var.get().strip() or "",
                vision_model=self.vision_model_var.get().strip() or "",
            )
            self.root.after(0, lambda: self._done(res))
        except Exception as e:
            self.root.after(0, lambda: self._fail(e))

    def _done(self, res):
        self.busy = False
        self.btn_go.config(state="normal", text="生成思维导图 🚀")
        w = "".join(f"\n· {x}" for x in res["warnings"])
        msg = (f"✅ 完成！\n\n"
               f"会话：{res['chat_name']}\n"
               f"消息：{res['message_count']} 条，{res['senders_count']} 位成员{w}\n\n"
               f"已保存：\n{res['out_file']}\n\n是否立即打开？")
        self.status.set(f"完成：{os.path.basename(res['out_file'])}")
        if messagebox.askyesno("成功", msg):
            webbrowser.open("file:///" + res["out_file"].replace("\\", "/"))

    def _fail(self, e):
        self.busy = False
        self.btn_go.config(state="normal", text="生成思维导图 🚀")
        self.status.set("出错了")
        messagebox.showerror("出错", f"{e}")


def main():
    import tkinter as tk
    root = tk.Tk()
    app = WeChatSummaryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

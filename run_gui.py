#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信消息总结 · 图形界面入口（Windows 双击本文件或 run_gui.bat）。"""
import sys
import os

# 优先加载项目自带 .venv 的 site-packages（避免 Windows PYTHONPATH 污染导致 Pillow 报错）
_venv_sp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".venv", "Lib", "site-packages")
if os.path.isdir(_venv_sp) and _venv_sp not in sys.path:
    sys.path.insert(0, _venv_sp)

from wx_mindmap.gui import main

if __name__ == "__main__":
    sys.exit(main())

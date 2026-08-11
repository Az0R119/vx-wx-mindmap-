"""
微信消息总结 · 可选压缩模块

当用户勾选"压缩图片"时，把 zip 里的图片压小（长边限幅 + JPEG 质量），
为"之后把这个 zip 喂给 AI 视觉模型"省钱。不压则跳过，不影响出图。

自包含标准库 + Pillow（可选），其他文件字节原样保留。
"""
from __future__ import annotations

import io
import os
import shutil
import zipfile
from typing import Optional

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def compress_zip_images(src_zip: str, dst_zip: str,
                        max_side: int = 1024, quality: int = 80) -> dict:
    """
    把 src_zip 里的图片压小写进 dst_zip；其余文件原样复制。
    返回统计：{files_total, compressed, copied, in_bytes, out_bytes, ratio_pct}
    """
    if not HAVE_PIL:
        raise RuntimeError("未安装 Pillow，无法压缩图片（可跳过压缩直接出图）")

    comp = 0
    copied = 0
    in_bytes = 0
    out_bytes = 0
    total = 0

    with zipfile.ZipFile(src_zip, "r") as zin:
        infos = zin.infolist()
        total = len(infos)
        tmp = dst_zip + ".tmp"
        try:
            with zipfile.ZipFile(src_zip, "r") as zin, \
                 zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                for i in infos:
                    ext = os.path.splitext(i.filename)[1].lower()
                    raw = zin.read(i.filename)
                    in_bytes += len(raw)
                    if ext in IMAGE_EXTS:
                        try:
                            nb = _compress_bytes(raw, max_side, quality)
                        except Exception:
                            nb = raw
                        if len(nb) < len(raw):
                            comp += 1
                            out_bytes += len(nb)
                            zout.writestr(i, nb)
                        else:
                            copied += 1
                            out_bytes += len(raw)
                            zout.writestr(i, raw)
                    else:
                        copied += 1
                        out_bytes += len(raw)
                        zout.writestr(i, raw)
            shutil.move(tmp, dst_zip)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    return {
        "files_total": total,
        "compressed": comp,
        "copied": copied,
        "in_bytes": in_bytes,
        "out_bytes": out_bytes,
        "ratio_pct": round(out_bytes / in_bytes * 100, 1) if in_bytes else 0,
    }


def _compress_bytes(raw: bytes, max_side: int, quality: int) -> bytes:
    im = Image.open(io.BytesIO(raw))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > max_side:
        r = max_side / max(w, h)
        im = im.resize((int(w * r), int(h * r)), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True,
            progressive=True, exif=b"")
    return out.getvalue()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工具在独立套件与作者目录共用的路径、中文字体定位。"""

import os
from functools import lru_cache
from pathlib import Path


def get_suite_root(start=None):
    here = Path(start or __file__).resolve()
    if not here.is_dir():
        here = here.parent
    parents = (here, *here.parents)
    for root in parents:
        if (root / "skills").is_dir() and any(
            (root / name).is_dir() for name in ("指令", "指令模板_v3")
        ):
            return str(root)
    for root in parents:
        candidate = (root / "13_内容复盘" / "YouTube" / "我的频道全套数据"
                     / "06_制作对话与决策" / "00_视频生产流程规范_v1")
        if (candidate / "skills").is_dir() and any(
            (candidate / name).is_dir() for name in ("指令", "指令模板_v3")
        ):
            return str(candidate)
    raise FileNotFoundError("找不到套件根目录：需包含 skills/ 及 指令/ 或 指令模板_v3/")


def get_instruction_dir(root=None):
    root = Path(root or get_suite_root())
    for name in ("指令", "指令模板_v3"):
        candidate = root / name
        if candidate.is_dir():
            return str(candidate)
    raise FileNotFoundError(f"找不到指令目录：{root}（指令/ 或 指令模板_v3/）")


def get_reference_library():
    root = Path(get_suite_root())
    local = root / "对标库"
    if local.is_dir():
        return str(local)
    here = Path(__file__).resolve().parent
    if here.name == "09 工具":
        legacy = here.parent / "12_视频拆解内化" / "对标库"
        if legacy.is_dir():
            return str(legacy)
    return str(local)


def _font_candidates(bold):
    names = ("VIDEO_FLOW_FONT_BOLD", "VIDEO_FLOW_FONT") if bold else ("VIDEO_FLOW_FONT",)
    for name in names:
        if os.environ.get(name):
            yield os.path.expandvars(os.path.expanduser(os.environ[name]))
    win = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if win:
        for name in (("msyhbd.ttc", "msyh.ttc", "simhei.ttf", "simsun.ttc") if bold
                     else ("msyh.ttc", "simhei.ttf", "simsun.ttc")):
            yield str(Path(win) / "Fonts" / name)
    for base in (Path("/usr/share/fonts/opentype/noto"), Path("/usr/share/fonts/truetype/noto"),
                 Path("/usr/share/fonts/truetype/wqy"), Path.home() / ".local/share/fonts",
                 Path("/System/Library/Fonts"), Path("/Library/Fonts")):
        for name in (("NotoSansCJK-Bold.ttc", "NotoSansCJK-Regular.ttc", "wqy-zenhei.ttc",
                      "PingFang.ttc", "STHeiti Medium.ttc") if bold else
                     ("NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.ttf", "wqy-zenhei.ttc",
                      "PingFang.ttc", "STHeiti Light.ttc")):
            yield str(base / name)


@lru_cache(maxsize=64)
def get_font(size, bold=False):
    from PIL import ImageFont

    for candidate in _font_candidates(bold):
        if not Path(candidate).is_file():
            continue
        try:
            font = ImageFont.truetype(candidate, size)
            missing = font.getmask("\u0378")
            signature = (missing.size, bytes(missing))
            if all((mask.size, bytes(mask)) != signature and mask.getbbox()
                   for mask in (font.getmask(c) for c in "视频体检单工序")):
                return font
        except (OSError, ValueError):
            continue
    raise RuntimeError("找不到可用中文字体，无法生成必需图片。请安装微软雅黑、Noto Sans CJK、"
                       "文泉驿或苹方，或设置 VIDEO_FLOW_FONT / VIDEO_FLOW_FONT_BOLD 为中文字体文件路径。")

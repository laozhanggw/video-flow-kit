#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
体检.py —— 六段一张图。人不记参数，只给一个文件夹。

用法（两种都行）：
    python 体检.py "…\\V01_la_casa_del_sueno"
    python 体检.py "…\\20261023_B0001_la_casa_del_sueno"   批次目录会自动取最新 V

输出：
    <版本目录>\\_验收\\体检单.png     一张图，六行
    终端同时打印六行，AI 可以直接复述给人

退出码：0 六段全过 / 1 有不过 / 2 有段还没做
"""
import os
import re
import sys
import glob
import subprocess
from datetime import datetime

from PIL import Image, ImageDraw
from pipeline_runtime import get_font, get_reference_library

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(HERE, "Pipeline.py")
REPO_ROOT = get_reference_library()

BG = (250, 250, 250)
INK = (28, 28, 28)
SUB = (110, 110, 110)
LINE = (222, 222, 222)
GREEN = (34, 139, 58)
RED = (198, 40, 40)
AMBER = (196, 132, 0)
GRAY = (152, 152, 152)


def font(sz, bold=False):
    return get_font(sz, bold)


LOG = os.path.join(HERE, "_上次检查日志.txt")
LEGACY_LIST = os.path.join(REPO_ROOT, "_legacy.txt")


def legacy_ids():
    """旧库编号：这批是在加新字段之前拆的，①不过只标灰、不判红"""
    try:
        with open(LEGACY_LIST, encoding="utf-8", errors="replace") as f:
            return [x.strip() for x in f.read().splitlines()
                    if x.strip() and not x.strip().startswith("#")]
    except Exception:
        return []


def run(args):
    """跑 Pipeline 的一条检查，返回 (退出码, 输出文本, 日志文本)"""
    try:
        p = subprocess.run([sys.executable, PIPELINE] + args,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
        out = (p.stdout or "") + (p.stderr or "")
        log = ""
        try:
            with open(LOG, encoding="utf-8", errors="replace") as f:
                log = f.read()
        except Exception:
            pass
        return p.returncode, out, log
    except Exception as e:
        return 9, str(e), ""


def first_reason(out, log=""):
    """从检查输出/日志里抽第一句人话原因（四种格式都认）"""
    text = log or out
    lines = [x.strip() for x in text.splitlines()]

    for ln in lines:
        if ln.startswith("×"):
            t = ln.lstrip("×").strip(" ·—-")
            if t:
                return t

    for ln in lines:
        if "FAIL" in ln:
            t = re.sub(r"\s{2,}", " ", ln.split("FAIL")[0]).strip(" ·—-")
            if t:
                return t

    for ln in lines:
        if ln.startswith("没找到"):
            return ln.strip(" =")

    for ln in lines:
        if "不通过" in ln and ("·" in ln or "-" in ln):
            t = ln.split("·")[-1].split("-")[-1].strip(" ·—-")
            if t and "必过项" not in t:
                return t

    for ln in lines:
        if ln.startswith("[红灯]"):
            return ln.replace("[红灯]", "").strip(" ·—-")
    return ""


def polish(s):
    """把机器口吻改成人的话"""
    if not s:
        return s
    m = re.match(r"^(.+?)\s+(\d+/\d+)\s*=\s*(\d+)$", s)
    if m:
        return "%s 只有 %s（要 %s）" % (m.group(1), m.group(2), m.group(3))
    m = re.match(r"^(.+?)\s+(\d+\s*种|\d+\s*个|\d+\s*项|\d+\.?\d*\s*秒)\s*=\s*(\S+)$", s)
    if m:
        return "%s %s（要求 %s）" % (m.group(1), m.group(2), m.group(3))
    s = s.replace(" —— ", "：")
    if ("≥" in s or "≤" in s) and "要求" not in s:
        s = re.sub(r"\s+(≥|≤)\s+", r"，要求 \1 ", s, count=1)
    return s


def is_missing(out, log):
    """这些措辞说明「还没做」，不是「不合格」"""
    t = (log or "") + (out or "")
    if "×" in t or "FAIL" in t:
        return False
    marks = ["还没有可检查的交付物", "不存在，跳过", "找不到设定书",
             "这一段还没有", "还没有生成"]
    return any(m in t for m in marks)


def find_project(start):
    """从任意一层往上找「项目总文件夹」：含 01_拆解 或 名字像 20261024_B0006_xxx 的那层"""
    cur = os.path.abspath(start)
    for _ in range(6):
        if os.path.isdir(os.path.join(cur, "01_拆解")):
            return cur
        if re.search(r"\d{8}_B\d{4}_", os.path.basename(cur)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def resolve(path):
    """解析成：版本目录、拆解目录、基准文件、成片（新结构优先，旧结构兜底）"""
    path = path.strip().strip('"').strip("'")
    if os.path.isfile(path):
        video = path if path.lower().endswith((".mp4", ".mov", ".mkv")) else None
        path = os.path.dirname(path)
    else:
        video = None

    project = find_project(path)

    # 版本目录：传入的是版本就用它，否则在 02_复刻\ 或当前层找最新的 V*
    ver = None
    if os.path.exists(os.path.join(path, "00_版本设定书.md")):
        ver = path
    else:
        search_root = os.path.join(project, "02_复刻") if project else path
        cands = [d for d in glob.glob(os.path.join(search_root, "V*")) if os.path.isdir(d)
                 and os.path.exists(os.path.join(d, "00_版本设定书.md"))]
        if cands:
            ver = sorted(cands)[-1]
    if ver is None:
        ver = path

    # 拆解目录：新结构 <项目>\01_拆解；旧结构 12_视频拆解内化\对标库\B####_*
    repo, baseline = None, None
    if project:
        cand = os.path.join(project, "01_拆解")
        if os.path.isdir(cand):
            repo = cand
    if repo is None:
        m = re.search(r"B(\d{4})", path)
        if m:
            for d in glob.glob(os.path.join(REPO_ROOT, "B" + m.group(1) + "_*")):
                if os.path.isdir(d):
                    repo = d
                    break
    if repo:
        bp = os.path.join(repo, "03_整片拆解.md")
        baseline = bp if os.path.exists(bp) else None

    if not video:
        for pat in ("最终的.mp4", "成品.mp4", "*.mp4"):
            hit = glob.glob(os.path.join(ver, pat))
            if hit:
                video = sorted(hit)[0]
                break
    if not video and project:
        hit = glob.glob(os.path.join(project, "03_成片", "*.mp4"))
        if hit:
            video = sorted(hit)[0]

    return ver, repo, baseline, video


def main():
    if len(sys.argv) < 2:
        print('用法： python 体检.py "版本文件夹或批次文件夹"')
        return 2

    ver, repo, baseline, video = resolve(sys.argv[1])
    base_args = []
    if baseline:
        base_args = ["--基准", baseline]

    checks = []

    if repo:
        rc, out, log = run(["查", "拆解", "--对标库", repo])
        checks.append(("① 拆解", rc, out, log, "四份产物、占比、情绪弧、三段式"))
    else:
        checks.append(("① 拆解", 2, "没有找到这一版对应的对标库目录", "", ""))

    for name, stage in (("② 设定书", "设定书"), ("③ 开头", "开头"),
                        ("④ 小分镜", "分镜"), ("⑤ 生产单元", "单元")):
        rc, out, log = run(["查", stage, "--版本", ver] + base_args)
        checks.append((name, rc, out, log, ""))

    if video:
        rc, out, log = run(["查", "成片", "--视频", video])
        checks.append(("⑥ 成片", rc, out, log, ""))
    else:
        checks.append(("⑥ 成片", 2, "还没有生成成片", "", ""))

    # ---- 判定 ----
    legacy = any(os.path.basename(repo or "").startswith(x) for x in legacy_ids())
    rows = []
    fail_idx = []
    gray = 0
    for i, (name, rc, out, log, hint) in enumerate(checks):
        if rc == 0:
            state, color = "通过", GREEN
            reason = hint
        elif rc == 2 or is_missing(out, log):
            state, color = "还没做", GRAY
            reason = hint or "这一段还没有产物"
            gray += 1
        elif i == 0 and legacy:
            state, color = "旧版未含新字段", GRAY
            reason = polish(first_reason(out, log)) or "旧库在加新字段之前拆的"
            gray += 1
        else:
            state, color = "不过", RED
            reason = polish(first_reason(out, log)) or "有不合格项"
            fail_idx.append(i + 1)
        rows.append((name, state, color, reason[:44]))

    # ---- 画图 ----
    W, H = 1320, 132 + 96 * 6 + 118
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.text((48, 38), "视频体检单", font=font(38, True), fill=INK)
    d.text((48, 88), os.path.basename(ver) + "　·　" + datetime.now().strftime("%m-%d %H:%M"),
           font=font(20), fill=SUB)
    d.line([(48, 122), (W - 48, 122)], fill=LINE, width=2)

    y = 126
    for name, state, color, reason in rows:
        d.ellipse([(52, y + 24), (76, y + 48)], fill=color)
        d.text((94, y + 16), name, font=font(30, True), fill=INK)
        d.text((300, y + 20), state, font=font(28, True), fill=color)
        if reason:
            rx = max(430, 300 + int(d.textlength(state, font=font(28, True))) + 18)
            d.text((rx, y + 24), reason, font=font(21), fill=(90, 90, 90))
        d.line([(48, y + 86), (W - 48, y + 86)], fill=(238, 238, 238), width=1)
        y += 96

    # ---- 结论 ----
    if len(fail_idx) == 0 and gray == 0:
        head = "六段都过了。可以生成。"
        tail = "但记住：机器只保证「没走偏」，像不像还得你自己并排看一遍。"
        hc = GREEN
    elif len(fail_idx) == 0:
        head = "已经做的都过了，还有 %d 段没做。" % gray
        tail = "接着做下一段就行，不用回头改。"
        hc = AMBER
    elif gray >= 3 and len(fail_idx) <= 1:
        head = "这条片子才刚开始，产物还不全。"
        tail = "先做到第 %d 段，再回来看这一页。" % (6 - gray + 1)
        hc = AMBER
    elif fail_idx[0] == 6:
        head = "结构全过了，卡在成片。"
        tail = "回去让「生产单元」那个对话框重做结尾那一盒。"
        hc = AMBER
    else:
        seg = "、".join("第%d段" % i for i in fail_idx)
        head = "卡在 %s。" % seg
        tail = "只改这几段，其余不用管。改完再让我看一次。"
        hc = RED

    d.text((48, H - 100), head, font=font(30, True), fill=hc)
    d.text((48, H - 56), tail, font=font(21), fill=SUB)

    out_dir = os.path.join(ver, "_验收")
    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, "体检单.png")
    img.save(out_png)

    # ---- 终端也打一遍，AI 可直接复述 ----
    print()
    for name, state, color, reason in rows:
        print("  %-10s %-6s %s" % (name, state, reason))
    print()
    print("  " + head + " " + tail)
    print("  图： " + out_png)
    return 0 if not fail_idx else (1 if any(r[1] == "不过" for r in rows) else 2)


if __name__ == "__main__":
    sys.exit(main())

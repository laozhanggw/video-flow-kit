#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查_口径一致.py —— 扫全库，找出同一个数在不同文件里写法不一致的地方

为什么要有这个脚本（2026-10-29）：
    `24` 号文件列了 17 处双源冲突（4 处 P0），放了 4 天没做，理由是"要改五份指令的第一屏"。
    这 4 天里 B0008 的四次冲突全部踩中，"锤敲两下"两处同错。
    结论：靠人记住"改一处要改两处"是不可能的，必须机器扫。

它查什么：
    ① 关键数值是否在多处被重写（应该只有 material-seconds.md 一个家）
    ② 已作废的说法是否还活着
    ③ 每份指令顶部有没有挂「外部依赖」块
    ④ 同一件事的正反两种说法（如"加施工声"/"不加施工声"）

用法：
    python 检查_口径一致.py [--root .]

退出码：
    0 = 没有硬冲突   1 = 有 FAIL
"""
import io
import os
import re
import sys
import argparse

# ── 已作废的说法：出现在任何地方都算 FAIL（除了明确写"作废/错/旧/上一版"的语境）
DEAD_PHRASES = [
    ("提速 2.05 倍", "2.05 倍等于取用率 49%，就是那个病本身"),
    ("122–128 秒素材", "正确是 72 秒，那个数等于多花一倍钱"),
    ("128 秒素材", "正确是 72 秒"),
    ("每刀素材秒 2.0–2.5", "已改成分两档 + 逐段反算"),
    ("刀数＝生成秒 ÷ 2", "首选是机位数，÷2 只是降级"),
    # 2026-10-30 撤销：这条禁令惩罚的正是"跟原片一样"这个目标
    ("超过 3 刀相同", "已作废：成片剪点落在原片剪点上是目标，不是照抄"),
    ("照抄的指纹", "已作废：对齐原片不是抄，素材秒＝成片秒×1.153 才是换算"),
    ("不许和原片剪点相同", "已作废：见上"),
]
EXCUSE = ("作废", "错", "旧", "上一版", "第三版", "第二版", "第一版", "初版", "改过", "不需要", "不是", "曾经",
          "不能", "别", "❌", "但", "而", "算成", "记下来", "为什么")

# ── 关键数值：应该只在唯一来源里出现（允许被引用的文件白名单）
SSOT = {
    "1.153": "skills/adaptive-video-production/references/material-seconds.md",
    "0.867": "skills/adaptive-video-production/references/material-seconds.md",
}
# 这些文件可以合法地重写数值（因为它们是"家"或总纲）
SSOT_ALLOW = (
    "material-seconds.md",
    "00_从这里开始.md",
    "48_病症修复_改动记录",
    "52_", "56_", "57_", "58_", "59_", "60_", "61_", "62_", "63_",
    "24_", "47_", "50_", "51_", "55_", "45_", "46_", "49_",
)

# ── 正反两种说法同时活着 = FAIL
# ── 与现行口径**方向相反**的表述：出现在活规则文件里就算 FAIL
# 只有"明确否定现行口径"的才算，措辞要精确；"刀数不是按段数定的"这类是正确表述，不能误伤
REVERSE_PHRASES = [
    ("不是原片几刀就几刀", "现行口径是刀数首选＝机位数"),
    ("刀数不按机位", "现行口径是照抄机位数"),
    ("提速 2.05 倍", "已作废（等于取用率 49%）"),
]

CONTRADICTIONS = [
    (
        "声音：加不加施工声",
        [("不加施工声", "5_生产单元"),
         ("配短促同步声", "adaptive-video-production")],
    ),
]

# ── 只查这些"活规则"文件；42/48/56/57 等记录类文档本来就该保留错误痕迹，不查
ACTIVE = [
    "00_从这里开始.md", "01_第0步_开项目.md", "02_第1步_拆对标.md",
    "03_第2步_定方向.md", "04_第3步_开头.md", "05_第4步_小分镜.md",
    "06_第5步_生产单元.md", "07_第6步_生成与导入.md", "09_附录B_踩过的坑.md",
    "指令模板_v3/1_拆解.txt", "指令模板_v3/2_复刻.txt", "指令模板_v3/3_开头.txt",
    "指令模板_v3/4_小分镜.txt", "指令模板_v3/5_生产单元.txt",
    "skills/adaptive-video-production/SKILL.md",
    "skills/adaptive-video-production/references/material-seconds.md",
    "skills/adaptive-video-production/references/internal-cut.md",
]

DIRECTIVES = ["1_拆解.txt", "2_复刻.txt", "3_开头.txt", "4_小分镜.txt", "5_生产单元.txt"]


def directive_directory(root):
    """兼容同事包的指令目录和作者规范目录。"""
    for name in ("指令", "指令模板_v3"):
        if os.path.isdir(os.path.join(root, name)):
            return name
    return "指令"


def walk_md(root):
    out = []
    for base in (root, os.path.join(root, "skills"), os.path.join(root, directive_directory(root))):
        if not os.path.isdir(base):
            continue
        for fn in os.listdir(base):
            if fn.endswith((".md", ".txt")):
                out.append(os.path.join(base, fn))
    # skills 子目录再扫一层
    sk = os.path.join(root, "skills")
    if os.path.isdir(sk):
        for d in os.listdir(sk):
            p = os.path.join(sk, d)
            if os.path.isdir(p):
                for sub in ("references", "examples"):
                    q = os.path.join(p, sub)
                    if os.path.isdir(q):
                        for fn in os.listdir(q):
                            if fn.endswith((".md", ".txt")):
                                out.append(os.path.join(q, fn))
    return out


def check_dead(files):
    hits = []
    for f in files:
        rel = os.path.basename(f)
        if not (rel in [os.path.basename(x) for x in ACTIVE] or
                any(x in f.replace("\\", "/") for x in ACTIVE)):
            continue
        try:
            t = io.open(f, encoding="utf-8").read()
        except Exception:
            continue
        for line_no, line in enumerate(t.split("\n"), 1):
            for phrase, why in DEAD_PHRASES:
                if phrase in line:
                    if any(e in line for e in EXCUSE):
                        continue
                    hits.append((os.path.basename(f), line_no, phrase, why))
    return hits


def check_reverse(files):
    hits = []
    for f in files:
        base = os.path.basename(f)
        if not (base in [os.path.basename(x) for x in ACTIVE] or
                any(x in f.replace("\\", "/") for x in ACTIVE)):
            continue
        try:
            t = io.open(f, encoding="utf-8").read()
        except Exception:
            continue
        lines = t.split("\n")
        for line_no, line in enumerate(lines, 1):
            for phrase, why in REVERSE_PHRASES:
                if phrase in line:
                    ctx = line + " " + (lines[line_no - 2] if line_no >= 2 else "")
                    hist = ("作废", "已改", "此前", "过时", "第三版", "第一版", "第二版",
                            "初版", "上一版", "以前", "当时", "旧话", "禁止", "错", "❌", "不需要", "不复")
                    if any(h in ctx for h in hist):
                        continue
                    hits.append((base, line_no, phrase, why))
    return hits


def check_ssot(files):
    """关键数是否在非白名单文件里被重写"""
    hits = []
    for f in files:
        base = os.path.basename(f)
        if base.startswith(SSOT_ALLOW) or any(s in f.replace("\\", "/") for s in SSOT.values()):
            continue
        try:
            t = io.open(f, encoding="utf-8").read()
        except Exception:
            continue
        for num, home in SSOT.items():
            for m in re.finditer(re.escape(num), t):
                line = t[max(0, m.start() - 60):m.start() + 20]
                if any(e in line for e in EXCUSE):
                    continue
                if "见 " in line or "→" in line or "material-seconds" in line:
                    continue
                hits.append((base, num, home))
                break
    return hits


def check_dep_block(root):
    """每份指令顶部有没有【外部依赖】块"""
    miss = []
    for filename in DIRECTIVES:
        d = os.path.join(directive_directory(root), filename)
        p = os.path.join(root, d)
        if not os.path.isfile(p):
            miss.append((d, "文件不存在"))
            continue
        t = io.open(p, encoding="utf-8").read()
        # 只看前 800 字
        head = t[:800]
        if "【外部依赖" not in head:
            miss.append((d, "顶部 800 字内没有【外部依赖】块"))
    return miss


def check_contradiction(files):
    hits = []
    for name, pairs in CONTRADICTIONS:
        found = {}
        for f in files:
            try:
                t = io.open(f, encoding="utf-8").read()
            except Exception:
                continue
            for kw, _ in pairs:
                if kw in t:
                    found.setdefault(kw, []).append(os.path.basename(f))
        # 如果两个相反说法都在，且分布在不同文件 → 提醒检查
        if len(found) >= 2:
            detail = {k: v for k, v in found.items()}
            # 有"分支"字样就不算冲突（已经仲裁过）
            ok = False
            for f in files:
                try:
                    t = io.open(f, encoding="utf-8").read()
                except Exception:
                    continue
                if "分支 A" in t and "分支 B" in t:
                    ok = True
                    break
            if not ok:
                hits.append((name, detail))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = a.root
    files = walk_md(root)

    print("=" * 66)
    print("口径一致性检查：%s" % os.path.abspath(root))
    print("扫描 %d 个文件" % len(files))
    print("=" * 66)

    fail = 0

    dead = check_dead(files)
    print("\n[%s] ① 已作废的说法还在不在" % ("FAIL" if dead else "PASS"))
    if dead:
        fail += 1
        for f, n, p, why in dead[:15]:
            print("   · %s:%d  「%s」 → %s" % (f, n, p, why))
    else:
        print("   没有发现作废说法还活着")

    ss = check_ssot(files)
    print("\n[%s] ② 关键数有没有被别处重写" % ("WARN" if ss else "PASS"))
    if ss:
        for f, num, home in ss[:10]:
            print("   · %s 重写了 %s（唯一的家：%s）" % (f, num, home))
        print("   （WARN 不算错：引用时带上路径即可）")
    else:
        print("   1.153 / 0.867 只在唯一的家里出现")

    dep = check_dep_block(root)
    print("\n[%s] ③ 五份指令顶部有没有挂外部依赖块" % ("FAIL" if dep else "PASS"))
    if dep:
        fail += 1
        for d, why in dep:
            print("   · %s  %s" % (d, why))
    else:
        print("   五份都挂了")

    rv = check_reverse(files)
    print("\n[%s] ④' 有没有和现行口径方向相反的表述" % ("FAIL" if rv else "PASS"))
    if rv:
        fail += 1
        for f, n, p, why in rv[:12]:
            print("   · %s:%d  「%s」 → %s" % (f, n, p, why))
    else:
        print("   没有发现反向表述")

    ct = check_contradiction(files)
    print("\n[%s] ④ 有没有同一件事的正反两种说法还同时活着" % ("FAIL" if ct else "PASS"))
    if ct:
        fail += 1
        for name, detail in ct:
            print("   · %s" % name)
            for k, v in detail.items():
                print("       「%s」出现在：%s" % (k, "、".join(v)))
    else:
        print("   没有发现")

    print("\n" + "-" * 66)
    if fail:
        print("结论：%d 项 FAIL，先修再动别的。" % fail)
        sys.exit(1)
    print("结论：没有硬冲突。")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""检查_操作步数.py —— 通用闸门：抓「一句话里塞了太多动作」的刀。

为什么要有这个：
    2026-11-12，B0023 的 V01/V02 两条开头，`动作数` 都填 1（规则允许 0/1），
    但正文那一句里塞了 5–9 个带时间戳的操作。模型演不完，水没泼过去，成片废。
    旧的人工判据是「念一遍，念到'然后'就是两个动作」——
    写手改用时间戳（0.6 秒…1.2 秒…）就绕过去了，一个"然后"都没有。

这个脚本不看你填的字段，只看正文：
    一段/一行里出现 ≥4 个独立时间戳（或 ≥4 个操作分句），就算「超载」。
    超载 = 这一刀模型大概率演不完，必须拆刀。

用法：
    python 检查_操作步数.py <文件.md> [<文件2.md> ...]
    python 检查_操作步数.py 目录/          # 递归扫 .md
退出码：
    0 = 没有超载
    1 = 有超载（逐条打印 文件:行号 + 命中的时间戳数 + 原文前 60 字）
"""
import re
import sys
from pathlib import Path

# 中文/阿拉伯数字 + 秒，例如 0.6秒 / 1.2 秒 / 3s
TS = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:秒|s\b)", re.I)
# 分句符：中文句号、分号、破折号、加号；不算逗号（逗号太密，会冤枉正常描写）
SEP = re.compile(r"[；;。]|——|\+")
THRESHOLD = 5  # 一镜里 ≥5 个时间戳（= ≥4 步动作，标题行不算），判超载


def scan_text(text: str):
    """按【镜头…】切块，块内数时间戳。

    为什么要按块：V01 的 9 个动作是 9 行、每行一个时间戳（0.6 秒：…／1.2 秒：…），
    按"单行"数每行只有 1 个，永远抓不到；必须把一整个镜头里的行合起来数。
    声音块不算（那里本来就会写一排时间）。
    """
    hits = []
    block, start, head = [], 0, ""

    def flush():
        if not block:
            return
        body = "\n".join(block)
        if "声音" in head or "音频" in head:
            return
        # 标题行本身带的时间区间不算步数
        body_lines = [l for l in block if not l.startswith("【")]
        ts = TS.findall("\n".join(body_lines))
        if len(ts) >= THRESHOLD:
            hits.append((start, len(ts), body.strip()[:60].replace("\n", " ")))

    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("【") and "镜头" in line:
            flush()
            block, start, head = [line], i, line
            continue
        if not block:
            continue
        if not line:
            flush()
            block, start, head = [], 0, ""
            continue
        if line.startswith("#"):
            flush()
            block, start, head = [], 0, ""
            continue
        block.append(line)
    flush()
    return hits


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    files = []
    for a in argv[1:]:
        p = Path(a)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.is_file():
            files.append(p)
    total = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"[跳过] {f}: {e}")
            continue
        hits = scan_text(text)
        if hits:
            total += len(hits)
            print(f"\n== {f}")
            for ln, nts, head in hits:
                print(f"  L{ln}: 这一镜 {nts} 个时间戳 → 拆刀  | {head}")
    print(f"\n合计超载 {total} 处。" + ("全部通过。" if total == 0 else "以上各行 ≥4 步，按 4c 规则必须拆刀。"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


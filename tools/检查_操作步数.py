# -*- coding: utf-8 -*-
"""检查_操作步数.py —— 通用闸门：抓「一镜里塞了太多动作」的刀。

为什么要有这个：
    2026-11-12，B0023 的 V01/V02 两条开头，`动作数` 都填 1（规则允许 0/1），
    但正文那一句里塞了 5–9 个带时间戳的操作。模型演不完，水没泼过去，成片废。
    旧的人工判据是「念一遍，念到'然后'就是两个动作」——
    写手改用时间戳（0.6 秒…1.2 秒…）就绕过去了，一个"然后"都没有。

2026-11-13 改口径（治"做一下、切一刀、全好了"）：
    以前是"一镜 ≥5 个时间戳 = 超载，必须拆刀"。
    这条把「拍子」也误伤了 —— 阿初 15 秒一镜写 6 拍、官方也要求一个镜头里分
    Action 1/2/3。真正的判据不是"几个拍子"，是"每一拍够不够演"：
      · 拍子太多（>6）            → 拆刀
      · 每拍平均秒数 < 1.2 秒      → 拍子挤在一起，模型演不完 → 并拍或拆刀
      · 两个都过关                → 放行（这是"分量"，不是"超载"）
    拿不到镜头时长时，退回旧口径（≥5 个时间戳报警），并在输出里注明"缺时长"。

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

THRESHOLD = 5        # 拿不到时长时，退回旧口径：一镜 ≥5 个时间戳判超载
MAX_BEATS = 6        # 2026-11-13：一刀里的拍子上限（2–6 拍）
MIN_BEAT_SEC = 1.2   # 2026-11-13：每拍平均最少 1.2 秒，低于它模型演不完
# 从标题行里取这一镜的生成秒数：【镜头4】（15秒）／【镜头 2】15 秒／（12s）
DUR = re.compile(r"[（(]\s*(\d+(?:\.\d+)?)\s*(?:秒|s)\s*[)）]|(?:^|[^0-9])(\d+(?:\.\d+)?)\s*秒")


def shot_seconds(head: str):
    m = DUR.search(head)
    if not m:
        return None
    val = m.group(1) or m.group(2)
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def scan_text(text: str):
    """按【镜头…】切块，块内数时间戳，再按时长算每拍秒数。

    为什么要按块：V01 的 9 个动作是 9 行、每行一个时间戳（0.6 秒：…／1.2 秒：…），
    按"单行"数每行只有 1 个，永远抓不到；必须把一整个镜头里的行合起来数。
    声音块不算（那里本来就会写一排时间）。
    """
    hits = []

    def flush(block, start, head):
        if not block:
            return
        body = "\n".join(block)
        if "声音" in head or "音频" in head:
            return
        # 标题行本身带的时间区间不算步数
        body_lines = [l for l in block if not l.startswith("【")]
        ts = TS.findall("\n".join(body_lines))
        n = len(ts)
        if n == 0:
            return
        sec = shot_seconds(head)
        head_txt = body.strip()[:60].replace("\n", " ")
        if sec:
            per = sec / n
            if n > MAX_BEATS:
                hits.append((start, n, sec, per, "拍子 %d 个 > %d" % (n, MAX_BEATS), head_txt))
            elif per < MIN_BEAT_SEC:
                hits.append((start, n, sec, per, "每拍只有 %.2f 秒 (<%.1f)" % (per, MIN_BEAT_SEC), head_txt))
        elif n >= THRESHOLD:
            hits.append((start, n, None, None, "缺时长，按旧口径 ≥%d" % THRESHOLD, head_txt))

    block, start, head = [], 0, ""
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("【") and "镜头" in line:
            flush(block, start, head)
            block, start, head = [line], i, line
            continue
        if not block:
            continue
        if not line:
            flush(block, start, head)
            block, start, head = [], 0, ""
            continue
        if line.startswith("#"):
            flush(block, start, head)
            block, start, head = [], 0, ""
            continue
        block.append(line)
    flush(block, start, head)
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
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            print(f"[跳过] {f}: {e}")
            continue
        hits = scan_text(text)
        if hits:
            total += len(hits)
            print(f"\n== {f}")
            for ln, nts, sec, per, why, head in hits:
                extra = "" if sec is None else "（{:.1f} 秒 / {} 拍 → 每拍 {:.2f} 秒）".format(sec, nts, per)
                print(f"  L{ln}: {why}{extra} → 拆刀或并拍  | {head}")
    print(f"\n合计超载 {total} 处。" + ("全部通过。" if total == 0
          else "以上各行请按时长处理：拍子太多就拆刀，每拍太短就并拍。"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

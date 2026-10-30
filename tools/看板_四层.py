#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看板_四层.py —— 同一根时间轴上，四层纵向对照

  第 1 行  对标拆解的分镜（参照系，不是标准答案）
  第 2 行  我们开头的分镜
  第 3 行  我们整片的小分镜
  第 4 行  生产单元覆盖（一个单元跨多刀，画成横跨的块 + 竖线连到它盖的那几刀）

它查什么
--------
不是查「和对标像不像」——不同是正常的，一样反而同质化。
它查的是**我们自己内部有没有走偏**：

  1. 第 4 行有没有把第 2+3 行的每一刀都盖住（遗漏）
  2. 有没有一刀被两个单元同时盖（重叠）
  3. 每个单元独占多少秒，超过 15 秒装不下（平台单段上限）
  4. 第 2 行末尾是不是正好接上第 3 行开头（T 点对齐）
  5. 第 2+3 行秒数加起来是不是等于成片总时长（秒数守恒）

第 1 行只画成灰条，刻意不做红绿判定。它只回答一个事：
「对标在这个时间点在做 A，我们在做 B」——B 可以完全不同，只要你自己写清了。

用法
----
  看板_四层.py --ref-file ref.csv --head-file head.csv --shots-file shots.csv \
               --units "U01=1-2;U02=3-7;U03=8-12;U04=13-17;U05=18-25" \
               --out 四层.png

  三个 csv 每行：名字,起,止    （也支持 名字,秒 的紧凑写法，会从 0 累加）

  --units 里的数字是「第2行+第3行拼起来」之后的第几刀，从 1 开始。

退出码：0 无内部矛盾 / 1 有 / 2 出错
"""

import argparse
import os
import re
import sys
from PIL import Image, ImageDraw
from pipeline_runtime import get_font

BG = (253, 253, 253)
INK = (32, 32, 32)
GRAY = (145, 145, 145)
GRID = (226, 226, 226)
C_REF = (222, 222, 222)
C_HEAD = (247, 214, 170)
C_SHOT = (196, 219, 238)
C_UNIT = (176, 212, 186)
C_BAD = (198, 56, 56)
C_WARN = (210, 140, 40)
C_OK = (42, 132, 78)
C_LINK = (168, 196, 176)

def font(sz, bold=True):
    return get_font(sz, bold)


def load(path):
    """每行: 名字,起,止  或  名字,秒"""
    out = []
    t = 0.0
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [x.strip() for x in line.replace('\t', ',').split(',')]
            if len(parts) >= 3:
                try:
                    a, b = float(parts[1]), float(parts[2])
                except ValueError:
                    continue
                out.append((parts[0], a, b))
                t = b
            elif len(parts) == 2:
                try:
                    d = float(parts[1])
                except ValueError:
                    continue
                out.append((parts[0], t, t + d))
                t += d
    return out


def code_of(name):
    """取名字开头的刀号：'N03 冲地缝' → 'N03'；没有就返回 None"""
    m = re.match(r'\s*([A-Za-z]+\d+)', name)
    return m.group(1).upper() if m else None


def parse_units(s, combined=None):
    """两种写法都认：
         U01=1-2            → 第 1 到第 2 刀（按顺序数）
         U01=N01-N02        → 按刀号
       → [(U01, 起始索引1based, 结束索引1based)]
    """
    idx = {}
    if combined:
        for k, (nm, _, _) in enumerate(combined, 1):
            c = code_of(nm)
            if c:
                idx[c] = k

    out = []
    for part in re.split(r'[;；\n]', s or ''):
        part = part.strip()
        if not part or '=' not in part:
            continue
        name, rng = part.split('=', 1)
        name, rng = name.strip(), rng.strip()

        def to_i(tok):
            tok = tok.strip()
            if re.fullmatch(r'\d+', tok):
                return int(tok)
            return idx.get(tok.upper())

        m = re.fullmatch(r'([\w]+)\s*[-–~到至]\s*([\w]+)', rng)
        if m:
            i, j = to_i(m.group(1)), to_i(m.group(2))
        else:
            i = j = to_i(rng)
        if i and j:
            out.append((name, i, j))
    return out


def draw_row(d, x0, y0, w, total, cells, color, label, h=54, show_name=True):
    d.text((x0 - 96, y0 + 14), label, font=font(19), fill=GRAY)
    for name, a, b in cells:
        xa = x0 + w * a / total
        xb = x0 + w * b / total
        if xb - xa < 1.2:
            xb = xa + 1.2
        d.rectangle([xa, y0, xb, y0 + h], fill=color, outline=(255, 255, 255))
        if show_name and xb - xa > 26:
            fs = 14 if xb - xa > 60 else 11
            maxc = max(2, int((xb - xa - 6) / (fs * 0.95)))
            d.text((xa + 3, y0 + h / 2 - fs * 0.7), name[:maxc], font=font(fs, False), fill=INK)
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=(205, 205, 205))
    return y0 + h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref-file', default=None)
    ap.add_argument('--head-file', required=True)
    ap.add_argument('--shots-file', required=True)
    ap.add_argument('--units', required=True)
    ap.add_argument('--title', default='四层对照 · 分镜 ↔ 生产单元')
    ap.add_argument('--out', default='看板_四层.png')
    ap.add_argument('--unit-cap', type=float, default=15.0)
    a = ap.parse_args()

    head = load(a.head_file)
    shots = load(a.shots_file)
    ref = load(a.ref_file) if a.ref_file else []
    combined = head + shots
    units = parse_units(a.units, combined)
    if not combined:
        print('分镜表是空的')
        return 2

    total = max(b for _, _, b in combined)
    ref_total = max((b for _, _, b in ref), default=0.0)
    axis = max(total, ref_total)   # 画图用；两条都放得下，差的那截留空
    reds, warns = [], []

    # 覆盖校验
    cover = [0] * len(combined)
    for uname, i, j in units:
        if i < 1 or j > len(combined) or i > j:
            reds.append(f'{uname} 的刀号 {i}-{j} 超出范围（共 {len(combined)} 刀）')
            continue
        for k in range(i - 1, j):
            cover[k] += 1
    gaps = [k for k, c in enumerate(cover) if c == 0]
    dups = [k for k, c in enumerate(cover) if c > 1]
    if gaps:
        reds.append('没被任何单元盖住：' + '、'.join(combined[k][0] for k in gaps))
    if dups:
        reds.append('被两个以上单元重复盖：' + '、'.join(combined[k][0] for k in dups))

    # 单元秒数
    uinfo = []
    for uname, i, j in units:
        if i < 1 or j > len(combined) or i > j:
            continue
        sec = sum(combined[k][2] - combined[k][1] for k in range(i - 1, j))
        uinfo.append((uname, i, j, sec))
        if sec > a.unit_cap:
            reds.append(f'{uname} 共 {sec:.2f} 秒 > {a.unit_cap:.0f} 秒上限（一段装不下）')

    # 衔接与守恒
    if head and shots:
        gap = shots[0][1] - head[-1][2]
        if abs(gap) > 0.02:
            reds.append(f'衔接断开：开头止于 {head[-1][2]:.2f}s，后段从 {shots[0][1]:.2f}s 起，差 {gap:+.2f}s')
    ssum = sum(b - x for _, x, b in combined)
    if abs(ssum - total) > 0.05:
        reds.append(f'秒数不守恒：Σ分镜 {ssum:.2f} ≠ 总长 {total:.2f}')
    if ref:
        rs = sum(b - x for _, x, b in ref)
        if abs(rs - total) > 0.5:
            warns.append(f'对标总长 {rs:.2f}s，我们 {total:.2f}s，差 {rs-total:+.2f}s（不同是正常的，写清理由即可）')

    # ---- 画 ----
    W = 3000
    ML, MR = 150, 40
    bw = W - ML - MR
    H = 820
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    d.text((ML, 22), a.title, font=font(34), fill=INK)
    d.text((ML, 66), '同一根时间轴，四层对齐看。第 1 行只作参照——我们和对标不同是正常的，'
                      '不算错；红框只标「我们自己内部对不上」。', font=font(18, False), fill=GRAY)

    y = 108
    # 时间刻度
    step = 1 if axis <= 35 else 2
    t = 0
    while t <= axis + 0.01:
        x = ML + bw * t / axis
        d.line([x, y, x, y + 470], fill=GRID)
        d.text((x - 10, y - 22), f'{t:.0f}', font=font(15, False), fill=GRAY)
        t += step

    y1 = draw_row(d, ML, y, bw, axis, ref, C_REF, '对标', h=50)
    y2 = draw_row(d, ML, y1 + 14, bw, axis, head, C_HEAD, '我们开头', h=50)
    y3 = draw_row(d, ML, y2 + 14, bw, axis, shots, C_SHOT, '我们整片', h=50)
    y4 = y3 + 40

    # 单元块 + 竖线
    d.text((ML - 96, y4 + 12), '生产单元', font=font(19), fill=GRAY)
    for uname, i, j, sec in uinfo:
        a0 = combined[i - 1][1]
        b0 = combined[j - 1][2]
        xa = ML + bw * a0 / axis
        xb = ML + bw * b0 / axis
        # 竖线：从被盖的每一刀连下来
        for k in range(i - 1, j):
            cx = ML + bw * (combined[k][1] + combined[k][2]) / 2 / axis
            d.line([cx, y3, cx, y4], fill=C_LINK, width=2)
        d.rectangle([xa, y4, xb, y4 + 46], fill=C_UNIT, outline=(120, 160, 130))
        txt = f'{uname} {sec:.2f}s·{j-i+1}刀'
        if xb - xa > 70:
            d.text((xa + 5, y4 + 12), txt, font=font(15), fill=INK)
        else:
            d.text((xa - 2, y4 - 20), uname, font=font(13, False), fill=INK)
    d.rectangle([ML, y4, ML + bw, y4 + 46], outline=(205, 205, 205))

    # 我们的结尾线（对标还在继续，这截差就是总时长差）
    if axis > total + 0.05:
        xe = ML + bw * total / axis
        d.line([xe, y1, xe, y4 + 46], fill=(200, 60, 60), width=2)
        d.text((xe + 6, y1 - 20), f'我们到此 {total:.2f}s', font=font(15), fill=C_BAD)

    # 缺口标红
    for k in gaps:
        xa = ML + bw * combined[k][1] / axis
        xb = ML + bw * combined[k][2] / axis
        d.rectangle([xa, y4, max(xb, xa + 2), y4 + 46], fill=(250, 220, 220),
                    outline=C_BAD, width=2)

    # ---- 判定 ----
    y = y4 + 78
    d.text((ML, y), '内部一致性', font=font(24), fill=INK)
    y += 36
    stat = (f'分镜 {len(combined)} 刀 / {ssum:.2f} 秒'
            f'　　单元 {len(uinfo)} 个'
            f'　　最长单元 {max((s for *_, s in uinfo), default=0):.2f} 秒'
            f'　　覆盖 {len(combined)-len(gaps)}/{len(combined)} 刀')
    d.text((ML, y), stat, font=font(24), fill=INK)
    y += 40

    if reds:
        d.text((ML, y), f'内部矛盾 {len(reds)} 条（这些是我们的错，和标的不同无关）',
               font=font(21), fill=C_BAD)
        y += 30
        for r in reds[:8]:
            d.text((ML, y), '· ' + r, font=font(19, False), fill=C_BAD)
            y += 26
    else:
        d.text((ML, y), '内部一致：层层对得上，无遗漏无重叠，秒数守恒',
               font=font(21), fill=C_OK)
        y += 28

    if warns:
        for w in warns:
            d.text((ML, y), '· ' + w, font=font(18, False), fill=C_WARN)
            y += 24

    img = img.crop((0, 0, W, min(H, y + 22)))
    img.save(a.out)
    print('已生成：' + os.path.abspath(a.out))
    print(stat)
    for r in reds:
        print('  [内部矛盾] ' + r)
    for w in warns:
        print('  [提示] ' + w)
    return 1 if reds else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)

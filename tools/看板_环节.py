#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看板_环节.py —— 任意环节与对标「按同一把尺子」对格子（事前用，不用等成片）

三种对齐方式，对应三个环节：

  --mode name  （默认）按工序名对齐
      适合：小分镜、生产单元
      对标有、我们没有 → 红框「缺」；我们多出来 → 灰格

  --mode seq   按镜头顺序对齐
      适合：开头（对标 2 镜、我们几镜，一比就露）
      逐个位置比，多的显示「多」，少的显示「缺」，景别不一致标红

  --map        画第三条「工序 → 单元」覆盖条
      适合：生产单元。每个对标工序染色写明落在哪个 U，
      没进盒的留红框「没进盒」；下面按 U 汇总秒数和工序数，
      U 的合计秒数 >15 直接红灯（平台一段最多 15 秒，装不下就是划错了）

用法
----
  python 看板_环节.py --stage 开头 --mode seq \
    --ref "局部:1.10,全景:2.00" --ref-lbl "中景45度,广角后侧" \
    --ours "捡叶:0.97,拢叶:0.87,冲地缝:0.73,刷墙根:0.83" --ours-lbl "中景,中全景,下肢近景,特写" \
    --out 看板_开头.png

  python 看板_环节.py --stage 生产单元 \
    --ref "冲地:1.43,刷墙:1.00" --ours "U02:2.43,U03:9.00" \
    --map "冲地=U02,刷墙=U02" --out 看板_单元.png

退出码：0 全绿 / 1 有红灯 / 2 出错
"""

import argparse
import os
import re
import sys
from PIL import Image, ImageDraw
from pipeline_runtime import get_font

BG = (252, 252, 252)
INK = (30, 30, 30)
GRAY = (150, 150, 150)
CELL = (226, 238, 230)
CELL_EDGE = (140, 185, 155)
MISS_BG = (252, 228, 228)
MISS_EDGE = (206, 70, 70)
EXTRA = (234, 234, 234)
C_BAD = (198, 56, 56)
C_OK = (42, 132, 78)

UPAL = [(198, 222, 240), (246, 222, 186), (214, 232, 200), (236, 210, 232),
        (222, 216, 240), (244, 224, 200), (204, 228, 222), (238, 226, 206)]

def font(sz, bold=True):
    return get_font(sz, bold)


def parse_pairs(s):
    out = []
    for part in re.split(r'[,\uFF0C;；]', s or ''):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'(.+?)\s*[:：=]\s*([\d.]+)\s*$', part)
        if m:
            out.append((m.group(1).strip(), float(m.group(2))))
    return out


def parse_list(s):
    return [x.strip() for x in re.split(r'[,\uFF0C]', s or '') if x.strip()]


def parse_file(p):
    out = []
    with open(p, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = re.match(r'(.+?)[,\t]\s*([\d.]+)\s*$', line)
            if m:
                out.append((m.group(1).strip(), float(m.group(2))))
    return out


def norm(s):
    return re.sub(r'\s+', '', s)


def draw_bar(d, x0, y0, w, cells, total, title, subtitle, h=58):
    """cells: [(label, sec, kind, sub, tint)]"""
    d.text((x0, y0), title, font=font(25), fill=INK)
    d.text((x0 + 150, y0 + 5), subtitle, font=font(18, False), fill=GRAY)
    y = y0 + 36
    x = x0
    for cell in cells:
        label, sec, kind, sub = cell[0], cell[1], cell[2], cell[3]
        tint = cell[4] if len(cell) > 4 else None
        cw = max(2.0, w * sec / total) if total else 2.0
        x2 = min(x + cw, x0 + w)
        if kind == 'miss':
            d.rectangle([x, y, x2, y + h], fill=MISS_BG, outline=MISS_EDGE, width=2)
            if cw > 30:
                d.text((x + 5, y + 8), '缺', font=font(22), fill=MISS_EDGE)
                d.text((x + 5, y + 34), f'{sec:.2f}', font=font(13, False), fill=MISS_EDGE)
            else:
                d.text((x - 2, y - 20), '缺', font=font(18), fill=MISS_EDGE)
        else:
            bg = tint if tint else (EXTRA if kind == 'extra' else CELL)
            ed = (196, 196, 196) if kind == 'extra' else CELL_EDGE
            d.rectangle([x, y, x2, y + h], fill=bg, outline=ed)
            if cw > 52:
                fs = 17 if cw > 100 else 14
                maxc = max(2, int(cw / (fs * 1.05)))
                d.text((x + 4, y + 4), label[:maxc], font=font(fs, False), fill=INK)
                d.text((x + 4, y + 24), f'{sec:.2f}', font=font(13), fill=(90, 90, 90))
                if sub and cw > 84:
                    d.text((x + 4, y + 41), sub[:max(2, int(cw / 12))], font=font(11, False), fill=(115, 115, 115))
            elif cw > 20:
                d.text((x + 2, y + 20), f'{sec:.1f}', font=font(12, False), fill=INK)
        x = x2
    d.rectangle([x0, y, x0 + w, y + h], outline=(200, 200, 200))
    return y + h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', default='本环节')
    ap.add_argument('--mode', choices=['name', 'seq'], default='name')
    ap.add_argument('--ref', default=None)
    ap.add_argument('--ours', default=None)
    ap.add_argument('--ref-file', default=None)
    ap.add_argument('--ours-file', default=None)
    ap.add_argument('--ref-lbl', default=None)
    ap.add_argument('--ours-lbl', default=None)
    ap.add_argument('--map', default=None)
    ap.add_argument('--tol', type=float, default=0.85)
    ap.add_argument('--unit-cap', type=float, default=15.0)
    ap.add_argument('--out', default='看板_环节.png')
    a = ap.parse_args()

    ref = parse_pairs(a.ref) if a.ref else (parse_file(a.ref_file) if a.ref_file else [])
    ours = parse_pairs(a.ours) if a.ours else (parse_file(a.ours_file) if a.ours_file else [])
    is_map = bool(a.map)
    if not ref:
        print('需要 --ref')
        return 2
    if not ours and not is_map:
        print('需要 --ours（有 --map 时可以不给，U 的秒数会从映射里算）')
        return 2
    rl, ol = parse_list(a.ref_lbl), parse_list(a.ours_lbl)

    ref_total = sum(s for _, s in ref)
    ours_total = sum(s for _, s in ours)
    cells, reds = [], []
    covered = len(ref)

    if a.mode == 'seq':
        n = max(len(ref), len(ours))
        for i in range(n):
            r = ref[i] if i < len(ref) else None
            o = ours[i] if i < len(ours) else None
            rlb = rl[i] if i < len(rl) else ''
            olb = ol[i] if i < len(ol) else ''
            if r and o:
                cells.append((o[0], o[1], 'ok', olb))
                if rlb and olb and norm(rlb) != norm(olb):
                    reds.append(f'第{i+1}镜景别不一致：对标「{rlb}」/ 我们「{olb}」')
                if abs(o[1] - r[1]) > max(0.3, r[1] * 0.25):
                    reds.append(f'第{i+1}镜秒数 {o[1]:.2f} vs 对标 {r[1]:.2f}')
            elif o:
                cells.append((o[0], o[1], 'extra', olb))
                reds.append(f'我们多出第{i+1}镜「{o[0]}」（{o[1]:.2f}s）')
            else:
                cells.append((r[0], r[1], 'miss', rlb))
                covered -= 1
                reds.append(f'缺第{i+1}镜「{r[0]}」（对标 {r[1]:.2f}s {rlb}）')
        if len(ours) != len(ref):
            reds.append(f'镜数：对标 {len(ref)} 镜 / 我们 {len(ours)} 镜')
    elif is_map:
        # 单元环节：不按名字比，改成按「工序→盒子」的覆盖来比
        mp0 = {}
        for part in re.split(r'[,\uFF0C;；]', a.map):
            if '=' in part:
                k, v = part.split('=', 1)
                mp0[norm(k.strip())] = v.strip()
        us0 = {}
        for n2, s in ref:
            u = mp0.get(norm(n2))
            if u:
                us0.setdefault(u, [0.0, 0])
                us0[u][0] += s
                us0[u][1] += 1
            else:
                covered -= 1
        for u in sorted(us0):
            cells.append((u, us0[u][0], 'ok', f'{us0[u][1]} 个工序'))
        if not ours:
            ours = [(u, v[0]) for u, v in sorted(us0.items())]
            ours_total = sum(x[1] for x in ours)
    else:
        omap = {norm(n2): (n2, s) for n2, s in ours}
        used = set()

        def find(rn):
            k = norm(rn)
            if k in omap:
                return k
            cand = [kk for kk in omap if kk not in used and (k in kk or kk in k)]
            return cand[0] if len(cand) == 1 else None

        short, miss, fuzzy = [], [], []
        for n2, s in ref:
            k = find(n2)
            if k:
                used.add(k)
                shown, act = omap[k]
                if norm(shown) != norm(n2):
                    fuzzy.append((n2, shown))
                if act < s * a.tol:
                    short.append((n2, act, s))
                cells.append((shown, act, 'ok', ''))
            else:
                miss.append((n2, s))
                covered -= 1
                cells.append((n2, s, 'miss', ''))
        extras = [(omap[k][0], omap[k][1]) for k in omap if k not in used]
        for n2, s in extras:
            cells.append((n2, s, 'extra', ''))
        if miss:
            reds.append('缺：' + '、'.join(f'{x}（{s:.2f}s）' for x, s in miss))  # noqa
        if short:
            reds.append('秒数不够：' + '、'.join(f'{x} {v:.2f}<{s:.2f}' for x, v, s in short[:8]))
        if extras:
            reds.append('多出来：' + '、'.join(f'{x}（{s:.2f}s）' for x, s in extras[:8]))
        if fuzzy:
            reds.append('命名不一致：' + '、'.join(f'{x}→{y}' for x, y in fuzzy[:6]))

    ratio_n = covered / len(ref) if ref else 0
    ratio_s = ours_total / ref_total if ref_total else 0
    if ratio_s < 0.9:
        reds.append(f'总秒数只有对标的 {ratio_s*100:.0f}%')
    if a.mode == 'name' and ratio_n < 0.9:
        reds.append(f'工序只有对标的 {ratio_n*100:.0f}%')

    W, margin = 2100, 40
    barw = W - margin * 2
    H = 1150
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((margin, 22), f'环节看板 · {a.stage}　——　和标的对格子', font=font(35), fill=INK)
    d.text((margin, 68), '格子宽＝秒数｜红框＝对标有、我们没有｜灰格＝我们多出来｜格内第二行秒数，第三行景别',
           font=font(18, False), fill=GRAY)

    y = 108
    y = draw_bar(d, margin, y, barw,
                 [(n2, s, 'ok', (rl[i] if i < len(rl) else '')) for i, (n2, s) in enumerate(ref)],
                 ref_total, '对标', f'{len(ref)} 格 / {ref_total:.2f} 秒') + 48
    y = draw_bar(d, margin, y, barw, cells, ours_total,
                 '单元' if is_map else '我们',
                 f'{len(cells)} 格 / {ours_total:.2f} 秒') + 30

    if a.map:
        mp = {}
        for part in re.split(r'[,\uFF0C;；]', a.map):
            if '=' in part:
                k, v = part.split('=', 1)
                mp[norm(k.strip())] = v.strip()
        us, cov_cells, unmapped = {}, [], []
        for n2, s in ref:
            u = mp.get(norm(n2))
            if u:
                us.setdefault(u, [0.0, 0])
                us[u][0] += s
                us[u][1] += 1
                cov_cells.append((n2, s, 'ok', u))
            else:
                unmapped.append((n2, s))
                cov_cells.append((n2, s, 'miss', ''))
        d.text((margin, y), '工序 → 单元 覆盖', font=font(23), fill=INK)
        d.text((margin + 200, y + 4), '每格是一个对标工序，颜色＝它落在哪个单元；红框＝没进任何盒子',
               font=font(17, False), fill=GRAY)
        y += 32
        order = sorted(us.keys())
        palette = {u: UPAL[i % len(UPAL)] for i, u in enumerate(order)}
        tinted = []
        for n2, s, kind, sub in cov_cells:
            tinted.append((n2, s, kind, sub, palette.get(sub) if kind == 'ok' else None))
        y = draw_bar(d, margin, y, barw, tinted, ref_total, '覆盖', '') + 22
        cx = margin
        for u in order:
            sec, cnt = us[u]
            label = f'{u}：{cnt} 个工序 / {sec:.2f} 秒'
            tw = 20 + len(label) * 14
            if cx + tw > W - margin:
                cx = margin
                y += 32
            d.rectangle([cx, y, cx + tw, y + 26], fill=palette[u], outline=(168, 168, 168))
            d.text((cx + 5, y + 2), label, font=font(15, False), fill=INK)
            cx += tw + 8
            if sec > a.unit_cap:
                reds.append(f'{u} 合计 {sec:.2f} 秒 > {a.unit_cap:.0f} 秒上限（一段装不下）')
        y += 36
        if unmapped:
            reds.append('没进盒子的工序：' + '、'.join(f'{x}（{s:.2f}s）' for x, s in unmapped))

    d.text((margin, y), '三个数', font=font(23), fill=INK)
    y += 34
    per_o = ours_total / max(1, len(ours))
    per_r = ref_total / max(1, len(ref))
    if a.mode == 'seq':
        line = (f'镜数 对标 {len(ref)} / 我们 {len(ours)}'
                f'　　秒数 {ours_total:.2f}/{ref_total:.2f} = {ratio_s*100:.0f}%'
                f'　　每镜 {per_o:.2f}/{per_r:.2f} = {per_o/per_r*100:.0f}%')
    else:
        line = (f'格数 {covered}/{len(ref)} = {ratio_n*100:.0f}%'
                f'　　秒数 {ours_total:.2f}/{ref_total:.2f} = {ratio_s*100:.0f}%'
                f'　　每格 {per_o:.2f}/{per_r:.2f} = {per_o/per_r*100:.0f}%')
    d.text((margin, y), line, font=font(26), fill=INK)
    y += 42

    if reds:
        d.text((margin, y), f'红灯 {len(reds)} 条', font=font(23), fill=C_BAD)
        y += 32
        for r in reds[:11]:
            d.text((margin, y), '· ' + r, font=font(19, False), fill=C_BAD)
            y += 27
        if len(reds) > 11:
            d.text((margin, y), f'…还有 {len(reds)-11} 条', font=font(17, False), fill=C_BAD)
            y += 24
    else:
        d.text((margin, y), '全绿：格子齐、秒数够、没有多出来', font=font(23), fill=C_OK)
        y += 28

    img = img.crop((0, 0, W, min(H, y + 24)))
    img.save(a.out)
    print('已生成：' + os.path.abspath(a.out))
    print(line)
    for r in reds:
        print('  [红灯] ' + r)
    return 1 if reds else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看板_对比.py —— 一屏看完「我们 vs 对标」的结构和画面

它不做判断，只把两件事并排摆在同一把尺子上，让你用眼睛比：
  上排：对标——缩略图 + 三段时间条
  下排：我们——缩略图 + 三段时间条
  底部：4 个能一眼判死的大数字

为什么要这样
------------
人眼只能「比较」，不能「阅读」。所以要判「像不像、缺没缺」，
唯一的办法是把两个东西按同一时间尺度并排，让差异自己暴露出来。
三个前提：同尺度、一屏到底、缺的要留空。

用法
----
  python 看板_对比.py --ref 对标.mp4 --ours 成品.mp4 \
      --ref-ends 3.10,23.67 --ours-ends 3.40,18.13 --out 看板.png

  --ref-ends / --ours-ends：开头结束秒、中间结束秒（逗号分隔）。
  不给就按三等分画，会有提示。

退出码：0 生成成功 / 2 出错
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from PIL import Image, ImageDraw
from pipeline_runtime import get_font

BG = (250, 250, 250)
INK = (32, 32, 32)
GRAY = (140, 140, 140)
C_HEAD = (232, 168, 124)     # 开头
C_MID = (146, 190, 226)      # 中间
C_END = (150, 200, 160)      # 结尾
C_BAD = (208, 72, 72)
C_OK = (52, 140, 88)

def font(size, bold=True):
    return get_font(size, bold)


def ffprobe_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=nw=1:nk=1', path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def yavg(path, last=False):
    cmd = ['ffmpeg', '-hide_banner']
    if last:
        cmd += ['-sseof', '-0.15']
    cmd += ['-i', path, '-frames:v', '1',
            '-vf', 'signalstats,metadata=print:key=lavfi.signalstats.YAVG',
            '-f', 'null', '-']
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    m = re.search(r'YAVG=([\d.]+)', r.stderr)
    return float(m.group(1)) if m else 0.0


def grab(path, times, tmpdir, tag, size):
    """抓帧，返回 PIL 图列表。"""
    out = []
    for i, t in enumerate(times):
        f = os.path.join(tmpdir, f'{tag}_{i}.png')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{t:.3f}', '-i', path,
                        '-frames:v', '1', '-vf', f'scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,crop={size[0]}:{size[1]}',
                        f], capture_output=True)
        if os.path.exists(f):
            out.append(Image.open(f).convert('RGB'))
        else:
            out.append(Image.new('RGB', size, (220, 220, 220)))
    return out


def parse_ends(s, dur):
    if not s:
        return [dur / 3, dur * 2 / 3, True]
    parts = [float(x) for x in s.split(',')]
    return [parts[0], parts[1], False]


def draw_row(img, draw, x0, y0, frames, ends, dur, label, fw, fh):
    """画一排缩略图 + 一条三段的时间条。返回下一行的 y。"""
    n = len(frames)
    label_font = font(30)
    small = font(21, bold=False)
    draw.text((x0, y0), label, font=label_font, fill=INK)
    draw.text((x0 + 300, y0 + 6), f'{dur:.2f} 秒', font=font(24), fill=GRAY)
    y1 = y0 + 44

    for i, im in enumerate(frames):
        img.paste(im, (x0 + i * fw, y1))

    y2 = y1 + fh + 10
    total_w = n * fw
    segs = [('开头', 0, ends[0], C_HEAD),
            ('中间', ends[0], ends[1], C_MID),
            ('结尾', ends[1], dur, C_END)]
    for name, a, b, color in segs:
        xa = x0 + int(total_w * a / dur)
        xb = x0 + int(total_w * b / dur)
        draw.rectangle([xa, y2, xb, y2 + 34], fill=color)
        secs = b - a
        pct = secs / dur * 100
        txt = f'{name} {secs:.2f}s ({pct:.0f}%)'
        if xb - xa > 150:
            draw.text((xa + 8, y2 + 4), txt, font=small, fill=INK)
        else:
            draw.text((xa + 4, y2 - 26), f'{secs:.1f}s', font=small, fill=INK)
    draw.rectangle([x0, y2, x0 + total_w, y2 + 34], outline=(200, 200, 200))
    return y2 + 34


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', required=True)
    ap.add_argument('--ours', required=True)
    ap.add_argument('--ref-ends', default=None, help='开头结束,中间结束')
    ap.add_argument('--ours-ends', default=None)
    ap.add_argument('--cols', type=int, default=14)
    ap.add_argument('--ref-tasks', default=None, help='对标工序名，英文逗号分隔')
    ap.add_argument('--ours-tasks', default=None, help='本片工序名，英文逗号分隔')
    ap.add_argument('--out', default='看板_对比.png')
    a = ap.parse_args()

    for p in (a.ref, a.ours):
        if not os.path.exists(p):
            print('找不到：' + p)
            return 2

    dr, do = ffprobe_duration(a.ref), ffprobe_duration(a.ours)
    re_, me_, rd = parse_ends(a.ref_ends, dr)
    ro, mo, od = parse_ends(a.ours_ends, do)

    fw, fh = 150, 266
    margin = 40
    W = margin * 2 + a.cols * fw
    H = 1620
    img = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.text((margin, 26), '我们  vs  对标 —— 一把尺子并排看', font=font(40), fill=INK)
    if rd or od:
        draw.text((margin, 76), '（没给三段分界，时间条按三等分画，只作参考）',
                  font=font(20, False), fill=C_BAD)

    tmp = tempfile.mkdtemp()
    t_ref = [dr * (i + 0.5) / a.cols for i in range(a.cols)]
    t_our = [do * (i + 0.5) / a.cols for i in range(a.cols)]

    yr = draw_row(img, draw, margin, 108, grab(a.ref, t_ref, tmp, 'r', (fw, fh)),
                  (re_, me_), dr, '对标', fw, fh)
    yo = draw_row(img, draw, margin, yr + 46, grab(a.ours, t_our, tmp, 'o', (fw, fh)),
                  (ro, mo), do, '我们', fw, fh)

    # 底部四个数字
    by = yo + 54
    ratio_mid = (mo - ro) / (me_ - re_) if (me_ - re_) > 0 else 0
    y_r1, y_r2 = yavg(a.ref), yavg(a.ref, True)
    y_o1, y_o2 = yavg(a.ours), yavg(a.ours, True)
    light_r = y_r2 / y_r1 if y_r1 else 0
    light_o = y_o2 / y_o1 if y_o1 else 0

    head_o = ro / do * 100
    head_r = re_ / dr * 100
    stats = [
        ('总时长', f'{do:.2f} / {dr:.2f} 秒', f'{do/dr*100:.0f}%', do / dr, '高好'),
        ('中间改造段', f'{(mo-ro):.2f} / {(me_-re_):.2f} 秒', f'{ratio_mid*100:.0f}%', ratio_mid, '高好'),
        ('结尾末帧亮度', f'×{light_o:.2f} / ×{light_r:.2f}', '要不要更亮？',
         (light_o / light_r) if light_r else 0, '高好'),
        ('开头占全片', f'{head_o:.0f}% / {head_r:.0f}%', '别抢中间的时间',
         (head_r / head_o) if head_o else 99, '高好'),
    ]
    draw.text((margin, by), '四个数，对不上就是有问题', font=font(28), fill=INK)
    by += 42
    cw = (W - margin * 2) // 4
    for i, (k, v, tag, r, _dir) in enumerate(stats):
        x = margin + i * cw
        ok = r >= 0.9
        draw.rectangle([x, by, x + cw - 16, by + 116], fill=(255, 255, 255), outline=(225, 225, 225))
        draw.text((x + 14, by + 10), k, font=font(22, False), fill=GRAY)
        draw.text((x + 14, by + 38), v, font=font(28), fill=INK)
        draw.text((x + 14, by + 76), tag, font=font(26), fill=C_OK if ok else C_BAD)


    # ===== 工序对照：缺的直接留空并标红 =====
    if a.ref_tasks or a.ours_tasks:
        rt = [t.strip() for t in (a.ref_tasks or '').split(',') if t.strip()]
        ot = [t.strip() for t in (a.ours_tasks or '').split(',') if t.strip()]
        ty = by + 140
        draw.text((margin, ty), '工序对照：对标的每一格，我们有没有对应的', font=font(28), fill=INK)
        ty += 42
        cell_h, gap = 40, 8
        # 对标行：一格一工序
        draw.text((margin, ty + 8), '对标', font=font(22, False), fill=GRAY)
        x = margin + 86
        for t in rt:
            w = max(96, 26 + len(t) * 21)
            draw.rectangle([x, ty, x + w, ty + cell_h], fill=(224, 238, 226), outline=(150, 190, 160))
            draw.text((x + 8, ty + 8), t, font=font(20, False), fill=INK)
            x += w + gap
        ry = ty + cell_h + 18
        # 我们行：按名字对齐，缺的留空红框
        draw.text((margin, ry + 8), '我们', font=font(22, False), fill=GRAY)
        x = margin + 86
        missing = 0
        for t in rt:
            w = max(96, 26 + len(t) * 21)
            if t in ot:
                draw.rectangle([x, ry, x + w, ry + cell_h], fill=(224, 238, 226), outline=(150, 190, 160))
                draw.text((x + 8, ry + 8), t, font=font(20, False), fill=INK)
            else:
                draw.rectangle([x, ry, x + w, ry + cell_h], fill=(250, 232, 232), outline=C_BAD, width=2)
                draw.text((x + 8, ry + 8), '缺', font=font(30), fill=C_BAD)
                missing += 1
            x += w + gap
        draw.text((margin, ry + cell_h + 16),
                  f'对标 {len(rt)} 个工序，我们少 {missing} 个（红框就是缺口）'
                  + (f'；我们多出：{", ".join([t for t in ot if t not in rt])}' if any(t not in rt for t in ot) else ''),
                  font=font(24), fill=C_BAD if missing else C_OK)
        by = ry + cell_h + 60

    img = img.crop((0, 0, W, min(H, by + 230)))
    img.save(a.out)
    print('已生成：' + os.path.abspath(a.out))
    print(f'  画布 {img.size[0]}×{img.size[1]}')
    print(f'  中间段比 {ratio_mid*100:.0f}% ｜ 末帧亮度比 ×{light_o:.2f}（对标 ×{light_r:.2f}）')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)

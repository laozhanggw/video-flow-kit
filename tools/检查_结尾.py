#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_结尾.py —— 改造类视频「结尾验证段」机器闸门

只判可测的事实，不判好不好看。判不了的会明确列成「需人判」，不假装能判。

三项硬检查
----------
1. 末帧/首帧亮度比：末帧 YAVG ≥ 首帧 YAVG × 1.05
   （这类片子的视觉语法是「变亮＝变好」；变暗要另写理由）
2. 末镜时长 ≥ 阈值（默认 2.0 秒，来自对标 B0001 的 2.07 秒）
3. 验证段镜数 ≥ 3
   2、3 需要 --end-start（验证段起点，秒）。设定书第 9 节里就有；
   不给就跳过并标「需人填」，不会瞎猜。

一项闸门
--------
4. 待裁决清零：版本目录里不许有「未裁决」的表格行。

关键经验
--------
镜头切点用 ffmpeg scene 检测，阈值必须 ≥0.30。雨丝、水雾、手持抖动
会在 0.10–0.25 之间制造大量假切点（实测对标尾段 10 秒能报出 20 多个假切点，
真实只有 4 个）。所以本脚本默认 0.30，且只在给出的验证段窗口内找。

用法
----
  python 检查_结尾.py --video 成品.mp4
  python 检查_结尾.py --video 成品.mp4 --end-start 18.133
  python 检查_结尾.py --video 成品.mp4 --end-start 18.133 \
      --ref 对标.mp4 --ref-end-start 23.670 --version-dir <V01目录>

退出码：0 全过 / 1 有不过 / 2 参数或环境错误
"""

import argparse
import glob
import os
import re
import subprocess
import sys

CUT_THRESHOLD = 0.30          # 低于这个值会被雨丝和水雾骗
DEFAULT_MIN_LAST_SHOT = 2.0   # 秒；对标 B0001 末镜 2.07
DEFAULT_MIN_LIGHT = 1.05      # 末帧/首帧
DEFAULT_MIN_SHOTS = 3

PENDING_HARD = re.compile(r'\|\s*[^|\n]*未裁决[^|\n]*\|')
PENDING_SOFT = re.compile(r'待裁决|需要你决定|待你决定|唯一需要你决定')
RESOLVED = re.compile(r'已裁决|已经裁决|裁决结果')


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def duration(path):
    r = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nw=1:nk=1', path])
    if r.returncode != 0:
        raise RuntimeError('ffprobe 失败：' + r.stderr.strip()[:200])
    return float(r.stdout.strip())


def yavg(path, last=False):
    cmd = ['ffmpeg', '-hide_banner']
    if last:
        cmd += ['-sseof', '-0.15']
    cmd += ['-i', path, '-frames:v', '1',
            '-vf', 'signalstats,metadata=print:key=lavfi.signalstats.YAVG',
            '-f', 'null', '-']
    r = run(cmd)
    m = re.search(r'YAVG=([\d.]+)', r.stderr)
    if not m:
        raise RuntimeError('取 YAVG 失败')
    return float(m.group(1))


def cuts_between(path, start, end):
    """在 [start,end] 内找切点，返回绝对秒列表。"""
    cmd = ['ffmpeg', '-hide_banner', '-ss', f'{start:.3f}', '-i', path,
           '-t', f'{max(0.1, end - start):.3f}',
           '-vf', f"select='gt(scene,{CUT_THRESHOLD})',metadata=print:key=lavfi.scene_score",
           '-f', 'null', '-']
    r = run(cmd)
    pts = [float(x) for x in re.findall(r'pts_time:([\d.]+)', r.stderr)]
    return sorted(start + p for p in pts if start + p < end - 0.03)


def scan_pending(version_dir):
    hard, soft = [], []
    if not version_dir or not os.path.isdir(version_dir):
        return hard, soft
    for path in glob.glob(os.path.join(version_dir, '**', '*.md'), recursive=True):
        rel = os.path.relpath(path, version_dir)
        try:
            text = open(path, encoding='utf-8').read()
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if PENDING_HARD.search(line):
                hard.append((rel, i, line.strip()[:110]))
            elif PENDING_SOFT.search(line) and not RESOLVED.search(line):
                soft.append((rel, i, line.strip()[:110]))
    return hard, soft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--end-start', type=float, default=None,
                    help='验证段起点（秒），不给就跳过末镜/镜数两项')
    ap.add_argument('--ref', default=None)
    ap.add_argument('--ref-end-start', type=float, default=None)
    ap.add_argument('--version-dir', default=None)
    ap.add_argument('--min-last-shot', type=float, default=DEFAULT_MIN_LAST_SHOT)
    ap.add_argument('--min-light', type=float, default=DEFAULT_MIN_LIGHT)
    ap.add_argument('--min-shots', type=int, default=DEFAULT_MIN_SHOTS)
    a = ap.parse_args()

    if not os.path.exists(a.video):
        print('找不到视频：' + a.video)
        return 2
    try:
        dur = duration(a.video)
        y1, y2 = yavg(a.video), yavg(a.video, last=True)
    except Exception as e:
        print('读取视频失败：', e)
        return 2
    ratio = (y2 / y1) if y1 else 0.0

    rows = []          # (项目, 实测, 阈值, ok, note)
    rows.append(('末帧/首帧亮度', f'{y1:.1f} → {y2:.1f}（×{ratio:.2f}）',
                 f'≥ ×{a.min_light:.2f}', ratio >= a.min_light,
                 '变亮＝变好的视觉语法；变暗必须另写理由'))

    if a.end_start is not None:
        cuts = cuts_between(a.video, a.end_start, dur)
        last_cut = cuts[-1] if cuts else a.end_start
        last_shot = dur - last_cut
        shots = len(cuts) + 1
        rows.append(('末镜时长', f'{last_shot:.2f} 秒', f'≥ {a.min_last_shot:.2f} 秒',
                     last_shot >= a.min_last_shot,
                     f'末镜从 {last_cut:.2f}s 起／总长 {dur:.2f}s'))
        rows.append((f'验证段镜数（{a.end_start:.2f}s 起）', f'{shots} 镜',
                     f'≥ {a.min_shots} 镜', shots >= a.min_shots,
                     '一两个镜头讲不完「根治—使用—升华」'))
    else:
        rows.append(('末镜时长 / 验证段镜数', '未给 --end-start', '跳过', None,
                     '这两项必须知道验证段起点才能算，请在设定书第 9 节里取'))

    if a.ref and os.path.exists(a.ref):
        ry1, ry2 = yavg(a.ref), yavg(a.ref, last=True)
        rr = (ry2 / ry1) if ry1 else 0.0
        extra = ''
        if a.ref_end_start is not None:
            rdur = duration(a.ref)
            rc = cuts_between(a.ref, a.ref_end_start, rdur)
            rlast = (rdur - rc[-1]) if rc else (rdur - a.ref_end_start)
            extra = f'／末镜 {rlast:.2f} 秒／{len(rc)+1} 镜'
        rows.append(('（参照）对标', f'亮度 ×{rr:.2f}{extra}', '—', True,
                     '阈值如果低于对标实测，说明这道闸门偏松'))

    hard, soft = scan_pending(a.version_dir)
    rows.append(('待裁决（未裁决表格行）', f'{len(hard)} 行', '= 0 行',
                 len(hard) == 0, '有未裁决项就不许进生产'))

    print('=' * 78)
    print('结尾验证段机器闸门')
    print(f'  成片：{a.video}')
    if a.ref:
        print(f'  对标：{a.ref}')
    print('=' * 78)
    print(f"{'项目':<30}{'实测':<28}{'阈值':<16}判定")
    print('-' * 78)
    fails = 0
    for name, actual, need, ok, note in rows:
        flag = '跳过' if ok is None else ('PASS' if ok else 'FAIL')
        if ok is False:
            fails += 1
        print(f'{name:<30}{actual:<28}{need:<16}{flag}')
        if note:
            print(f'    · {note}')
    print('-' * 78)

    if hard:
        print('未裁决（硬失败）：')
        for f, ln, t in hard[:10]:
            print(f'    {f}:{ln}  {t}')
    if soft:
        print(f'历史遗留「要你拍板」字样 {len(soft)} 处（需你确认是否已裁决）：')
        for f, ln, t in soft[:10]:
            print(f'    {f}:{ln}  {t}')
        print('    → 这些不算失败，但每一处都该有你的明确答复，否则会像这次一样被静默跳过')

    print('-' * 78)
    print('需人判（机器判不了，必须你看一眼成片末镜）：')
    print('    1. 对照物（雨／噪音／尘／乱）在末镜里还在不在？')
    print('    2. 末镜里有没有「人在用」或「刚被用过」的痕迹？')
    print('    3. 升华物是否 ≥3 类同框、且有一处明显主光？')
    print('=' * 78)
    print('结果：' + ('全部通过' if fails == 0 else f'{fails} 项不过'))
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)

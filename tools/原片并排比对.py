# -*- coding: utf-8 -*-
"""原片并排比对：我们生成的视频 vs 原片同一段，等比对齐抽帧，左原片右我们。
用法：python 原片并排比对.py <我们的视频> <原片视频> <输出目录> --orig-start 0 --orig-end 8 [--step 0.4]
2026-11-10 第3批新建（P-1 第5条：生成后先并排比，再给人看）。
"""
import argparse, io, os, subprocess, sys


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("命令失败：", " ".join(cmd))
        print(r.stderr[-2000:])
        sys.exit(2)
    return r.stdout


def duration(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", p]).strip())


def grab(video, t, out):
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % t, "-i", video,
         "-frames:v", "1", "-vf", "scale=-2:720", out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ours")
    ap.add_argument("orig")
    ap.add_argument("out")
    ap.add_argument("--orig-start", type=float, required=True)
    ap.add_argument("--orig-end", type=float, required=True)
    ap.add_argument("--step", type=float, default=0.4, help="原片每隔几秒取一对")
    a = ap.parse_args()
    for p in (a.ours, a.orig):
        if not os.path.isfile(p):
            print("找不到视频：", p)
            sys.exit(2)
    span = a.orig_end - a.orig_start
    if span <= 0:
        print("--orig-end 必须大于 --orig-start")
        sys.exit(2)
    d_ours = duration(a.ours)
    d_orig = duration(a.orig)
    if a.orig_end > d_orig + 0.05:
        print("--orig-end 超过原片时长 %.2f 秒" % d_orig)
        sys.exit(2)
    ratio = d_ours / span
    os.makedirs(a.out, exist_ok=True)
    tmp = os.path.join(a.out, "_tmp")
    os.makedirs(tmp, exist_ok=True)

    rows, k = [], 0
    while True:
        to = a.orig_start + k * a.step
        if to > a.orig_end - 0.05:
            break
        tw = min((to - a.orig_start) * ratio, max(0.0, d_ours - 0.05))
        fo = os.path.join(tmp, "o_%03d.jpg" % k)
        fw = os.path.join(tmp, "w_%03d.jpg" % k)
        grab(a.orig, to, fo)
        grab(a.ours, tw, fw)
        pair = "对_%03d_原%.2fs_我%.2fs.jpg" % (k + 1, to, tw)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", fo, "-i", fw,
             "-filter_complex", "[0][1]hstack=inputs=2", "-frames:v", "1",
             os.path.join(a.out, pair)])
        rows.append((k + 1, to, tw, pair))
        k += 1
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)

    with io.open(os.path.join(a.out, "00_并排比对.md"), "w", encoding="utf-8") as f:
        f.write("# 原片并排比对\n\n- 我们：%s（%.2f 秒）\n- 原片：%s（取 %.2f–%.2f 秒）\n"
                "- 对齐：我们的第 t 秒 ＝ 原片第 %.2f＋t÷%.3f 秒（两边按各自时长等比）\n"
                "- 每张图左边是原片，右边是我们\n\n"
                "「同一件事」＝同一个人或动物、对同一个东西、做同一个动作。只是长相不同不算差。\n\n"
                "| # | 原片秒 | 我们秒 | 并排图 | 对照表第几行 | 同一件事吗 | 差在哪 |\n"
                "|---|---|---|---|---|---|---|\n"
                % (a.ours, d_ours, a.orig, a.orig_start, a.orig_end, a.orig_start, ratio))
        for n, to, tw, pair in rows:
            f.write("| %d | %.2f | %.2f | %s |  |  |  |\n" % (n, to, tw, pair))
    print("完成：%d 对并排图，比例 %.3f（我们 %.2f 秒 / 原片 %.2f 秒）" % (len(rows), ratio, d_ours, span))


if __name__ == "__main__":
    main()

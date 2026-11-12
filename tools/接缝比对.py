# -*- coding: utf-8 -*-
"""
接缝比对｜把"上一盒最后一帧"和"这一盒第一帧"拼成一张对比图。

用法（单对）：
    python tools\\接缝比对.py --prev <上一盒的 mp4 或 png> --next <这一盒的首帧 png> --out <输出 png>
用法（整版批量，按 单元\\U02.. 顺序自动找 生成\\U0N_v01.mp4 和 生成\\U0N_首帧* / RC*_首帧_U0N*）：
    python tools\\接缝比对.py --version <版本目录>

输出：<版本目录>\\_验收\\接缝_U03.png 这种名字。一张图，左边上一盒最后一帧，右边本盒第一帧。
规则见 07_第6步_生成与导入.md 6.6b：没有这张图，不许开始剪。
"""
import argparse, os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]

def font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def last_frame(path, out_jpg):
    """视频取最后一帧；图片直接返回自身。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        return path
    cmd = ["ffmpeg", "-y", "-v", "error", "-sseof", "-0.2", "-i", path,
           "-frames:v", "1", out_jpg]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not os.path.exists(out_jpg):
        raise RuntimeError("取最后一帧失败：%s\n%s" % (path, r.stderr.decode("utf-8", "replace")[:400]))
    return out_jpg

def compose(left_img, right_img, out_path, left_label, right_label):
    H = 900
    ims = []
    for p in (left_img, right_img):
        im = Image.open(p).convert("RGB")
        w = int(im.width * H / im.height)
        ims.append(im.resize((w, H), Image.LANCZOS))
    margin, bar, footer = 24, 56, 44
    W = ims[0].width + ims[1].width + margin * 3
    canvas = Image.new("RGB", (W, H + bar + margin * 2 + footer), (245, 245, 245))
    f = font(26)
    d = ImageDraw.Draw(canvas)
    x = margin
    for im, label in zip(ims, (left_label, right_label)):
        canvas.paste(im, (x, margin + bar))
        d.text((x + 4, margin + 12), label, fill=(20, 20, 20), font=f)
        x += im.width + margin
    d.text((margin + 4, margin + bar + H + 8), "只看四样：主体物（池子）／房子／栅栏／人。有一项不同 → 停，回去重做这一盒首帧。",
           fill=(120, 30, 30), font=font(22))
    canvas.save(out_path)
    return out_path

def find_pairs(version_dir):
    gen = os.path.join(version_dir, "生成")
    out = []
    if not os.path.isdir(gen):
        return out
    vids = {}
    for n in os.listdir(gen):
        m = re.match(r"(U\d+)_v\d+\.mp4$", n)
        if m:
            k = m.group(1)
            if k not in vids or n > vids[k]:
                vids[k] = n
    frames = {}
    for n in os.listdir(gen):
        m = re.match(r"(?:RC\d+_)?首帧_(U\d+)", n)
        if m and n.lower().endswith((".png", ".jpg", ".jpeg")):
            frames[m.group(1)] = n
    units = sorted(set(vids) | set(frames))
    for i in range(1, len(units)):
        a, b = units[i - 1], units[i]
        if a in vids and b in frames:
            out.append((a, b,
                        os.path.join(gen, vids[a]),
                        os.path.join(gen, frames[b])))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", help="上一盒 mp4 / png")
    ap.add_argument("--next", help="这一盒首帧 png")
    ap.add_argument("--out", help="输出 png")
    ap.add_argument("--version", help="版本目录：批量做整版所有相邻盒")
    a = ap.parse_args()

    if a.version:
        v = os.path.abspath(a.version)
        acc = os.path.join(v, "_验收")
        os.makedirs(acc, exist_ok=True)
        pairs = find_pairs(v)
        if not pairs:
            print("没找到可比的相邻盒（要有 生成\\U0N_vNN.mp4 和 生成\\*首帧_U0N*.png）")
            return 2
        tmp = tempfile.mkdtemp()
        made = []
        for a_u, b_u, prev, nxt in pairs:
            lf = last_frame(prev, os.path.join(tmp, "%s_last.jpg" % a_u))
            out = os.path.join(acc, "接缝_%s_%s.png" % (a_u, b_u))
            compose(lf, nxt, out, "%s 最后一帧（%s）" % (a_u, os.path.basename(prev)),
                    "%s 第一帧（%s）" % (b_u, os.path.basename(nxt)))
            made.append(out)
            print("生成:", out)
        print("共 %d 张。按 07_第6步 6.6b 逐张看四项，不同就停。" % len(made))
        return 0

    if not (a.prev and a.next):
        ap.print_help()
        return 2
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.next)), "接缝对比.png")
    tmp = tempfile.mkdtemp()
    lf = last_frame(a.prev, os.path.join(tmp, "last.jpg"))
    compose(lf, a.next, out, "上一盒最后一帧（%s）" % os.path.basename(a.prev),
            "这一盒第一帧（%s）" % os.path.basename(a.next))
    print("生成:", out)
    return 0

if __name__ == "__main__":
    sys.exit(main())

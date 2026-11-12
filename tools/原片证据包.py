# -*- coding: utf-8 -*-
"""原片证据包：开头每0.2秒单帧 + 拼图 + 整片分窗转写（句子带真实起止秒）。
用法：python 原片证据包.py <视频完整路径> <输出目录> [--seconds 8]
2026-11-10 第2批：开逐词时间；相邻窗口同一句合并；两种听法、疑似幻听打标。
"""
import argparse, io, json, os, re, subprocess, sys

HALLU = ["thanks for watching", "thank you for watching", "please subscribe",
         "subscribe to my channel", "see you in the next video", "like and subscribe"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("命令失败：", " ".join(cmd))
        print(r.stderr[-2000:])
        sys.exit(2)
    return r.stdout


def norm(t):
    return re.sub(r"[^a-z0-9' ]+", " ", t.lower()).split()


def contains(big, small):
    n = len(small)
    return n > 0 and any(big[i:i + n] == small for i in range(len(big) - n + 1))


def overlap(a, b):
    return min(a["止"], b["止"]) - max(a["起"], b["起"])


def merge(rows):
    rows = sorted(rows, key=lambda r: (r["起"], r["止"]))
    out = []
    for r in rows:
        nr, hit = norm(r["原文"]), None
        for o in out:
            if overlap(o, r) <= 0:
                continue
            no = norm(o["原文"])
            if nr == no or contains(no, nr) or contains(nr, no):
                hit = o
                break
        if hit is None:
            out.append(dict(r, 窗口=[r["窗口"]]))
            continue
        hit["窗口"].append(r["窗口"])
        no = norm(hit["原文"])
        better = (r["可信"] and not hit["可信"]) or \
                 (r["可信"] == hit["可信"] and len(nr) > len(no) and contains(nr, no))
        if better:
            for k in ("起", "止", "原文", "可信", "no_speech", "logprob"):
                hit[k] = r[k]
    for r in out:
        r["两种听法"] = []
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            ov = overlap(a, b)
            short = min(a["止"] - a["起"], b["止"] - b["起"])
            if short > 0 and ov >= 0.5 * short:
                a["两种听法"].append(b["原文"])
                b["两种听法"].append(a["原文"])
    for r in out:
        if any(h in " ".join(norm(r["原文"])) for h in HALLU):
            r["可信"] = False
            r["备注"] = "疑似幻听"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--win", type=float, default=3.0)
    ap.add_argument("--step", type=float, default=2.0)
    a = ap.parse_args()
    if not os.path.isfile(a.video):
        print("找不到视频：", a.video)
        sys.exit(2)
    fdir = os.path.join(a.out, "开头单帧")
    adir = os.path.join(a.out, "音频")
    os.makedirs(fdir, exist_ok=True)
    os.makedirs(adir, exist_ok=True)

    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=nw=1:nk=1", a.video]).strip())
    n = min(a.seconds, dur)

    # 1) 开头单帧：每 0.2 秒一张
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "0", "-t", str(n),
         "-i", a.video, "-vf", "fps=5,scale=540:-1", os.path.join(fdir, "f_%03d.jpg")])
    frames = sorted(x for x in os.listdir(fdir) if x.startswith("f_") and x.endswith(".jpg"))

    # 2) 拼图：每 4 秒一张，20 格
    s, k = 0.0, 1
    while s < n:
        t = min(4.0, n - s)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(s), "-t", str(t),
             "-i", a.video, "-vf", "fps=5,scale=270:-1,tile=5x4", "-frames:v", "1",
             os.path.join(a.out, "拼图_%02d_%.1f-%.1fs.jpg" % (k, s, s + t))])
        s += 4.0
        k += 1

    # 3) 整片分窗转写：3 秒一窗、2 秒一步；开逐词时间，句子起止＝第一个词起、最后一个词止
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    raw, st = [], 0.0
    while st < dur:
        L = min(a.win, dur - st)
        if L < 0.5:
            break
        wav = os.path.join(adir, "w_%06.2f.wav" % st)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(st), "-t", str(L),
             "-i", a.video, "-vn", "-ac", "1", "-ar", "16000", "-af", "volume=6dB", wav])
        segs, _ = model.transcribe(wav, language="en", beam_size=5, vad_filter=False,
                                   word_timestamps=True)
        for sg in segs:
            txt = sg.text.strip()
            if not txt:
                continue
            ws = [w for w in (sg.words or []) if w.word.strip()]
            s0 = ws[0].start if ws else sg.start
            s1 = ws[-1].end if ws else sg.end
            s0, s1 = max(0.0, min(s0, L)), max(0.0, min(s1, L))
            ok = sg.no_speech_prob <= 0.6 and sg.avg_logprob >= -1.0
            raw.append({"起": round(st + s0, 2), "止": round(st + max(s1, s0 + 0.05), 2),
                        "原文": txt, "可信": ok, "no_speech": round(sg.no_speech_prob, 2),
                        "logprob": round(sg.avg_logprob, 2),
                        "窗口": "%.2f-%.2f" % (st, st + L)})
        st += a.step

    rows = merge(raw)
    with io.open(os.path.join(a.out, "转写_未合并.json"), "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    with io.open(os.path.join(a.out, "转写.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    with io.open(os.path.join(a.out, "转写.txt"), "w", encoding="utf-8") as f:
        f.write("# 分窗转写（窗口%.1f秒，步长%.1f秒；时间＝原片秒，句子自己的起止；"
                "相邻窗口同一句已合并，取先出现的；原始每窗结果见 转写_未合并.json）\n"
                % (a.win, a.step))
        for r in rows:
            tag = ""
            if r.get("备注"):
                tag += "   〔%s〕" % r["备注"]
            elif not r["可信"]:
                tag += "   〔不可信〕"
            if r["两种听法"]:
                tag += "   〔两种听法：%s／%s〕" % (r["原文"], "／".join(r["两种听法"]))
            f.write("[%6.2f -> %6.2f] %s%s\n" % (r["起"], r["止"], r["原文"], tag))
        if not rows:
            f.write("（整片没识别出任何话）\n")
    with io.open(os.path.join(a.out, "00_证据包说明.md"), "w", encoding="utf-8") as f:
        f.write("# 原片证据包\n\n- 原片：%s\n- 时长：%.2f 秒\n- 开头单帧：开头单帧\\ 共 %d 张，f_k ＝ (k−1)×0.2 秒\n"
                "- 拼图：每张 20 格，从左到右、从上到下，每格 0.2 秒\n- 转写：转写.txt（合并后 %d 句；未合并 %d 条见 转写_未合并.json）\n\n"
                "## 帧号对照\n\n| 帧 | 秒 |\n|---|---|\n" % (a.video, dur, len(frames), len(rows), len(raw)))
        for i, fn in enumerate(frames):
            f.write("| %s | %.1f |\n" % (fn, i * 0.2))
    print("完成：单帧 %d 张，转写 %d 句（未合并 %d 条），时长 %.2f 秒" % (len(frames), len(rows), len(raw), dur))


if __name__ == "__main__":
    main()

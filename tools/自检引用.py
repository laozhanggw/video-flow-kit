# -*- coding: utf-8 -*-
"""检查包内引用是否都能找到（自检用，随身带着也行）"""
import io, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAT = re.compile(r"[A-Za-z]:\\[^\r\n\"'（）:，,；;）]+")

def main():
    ok, miss = 0, []
    for sub in ["指令", ""]:
        d = os.path.join(ROOT, sub) if sub else ROOT
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if not (os.path.isfile(p) and f.endswith((".txt", ".md"))):
                continue
            t = io.open(p, encoding="utf-8", errors="ignore").read()
            for m in set(PAT.findall(t)):
                q = m.rstrip("\\/ ")
                if any(x in q for x in ("<", "B####", "*", "{{")):
                    continue
                if os.path.exists(q):
                    ok += 1
                else:
                    miss.append((f, q))
    print("能对上的引用:", ok)
    print("对不上的引用:", len(miss))
    seen = set()
    for f, q in miss:
        k = q.replace(ROOT + "\\", "")
        if k in seen:
            continue
        seen.add(k)
        print("  ", f, "->", k[:90])
        if len(seen) >= 15:
            break
    return 0 if not miss else 1

if __name__ == "__main__":
    sys.exit(main())

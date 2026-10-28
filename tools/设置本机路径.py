# -*- coding: utf-8 -*-
"""
设置本机路径 —— 换电脑后跑一次这个，五份指令才能用。

原理：
  打包时所有路径都写成了 {{ROOT}} 占位符，因为不知道你的电脑会把这个文件夹放在哪。
  这个脚本算出「本套件当前所在的绝对路径」，把 {{ROOT}} 填回去。

用法：
  · 有 Python：双击 设置本机路径.bat，或命令行 python tools\设置本机路径.py
  · 不会 Python：让 AI 帮你跑，或者直接把 {{ROOT}} 手动替换成实际路径

可以重复跑。每次都从 _原始备份 恢复再填，不会越填越乱。
"""
import io, os, shutil, sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP = os.path.join(ROOT_DIR, "_原始备份")
# 只处理指令。根目录那些 md 是给人看的资料，不能被脚本还原覆盖
TARGET_DIRS = ["指令"]
EXTS = (".txt",)
PLACEHOLDER = "{{ROOT}}"


def targets():
    out = []
    for d in TARGET_DIRS:
        base = os.path.join(ROOT_DIR, d) if d else ROOT_DIR
        if not os.path.isdir(base):
            continue
        for f in sorted(os.listdir(base)):
            p = os.path.join(base, f)
            if os.path.isfile(p) and f.endswith(EXTS):
                out.append(p)
    return out


def backup_once(files):
    os.makedirs(BACKUP, exist_ok=True)
    n = 0
    for src in files:
        rel = os.path.relpath(src, ROOT_DIR)
        dst = os.path.join(BACKUP, rel)
        if not os.path.exists(dst):          # 只备份一次，保住最原始的占位符版
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    return n


def main():
    print("=" * 58)
    print("设置本机路径")
    print("=" * 58)
    print("套件位置：", ROOT_DIR)

    files = targets()
    if not files:
        print("\n[错误] 没找到要处理的文件。请确认这个脚本在 最新流程\\tools\\ 下。")
        return 1

    n = backup_once(files)
    if n:
        print(f"已备份 {n} 个原始文件到 _原始备份\\")

    # 从备份恢复，再填占位符 —— 保证可重复运行
    filled = 0
    for f in files:
        rel = os.path.relpath(f, ROOT_DIR)
        bk = os.path.join(BACKUP, rel)
        src = bk if os.path.exists(bk) else f
        t = io.open(src, encoding="utf-8").read()
        if PLACEHOLDER in t:
            t = t.replace(PLACEHOLDER, ROOT_DIR)
            io.open(f, "w", encoding="utf-8", newline="\n").write(t)
            filled += 1

    print(f"已填好 {filled} 个文件")

    # 检查
    print("\n【检查】")
    problems = []

    for d in ["指令", "skills", "模板", "对标库", "_项目"]:
        p = os.path.join(ROOT_DIR, d)
        print(("  有  " if os.path.isdir(p) else "  缺  ") + d + "\\")
        if not os.path.isdir(p):
            problems.append(d)

    instr = os.path.join(ROOT_DIR, "指令")
    if os.path.isdir(instr):
        need = ["1_拆解.txt", "2_复刻.txt", "3_开头.txt", "4_小分镜.txt", "5_生产单元.txt"]
        for f in need:
            ok = os.path.exists(os.path.join(instr, f))
            print(("  有  " if ok else "  缺  ") + "指令\\" + f)
            if not ok:
                problems.append(f)

    skills = ["benchmark-select-and-breakdown", "benchmark-video-deconstruction",
              "benchmark-batch-variants", "benchmark-adapt-hook",
              "full-storyboard-design", "adaptive-video-production"]
    sk = os.path.join(ROOT_DIR, "skills")
    miss = [s for s in skills if not os.path.isdir(os.path.join(sk, s))]
    if miss:
        problems.append("skills 缺：" + "、".join(miss))
        print("  缺  skills\\" + "、".join(miss))
    else:
        print("  有  六个 skill 全在")

    # 还有没有没填的占位符
    left = 0
    for dp, dn, fn in os.walk(ROOT_DIR):
        if "_原始备份" in dp:
            continue
        for f in fn:
            if f.endswith(EXTS):
                try:
                    t = io.open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read()
                    if PLACEHOLDER in t:
                        left += 1
                except Exception:
                    pass
    if left:
        print(f"  提示  还有 {left} 个文件留着 {PLACEHOLDER}（正常，这些是给人看的模板举例）")

    print("\n" + "=" * 58)
    if problems:
        print("有缺项，先补齐再用：")
        for p in problems:
            print("  ·", p)
    else:
        print("全部就绪。")
        # 路径变了，流程图里嵌的指令全文也要跟着更新
        gen = os.path.join(ROOT_DIR, "tools", "生成流程导图.py")
        if os.path.exists(gen):
            print("\n正在更新流程导图…")
            try:
                import subprocess
                r = subprocess.run([sys.executable, gen], cwd=ROOT_DIR,
                                   capture_output=True, text=True, timeout=120)
                if r.returncode == 0:
                    for ln in (r.stdout or "").strip().splitlines():
                        print("  " + ln)
                else:
                    print("  自动更新失败：" + (r.stderr or "")[-300:])
                    print("  可手动跑：python tools\\生成流程导图.py")
            except Exception as e:
                print("  自动更新失败：", e)
                print("  可手动跑：python tools\\生成流程导图.py")
        print("\n下一步：")
        print("  1. 双击 流程导图.html，先看懂整套流程")
        print("  2. 打开 指令\\1_拆解.txt，只改第 5 行「对标视频：」，发给 AI")
        print("  3. 往后按 2 → 3/4 → 5 的顺序走")
    print("=" * 58)
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())

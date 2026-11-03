"""
bi-girl.net RSS の半自動更新ヘルパー
1. ブラウザで https://bi-girl.net/feed/ を開く
2. クリップボード（Ctrl+A → Ctrl+C）またはダウンロードフォルダへの保存（Ctrl+S）を自動検知
3. feed.xml と scratch/feed.xml を更新し、GitHub へ git push する
"""
import os
import re
import sys
import time
import glob
import shutil
import subprocess
import webbrowser

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_MAIN = os.path.join(BASE_DIR, "feed.xml")
TARGET_SCRATCH = os.path.join(BASE_DIR, "scratch", "feed.xml")
FEED_URL = "https://bi-girl.net/feed/"


def get_clipboard_text():
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=5
        )
        return res.stdout or ""
    except Exception:
        return ""


def clear_clipboard():
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $null"], timeout=5)
    except Exception:
        pass


def is_valid_bigirl_rss(text):
    return bool(text and "<rss" in text and "bi-girl.net" in text and "<item>" in text)


def find_recent_saved_xml(since_ts):
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    candidates = [
        TARGET_MAIN,
        TARGET_SCRATCH,
        *glob.glob(os.path.join(downloads, "*.xml")),
    ]
    for path in candidates:
        try:
            if os.path.exists(path) and os.path.getmtime(path) > since_ts:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                if is_valid_bigirl_rss(txt):
                    return txt, f"ファイル保存 ({os.path.basename(path)})"
        except Exception:
            pass
    return None, None


def main():
    print("============================================================")
    print("🔄 bi-girl.net RSS 半自動更新ツール")
    print("============================================================")
    print("1. 既定のブラウザで https://bi-girl.net/feed/ を開きます...")
    print("2. ブラウザで開いたら、以下の【どちらか】を行ってください：")
    print("   ・方法A（一番簡単）：画面上で [Ctrl + A] → [Ctrl + C]（全選択してコピー）")
    print("   ・方法B：画面上で [Ctrl + S] で保存（ダウンロードフォルダ等でOK）")
    print("------------------------------------------------------------")
    print("待機中...（最大120秒 / 中止は Ctrl+C）")

    start_ts = time.time()
    clear_clipboard()
    webbrowser.open(FEED_URL)

    xml_content = None
    source_desc = ""

    for _ in range(120):
        time.sleep(1)
        clip = get_clipboard_text()
        if is_valid_bigirl_rss(clip):
            xml_content = clip.strip()
            source_desc = "クリップボード (Ctrl+C)"
            break
        saved_txt, desc = find_recent_saved_xml(start_ts)
        if saved_txt:
            xml_content = saved_txt.strip()
            source_desc = desc
            break

    if not xml_content:
        print("\n⚠️ タイムアウトしました。RSSデータが検知されませんでした。")
        return 1

    os.makedirs(os.path.dirname(TARGET_SCRATCH), exist_ok=True)
    with open(TARGET_MAIN, "w", encoding="utf-8") as f:
        f.write(xml_content)
    shutil.copyfile(TARGET_MAIN, TARGET_SCRATCH)

    titles = re.findall(r"<item>\s*<title>(.*?)</title>", xml_content, re.S)
    print(f"\n✅ RSSを検知・保存しました！（取得元: {source_desc} / 記事数: {len(titles)}件）")
    for i, t in enumerate(titles[:5], 1):
        print(f"   {i}. {t[:50]}")

    print("\n🚀 GitHub へ自動同期（git commit & push）しています...")
    subprocess.run(["git", "pull", "--rebase", "origin", "master"], cwd=BASE_DIR)
    subprocess.run(["git", "add", "feed.xml"], cwd=BASE_DIR)
    commit_res = subprocess.run(
        ["git", "commit", "-m", "Update feed.xml"],
        cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    if "nothing to commit" in (commit_res.stdout or "") + (commit_res.stderr or ""):
        print("ℹ️ 前回のRSSから変更はありませんでした（最新状態です）。")
    else:
        push_res = subprocess.run(["git", "push", "origin", "master"], cwd=BASE_DIR)
        if push_res.returncode == 0:
            print("🎉 GitHub へのプッシュが完了しました！明日からの自動投稿に反映されます。")
        else:
            print("⚠️ git push に失敗しました。")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


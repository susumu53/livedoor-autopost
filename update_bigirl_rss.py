"""
bi-girl.net RSS の半自動更新＆1時間おき自動順次投稿ツール
1. ブラウザで https://bi-girl.net/feed/ を開く
2. クリップボード（Ctrl+A → Ctrl+C）またはファイル保存（Ctrl+S）を自動検知して feed.xml を更新
3. 未投稿の候補をすべて抽出し（3重の二重投稿防止チェック付き）、
   サーバーに負担がかからないよう【1時間おきに1記事ずつ】順番に自動投稿する
"""
import os
import re
import sys
import time
import glob
import shutil
import argparse
import datetime
import subprocess
import webbrowser
import xml.etree.ElementTree as ET
import requests
from requests.auth import HTTPBasicAuth

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_MAIN = os.path.join(BASE_DIR, "feed.xml")
TARGET_SCRATCH = os.path.join(BASE_DIR, "scratch", "feed.xml")
FEED_URL = "https://bi-girl.net/feed/"
DEFAULT_INTERVAL_SEC = 3600  # 1時間 (3600秒)
GIT_BIN = shutil.which("git") or r"C:\Users\user\.gemini\antigravity-ide\bin\git.bat"


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


def git_sync(commit_msg):
    """feed.xml と bijozukan_history.json を GitHub へ同期する"""
    try:
        subprocess.run([GIT_BIN, "add", "feed.xml", "bijozukan_history.json"], cwd=BASE_DIR)
        commit_res = subprocess.run(
            [GIT_BIN, "commit", "-m", commit_msg],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="ignore"
        )
        subprocess.run([GIT_BIN, "pull", "--rebase", "--autostash", "origin", "master"], cwd=BASE_DIR)
        if "nothing to commit" not in (commit_res.stdout or "") + (commit_res.stderr or ""):
            subprocess.run([GIT_BIN, "push", "origin", "master"], cwd=BASE_DIR)
    except Exception as e:
        print(f"[Git同期エラー] {e}")


def get_live_article_titles(engine):
    """ライブドアブログ上の最新記事タイトル一覧を取得して二重投稿を防止する"""
    auth = HTTPBasicAuth(engine.livedoor_id, engine.api_key)
    titles = []
    for page in (1, 2, 3):
        url = f"https://livedoor.blogcms.jp/atompub/{engine.blog_id}/article" + (f"?page={page}" if page > 1 else "")
        try:
            r = requests.get(url, auth=auth, timeout=15)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                    t = entry.findtext("{http://www.w3.org/2005/Atom}title") or ""
                    titles.append(t)
        except Exception as e:
            print(f"[ブログ記事一覧取得エラー] {e}")
    return titles


def post_unposted_bigirl_items(interval_sec=DEFAULT_INTERVAL_SEC):
    """feed.xml 内の未投稿候補を1時間おきに1記事ずつ順番に投稿する"""
    from bijozukan_profile_engine import BijozukanProfileEngine

    engine = BijozukanProfileEngine()
    live_titles = get_live_article_titles(engine)
    raw_candidates = engine.load_bigirl_feed(include_uraaka=True)

    # 二重投稿トリプルチェック（①履歴の名前 ②履歴のX_ID ③実ブログの公開タイトル）
    unposted = []
    for c in raw_candidates:
        name = c["name"]
        x_id = (c.get("x_id") or "").strip("/")
        if name in engine.posted_names() or (x_id and x_id.lower() in engine.posted_x_ids()):
            continue
        if any(t.startswith(f"{name}のプロフィール") for t in live_titles):
            continue
        unposted.append(c)

    if not unposted:
        print("\n✨ feed.xml 内の全候補はすでに記事化・公開済みです（二重投稿なし）。")
        return 0

    # 古い順（下から順）に投稿して、最新記事がブログの一番上に来るようにする
    queue = list(reversed(unposted))
    total = len(queue)
    print("\n============================================================")
    print(f"📝 未投稿の候補が {total} 件見つかりました。")
    print(f"⏱️ サーバー負荷軽減のため、1時間（{interval_sec // 60}分）おきに1記事ずつ自動投稿します。")
    print("   （※このウィンドウを開いたままにしておくと自動で順次投稿されます）")
    print("============================================================")

    posted_count = 0
    for idx, c in enumerate(queue, 1):
        name = c["name"]
        x_id = (c.get("x_id") or "").strip("/")

        # 投稿直前にも最新の履歴・ブログタイトルを再チェック（二重投稿防止）
        engine.history = engine.load_history()
        if name in engine.posted_names() or (x_id and x_id.lower() in engine.posted_x_ids()):
            print(f"[{idx}/{total}] スキップ（すでに履歴に存在）: {name} (@{x_id})")
            continue
        if any(t.startswith(f"{name}のプロフィール") for t in live_titles):
            print(f"[{idx}/{total}] スキップ（すでにブログ上に公開済み）: {name} (@{x_id})")
            continue

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"\n[{now_str}] ({idx}/{total}) 記事作成中: {name} (@{x_id})")
        fb_query = "早希 Lカップ" if x_id == "sakisaki_hh" else name

        profile, reason = engine.build_profile(
            name=name,
            actor_id=c["actor_id"],
            kind=c.get("kind", "gravure"),
            x_id=x_id,
            categories=c.get("categories"),
            eyecatch=c.get("eyecatch", ""),
            fallback_query=fb_query,
        )
        if not profile:
            print(f"   × スキップ: {name} ({reason})")
            engine.history.setdefault("skipped", {})[name] = reason
            engine.save_history()
            continue

        profile["pool"] = "bigirl"
        ok = engine._post_process_profile(profile, dry_run=False)
        if ok:
            posted_count += 1
            latest_entry = engine.history["profiles"][-1]
            live_titles.append(latest_entry["title"])
            print(f"   🎉 投稿成功 ({posted_count}件目): {latest_entry['url']}")
            git_sync(f"Post bi-girl profile: {name} [skip ci]")

            # まだ次の未投稿候補がある場合は1時間待機する
            if idx < total and interval_sec > 0:
                next_time = (datetime.datetime.now() + datetime.timedelta(seconds=interval_sec)).strftime("%H:%M:%S")
                print(f"   ⏳ 次の記事（{queue[idx]['name']}）は 1時間後（{next_time}頃）に投稿します...")
                remaining = interval_sec
                while remaining > 0:
                    step = min(300, remaining)  # 5分ごとに残り時間を表示
                    time.sleep(step)
                    remaining -= step
                    if remaining > 0:
                        print(f"      ...次の投稿まであと {remaining // 60} 分")

    print(f"\n✅ 全スケジュール完了！ 合計 {posted_count} 件の記事を投稿しました。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="bi-girl.net RSS 半自動更新＆1時間おき順次投稿ツール")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC, help="投稿間隔（秒）。デフォルト: 3600（1時間）")
    ap.add_argument("--post-only", action="store_true", help="ブラウザを開かず既存の feed.xml から未投稿分を1時間おきに投稿する")
    args = ap.parse_args()

    print("🔄 GitHub から最新の投稿履歴を同期しています...")
    try:
        subprocess.run([GIT_BIN, "pull", "--rebase", "--autostash", "origin", "master"], cwd=BASE_DIR)
    except Exception as e:
        print(f"[Git pull スキップ] {e}")

    if not args.post_only:
        print("============================================================")
        print("🔄 bi-girl.net RSS 半自動更新＆1時間おき自動投稿ツール")
        print("============================================================")
        print("1. 既定のブラウザで https://bi-girl.net/feed/ を開きます...")
        print("2. ブラウザで開いたら、以下の【どちらか】を行ってください：")
        print("   ・方法A（一番簡単）：画面上で [Ctrl + A] → [Ctrl + C]（全選択してコピー）")
        print("   ・方法B：画面上で [Ctrl + S] で保存（feed.xml またはダウンロードフォルダ）")
        print("------------------------------------------------------------")
        print("待機中...（最大120秒 / すでに feed.xml を更新済みの場合はそのままお待ちください）")

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

        if xml_content:
            os.makedirs(os.path.dirname(TARGET_SCRATCH), exist_ok=True)
            with open(TARGET_MAIN, "w", encoding="utf-8") as f:
                f.write(xml_content)
            shutil.copyfile(TARGET_MAIN, TARGET_SCRATCH)

            titles = re.findall(r"<item>\s*<title>(.*?)</title>", xml_content, re.S)
            print(f"\n✅ RSSを検知・保存しました！（取得元: {source_desc} / 記事数: {len(titles)}件）")
            for i, t in enumerate(titles[:5], 1):
                print(f"   {i}. {t[:50]}")
            git_sync("Update feed.xml")
        elif os.path.exists(TARGET_MAIN):
            print("\nℹ️ 新規コピーは検知されませんでしたが、既存の feed.xml を使用して未投稿チェックに進みます。")
        else:
            print("\n⚠️ RSSデータが検知されませんでした。")
            return 1

    return post_unposted_bigirl_items(interval_sec=args.interval)


if __name__ == "__main__":
    sys.exit(main())

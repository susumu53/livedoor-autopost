import os
import re
import sys
import io
import time
import requests
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

class BijozukanEyecatchManager:
    """美女図鑑（bijozukan.doorblog.jp）のアイキャッチ画像を自動生成・同期するマネージャー"""

    def __init__(self, blog_id="ranking000-w6crxelo"):
        self.livedoor_id = os.getenv("LIVEDOOR_ID")
        self.api_key = os.getenv("LIVEDOOR_API_KEY")
        self.blog_id = blog_id
        self.ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'app': 'http://www.w3.org/2007/app'
        }

    def upload_to_livedoor(self, image_url):
        """外部画像（Twitter/X等）をライブドアの画像サーバーにアップロード"""
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            res = requests.get(image_url, headers=headers, timeout=15)
            if res.status_code != 200:
                print(f"[画像取得失敗] HTTP {res.status_code}: {image_url}")
                return None
            
            # Content-Type判定
            ct = res.headers.get("Content-Type", "image/jpeg")
            if "png" in ct:
                content_type = "image/png"
            elif "gif" in ct:
                content_type = "image/gif"
            elif "webp" in ct:
                content_type = "image/webp"
            else:
                content_type = "image/jpeg"

            endpoint = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/image"
            upload_resp = requests.post(
                endpoint,
                auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
                data=res.content,
                headers={"Content-Type": content_type},
                timeout=25
            )
            if upload_resp.status_code in [200, 201]:
                up_root = ET.fromstring(upload_resp.text)
                for elem in up_root.iter():
                    if elem.tag.endswith("content") and "src" in elem.attrib:
                        return elem.attrib["src"]
            else:
                print(f"[アップロード失敗] HTTP {upload_resp.status_code}: {upload_resp.text[:100]}")
        except Exception as e:
            print(f"[アップロード例外] {e}")
        return None

    def process_article(self, entry, notify=False):
        """1件の記事をチェックし、アイキャッチが未設定ならライブドア画像に変換して保存"""
        title_elem = entry.find('atom:title', self.ns)
        title = title_elem.text if title_elem is not None else "無題"
        content_elem = entry.find('atom:content', self.ns)
        content = content_elem.text if content_elem is not None else ""

        # 記事IDの取得
        edit_link = None
        alt_link = None
        for l in entry.findall('atom:link', self.ns):
            rel = l.attrib.get('rel')
            if rel == 'edit':
                edit_link = l.attrib.get('href')
            elif rel == 'alternate':
                alt_link = l.attrib.get('href')

        if not edit_link:
            return False

        article_id = edit_link.rstrip('/').split('/')[-1]

        # 記事内の最初の画像を取得
        imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)
        if not imgs:
            return False

        first_img = imgs[0]
        # すでにlivedoor.blogimg.jpの画像が使われていればアイキャッチ設定済み
        if "livedoor.blogimg.jp" in first_img or "blogimg.jp" in first_img:
            return False

        try:
            print(f"[アイキャッチ変換中] [{article_id}] {title}", flush=True)
        except Exception:
            print(f"[アイキャッチ変換中] [{article_id}]", flush=True)

        uploaded_url = self.upload_to_livedoor(first_img)
        if not uploaded_url:
            print(f"[スキップ] 画像のアップロードに失敗: {first_img}", flush=True)
            return False

        # 本文の先頭画像をlivedoor画像に置換
        updated_content = content.replace(first_img, uploaded_url, 1)

        # カテゴリ一覧の取得
        categories = [elem.attrib.get('term') for elem in entry.findall('atom:category', self.ns) if elem.attrib.get('term')]

        escaped_title = saxutils.escape(title)
        cat_tags = "".join([f'<category term="{saxutils.escape(c)}" />\n' for c in categories])
        xml_payload = f'''<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{escaped_title}</title>
  <content type="text/html">
    <![CDATA[{updated_content}]]>
  </content>
  {cat_tags}
  <app:control>
    <app:draft>no</app:draft>
  </app:control>
</entry>'''

        put_res = requests.put(
            edit_link,
            auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
            data=xml_payload.encode('utf-8'),
            headers={'Content-Type': 'application/atom+xml;type=entry'},
            timeout=25
        )

        if put_res.status_code in [200, 201]:
            print(f"[成功] アイキャッチ反映完了: {uploaded_url}", flush=True)
            if notify and alt_link:
                try:
                    from notifier import ArticleNotifier
                    notifier = ArticleNotifier()
                    cat = "美女総集編" if "総集編" in title else "美女図鑑"
                    notifier.send_notification_email(
                        title=title,
                        article_url=alt_link,
                        category=cat,
                        blog_title="美女図鑑",
                        hashtags=["美女図鑑", "美女", "グラビア"],
                        image_url=uploaded_url
                    )
                except Exception as n_err:
                    print(f"[通知エラー] {n_err}", flush=True)
            return True
        else:
            print(f"[失敗] 記事更新失敗: HTTP {put_res.status_code}", flush=True)
            return False

    def sync_eyecatches(self, limit=30, max_pages=5, notify_new=False):
        """最新記事から順にアイキャッチ未設定の記事を検出して自動変換"""
        print(f"=== 美女図鑑 アイキャッチ自動同期開始 (最大 {limit} 件) ===")
        processed_count = 0
        converted_count = 0

        for page in range(1, max_pages + 1):
            url = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article?page={page}"
            res = requests.get(url, auth=HTTPBasicAuth(self.livedoor_id, self.api_key), timeout=20)
            if res.status_code != 200:
                print(f"記事取得エラー: HTTP {res.status_code}")
                break

            root = ET.fromstring(res.text)
            entries = root.findall('atom:entry', self.ns)
            if not entries:
                break

            for entry in entries:
                processed_count += 1
                if self.process_article(entry, notify=notify_new):
                    converted_count += 1
                    time.sleep(1) # API制限に配慮したインターバル

                if processed_count >= limit:
                    break

            if processed_count >= limit:
                break

        print(f"=== 完了: チェック {processed_count} 件 / アイキャッチ設定 {converted_count} 件 ===")
        return converted_count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="美女図鑑 アイキャッチ一括設定・同期ツール")
    parser.add_argument("--limit", type=int, default=20, help="チェックする記事数 (デフォルト: 20)")
    parser.add_argument("--pages", type=int, default=3, help="検索する最大ページ数 (デフォルト: 3)")
    parser.add_argument("--notify", action="store_true", help="アイキャッチ反映時に ntfy へも通知を送信")
    args = parser.parse_args()

    manager = BijozukanEyecatchManager()
    manager.sync_eyecatches(limit=args.limit, max_pages=args.pages, notify_new=args.notify)

import os
import sys
import argparse
import requests
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

class ArticleHeaderUpdater:
    def __init__(self, blog_id=None):
        self.livedoor_id = os.getenv("LIVEDOOR_ID")
        self.api_key = os.getenv("LIVEDOOR_API_KEY")
        self.blog_id = blog_id or os.getenv("LIVEDOOR_BLOG_ID")
        
        if not all([self.livedoor_id, self.api_key, self.blog_id]):
            raise ValueError("LIVEDOOR_ID, LIVEDOOR_API_KEY, LIVEDOOR_BLOG_IDが設定されていません。")

        tpl_path = os.path.join(os.path.dirname(__file__), "templates", "header_menu.html")
        with open(tpl_path, "r", encoding="utf-8") as f:
            self.header_menu_html = f.read()

    def update_article(self, article_id="14752137", dry_run=False):
        """既存の記事を取得し、最上部にセックステクニックメニューを挿入して更新する"""
        article_url = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article/{article_id}"
        print(f"記事を取得中... ID: {article_id} ({article_url})")

        auth = HTTPBasicAuth(self.livedoor_id, self.api_key)
        res = requests.get(article_url, auth=auth, timeout=15)
        if res.status_code != 200:
            print(f"記事取得失敗: ステータス {res.status_code}")
            print(res.text)
            return False

        root = ET.fromstring(res.text)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'app': 'http://www.w3.org/2007/app'
        }

        title_elem = root.find('atom:title', ns)
        title = title_elem.text if title_elem is not None and title_elem.text else ""

        content_elem = root.find('atom:content', ns)
        content = content_elem.text if content_elem is not None and content_elem.text else ""

        # すでにメニューが挿入されているか確認
        if "st-nav-wrapper" in content:
            print(f"すでにセックステクニックメニューが挿入されています。更新をスキップします。")
            return True

        # 本文の最上部にメニューを追加（ブログタイトルの直下へ自動移動するスクリプト付き）
        auto_move_script = """
        <script>
        (function() {
            function moveMenuToHeader() {
                var menu = document.querySelector('.st-nav-wrapper');
                var header = document.getElementById('blog-header');
                if (menu && header && menu.parentNode !== header.parentNode) {
                    header.parentNode.insertBefore(menu, header.nextSibling);
                    menu.style.marginBottom = '20px';
                }
            }
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', moveMenuToHeader);
            } else {
                moveMenuToHeader();
            }
        })();
        </script>
        """
        new_content = self.header_menu_html + "\n" + auto_move_script + "\n" + content

        # カテゴリ一覧の取得
        category_elems = root.findall('atom:category', ns)
        categories = [c.attrib.get('term', '') for c in category_elems if c.attrib.get('term')]

        # XMLの再構築
        escaped_title = saxutils.escape(title)
        category_tags = "".join([f'<category term="{saxutils.escape(cat)}" />\n' for cat in categories])

        xml_template = f'''<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{escaped_title}</title>
  <content type="text/html">
    <![CDATA[{new_content}]]>
  </content>
  {category_tags}
  <app:control>
    <app:draft>no</app:draft>
  </app:control>
</entry>'''

        if dry_run:
            print(f"[DRY-RUN] タイトル: {title}")
            print(f"[DRY-RUN] メニューを本文最上部に追加しました (追加後文字数: {len(new_content)})")
            return True

        print(f"記事を上書き更新中... [ID: {article_id}]")
        put_res = requests.put(
            article_url,
            auth=auth,
            data=xml_template.encode('utf-8'),
            headers={'Content-Type': 'application/atom+xml;type=entry'}
        )

        if put_res.status_code in [200, 201]:
            print(f"記事 {article_id} の更新に成功しました！")
            return True
        else:
            print(f"記事更新失敗: ステータス {put_res.status_code}")
            print(put_res.text)
            return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="既存記事への上部メニュー挿入スクリプト")
    parser.add_argument("--id", type=str, default="14752137", help="更新対象の記事ID (デフォルト: 14752137)")
    parser.add_argument("--dry-run", action="store_true", help="更新せずシミュレーションのみ行う")
    args = parser.parse_args()

    updater = ArticleHeaderUpdater()
    updater.update_article(article_id=args.id, dry_run=args.dry_run)

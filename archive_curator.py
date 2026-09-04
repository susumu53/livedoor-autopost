import os
import re
import json
import datetime
import requests
import xml.etree.ElementTree as ET
import bs4
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from curation_engine import sanitize_text

load_dotenv()

class ArchiveCurator:
    def __init__(self, blog_id="ranking000-w6crxelo"):
        self.livedoor_id = os.getenv("LIVEDOOR_ID")
        self.api_key = os.getenv("LIVEDOOR_API_KEY")
        self.blog_id = blog_id or os.getenv("LIVEDOOR_BLOG_ID", "ranking000-w6crxelo")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-3.6-flash"

    def upload_image(self, image_source, content_type="image/jpeg"):
        """画像をライブドアブログにアップロードし、livedoor.blogimg.jpの画像URLを返す（OGP・見出し画像用）"""
        image_endpoint = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/image"
        try:
            image_data = None
            if isinstance(image_source, str) and (image_source.startswith("http://") or image_source.startswith("https://")):
                res = requests.get(image_source, timeout=15)
                if res.status_code == 200:
                    image_data = res.content
                    ct = res.headers.get("Content-Type", "")
                    if "png" in ct:
                        content_type = "image/png"
                    elif "gif" in ct:
                        content_type = "image/gif"
                    elif "webp" in ct:
                        content_type = "image/webp"
                else:
                    return image_source
            elif isinstance(image_source, (bytes, bytearray)):
                image_data = image_source
            else:
                return image_source

            headers = {"Content-Type": content_type}
            resp = requests.post(
                image_endpoint,
                auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
                data=image_data,
                headers=headers,
                timeout=25
            )
            if resp.status_code in [200, 201]:
                root = ET.fromstring(resp.text)
                for elem in root.iter():
                    if elem.tag.endswith("content") and "src" in elem.attrib:
                        uploaded_url = elem.attrib["src"]
                        print(f"[アイキャッチ画像アップロード成功] {uploaded_url}")
                        return uploaded_url
            print(f"[アイキャッチ画像アップロード失敗] ステータス: {resp.status_code}")
        except Exception as e:
            print(f"[画像アップロードエラー] {e}")
        return image_source

    def fetch_past_articles(self, target_count=30, start_offset=0, max_pages=30):
        """過去に投稿された記事をAtomPub経由で取得し、美女情報を抽出する"""
        items = []
        seen_names = set()
        skipped = 0
        page_url = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article"

        print(f"過去記事の取得を開始します (スキップ: {start_offset}件, 目標取得: {target_count}件)...")

        for page in range(1, max_pages + 1):
            if not page_url:
                break

            try:
                res = requests.get(page_url, auth=HTTPBasicAuth(self.livedoor_id, self.api_key), timeout=15)
                if res.status_code != 200:
                    print(f"AtomPub取得エラー (Page {page}): {res.status_code}")
                    break

                root = ET.fromstring(res.text)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('atom:entry', ns)

                if not entries:
                    break

                for e in entries:
                    title_elem = e.find('atom:title', ns)
                    raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
                    content_elem = e.find('atom:content', ns)
                    content = content_elem.text if content_elem is not None and content_elem.text else ""

                    # 記事URL
                    alt_links = [l.attrib.get('href') for l in e.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                    article_url = alt_links[0] if alt_links else ""

                    # HTMLの解析
                    soup = bs4.BeautifulSoup(content, 'html.parser')
                    img = soup.find('img')
                    img_src = img.get('src') if img else ""

                    # DMM / FANZAアフィリエイトリンク
                    dmm_links = [a.get('href') for a in soup.find_all('a') if 'fanza' in a.get('href', '') or 'dmm' in a.get('href', '')]
                    dmm_url = dmm_links[0] if dmm_links else ""

                    # 名前の抽出
                    m = re.search(r'ネットで見つけた美女\s*(.*?)\s*\(@([a-zA-Z0-9_]+)\)', raw_title)
                    if m:
                        name = m.group(1).strip()
                        tw_id = m.group(2).strip()
                    else:
                        name = raw_title.replace("ネットで見つけた美女", "").strip()
                        tw_id = ""

                    name = sanitize_text(name)
                    if not name or name in seen_names or not img_src:
                        continue

                    seen_names.add(name)

                    # オフセット処理
                    if skipped < start_offset:
                        skipped += 1
                        continue

                    items.append({
                        "name": name,
                        "twitter_id": tw_id,
                        "twitter_url": f"https://x.com/{tw_id}" if tw_id else "",
                        "article_url": article_url,
                        "image_url": img_src,
                        "dmm_url": dmm_url,
                        "raw_title": raw_title
                    })

                    if len(items) >= target_count:
                        break

                if len(items) >= target_count:
                    break

                # 次のページのURL
                next_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'next']
                page_url = next_links[0] if next_links else None

            except Exception as e:
                print(f"ページ {page} 取得中にエラー: {e}")
                break

        print(f"合計 {len(items)} 件の過去美女データを取得しました。")
        return items

    def generate_ai_commentary(self, items):
        """Gemini AIで過去の美女たちの紹介レビューを生成する"""
        fallbacks = [
            "透明感あふれるビジュアルと愛らしい笑顔が魅力的。SNSでも常にファンを魅了している大注目の美女です。",
            "抜群のスタイルと大人っぽい色気が眩しい存在感を放つ美女。洗練された美しいルックスに視線が釘付けになります。",
            "可憐な雰囲気の中に芯のある美しさを感じる注目の逸材。自然体な仕草と笑顔が多くの支持を集めています。",
            "モデル顔負けの引き締まったプロポーションが素晴らしい美女。どこを切り取っても絵になる華やかさです。",
            "一度見たら忘れられない印象的な瞳と美貌を持つ美女。話題沸騰の理由がひと目でわかる圧倒的な魅力です。"
        ]

        if not self.gemini_api_key:
            return {
                "intro": "当ブログ「美女図鑑」でこれまでご紹介してきた数多くの美女の中から、特に反響の大きかった注目の美女たちを厳選！個性豊かで魅力的な彼女たちの魅力を、総集編として一挙にお届けします。",
                "reviews": {i: fallbacks[i % len(fallbacks)] for i in range(len(items))}
            }

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.model_name)

            names_str = "\n".join([f"{i+1}. 名前: {it['name']} (@{it['twitter_id']})" for i, it in enumerate(items)])

            prompt = f"""あなたは美女まとめブログ「美女図鑑」の専任ライターです。
当ブログで過去に紹介した美女たちの【総集編・大全集】記事を作成します。
以下の美女一覧（全{len(items)}名）について、読者がワクワクする品のある紹介文を執筆してください。

美女一覧:
{names_str}

以下のJSON形式のみで出力してください（マークダウンのコードブロック```json ... ```で囲む）:
{{
  "intro": "記事冒頭の読者を引き込む総集編の導入文（150文字程度。当ブログが厳選した神美女たちを一挙紹介する熱量の高い文章）",
  "reviews": [
    "1人目の魅力・見どころレビュー（50〜80文字程度。ポジティブで華やかな紹介文）",
    "2人目の魅力・見どころレビュー...",
    ...（全{len(items)}名分）
  ]
}}
※過激な露骨表現は避け、ビジュアル、透明感、スタイル、笑顔、SNSでの話題性を称賛する文章にしてください。
"""
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
            else:
                parsed = json.loads(raw_text)

            reviews_dict = {}
            for idx, rev in enumerate(parsed.get("reviews", [])):
                reviews_dict[idx] = rev

            for i in range(len(items)):
                if i not in reviews_dict:
                    reviews_dict[i] = fallbacks[i % len(fallbacks)]

            return {
                "intro": parsed.get("intro", "当ブログ「美女図鑑」がこれまでご紹介してきた美女たちの中から、特に注目の神美女を厳選！"),
                "reviews": reviews_dict
            }
        except Exception as e:
            print(f"Gemini API Exception in archive: {e}")
            return {
                "intro": "当ブログ「美女図鑑」でこれまでご紹介してきた美女たちの中から、特にSNS等で大きな反響を呼んだ美女を厳選ピックアップ！それぞれの個性と輝く魅力を一挙に振り返る豪華総集編です。",
                "reviews": {i: fallbacks[i % len(fallbacks)] for i in range(len(items))}
            }

    def generate_mega_archive_html(self, count=30, vol=1, start_offset=0):
        """過去記事から総集編まとめ記事を生成する"""
        items = self.fetch_past_articles(target_count=count, start_offset=start_offset)
        if not items:
            print("過去記事の抽出に失敗しました。")
            return None, None, None, None

        # 先頭（No.1）美女の画像をライブドアにアップロードしてOGP/Twitter Card画像として自動認識させる
        if items and items[0].get("image_url"):
            uploaded_url = self.upload_image(items[0]["image_url"])
            if uploaded_url:
                items[0]["image_url"] = uploaded_url

        actual_count = len(items)
        now = datetime.datetime.now()
        date_str = now.strftime("%Y年%m月%d日")
        vol_str = f" Vol.{vol}" if vol else ""
        title = f"【保存版・総集編{vol_str}】歴代の注目美女{actual_count}選！当ブログ「美女図鑑」が厳選したSNS話題の神美女カタログ"
        category = "美女総集編"

        print(f"Gemini AIで紹介文と導入文を生成中 (Vol.{vol} / {actual_count}人分)...")
        ai_data = self.generate_ai_commentary(items)
        intro_text = ai_data["intro"]
        reviews = ai_data["reviews"]

        # タグの収集
        all_tags = ["美女総集編", "美女まとめ", "保存版"]
        for it in items:
            clean_name = re.sub(r'[^\w\s]', '', it["name"]).strip()
            if clean_name and clean_name not in all_tags:
                all_tags.append(clean_name)
        final_tags = all_tags[:20]

        # スタイル
        style = """
<style>
.archive-wrap {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #2d3748;
  max-width: 820px;
  margin: 0 auto;
  line-height: 1.7;
}
.archive-hero {
  background: linear-gradient(135deg, #111827 0%, #374151 100%);
  color: #ffffff;
  padding: 40px 25px;
  border-radius: 16px;
  text-align: center;
  margin-bottom: 30px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.15);
}
.hero-tag {
  display: inline-block;
  background: #ec4899;
  color: #fff;
  font-size: 13px;
  font-weight: bold;
  padding: 4px 16px;
  border-radius: 20px;
  margin-bottom: 12px;
  letter-spacing: 1px;
}
.archive-hero h1 {
  font-size: 24px;
  margin: 0 0 15px;
  line-height: 1.4;
  color: #ffffff;
}
.hero-intro {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(5px);
  padding: 18px 20px;
  border-radius: 10px;
  font-size: 15px;
  text-align: left;
  line-height: 1.8;
  margin-top: 15px;
}
.toc-box {
  background: #fdf2f8;
  border: 1px solid #fbcfe8;
  border-left: 5px solid #ec4899;
  border-radius: 12px;
  padding: 22px 25px;
  margin-bottom: 40px;
}
.toc-title {
  font-size: 18px;
  font-weight: bold;
  color: #831843;
  margin-bottom: 15px;
}
.toc-grid {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px 20px;
}
.toc-grid a {
  color: #be185d;
  text-decoration: none;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.toc-grid a:hover {
  text-decoration: underline;
  color: #9d174d;
}
.archive-card {
  background: #ffffff;
  border-radius: 16px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06);
  padding: 25px;
  margin-bottom: 45px;
  transition: transform 0.2s;
}
.archive-card:hover {
  transform: translateY(-3px);
}
.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 15px;
}
.rank-badge {
  background: linear-gradient(135deg, #ec4899 0%, #f43f5e 100%);
  color: #ffffff;
  font-size: 15px;
  font-weight: bold;
  padding: 4px 14px;
  border-radius: 20px;
}
.name-text {
  font-size: 21px;
  font-weight: bold;
  color: #1f2937;
}
.card-photo {
  text-align: center;
  margin-bottom: 20px;
}
.card-photo img {
  max-width: 100%;
  max-height: 500px;
  height: auto;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}
.card-comment {
  background: #fdf2f8;
  border-left: 4px solid #ec4899;
  padding: 14px 18px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  margin-bottom: 20px;
}
.btn-container {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.btn-sub {
  flex: 1;
  min-width: 200px;
  display: block;
  background: #1f2937;
  color: #ffffff !important;
  text-decoration: none;
  font-weight: bold;
  font-size: 14px;
  text-align: center;
  padding: 12px 15px;
  border-radius: 25px;
  transition: background 0.2s;
}
.btn-sub:hover {
  background: #374151;
}
.btn-main {
  flex: 1;
  min-width: 200px;
  display: block;
  background: linear-gradient(135deg, #ec4899 0%, #f43f5e 100%);
  color: #ffffff !important;
  text-decoration: none;
  font-weight: bold;
  font-size: 14px;
  text-align: center;
  padding: 12px 15px;
  border-radius: 25px;
  box-shadow: 0 4px 12px rgba(236, 72, 153, 0.3);
  transition: transform 0.2s;
}
.btn-main:hover {
  transform: translateY(-2px);
}
</style>
"""

        html_out = f'{style}\n<div class="archive-wrap">\n'
        
        # ヒーローバナー
        html_out += f'''
  <div class="archive-hero">
    <span class="hero-tag">ALL-STAR SPECIAL ARCHIVE</span>
    <h1>{title}</h1>
    <div style="font-size: 13px; opacity: 0.85;">集計日: {date_str} ｜ カテゴリー: {category}</div>
    <div class="hero-intro">
      {intro_text}
    </div>
  </div>
'''

        # 目次
        html_out += '''
  <div class="toc-box">
    <div class="toc-title">📑 掲載美女 目次一覧（クリックでジャンプ）</div>
    <ul class="toc-grid">
'''
        for idx, it in enumerate(items, 1):
            html_out += f'      <li><a href="#archive-{idx}"><b>#{idx}</b> {it["name"]}</a></li>\n'
        html_out += '''    </ul>
  </div>
'''

        # 各美女カード
        for idx, it in enumerate(items, 1):
            rev = reviews.get(idx - 1, "息をのむ美貌と独自の存在感が光る注目の美女です。")
            
            # ボタン群（内部リンク＋外部リンク）
            buttons_html = ""
            if it["article_url"]:
                buttons_html += f'<a href="{it["article_url"]}" class="btn-sub" target="_blank">📖 当ブログの個別記事を見る</a>\n'
            if it["dmm_url"]:
                buttons_html += f'<a href="{it["dmm_url"]}" class="btn-main" target="_blank" rel="noopener">🎬 公式作品・詳細を見る</a>\n'
            elif it["twitter_url"]:
                buttons_html += f'<a href="{it["twitter_url"]}" class="btn-main" target="_blank" rel="noopener">✨ X(Twitter)公式を見る</a>\n'

            html_out += f'''
  <div class="archive-card" id="archive-{idx}">
    <div class="card-header">
      <span class="rank-badge">No. {idx}</span>
      <span class="name-text">{it["name"]}</span>
    </div>

    <div class="card-photo">
      <a href="{it["article_url"] or it["twitter_url"] or '#'}" target="_blank">
        <img src="{it["image_url"]}" alt="{it["name"]}">
      </a>
    </div>

    <div class="card-comment">
      <div style="font-weight: bold; color: #be185d; font-size: 13px; margin-bottom: 4px;">💡 編集部ピックアップ解説</div>
      {rev}
    </div>

    <div class="btn-container">
      {buttons_html}
    </div>
  </div>
'''

        # フッター
        html_out += f'''
  <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 16px; padding: 30px 25px; text-align: center; margin-top: 50px;">
    <h3 style="font-size: 18px; margin: 0 0 10px; color: #1f2937;">🌟 美女図鑑の最新情報は週2回更新中！</h3>
    <p style="font-size: 14px; color: #6b7280; margin: 0 0 15px;">
      当ブログでは、毎週水曜日と日曜日にテーマ別の最新美女まとめ・ランキングをお届けしています。<br>
      お気に入りの美女が見つかったら、ぜひブックマークやSNSでのシェアをお願いいたします！
    </p>
  </div>
</div>
'''
        return title, html_out, category, final_tags

    def post_archive_article(self, count=30, vol=1, start_offset=0, publish=True):
        """総集編まとめ記事を生成してLivedoorブログへ投稿する"""
        title, html_content, category, tags = self.generate_mega_archive_html(count=count, vol=vol, start_offset=start_offset)
        if not title or not html_content:
            print("記事生成に失敗したため、投稿を中止します。")
            return None

        # AtomPub投稿
        import xml.sax.saxutils as saxutils
        endpoint = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article"
        escaped_title = saxutils.escape(title)
        
        category_tags = ""
        for tag in [category] + tags[:10]:
            category_tags += f'<category term="{saxutils.escape(tag)}" />\n'

        draft_val = "no" if publish else "yes"
        xml_payload = f'''<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{escaped_title}</title>
  <content type="text/html">
    <![CDATA[{html_content}]]>
  </content>
  {category_tags}
  <app:control>
    <app:draft>{draft_val}</app:draft>
  </app:control>
</entry>'''

        print(f"ライブドアブログ ({self.blog_id}) へ総集編記事を投稿中... [{title}]")
        response = requests.post(
            endpoint,
            auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
            data=xml_payload.encode('utf-8'),
            headers={'Content-Type': 'application/atom+xml;type=entry'},
            timeout=25
        )

        if response.status_code in [200, 201]:
            art_url = ""
            try:
                root = ET.fromstring(response.text)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                alt_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                if alt_links:
                    art_url = alt_links[0]
            except Exception as e:
                print(f"[URL抽出警告] {e}")

            if not art_url:
                art_url = "https://bijozukan.doorblog.jp/"

            print(f"[SUCCESS] 総集編記事の投稿に成功しました！(ステータス: {response.status_code})")
            print(f"[公開URL] {art_url}")

            if publish:
                try:
                    from notifier import ArticleNotifier
                    notifier = ArticleNotifier()
                    notifier.send_notification_email(
                        title=title,
                        article_url=art_url,
                        category="美女総集編",
                        blog_title="美女図鑑",
                        hashtags=["美女図鑑", "美女", "グラビア", f"Vol{vol}"]
                    )
                except Exception as notify_err:
                    print(f"[通知送信エラー] {notify_err}")

            return response.text
        else:
            print(f"[FAILED] 投稿失敗: ステータス {response.status_code}")
            print(response.text)
            return None

    def load_progress(self):
        """進捗管理ファイルから次回投稿予定のVol番号を取得する"""
        state_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive_progress.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"進捗ファイルの読み込みエラー: {e}")
        return {
            "current_vol": 2,
            "posted_history": [
                {"vol": 1, "posted_at": "2026-09-03T07:43:00", "url": "https://bijozukan.doorblog.jp/archives/16986201.html"}
            ]
        }

    def save_progress(self, data):
        """進捗管理ファイルに進捗を保存する"""
        state_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive_progress.json")
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"進捗ファイルの保存エラー: {e}")

    def notify_article(self, article_url=None, title=None):
        """指定した記事（または最新記事）のX投稿通知を ntfy に送信する"""
        from notifier import ArticleNotifier
        if not article_url or not title:
            print(f"最新記事をAtomPubから取得中 ({self.blog_id})...")
            page_url = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article"
            try:
                res = requests.get(page_url, auth=HTTPBasicAuth(self.livedoor_id, self.api_key), timeout=15)
                if res.status_code == 200:
                    root = ET.fromstring(res.text)
                    ns = {'atom': 'http://www.w3.org/2005/Atom'}
                    entries = root.findall('atom:entry', ns)
                    if entries:
                        latest = entries[0]
                        t_elem = latest.find('atom:title', ns)
                        title = title or (t_elem.text if t_elem is not None else "美女図鑑 新着記事")
                        alt_links = [l.attrib.get('href') for l in latest.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                        article_url = article_url or (alt_links[0] if alt_links else "https://bijozukan.doorblog.jp/")
            except Exception as e:
                print(f"AtomPub取得エラー: {e}")

        if not article_url:
            print("[エラー] 通知対象の記事URLが特定できませんでした。")
            return False

        notifier = ArticleNotifier()
        print(f"[通知送信開始] {title} ({article_url})")
        notifier.send_notification_email(
            title=title,
            article_url=article_url,
            category="美女総集編",
            blog_title="美女図鑑",
            hashtags=["美女図鑑", "美女", "グラビア"]
        )
        return True

    def run_daily_archive_post(self, count=30):
        """一日一回、次の巻（Vol.X）を自動投稿して進捗を更新する"""
        progress = self.load_progress()
        vol = progress.get("current_vol", 2)
        offset = (vol - 1) * count

        print(f"==================================================")
        print(f"🚀 一日一回 総集編自動投稿: Vol.{vol} (スキップ: {offset}件)")
        print(f"==================================================")

        res = self.post_archive_article(count=count, vol=vol, start_offset=offset, publish=True)
        if res:
            art_url = ""
            try:
                root = ET.fromstring(res)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                alt_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                if alt_links:
                    art_url = alt_links[0]
            except Exception:
                pass

            progress["current_vol"] = vol + 1
            progress["posted_history"].append({
                "vol": vol,
                "posted_at": datetime.datetime.now().isoformat(),
                "url": art_url or "https://bijozukan.doorblog.jp/"
            })
            self.save_progress(progress)
            print(f"🎉 [SUCCESS] Vol.{vol} の投稿が完了しました！次回予定: Vol.{vol + 1}")
            return True
        else:
            print(f"❌ [FAILED] Vol.{vol} の投稿に失敗しました。進捗は更新されません。")
            return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="美女図鑑 過去記事まとめ（総集編）生成スクリプト")
    parser.add_argument("--count", type=int, default=30, help="総集編に掲載する人数 (デフォルト: 30)")
    parser.add_argument("--vol", type=int, default=None, help="手動指定時の巻数 (例: 1, 2, 3...)")
    parser.add_argument("--offset", type=int, default=None, help="手動指定時のスキップ件数")
    parser.add_argument("--daily-auto", action="store_true", help="一日一回モード：前回の続きから自動投稿して進捗を更新する")
    parser.add_argument("--notify-latest", action="store_true", help="美女図鑑の最新記事を ntfy に送信してX投稿リンクを発行する")
    parser.add_argument("--notify-url", type=str, default=None, help="指定URLの記事を ntfy に送信")
    parser.add_argument("--notify-title", type=str, default=None, help="通知時のタイトル（--notify-urlと併用）")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずHTML生成のみテストする")
    parser.add_argument("--blog-id", type=str, default="ranking000-w6crxelo", help="対象ブログID")
    args = parser.parse_args()

    curator = ArchiveCurator(blog_id=args.blog_id)

    if args.notify_latest:
        curator.notify_article()
    elif args.notify_url:
        curator.notify_article(article_url=args.notify_url, title=args.notify_title)
    elif args.daily_auto:
        # 一日一回自動実行モード
        curator.run_daily_archive_post(count=args.count)
    else:
        # 手動実行モード
        vol = args.vol or 1
        offset = args.offset if args.offset is not None else (vol - 1) * args.count

        if args.dry_run:
            title, html_content, category, tags = curator.generate_mega_archive_html(count=args.count, vol=vol, start_offset=offset)
            print(f"[DRY-RUN] タイトル: {title}")
            print(f"[DRY-RUN] カテゴリー: {category}")
            print(f"[DRY-RUN] タグ数: {len(tags)}")
            print(f"[DRY-RUN] HTML文字数: {len(html_content)}")
            with open("scratch/archive_test_preview.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            print("プレビューを scratch/archive_test_preview.html に保存しました。")
        else:
            curator.post_archive_article(count=args.count, vol=vol, start_offset=offset, publish=True)



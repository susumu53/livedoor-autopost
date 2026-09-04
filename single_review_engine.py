import os
import re
import json
import datetime
import requests
import xml.sax.saxutils as saxutils
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from dmm_client import DMMClient
from curation_engine import sanitize_text

load_dotenv()

class SingleReviewEngine:
    def __init__(self, blog_id=None):
        self.livedoor_id = os.getenv("LIVEDOOR_ID")
        self.api_key = os.getenv("LIVEDOOR_API_KEY")
        self.blog_id = blog_id or os.getenv("LIVEDOOR_BLOG_ID", "ranking000")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-3.6-flash"
        self.dmm = DMMClient()

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
                import xml.etree.ElementTree as ET
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

    def get_trending_work(self, keyword=None, service="digital", floor="videoa"):
        """おすすめの注目作を1本取得する"""
        items = self.dmm.get_top_fanza_works(service=service, floor=floor, hits=15, keyword=keyword)
        if not items:
            return None

        # レビュー件数が多く、画像とサンプルが豊富なものを選択
        best_item = None
        for it in items:
            img = it.get("imageURL", {}).get("large")
            samples = it.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
            if img and samples:
                best_item = it
                break
        
        return best_item or items[0]

    def extract_work_details(self, raw_item):
        """APIレスポンスから作品情報を整理・抽出する"""
        raw_title = raw_item.get("title", "")
        title = sanitize_text(raw_title)
        
        item_info = raw_item.get("iteminfo", {})
        actress_list = [sanitize_text(a.get("name", "")) for a in item_info.get("actress", []) if a.get("name")]
        actress_str = ", ".join(actress_list) if actress_list else "人気女優"
        
        maker = ", ".join([sanitize_text(m.get("name", "")) for m in item_info.get("maker", []) if m.get("name")])
        label = ", ".join([sanitize_text(l.get("name", "")) for l in item_info.get("label", []) if l.get("name")])
        series = ", ".join([sanitize_text(s.get("name", "")) for s in item_info.get("series", []) if s.get("name")])
        director = ", ".join([sanitize_text(d.get("name", "")) for d in item_info.get("director", []) if d.get("name")])

        # サンプル画像
        samples = raw_item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
        if isinstance(samples, str):
            sample_images = [samples]
        else:
            sample_images = samples if samples else []

        # 価格情報
        prices = raw_item.get("prices", {})
        deliveries = prices.get("deliveries", {}).get("delivery", [])
        price_display = "詳細は公式サイトへ"
        for d in deliveries:
            if d.get("price"):
                price_display = f"{d.get('price')}円〜"
                break

        # レビュー評価
        review = raw_item.get("review", {})
        rating = review.get("average", "4.5")
        review_count = review.get("count", "多数")

        return {
            "content_id": raw_item.get("content_id", ""),
            "title": title,
            "raw_title": raw_title,
            "actress": actress_str,
            "actress_tags": actress_list,
            "maker": maker or "公式メーカー",
            "label": label or "公式レーベル",
            "series": series or "単体作品",
            "director": director or "非公開",
            "date": raw_item.get("date", "配信中"),
            "price": price_display,
            "rating": rating,
            "review_count": review_count,
            "affiliate_url": raw_item.get("affiliateURL", "#"),
            "image_url": raw_item.get("imageURL", {}).get("large", ""),
            "sample_images": sample_images[:8]
        }

    def generate_deep_review_content(self, work):
        """Gemini AIを活用して本格的な1作品深掘りレビュー本文を執筆する"""
        fallback_data = {
            "catchphrase": f"圧倒的なビジュアルと息をのむリアリティ！{work['actress']}が魅せる極上の名作レビュー",
            "intro": f"今回ピックアップするのは、多くのファンから熱烈な支持を集めている注目作『{work['title']}』。主演を務める{work['actress']}さんの卓越した存在感と、細部まで計算された演出が見事に融合した一本です。なぜ本作がこれほどまでに高く評価されているのか、その見どころを徹底的に解説します。",
            "story": f"本作は、日常のふとした隙間に潜む非日常的なシチュエーションをリアルに描いたストーリー仕立て。{work['actress']}さんが演じるキャラクターのリアルな感情の揺れ動きと、徐々にエスカレートしていく緊迫感のある展開が観る者の心を掴んで離しません。",
            "highlights": [
                {
                    "title": f"① {work['actress']}の圧倒的な表情変化とリアルな演技",
                    "text": "カメラが捉える繊細な視線、戸惑いから快感へと移り変わるリアルな表情のグラデーションが秀逸。言葉以上に表情が多くを物語り、観る側をグイグイと作品の世界へ引き込みます。"
                },
                {
                    "title": "② 臨場感あふれるカメラワークとシチュエーション演出",
                    "text": "過剰な演出に頼らず、その場の空気感や緊迫した息遣いを丁寧に切り取った演出力が光ります。アングルの一つひとつにこだわりが感じられ、まるでその場にいるかのような錯覚を覚えます。"
                },
                {
                    "title": "③ 息をのむクライマックスと圧倒的なカタルシス",
                    "text": "序盤から積み重ねてきたシチュエーションが一気に炸裂する終盤は圧巻の一言。緊張の糸が解き放たれ、感情と快感が最高潮に達する瞬間はまさにファン必見の名シーンです。"
                }
            ],
            "recommended_for": [
                f"{work['actress']}さんの魅力的な表情やリアルな仕草をじっくり堪能したい方",
                "リアリティのあるシチュエーション設定や丁寧な演出を好む方",
                "単なる刺激だけでなく、物語や雰囲気の完成度を重視する方"
            ],
            "conclusion": f"『{work['title']}』は、ビジュアル・演技・演出の三拍子が揃った完成度の高い傑作です。今どの作品を観るべきか迷っているなら、まず間違いなく手に取る価値のある一本と言えるでしょう。"
        }

        if not self.gemini_api_key:
            return fallback_data

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.model_name)

            prompt = f"""あなたは映画やエンターテインメント作品を深く分析・解説するプロのカルチャー評論家・レビューライターです。
以下の作品について、読者が思わず引き込まれ、作品の魅力や見どころが手に取るように伝わる【本格的な徹底深掘りレビュー記事】を執筆してください。

【作品情報】
・タイトル: {work['title']}
・出演: {work['actress']}
・メーカー: {work['maker']}
・レーベル: {work['label']}
・シリーズ: {work['series']}
・配信日: {work['date']}

以下のJSON形式のみで出力してください（マークダウンのコードブロック```json ... ```で囲む）:
{{
  "catchphrase": "作品の本質を突いた魅力的な1行キャッチコピー（40〜60文字）",
  "intro": "作品の導入文。なぜ今この作品が注目されているのか、キャストの魅力を含めた引き込む文章（150〜200文字）",
  "story": "あらすじとシチュエーション設定の解説。ネタバレに配慮しつつ、設定の面白さや世界観を伝える（150〜200文字）",
  "highlights": [
    {{
      "title": "① 出演者の演技や表情の魅力に関する見出し（20〜30文字）",
      "text": "表情の変化、視線、リアリティなどキャストの素晴らしい見どころ解説（120〜160文字）"
    }},
    {{
      "title": "② 演出やシチュエーションのこだわりに関する見出し（20〜30文字）",
      "text": "カメラワーク、アングル、シチュエーションの臨場感の解説（120〜160文字）"
    }},
    {{
      "title": "③ クライマックスや名シーンに関する見出し（20〜30文字）",
      "text": "感情の高揚感や作品の決定的な見どころ解説（120〜160文字）"
    }}
  ],
  "recommended_for": [
    "こんな人におすすめのポイント1",
    "こんな人におすすめのポイント2",
    "こんな人におすすめのポイント3"
  ],
  "conclusion": "作品の総評とまとめ。読者に強く推薦する理由（150文字程度）"
}}
※過激な露骨表現は避け、ビジュアル、スタイル、表情、演技力、演出、シチュエーションの魅力を引き立てる知的で情熱的なレビュー文にしてください。
"""
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
            else:
                parsed = json.loads(raw_text)

            return parsed
        except Exception as e:
            print(f"Gemini API Exception in single review: {e}")
            return fallback_data

    def generate_review_article_html(self, work):
        """1作品深掘りレビューの完全なHTMLとタイトル、タグを生成する"""
        review = self.generate_deep_review_content(work)
        
        # タイトルSEO最適化
        title = f"【徹底レビュー】『{work['title']}』の見どころ＆感想！{work['actress']}の魅力を深掘り解説"
        category = "作品深掘りレビュー"

        now = datetime.datetime.now()
        date_str = now.strftime("%Y年%m月%d日")

        # タグの構成
        all_tags = ["作品レビュー", "おすすめ", "徹底解説"]
        if work["actress_tags"]:
            all_tags.extend(work["actress_tags"])
        if work["maker"]:
            all_tags.append(work["maker"])
        final_tags = all_tags[:15]

        # サンプル画像HTML
        sample_html = ""
        if work["sample_images"]:
            sample_html = '<div class="sample-gallery">\n'
            for s_img in work["sample_images"]:
                sample_html += f'  <a href="{work["affiliate_url"]}" target="_blank" rel="noopener"><img src="{s_img}" alt="サンプルシーン"></a>\n'
            sample_html += '</div>\n'

        # おすすめリストHTML
        rec_html = "".join([f"<li>✅ {item}</li>" for item in review.get("recommended_for", [])])

        # ハイライトセクションHTML
        highlights_html = ""
        for h in review.get("highlights", []):
            highlights_html += f"""
            <div class="highlight-card">
              <div class="highlight-title">{h.get('title', '')}</div>
              <p class="highlight-text">{h.get('text', '')}</p>
            </div>
            """

        style = """
<style>
.review-container {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #2c3e50;
  max-width: 820px;
  margin: 0 auto;
  line-height: 1.8;
}
.review-hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  color: #ffffff;
  padding: 35px 25px;
  border-radius: 16px;
  text-align: center;
  margin-bottom: 30px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.15);
}
.review-hero .badge {
  display: inline-block;
  background: #3b82f6;
  color: #fff;
  font-size: 13px;
  font-weight: bold;
  padding: 4px 14px;
  border-radius: 20px;
  margin-bottom: 12px;
}
.review-hero h1 {
  font-size: 23px;
  margin: 0 0 15px;
  line-height: 1.4;
  color: #ffffff;
}
.review-catchphrase {
  background: rgba(59, 130, 246, 0.15);
  border-left: 4px solid #3b82f6;
  padding: 15px 18px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: bold;
  color: #93c5fd;
  text-align: left;
  margin-top: 15px;
}
.main-package {
  text-align: center;
  margin: 30px 0;
}
.main-package img {
  max-width: 100%;
  height: auto;
  border-radius: 14px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.15);
}
.specs-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 22px;
  margin-bottom: 35px;
}
.specs-title {
  font-size: 17px;
  font-weight: bold;
  color: #1e293b;
  margin-bottom: 15px;
  border-bottom: 2px solid #cbd5e1;
  padding-bottom: 8px;
}
.specs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.specs-table th {
  text-align: left;
  color: #64748b;
  padding: 8px 10px;
  width: 110px;
  border-bottom: 1px solid #e2e8f0;
}
.specs-table td {
  color: #1e293b;
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
}
.section-title {
  font-size: 20px;
  font-weight: bold;
  color: #0f172a;
  border-left: 5px solid #3b82f6;
  padding-left: 12px;
  margin: 35px 0 15px;
}
.section-body {
  background: #ffffff;
  padding: 20px 22px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  font-size: 15px;
  line-height: 1.8;
  margin-bottom: 25px;
}
.highlight-card {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 15px;
}
.highlight-title {
  font-size: 16px;
  font-weight: bold;
  color: #0284c7;
  margin-bottom: 8px;
}
.highlight-text {
  font-size: 14px;
  color: #334155;
  margin: 0;
  line-height: 1.7;
}
.sample-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
  margin: 20px 0 35px;
}
.sample-gallery img {
  width: 100%;
  height: auto;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: transform 0.2s, opacity 0.2s;
}
.sample-gallery img:hover {
  transform: scale(1.02);
  opacity: 0.9;
}
.rec-box {
  background: #fdf4ff;
  border: 1px solid #f0abfc;
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 35px;
}
.rec-box ul {
  list-style: none;
  padding: 0;
  margin: 10px 0 0;
}
.rec-box li {
  font-size: 14px;
  color: #701a75;
  margin-bottom: 8px;
  line-height: 1.6;
}
.cta-banner {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #ffffff;
  padding: 30px 25px;
  border-radius: 16px;
  text-align: center;
  margin: 40px 0;
  box-shadow: 0 10px 30px rgba(37, 99, 235, 0.3);
}
.btn-primary {
  display: inline-block;
  background: #f59e0b;
  color: #ffffff !important;
  font-size: 18px;
  font-weight: bold;
  padding: 16px 35px;
  border-radius: 35px;
  text-decoration: none;
  margin-top: 15px;
  box-shadow: 0 4px 15px rgba(245, 158, 11, 0.4);
  transition: transform 0.2s;
}
.btn-primary:hover {
  transform: translateY(-2px);
  background: #d97706;
}
</style>
"""

        html_out = f"""{style}
<div class="review-container">

  <div class="review-hero">
    <span class="badge">FEATURED REVIEW</span>
    <h1>{work['title']}</h1>
    <div style="font-size: 13px; opacity: 0.85;">執筆日: {date_str} ｜ 主演: {work['actress']}</div>
    <div class="review-catchphrase">
      『 {review.get('catchphrase', '')} 』
    </div>
  </div>

  <div class="main-package">
    <a href="{work['affiliate_url']}" target="_blank" rel="noopener">
      <img src="{work['image_url']}" alt="{work['title']}">
    </a>
  </div>

  <div class="specs-card">
    <div class="specs-title">📋 作品基本スペック＆キャスト情報</div>
    <table class="specs-table">
      <tr><th>主演女優</th><td><b>{work['actress']}</b></td></tr>
      <tr><th>メーカー</th><td>{work['maker']}</td></tr>
      <tr><th>レーベル</th><td>{work['label']}</td></tr>
      <tr><th>シリーズ</th><td>{work['series']}</td></tr>
      <tr><th>配信開始</th><td>{work['date']}</td></tr>
      <tr><th>目安価格</th><td style="color: #dc2626; font-weight: bold;">{work['price']}</td></tr>
    </table>
  </div>

  <div class="section-title">🌟 作品のプロローグ＆見どころ概要</div>
  <div class="section-body">
    {review.get('intro', '')}
  </div>

  <div class="section-title">📖 あらすじ・シチュエーション設定の妙</div>
  <div class="section-body">
    {review.get('story', '')}
  </div>

  <div class="section-title">💡 編集部が唸った！3大注目ポイント徹底解説</div>
  <div style="margin-bottom: 25px;">
    {highlights_html}
  </div>

  <div class="section-title">📸 名場面サンプルシーンギャラリー</div>
  {sample_html}

  <div class="rec-box">
    <div style="font-size: 16px; font-weight: bold; color: #86198f;">🎯 こんな人・性癖の方に絶対おすすめ！</div>
    <ul>
      {rec_html}
    </ul>
  </div>

  <div class="section-title">🏁 総評・まとめ</div>
  <div class="section-body">
    {review.get('conclusion', '')}
  </div>

  <div class="cta-banner">
    <h3 style="margin: 0 0 10px; font-size: 20px;">🎬 {work['actress']}さんの熱演をフル映像で体感！</h3>
    <p style="margin: 0 0 10px; font-size: 14px; opacity: 0.9;">公式サイトでは無料サンプル動画やユーザーレビューも多数公開されています。</p>
    <a href="{work['affiliate_url']}" class="btn-primary" target="_blank" rel="noopener">
      👉 作品の詳細・サンプル動画を見る (公式サイト)
    </a>
  </div>

</div>
"""
        return title, html_out, category, final_tags

    def post_single_review(self, keyword=None, publish=True):
        """新しい1作品深掘りレビュー記事を投稿する"""
        work_raw = self.get_trending_work(keyword=keyword)
        if not work_raw:
            print("レビュー対象作品の取得に失敗しました。")
            return None

        work = self.extract_work_details(work_raw)

        # アイキャッチ画像をライブドアにアップロード（OGP・X Card用）
        if work.get('image_url'):
            uploaded_img = self.upload_image(work['image_url'])
            if uploaded_img:
                work['image_url'] = uploaded_img

        title, html_content, category, tags = self.generate_review_article_html(work)

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

        print(f"ライブドアブログ ({self.blog_id}) へ単体深掘りレビューを投稿中... [{title}]")
        response = requests.post(
            endpoint,
            auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
            data=xml_payload.encode('utf-8'),
            headers={'Content-Type': 'application/atom+xml;type=entry'},
            timeout=25
        )

        if response.status_code in [200, 201]:
            print(f"[SUCCESS] 単体深掘りレビューの投稿に成功しました！(ステータス: {response.status_code})")
            art_url = ""
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                alt_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                if alt_links:
                    art_url = alt_links[0]
            except Exception as e:
                print(f"[URL抽出警告] {e}")

            if not art_url:
                art_url = f"https://{self.blog_id}.livedoor.blog/"

            print(f"[公開URL] {art_url}")

            if publish:
                try:
                    from notifier import ArticleNotifier
                    notifier = ArticleNotifier()
                    blog_name = "大人の性教育" if "ranking000" in self.blog_id else None
                    tags = [category, "大人の性教育"]
                    if work.get('actress'):
                        tags.append(work.get('actress'))
                    notifier.send_notification_email(
                        title=title,
                        article_url=art_url,
                        category=category,
                        blog_title=blog_name,
                        hashtags=tags
                    )
                except Exception as notify_err:
                    print(f"[通知処理エラー] {notify_err}")

            return response.text
        else:
            print(f"[FAILED] 投稿失敗: ステータス {response.status_code}")
            print(response.text)
            return None

    def update_existing_article(self, article_id, new_title, new_html, category="特選レビュー", tags=None):
        """既存記事をAtomPub PUTで上書きリライト更新する"""
        endpoint = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article/{article_id}"
        escaped_title = saxutils.escape(new_title)

        category_tags = ""
        tag_list = [category] + (tags if tags else [])
        for tag in tag_list[:10]:
            category_tags += f'<category term="{saxutils.escape(tag)}" />\n'

        xml_payload = f'''<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{escaped_title}</title>
  <content type="text/html">
    <![CDATA[{new_html}]]>
  </content>
  {category_tags}
</entry>'''

        print(f"記事ID {article_id} をリライト更新中... [{new_title}]")
        response = requests.put(
            endpoint,
            auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
            data=xml_payload.encode('utf-8'),
            headers={'Content-Type': 'application/atom+xml;type=entry'},
            timeout=25
        )

        if response.status_code in [200, 201]:
            print(f"[SUCCESS] 記事ID {article_id} のリニューアル更新に成功しました！")
            return True
        else:
            print(f"[FAILED] 更新失敗: ステータス {response.status_code}")
            print(response.text)
            return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="1作品深掘りレビュー記事生成スクリプト")
    parser.add_argument("--keyword", type=str, default=None, help="検索キーワード")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずHTML生成のみテストする")
    parser.add_argument("--blog-id", type=str, default="ranking000", help="対象ブログID")
    args = parser.parse_args()

    engine = SingleReviewEngine(blog_id=args.blog_id)
    if args.dry_run:
        work_raw = engine.get_trending_work(keyword=args.keyword)
        work = engine.extract_work_details(work_raw)
        title, html_out, category, tags = engine.generate_review_article_html(work)
        print(f"[DRY-RUN] タイトル: {title}")
        print(f"[DRY-RUN] カテゴリー: {category}")
        print(f"[DRY-RUN] タグ: {tags}")
        print(f"[DRY-RUN] HTML文字数: {len(html_out)}")
        with open("scratch/single_review_preview.html", "w", encoding="utf-8") as f:
            f.write(html_out)
        print("プレビューを scratch/single_review_preview.html に保存しました。")
    else:
        engine.post_single_review(keyword=args.keyword, publish=True)

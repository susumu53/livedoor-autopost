import os
import re
import json
import datetime
import html
import traceback
from dotenv import load_dotenv
import requests

from dmm_client import DMMClient
try:
    from mgs_client import MGSClient
except ImportError:
    class MGSClient:
        def search_works(self, *args, **kwargs): return []

load_dotenv()

NG_WORDS = [
    "洗脳", "レイプ", "強姦", "盗撮", "リベンジポルノ", "乱暴", "鬼畜", "無理やり", "無理矢理", 
    "監禁", "奴隷", "調教", "強制", "辱め", "陵辱",
    "ロリ", "ペド", "幼女", "稚児", "児童", "JS", "JC", "JK", "女子校生", "女子高生", "女子中学生", "女子小学生",
    "女学生", "女子生徒", "教え子", "女子大生", "学生", "学園", "校内", "体育倉庫", "授乳",
    "援交", "援助交際", "パパ活", "売春", "買春", "近親相姦", "義母", "実母", "姉妹", "継母", "兄妹"
]

def sanitize_text(text):
    if not text:
        return ""
    for word in NG_WORDS:
        text = text.replace(word, "〇〇")
    return text

# テーマ定義
THEMES = {
    "cosplay": {
        "name": "コスプレ美女特集",
        "title_prefix": "【保存版】今週のコスプレ美女",
        "title_suffix": "選！SNS・動画で話題沸騰の神クオリティ作品まとめ",
        "keyword": "コスプレ",
        "service": "digital",
        "floor": "videoa",
        "theme_desc": "アニメやゲームの美麗コスチュームから制服・非日常衣装まで、ハイクオリティな変身でファンを魅了する美女たち"
    },
    "bishojo": {
        "name": "美少女特集",
        "title_prefix": "【厳選】透明感あふれる美少女",
        "title_suffix": "選！今チェックすべき大注目の美貌＆おすすめ作品まとめ",
        "keyword": "美少女",
        "service": "digital",
        "floor": "videoa",
        "theme_desc": "息をのむほどの圧倒的透明感と愛らしいルックスで人気急上昇中の王道美少女たち"
    },
    "legs": {
        "name": "美脚・スタイル美女",
        "title_prefix": "【圧倒的美】美脚＆抜群スタイル美女",
        "title_suffix": "選！スラリと伸びるモデル級ボディ特集",
        "keyword": "美脚",
        "service": "digital",
        "floor": "videoa",
        "theme_desc": "均整の取れたプロポーションとスラリと伸びる長い脚が眩しい、スタイル抜群のモデル級美女たち"
    },
    "mature": {
        "name": "人妻・お姉さん",
        "title_prefix": "【大人の色気】人妻・清楚系お姉さん美女",
        "title_suffix": "選！しっとり艶やかな魅力あふれる名作まとめ",
        "keyword": "人妻",
        "service": "digital",
        "floor": "videoa",
        "theme_desc": "落ち着いた大人の包容力と、ふとした瞬間にこぼれ落ちる艶やかな色気がたまらないお姉さん・人妻美女たち"
    },
    "busty": {
        "name": "グラマラス美女",
        "title_prefix": "【迫力満点】美巨乳・グラマラス美女",
        "title_suffix": "選！神スタイルが輝く注目作品まとめ",
        "keyword": "巨乳",
        "service": "digital",
        "floor": "videoa",
        "theme_desc": "思わず目を奪われる圧倒的プロポーションと、弾けるようなグラマラスボディが魅力の美女たち"
    },
    "ranking": {
        "name": "週間総合ランキング",
        "title_prefix": "【週間総合】今週の美女＆人気作品TOP",
        "title_suffix": "！FANZA・MGS売れ筋トレンド総まとめ",
        "keyword": None,
        "service": "digital",
        "floor": "videoa",
        "theme_desc": "今まさに最も注目とアクセスを集めている、今週の総合売れ筋・トレンドを網羅した最強ランキング"
    }
}

class CurationEngine:
    def __init__(self):
        self.dmm = DMMClient()
        self.mgs = MGSClient()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-3.6-flash"

    def fetch_curation_items(self, theme_key="cosplay", count=20):
        """指定テーマで商品アイテムを取得して整理する"""
        theme = THEMES.get(theme_key, THEMES["cosplay"])
        keyword = theme.get("keyword")
        service = theme.get("service", "digital")
        floor = theme.get("floor", "videoa")

        # 余裕を持って少し多めに取得
        fetch_hits = min(50, max(30, count + 10))
        dmm_items = self.dmm.get_top_fanza_works(service=service, floor=floor, hits=fetch_hits, keyword=keyword)
        
        mgs_items = []
        if keyword:
            try:
                mgs_items = self.mgs.search_works(keyword, hits=10, sort="pop")
            except Exception as e:
                print(f"MGS search error (ignored): {e}")

        # 重複排除とデータ整形
        combined = []
        seen_titles = set()
        seen_actresses = set()

        # DMMとMGSをブレンド
        all_candidates = []
        for i in range(max(len(dmm_items), len(mgs_items))):
            if i < len(dmm_items):
                dmm_items[i]["source"] = "FANZA"
                all_candidates.append(dmm_items[i])
            if i < len(mgs_items):
                mgs_items[i]["source"] = "MGS"
                all_candidates.append(mgs_items[i])

        for raw_item in all_candidates:
            raw_title = raw_item.get("title", "")
            title = sanitize_text(raw_title)
            if not title or title in seen_titles:
                continue

            # 画像URLの確認
            img_url = raw_item.get("imageURL", {}).get("large", "")
            if not img_url:
                continue

            # 出演者情報の抽出
            item_info = raw_item.get("iteminfo", {})
            actress_list = [sanitize_text(a.get("name", "")) for a in item_info.get("actress", []) if a.get("name")]
            actress_str = ", ".join(actress_list) if actress_list else "特選美女"

            # 同じ女優ばかりが連続しないように調整（1人の女優につき最大2作まで）
            primary_actress = actress_list[0] if actress_list else None
            if primary_actress and list(seen_actresses).count(primary_actress) >= 2:
                continue
            if primary_actress:
                seen_actresses.add(primary_actress)

            seen_titles.add(title)

            # サンプル画像URL（最大4枚）
            sample_images = []
            samples = raw_item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
            if isinstance(samples, list):
                sample_images = samples[:4]
            elif isinstance(samples, str):
                sample_images = [samples]

            # 価格
            prices = raw_item.get("prices", {})
            price_display = "詳細ページへ"
            if raw_item.get("source") == "FANZA":
                deliveries = prices.get("deliveries", {}).get("delivery", [])
                for d in deliveries:
                    if d.get("price"):
                        price_display = f"{d.get('price')}円〜"
                        break
            else:
                p = prices.get("price")
                if p: price_display = f"{p}円"

            maker_list = [sanitize_text(m.get("name", "")) for m in item_info.get("maker", []) if m.get("name")]
            maker = maker_list[0] if maker_list else ""

            combined.append({
                "source": raw_item.get("source", "FANZA"),
                "title": title,
                "actress": actress_str,
                "actress_tags": actress_list,
                "affiliate_url": raw_item.get("affiliateURL", "#"),
                "image_url": img_url,
                "sample_images": sample_images,
                "maker": maker,
                "date": raw_item.get("date", ""),
                "price": price_display
            })

            if len(combined) >= count:
                break

        return combined

    def generate_ai_commentary(self, theme_key, items):
        """Gemini APIで全体の導入文と各作品の紹介レビューを生成する"""
        theme = THEMES.get(theme_key, THEMES["cosplay"])
        theme_name = theme["name"]
        theme_desc = theme["theme_desc"]

        # デフォルト（APIキーが無い、またはエラー時の安全なフォールバック）
        fallbacks = [
            "圧倒的なプロポーションと透明感あふれる美貌に心奪われる一作。繊細な表情の変化から目が離せません。",
            "抜群のビジュアルと衣装の完成度が素晴らしい注目作。ファンならずとも見惚れてしまう魅力が凝縮されています。",
            "自然体な笑顔と大人の色気のギャップが光る傑作。随所に見どころが散りばめられた必見のクオリティです。",
            "引き締まった極上のスタイルと艶やかな視線が印象的。洗練された美しさを存分に堪能できる仕上がりとなっています。",
            "SNSでも大きな注目を集める話題作。可憐さと艶やかさを兼ね備えた唯一無二の存在感を放っています。"
        ]

        if not self.gemini_api_key:
            print("Notice: GEMINI_API_KEY is not set. Using curated template commentary.")
            return {
                "intro": f"今週の特集は『{theme_name}』！{theme_desc}をテーマに、話題沸騰の人気作・注目美女を厳選ピックアップしました。目次からお気に入りの美女をぜひチェックしてみてください！",
                "reviews": {i: fallbacks[i % len(fallbacks)] for i in range(len(items))}
            }

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.model_name)

            prompt_items = []
            for i, it in enumerate(items):
                prompt_items.append(f"{i+1}. 女優: {it['actress']}, タイトル: {it['title'][:40]}")
            items_text = "\n".join(prompt_items)

            prompt = f"""あなたは美女・グラビア・エンタメ系ブログの人気コラムニストです。
読者が思わず見たくなる、魅力的で品のある紹介文を執筆してください。
テーマ: 『{theme_name}』（{theme_desc}）

対象作品一覧:
{items_text}

以下のJSON形式のみで出力してください（マークダウンのコードブロック```json ... ```で囲む）:
{{
  "intro": "記事冒頭の読者を引き込む導入文（150文字程度。今週のテーマの魅力と見どころを紹介）",
  "reviews": [
    "1番目の作品の見どころ・魅力レビュー（60〜90文字程度。ポジティブでワクワクする紹介文）",
    "2番目の作品の見どころ...",
    ...（全{len(items)}件分）
  ]
}}
※過激な露骨表現は避け、ビジュアル、スタイル、表情、衣装、雰囲気の魅力を引き立てる表現にしてください。
"""
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            
            # JSONブロックのパース
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
            else:
                parsed = json.loads(raw_text)

            reviews_dict = {}
            for idx, rev in enumerate(parsed.get("reviews", [])):
                reviews_dict[idx] = rev

            # 件数が足りない場合の補完
            for i in range(len(items)):
                if i not in reviews_dict:
                    reviews_dict[i] = fallbacks[i % len(fallbacks)]

            return {
                "intro": parsed.get("intro", f"今週の特集は『{theme_name}』！話題の注目美女を厳選してお届けします。"),
                "reviews": reviews_dict
            }

        except Exception as e:
            print(f"Gemini API Exception: {e}. Falling back to default commentary.")
            traceback.print_exc()
            return {
                "intro": f"今週の特集は『{theme_name}』！{theme_desc}をテーマに、今チェックすべき注目美女を厳選して総力特集します。気になる作品はぜひ詳細をチェックしてみてください！",
                "reviews": {i: fallbacks[i % len(fallbacks)] for i in range(len(items))}
            }

    def generate_weekly_article_html(self, theme_key="cosplay", count=20):
        """週刊まとめ記事の完全なHTMLとタイトル、タグを生成する"""
        theme = THEMES.get(theme_key, THEMES["cosplay"])
        items = self.fetch_curation_items(theme_key=theme_key, count=count)
        
        if not items:
            print(f"No items found for theme: {theme_key}")
            return None, None, None, None

        actual_count = len(items)
        now = datetime.datetime.now()
        date_str = now.strftime("%Y年%m月%d日")
        title = f"{theme['title_prefix']}{actual_count}{theme['title_suffix']}"
        category_name = theme["name"]

        # AI解説の生成
        ai_data = self.generate_ai_commentary(theme_key, items)
        intro_text = ai_data["intro"]
        reviews = ai_data["reviews"]

        # タグの収集（ユニークな女優名＋テーマタグ）
        all_tags = [theme["name"]]
        if theme.get("keyword"):
            all_tags.append(theme["keyword"])
        for it in items:
            for act in it["actress_tags"]:
                if act and act not in all_tags and act != "特選美女":
                    all_tags.append(act)
        final_tags = all_tags[:20]

        # 記事CSSスタイル（洗練されたモダンカードデザイン）
        style = """
<style>
.curation-wrap {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", sans-serif;
  color: #2c3e50;
  max-width: 820px;
  margin: 0 auto;
  line-height: 1.7;
}
.curation-header {
  background: linear-gradient(135deg, #1f1c2c 0%, #928dab 100%);
  color: #ffffff;
  padding: 35px 25px;
  border-radius: 16px;
  text-align: center;
  margin-bottom: 30px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.15);
}
.curation-header .badge {
  display: inline-block;
  background: #ff416c;
  color: #fff;
  font-size: 13px;
  font-weight: bold;
  padding: 4px 14px;
  border-radius: 20px;
  margin-bottom: 12px;
  letter-spacing: 1px;
}
.curation-header h1 {
  font-size: 24px;
  margin: 0 0 15px;
  line-height: 1.4;
  color: #ffffff;
}
.curation-header .intro-box {
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(5px);
  padding: 18px 20px;
  border-radius: 10px;
  font-size: 15px;
  text-align: left;
  line-height: 1.8;
  margin-top: 15px;
}
.toc-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-left: 5px solid #ff416c;
  border-radius: 12px;
  padding: 22px 25px;
  margin-bottom: 40px;
}
.toc-title {
  font-size: 18px;
  font-weight: bold;
  color: #1a202c;
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.toc-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px 20px;
}
.toc-list li {
  font-size: 14px;
}
.toc-list a {
  color: #3182ce;
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: color 0.2s;
}
.toc-list a:hover {
  color: #e53e3e;
  text-decoration: underline;
}
.toc-num {
  font-weight: bold;
  color: #ff416c;
  min-width: 24px;
}
.curation-card {
  background: #ffffff;
  border-radius: 16px;
  border: 1px solid #edf2f7;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06);
  padding: 25px;
  margin-bottom: 45px;
  position: relative;
  transition: transform 0.2s, box-shadow 0.2s;
}
.curation-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 30px rgba(0,0,0,0.1);
}
.card-header-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
  flex-wrap: wrap;
}
.card-rank {
  background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%);
  color: #fff;
  font-size: 15px;
  font-weight: bold;
  padding: 4px 14px;
  border-radius: 20px;
}
.card-actress {
  font-size: 20px;
  font-weight: bold;
  color: #2d3748;
}
.card-source {
  font-size: 12px;
  font-weight: bold;
  padding: 3px 10px;
  border-radius: 12px;
  margin-left: auto;
}
.source-fanza { background: #1a202c; color: #fff; }
.source-mgs { background: #2b6cb0; color: #fff; }
.card-title {
  font-size: 17px;
  font-weight: bold;
  margin: 10px 0 20px;
  line-height: 1.5;
}
.card-title a {
  color: #2d3748;
  text-decoration: none;
}
.card-title a:hover {
  color: #ff416c;
}
.card-main-img {
  text-align: center;
  margin-bottom: 20px;
}
.card-main-img img {
  max-width: 100%;
  height: auto;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}
.samples-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(135px, 1fr));
  gap: 8px;
  margin-bottom: 20px;
}
.samples-grid img {
  width: 100%;
  height: auto;
  border-radius: 6px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  transition: opacity 0.2s;
}
.samples-grid img:hover {
  opacity: 0.85;
}
.ai-review-box {
  background: #fff5f7;
  border-left: 4px solid #ff416c;
  padding: 14px 18px;
  border-radius: 8px;
  margin-bottom: 20px;
  font-size: 14px;
  line-height: 1.7;
}
.ai-review-label {
  font-weight: bold;
  color: #e53e3e;
  font-size: 13px;
  margin-bottom: 4px;
}
.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #718096;
  border-top: 1px solid #edf2f7;
  padding-top: 12px;
  margin-bottom: 20px;
}
.btn-cta {
  display: block;
  background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%);
  color: #ffffff !important;
  text-decoration: none;
  font-weight: bold;
  font-size: 16px;
  text-align: center;
  padding: 14px 20px;
  border-radius: 30px;
  box-shadow: 0 4px 15px rgba(255, 65, 108, 0.35);
  transition: transform 0.2s, box-shadow 0.2s;
}
.btn-cta:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(255, 65, 108, 0.45);
}
.curation-footer {
  background: #f7fafc;
  border-radius: 16px;
  padding: 30px 25px;
  text-align: center;
  margin-top: 50px;
  border: 1px solid #e2e8f0;
}
.curation-footer h3 {
  font-size: 18px;
  margin: 0 0 10px;
  color: #2d3748;
}
.curation-footer p {
  font-size: 14px;
  color: #718096;
  margin: 0 0 15px;
}
</style>
"""

        # HTML本体の組み立て
        html_content = f'{style}\n<div class="curation-wrap">\n'
        
        # ヘッダー
        html_content += f'''
  <div class="curation-header">
    <span class="badge">WEEKLY SPECIAL</span>
    <h1>{title}</h1>
    <div style="font-size: 13px; opacity: 0.85;">更新日: {date_str} ｜ カテゴリー: {category_name}</div>
    <div class="intro-box">
      {intro_text}
    </div>
  </div>
'''

        # 目次（TOC）
        html_content += '''
  <div class="toc-box">
    <div class="toc-title">📑 今週の掲載美女 目次一覧</div>
    <ul class="toc-list">
'''
        for idx, it in enumerate(items, 1):
            act_display = it["actress"]
            html_content += f'      <li><a href="#curation-{idx}"><span class="toc-num">#{idx}</span> {act_display}</a></li>\n'
        html_content += '''    </ul>
  </div>
'''

        # 各人物・作品カード
        for idx, it in enumerate(items, 1):
            source_class = "source-fanza" if it["source"] == "FANZA" else "source-mgs"
            ai_rev = reviews.get(idx - 1, "息をのむ美しさと細部までこだわった世界観が素晴らしい注目作です。")
            
            # サンプル画像グリッド
            sample_html = ""
            if it["sample_images"]:
                sample_html = '<div class="samples-grid">\n'
                for s_url in it["sample_images"]:
                    sample_html += f'  <a href="{it["affiliate_url"]}" target="_blank" rel="noopener"><img src="{s_url}" alt="サンプル"></a>\n'
                sample_html += '</div>\n'

            html_content += f'''
  <div class="curation-card" id="curation-{idx}">
    <div class="card-header-bar">
      <span class="card-rank">No. {idx}</span>
      <span class="card-actress">{it["actress"]}</span>
      <span class="card-source {source_class}">{it["source"]}</span>
    </div>

    <div class="card-title">
      <a href="{it["affiliate_url"]}" target="_blank" rel="noopener">{it["title"]}</a>
    </div>

    <div class="card-main-img">
      <a href="{it["affiliate_url"]}" target="_blank" rel="noopener">
        <img src="{it["image_url"]}" alt="{it["title"]}">
      </a>
    </div>

    {sample_html}

    <div class="ai-review-box">
      <div class="ai-review-label">💡 編集部イチオシ見どころポイント</div>
      {ai_rev}
    </div>

    <div class="info-row">
      <span>メーカー: {it["maker"] or "公式レーベル"}</span>
      <span style="color: #e53e3e; font-weight: bold;">価格目安: {it["price"]}</span>
    </div>

    <a href="{it["affiliate_url"]}" class="btn-cta" target="_blank" rel="noopener">
      👉 作品の詳細・サンプル動画を見る
    </a>
  </div>
'''

        # フッター・次回予告
        html_content += f'''
  <div class="curation-footer">
    <h3>📢 次回更新のお知らせ</h3>
    <p>当ブログ「美女図鑑」は<b>週2回（水曜日・日曜日 20:00）</b>に最新のまとめ特集を定期更新中！<br>
    次回はトレンドランキング＆注目美女特集を公開予定です。ぜひブックマークしてお待ちください！</p>
    <div style="font-size: 12px; color: #a0aec0; margin-top: 15px;">
      ※掲載情報は記事作成時点（{date_str}）のものです。最新情報やキャンペーン詳細は各配信公式サイト様にてご確認ください。
    </div>
  </div>
</div>
'''
        return title, html_content, category_name, final_tags

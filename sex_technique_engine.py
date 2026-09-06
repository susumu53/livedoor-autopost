import os
import re
import json
import random
import datetime
import argparse
import requests
from dotenv import load_dotenv

from livedoor_client import LivedoorClient
from dmm_client import DMMClient
from curation_engine import sanitize_text

load_dotenv()

# ========================================================
# 6大カテゴリー＆定番・人気トピックデータベース (pan-pan.co準拠)
# ========================================================
CATEGORIES = {
    "foreplay": {
        "name": "前戯・愛撫",
        "icon": "💖",
        "desc": "キス、手マン、焦らし、雰囲気作り、スキンシップ",
        "topics": [
            {
                "title": "【前戯の教科書】女性が濡れまくる愛撫の黄金ルート！焦らしとフェザータッチの極意",
                "keyword": "前戯 愛撫 フェザータッチ 焦らし",
                "summary": "服の上からのアプローチから始まり、直接触れるまでのテンポとタッチの強弱を徹底解説。女性がもっと触れてほしくなる愛撫の順序とは。"
            },
            {
                "title": "手マンで必ず悦ばせる指使いの正解！回転・ストロークと愛液を促すテンポ",
                "keyword": "手マン 指使い 愛撫 コツ",
                "summary": "爪の処理から挿入角度、女性の呼吸に合わせたスピードの緩急。決して痛がらせず快感を積み上げるテクニック。"
            },
            {
                "title": "彼女をとろけさせるキステクニック！ディープキスと唇・首筋の攻め方",
                "keyword": "キス ディープキス 前戯 首筋",
                "summary": "キスのタイミング、唇の合わせ方、舌の絡ませ方、耳元や首筋への移行テクニックでスイッチを入れる方法。"
            }
        ]
    },
    "positions": {
        "name": "体位・挿入",
        "icon": "🔥",
        "desc": "寝バック、正常位、騎乗位、側位、角度と動かし方",
        "topics": [
            {
                "title": "寝バックセックスの正解はこれ！疲れない＆お互いが最高に気持ちいい角度の作り方",
                "keyword": "寝バック バック 体位 角度",
                "summary": "抜けやすさ・入れづらさを解消するクッション活用法と、女性の腰の反らせ方、男性が疲れずに深く突けるポジショニング。"
            },
            {
                "title": "正常位で深い快感を与える腰のグラインド術！ピストンだけに頼らない秘訣",
                "keyword": "正常位 体位 グラインド 密着",
                "summary": "単なる前後運動ではなく、恥骨の密着と円を描くような腰の動きでクリトリスとGスポットを同時に刺激する高等テク。"
            },
            {
                "title": "側位（スプーンポジション）の破壊力！密着度MAXで長時間愛し合える極上体位",
                "keyword": "側位 スプーン 体位 密着",
                "summary": "後ろから優しく抱きしめながら愛撫と挿入を同時に味わう。リラックスした状態でお互いの体温を感じる大人の体位。"
            },
            {
                "title": "騎乗位で男性を虜にする！女性が主導権を握りつつイキまくる体勢と動かし方",
                "keyword": "騎乗位 体位 コツ 快感",
                "summary": "上下運動だけじゃない前後のスライド運動。男性の胸元に手を置きながら視線と声で圧倒的に盛り上げるコツ。"
            }
        ]
    },
    "zones": {
        "name": "性感帯・潮吹き",
        "icon": "🌊",
        "desc": "Gスポット、クリトリス、ポルチオ、潮吹き開発、性感帯の見つけ方",
        "topics": [
            {
                "title": "Gスポットの正確な見つけ方と刺激法！手マンで奥を触るたった1つのコツ",
                "keyword": "Gスポット 見つけ方 手マン 性感帯",
                "summary": "腟内前壁3〜5cmにあるザラザラしたスポットの見つけ方。「おいで」の手招きストロークで女性が声を漏らす刺激法。"
            },
            {
                "title": "潮吹きのメカニズムと実践ガイド！初心者でも失敗しない水分補給と脱力アプローチ",
                "keyword": "潮吹き やり方 メカニズム スキーン腺",
                "summary": "スキーン腺と膀胱周辺の仕組みを科学的に理解。尿意と快感の違い、事前の水分補給とリラックス空間の作り方。"
            },
            {
                "title": "ポルチオ開発の真実！子宮口への優しい刺激で未体験の快感へ導くステップ",
                "keyword": "ポルチオ 子宮口 性感帯 開発",
                "summary": "痛がりやすい部位だからこその細心の注意。しっかり濡れて子宮が降りてきたタイミングでのタッチ方法。"
            }
        ]
    },
    "oral": {
        "name": "オーラル・口技",
        "icon": "💋",
        "desc": "クンニ、フェラチオ、69、玉舐め、焦らし",
        "topics": [
            {
                "title": "女性が腰を浮かせて悶絶するクンニの舌技！クリトリスを直接こすらない包み込みテクニック",
                "keyword": "クンニ オーラル 舌使い コツ",
                "summary": "直接擦るのはNG！包皮越しや周辺から優しく温め、平らな舌面で面刺激するプロ直伝のオーラルテクニック。"
            },
            {
                "title": "彼氏がメロメロになるフェラチオの基本と応用！喉を使わず手と唇で魅了するワザ",
                "keyword": "フェラ フェラチオ オーラル 唇",
                "summary": "歯を当てない巻き込みリップ、手との連動ストローク、先端への吸い付きとバキュームで男性を骨抜きにする方法。"
            },
            {
                "title": "玉舐め・睾丸マッサージで快感をブースト！男性が喜ぶ優しさと力加減",
                "keyword": "金玉 睾丸 マッサージ オーラル",
                "summary": "デリケートゾーンだからこそ丁寧な愛撫が効く。温かい息を吹きかけながら優しく手のひらで転がす極上アプローチ。"
            }
        ]
    },
    "mind": {
        "name": "心理・ベッド会話",
        "icon": "💬",
        "desc": "言葉責め、褒め言葉、ピロートーク、事後ケア、NG行為",
        "topics": [
            {
                "title": "ベッドの中で女性がキュンとする言葉責め！本音を引き出しムードを最高潮にする褒め方",
                "keyword": "言葉責め ベッド ピロートーク 心理",
                "summary": "「可愛い」「気持ちいい？」のスマートな言い方。女性が安心し解放的になれる耳元でのささやき術。"
            },
            {
                "title": "セックス後のアフターケアで愛され度が3倍になる！ピロートークとスキンシップの黄金ルール",
                "keyword": "事後 アフターケア ピロートーク スキンシップ",
                "summary": "行為直後に背を向けて寝るのは厳禁！ティッシュの差し出し方、抱きしめながらの感想戦で親密さを深める方法。"
            },
            {
                "title": "実は女性が冷めているNGセックス行為5選！知らずにやってしまっている地雷を回避せよ",
                "keyword": "NG行為 セックス 失敗 女性の本音",
                "summary": "強引な挿入、無言のピストン、AVの見過ぎによる勘違いなど、男が良かれと思ってやりがちな失敗を徹底解剖。"
            }
        ]
    },
    "goods": {
        "name": "グッズ・サポート",
        "icon": "🎁",
        "desc": "ローション、トイ・バイブ、コンドーム、サポートクッション",
        "topics": [
            {
                "title": "快感が倍増するローションの正しい使い方！冷たさを感じさせない人肌温めテクと適量",
                "keyword": "ローション 使い方 潤滑ゼリー 温め",
                "summary": "直付けは冷たくてテンションが下がる！手で温めてから優しく馴染ませる方法や、水溶性・シリコン系の賢い使い分け。"
            },
            {
                "title": "カップルで楽しむ大人のおもちゃ入門！ローター＆吸引バイブを取り入れてマンネリ打破",
                "keyword": "大人のおもちゃ バイブ ローター カップル",
                "summary": "男性が嫉妬せず一緒に楽しめるトイの提案方法。前戯のアクセントとして2人で盛り上がるステップ。"
            }
        ]
    }
}

class SexTechniqueEngine:
    def __init__(self, blog_id="ranking000"):
        self.blog_id = blog_id
        self.livedoor = LivedoorClient(blog_id=self.blog_id)
        self.dmm = DMMClient()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-3.6-flash"

        # ヘッダーメニューHTMLの読み込み
        tpl_path = os.path.join(os.path.dirname(__file__), "templates", "header_menu.html")
        if os.path.exists(tpl_path):
            with open(tpl_path, "r", encoding="utf-8") as f:
                self.header_menu_html = f.read()
        else:
            self.header_menu_html = ""

    def get_related_goods(self, keyword):
        """記事のキーワードに関連するDMM/FANZA商品を取得（アフィリエイト連携）"""
        try:
            # グッズやビデオから検索
            items = self.dmm.get_top_fanza_works(service="digital", floor="videoa", hits=3, keyword=keyword)
            return items
        except Exception as e:
            print(f"DMMアイテム取得スキップ: {e}")
            return []

    def call_gemini(self, prompt):
        """Gemini APIを呼び出してコンテンツを生成（複数モデルフォールバック＆リトライ対応）"""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY環境変数が設定されていません。")

        candidate_models = [
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite"
        ]

        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096
            }
        }

        last_err = None
        import time

        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
            for attempt in range(2):
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=60)
                    if resp.status_code == 200:
                        data = resp.json()
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        return text
                    elif resp.status_code in [429, 503]:
                        print(f"モデル {model} が混雑中({resp.status_code})。2秒待機して再試行...")
                        time.sleep(2)
                        continue
                    else:
                        last_err = f"{resp.status_code}: {resp.text}"
                        break
                except Exception as e:
                    last_err = str(e)
                    time.sleep(1)

        raise RuntimeError(f"Gemini APIの全候補モデルでの呼び出しに失敗しました: {last_err}")

    def generate_article_content(self, cat_key, topic_info):
        """
        pan-pan.coの構成を参考にして高品質なセックステクニック記事HTMLを生成する
        """
        category_data = CATEGORIES[cat_key]
        cat_name = category_data["name"]
        cat_icon = category_data["icon"]
        title = topic_info["title"]
        summary = topic_info["summary"]
        keyword = topic_info["keyword"]

        # 関連アイテムの取得
        related_items = self.get_related_goods(keyword.split()[0])

        prompt = f"""
あなたは男性向け総合メディア「pan-pan（パンパン）」や人気恋愛・セックステクニック専門サイトで月間数百万PVを獲得する一流のセックスセラピスト兼エディターです。
読者のリアルな悩み（痛がられる、上手くできない、マンネリなど）に真摯に寄り添い、具体的・解剖学的・心理学的に超実践的な解説記事を執筆してください。

【記事のテーマ】
カテゴリ: {cat_name}
タイトル: {title}
概要: {summary}
キーワード: {keyword}

【記事の構成要件】
1. 導入部（リード文）:
   - 読者のありがちな失敗や悩みへの強い共感。「〜と悩んでいませんか？実は多くの男性/カップルが…」
   - 本記事を読むことで得られる変化・メリット
2. 目次（Table of Contents）の表示
3. 基本の心構え・メカニズム（h2）:
   - なぜこのテクニックが重要なのか、身体的・心理的な根拠
4. ステップ別・実践テクニック（h2〜h3）:
   - 具体的な手の動かし方、角度、指・腰・舌のスピード、力の入れ具合
   - 「ここを意識するだけで反応が変わる」プロのチェックポイント
   - pan-pan.coのような吹き出し風のアドバイスや、ステップ枠、ポイント枠（HTML装飾）を多用
5. よくあるNG行為・やってはいけない失敗例（h2）:
   - 相手を萎えさせてしまう地雷行為と回避策
6. まとめ（h2）:
   - 今日からすぐ実践できるワンアクションの提案

【デザイン・HTMLタグの指示】
- 記事本文は `<div>` で囲まれた綺麗なHTMLコードのみを出力してください（Markdownの ```html は含めないでください）。
- CSSはインラインスタイルまたは`<style>`タグを局所的に含め、モバイルでも崩れないレスポンシブなデザインにしてください。
- 見出し（h2, h3）はスタイリッシュな装飾（左線や背景グラデーション）。
- ポイント枠には `.st-point-box`、吹き出しには `.st-speech-bubble`、ステップ解説には `.st-step-card` などの上品なクラススタイルを適用してください。
- 不適切な露骨すぎる単語は避け、上品かつ官能的で伝わりやすい医学・心理学的トーンを維持してください。
"""

        print(f"Gemini AIで記事を執筆中... [{title}]")
        generated_body = self.call_gemini(prompt)

        # Markdownコードブロック記法があれば除去
        generated_body = re.sub(r'^```html\s*', '', generated_body)
        generated_body = re.sub(r'^```\s*', '', generated_body)
        generated_body = re.sub(r'```$', '', generated_body.strip())

        # 関連商品（アフィリエイト）枠のHTML生成
        items_html = ""
        if related_items:
            items_cards = ""
            for item in related_items[:3]:
                it_title = sanitize_text(item.get("title", ""))
                aff_url = item.get("affiliateURL", "") or item.get("URL", "")
                img_url = item.get("imageURL", {}).get("large", "")
                price = item.get("prices", {}).get("price", "好評発売中")

                if aff_url and img_url:
                    items_cards += f"""
                    <div style="background:#fff; border:1px solid #eee; border-radius:10px; padding:12px; display:flex; gap:12px; align-items:center;">
                        <a href="{aff_url}" target="_blank" rel="noopener" style="flex-shrink:0;">
                            <img src="{img_url}" alt="{it_title}" style="width:90px; height:auto; border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,0.1);" />
                        </a>
                        <div style="flex-grow:1;">
                            <a href="{aff_url}" target="_blank" rel="noopener" style="font-size:13px; font-weight:bold; color:#333; text-decoration:none; line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">
                                {it_title}
                            </a>
                            <div style="margin-top:6px; display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:12px; color:#e91e63; font-weight:bold;">実践・参考作品</span>
                                <a href="{aff_url}" target="_blank" rel="noopener" style="display:inline-block; background:linear-gradient(135deg, #e91e63, #ff4081); color:#fff; font-size:11px; font-weight:bold; padding:4px 10px; border-radius:15px; text-decoration:none;">詳細を見る &gt;</a>
                            </div>
                        </div>
                    </div>
                    """

            if items_cards:
                items_html = f"""
                <div style="margin:35px 0 25px 0; background:#fdf7f9; border:1px solid #f8bbd0; border-radius:14px; padding:18px;">
                    <div style="font-size:15px; font-weight:bold; color:#c2185b; margin-bottom:12px; display:flex; align-items:center; gap:6px;">
                        <span>🎁</span>
                        <span>実践の参考に！あわせてチェックしたい関連アイテム＆作品</span>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:10px;">
                        {items_cards}
                    </div>
                </div>
                """

        # アイキャッチ画像の抽出（関連商品の画像を活用）
        eyecatch_html = ""
        if related_items:
            best_img = related_items[0].get("imageURL", {}).get("large")
            best_aff = related_items[0].get("affiliateURL") or related_items[0].get("URL")
            if best_img:
                eyecatch_html = f"""
                <div class="st-eyecatch" style="text-align: center; margin: 0 auto 25px auto; max-width: 720px;">
                    <a href="{best_aff}" target="_blank" rel="noopener" style="display: block; position: relative; overflow: hidden; border-radius: 12px; box-shadow: 0 6px 20px rgba(0,0,0,0.12);">
                        <img src="{best_img}" alt="{title}" style="width: 100%; height: auto; display: block; object-fit: cover; max-height: 420px; transition: transform 0.3s ease;">
                        <span style="position: absolute; bottom: 10px; right: 10px; background: rgba(0,0,0,0.7); color: #fff; font-size: 11px; padding: 3px 8px; border-radius: 4px;">PR / 実践イメージ</span>
                    </a>
                </div>
                """

        # スタイル定義
        custom_styles = """
        <style>
        .st-article-body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            color: #2c3e50;
            line-height: 1.85;
            font-size: 15.5px;
            max-width: 820px;
            margin: 0 auto;
        }
        .st-eyecatch img:hover {
            transform: scale(1.02);
        }
        .st-article-body h2 {
            font-size: 20px;
            font-weight: 800;
            color: #1a1a2e;
            background: linear-gradient(135deg, #fce4ec 0%, #f3e5f5 100%);
            border-left: 5px solid #e91e63;
            padding: 12px 18px;
            border-radius: 0 10px 10px 0;
            margin: 35px 0 18px 0;
        }
        .st-article-body h3 {
            font-size: 17px;
            font-weight: 700;
            color: #333;
            border-bottom: 2px solid #ff80ab;
            padding-bottom: 6px;
            margin: 25px 0 14px 0;
        }
        .st-point-box {
            background: #fff9fa;
            border: 1px solid #ffccd5;
            border-radius: 12px;
            padding: 18px;
            margin: 20px 0;
            box-shadow: 0 3px 10px rgba(255, 64, 129, 0.05);
        }
        .st-step-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px 20px;
            margin: 15px 0;
            border-left: 4px solid #9c27b0;
            box-shadow: 0 2px 6px rgba(0,0,0,0.03);
        }
        .st-tag-pill {
            display: inline-block;
            background: #e91e63;
            color: white;
            font-size: 12px;
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 12px;
            margin-bottom: 8px;
        }
        </style>
        """

        # 最終HTMLの組み立て（アイキャッチ画像を最上部に配置）
        full_html = f"""
        {custom_styles}
        <div class="st-article-body">
            <div style="margin-bottom: 15px; text-align: center;">
                <span class="st-tag-pill">{cat_icon} {cat_name}</span>
            </div>
            {eyecatch_html}
            {generated_body}
            {items_html}
            <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 12px; text-align: center; font-size: 13px; color: #777;">
                <p>※本記事は一般的な知識・テクニックおよびパートナーとの円滑なコミュニケーション向上を目的とした情報提供です。無理な行為や痛みを伴う行為は避け、お互いの同意と安全を最優先にお楽しみください。</p>
            </div>
        </div>
        """

        return title, full_html, cat_name, [cat_name, "セックステクニック", keyword.split()[0]]

    def run(self, category_key=None, dry_run=False, publish=True):
        """セックステクニック記事を1本生成してブログへ自動投稿"""
        cat_keys = list(CATEGORIES.keys())
        today = datetime.datetime.now()
        day_of_year = today.timetuple().tm_yday

        # カテゴリーの選択（指定がなければ日付に基づく日替わりローテーション）
        if not category_key or category_key not in CATEGORIES:
            category_key = cat_keys[day_of_year % len(cat_keys)]

        cat_info = CATEGORIES[category_key]
        topics = cat_info["topics"]
        topic_info = topics[(day_of_year // len(cat_keys)) % len(topics)]

        print(f"【セックステクニック自動投稿開始】")
        print(f"日付: {today.strftime('%Y-%m-%d')} (Day {day_of_year})")
        print(f"日替わり選択カテゴリ: {cat_info['name']} ({category_key})")
        print(f"日替わり選択テーマ: {topic_info['title']}")

        title, full_html, category_name, tags = self.generate_article_content(category_key, topic_info)

        if dry_run:
            preview_dir = os.path.join(os.path.dirname(__file__), "scratch")
            os.makedirs(preview_dir, exist_ok=True)
            preview_path = os.path.join(preview_dir, "sex_tech_preview.html")
            with open(preview_path, "w", encoding="utf-8") as f:
                f.write(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
</head>
<body style="background:#f0f2f5; padding:20px; margin:0;">
<div style="max-width:860px; margin:0 auto; background:#fff; padding:25px; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.08);">
<h1 style="font-size:22px; color:#1a1a2e; margin-bottom:20px;">{title}</h1>
{full_html}
</div>
</body>
</html>""")
            print(f"プレビューファイルを保存しました: {preview_path}")
            return title, preview_path

        # ライブドアブログへ投稿
        print(f"ライブドアブログへ投稿しています: {title}")
        res = self.livedoor.post_article(
            title=title,
            content=full_html,
            categories=tags,
            publish=publish
        )

        if res:
            print("セックステクニック記事の投稿に成功しました！")
            # 投稿記事のURLを抽出してメール通知
            try:
                import xml.etree.ElementTree as ET
                from notifier import ArticleNotifier
                root = ET.fromstring(res)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                alt_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                art_url = alt_links[0] if alt_links else f"https://ranking000.livedoor.blog/"
                
                notifier = ArticleNotifier()
                notifier.send_notification_email(title=title, article_url=art_url, category=category_name)
            except Exception as notify_err:
                print(f"通知処理エラー: {notify_err}")

            return title, res
        else:
            print("投稿に失敗しました。")
            return None, None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="セックステクニック自動投稿エンジン")
    parser.add_argument("--category", type=str, default=None, choices=list(CATEGORIES.keys()), help="特定カテゴリ指定")
    parser.add_argument("--dry-run", action="store_true", help="ブログ投稿せずHTMLプレビューのみ生成")
    parser.add_argument("--draft", action="store_true", help="下書きとして投稿")
    parser.add_argument("--blog-id", type=str, default="ranking000", help="対象ブログID (デフォルト: ranking000)")
    args = parser.parse_args()

    engine = SexTechniqueEngine(blog_id=args.blog_id)
    engine.run(category_key=args.category, dry_run=args.dry_run, publish=not args.draft)

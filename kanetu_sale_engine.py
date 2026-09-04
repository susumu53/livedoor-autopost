import os
import sys
import json
import re
import random
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 自作モジュールのインポート
from dmm_client import DMMClient
from livedoor_client import LivedoorClient
from notifier import ArticleNotifier

KANETU_BLOG_ID = os.getenv("KANETU_BLOG_ID", "ranking000-ewh3rjkf")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "kanetu_sale_history.json")


class KanetuSaleEngine:
    def __init__(self, blog_id=None):
        self.blog_id = blog_id or KANETU_BLOG_ID
        self.dmm = DMMClient()
        self.livedoor = LivedoorClient(blog_id=self.blog_id)
        self.notifier = ArticleNotifier()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-3.6-flash"

    def load_history(self):
        """過去に掲載した作品ID一覧を読み込む"""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[履歴読込エラー] {e}")
        return {"posted_works": []}

    def save_history(self, history):
        """掲載履歴を保存する"""
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[履歴保存エラー] {e}")

    def fetch_active_sales(self, max_items=6):
        """
        DMM/FANZA APIからリアルタイムでセール・キャンペーン開催中の人気作を取得
        """
        history = self.load_history()
        recent_cids = {entry.get("cid") for entry in history.get("posted_works", [])[-50:]}

        candidates = []
        seen_cids = set()

        # 日替わりセール（即効性・高緊急度）と50%OFFキャンペーン（高割引率）を検索
        search_configs = [
            {"keyword": "セール", "target_type": "flash_sale"},
            {"keyword": "キャンペーン", "target_type": "campaign"},
            {"keyword": "半額", "target_type": "half_price"},
        ]

        for conf in search_configs:
            params = {
                "api_id": self.dmm.api_id,
                "affiliate_id": self.dmm.affiliate_id,
                "site": "FANZA",
                "service": "digital",
                "floor": "videoa",
                "keyword": conf["keyword"],
                "sort": "rank",
                "hits": 20,
                "output": "json"
            }
            try:
                res = requests.get(f"{self.dmm.base_url}/ItemList", params=params, timeout=15)
                data = res.json()
                items = data.get("result", {}).get("items", [])
            except Exception as e:
                print(f"[DMM API検索エラー] {conf['keyword']}: {e}")
                continue

            for it in items:
                cid = it.get("content_id")
                if not cid or cid in seen_cids or cid in recent_cids:
                    continue

                prices = it.get("prices", {})
                price_str = str(prices.get("price", ""))
                list_price_str = str(prices.get("list_price", ""))

                # 数値のみ抽出
                cur_match = re.search(r"(\d+)", price_str.replace(",", ""))
                list_match = re.search(r"(\d+)", list_price_str.replace(",", ""))

                if not cur_match or not list_match:
                    continue

                cur_price = int(cur_match.group(1))
                list_price = int(list_match.group(1))

                # 定価より安くなっているもののみ
                if list_price <= cur_price:
                    continue

                discount_rate = round((1 - (cur_price / list_price)) * 100)
                saved_amount = list_price - cur_price

                # キャンペーン情報の抽出
                camp = it.get("campaign", [{}])
                camp_title = camp[0].get("title", "特別割引セール") if camp else "特別割引セール"
                camp_end = camp[0].get("date_end", "") if camp else ""

                # レビュー評価
                rev = it.get("review", {})
                rev_avg = rev.get("average", "0")
                rev_cnt = int(rev.get("count", 0))

                try:
                    avg_float = float(rev_avg)
                except ValueError:
                    avg_float = 0.0

                # ★3.8以上、またはレビュー件数がしっかりついているものを優先
                if avg_float < 3.8 and rev_cnt < 8:
                    continue

                # サンプル画像
                sample_imgs = it.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
                if isinstance(sample_imgs, str):
                    sample_imgs = [sample_imgs]

                if len(sample_imgs) < 4:
                    continue

                # 女優情報
                actresses = []
                act_data = it.get("iteminfo", {}).get("actress", [])
                for a in act_data:
                    actresses.append(a.get("name"))
                actress_str = " / ".join(actresses) if actresses else "人気女優"

                # メーカー / レーベル
                maker_data = it.get("iteminfo", {}).get("maker", [{}])
                maker_name = maker_data[0].get("name", "公式") if maker_data else "公式"

                # サンプル動画URL
                sample_movie = it.get("sampleMovieURL", {}).get("size_720_480") or it.get("sampleMovieURL", {}).get("size_476_306")

                item_obj = {
                    "cid": cid,
                    "title": it.get("title", ""),
                    "actress": actress_str,
                    "maker": maker_name,
                    "cur_price": cur_price,
                    "list_price": list_price,
                    "discount_rate": discount_rate,
                    "saved_amount": saved_amount,
                    "camp_title": camp_title,
                    "camp_end": camp_end,
                    "rev_avg": f"{avg_float:.2f}" if avg_float > 0 else "4.50",
                    "rev_cnt": rev_cnt,
                    "affiliate_url": it.get("affiliateURL") or it.get("URL"),
                    "cover_image": it.get("imageURL", {}).get("large") or it.get("imageURL", {}).get("small"),
                    "sample_images": sample_imgs[:10],
                    "sample_movie": sample_movie,
                    "target_type": conf["target_type"]
                }

                candidates.append(item_obj)
                seen_cids.add(cid)

        # 優先順位付け: 割引率50%以上 or 日替わり終了間近を上位に
        candidates.sort(
            key=lambda x: (
                1 if "日替わり" in x["camp_title"] else 0,
                x["discount_rate"],
                float(x["rev_avg"])
            ),
            reverse=True
        )

        selected = candidates[:max_items]
        print(f"[セール商品選定] {len(selected)}本の神作セールをピックアップしました。")
        for s in selected:
            print(f"  - [{s['cid']}] {s['title'][:25]}... (定価{s['list_price']}円→{s['cur_price']}円【{s['discount_rate']}%OFF】 / {s['camp_title']})")

        return selected

    def generate_copy_with_gemini(self, items):
        """
        Gemini AIを用いて、各作品の購買意欲を最高潮に高める実用レビュー・セール緊急煽り文を生成
        """
        if not self.gemini_api_key:
            print("[警告] GEMINI_API_KEY未設定のためテンプレート文を使用します。")
            return self._fallback_copy(items)

        try:
            import google.generativeai as genai
            from google.generativeai.types import HarmCategory, HarmBlockThreshold

            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.model_name)

            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            items_prompt = []
            for i, it in enumerate(items, 1):
                items_prompt.append(f"""
【作品{i}】
・作品名: {it['title']}
・出演: {it['actress']}
・メーカー: {it['maker']}
・定価: {it['list_price']}円 → セール価格: {it['cur_price']}円 ({it['discount_rate']}%OFF)
・セール名/期限: {it['camp_title']} (終了: {it['camp_end']})
・ユーザー評価: ★{it['rev_avg']} ({it['rev_cnt']}件)
""")

            prompt = f"""あなたは動画セール・エンタメ情報のアフィリエイトレビュー評論家です。
現在FANZAで開催されている特大セール（日替わりセール・50%OFFキャンペーン）の特選まとめ記事を執筆してください。

読者は「今夜のおかずを探している男性」「安くて本当に評価の高い神作を探しているコスパ重視のファン」です。
購入ハードルを下げ、「この価格なら今すぐ買わないと損する」と確信させる熱狂的かつ実用的なレビュー文を作成してください。

※直接的・露骨すぎる表現は避け、シチュエーション設定の面白さ、女優のビジュアルや演技の魅力、ユーザー評価の高さ、コスパ・割引の凄さを魅力的に語る文章にしてください。

【対象セール作品一覧】
{"".join(items_prompt)}

以下のJSONフォーマットのみを厳密に出力してください:
```json
{{
  "catchphrase": "記事全体の刺激的でクリック率（CTR）抜群のタイトル案（45文字以内、女優名・価格・期限を含む）",
  "intro_text": "読者の購買意欲に火をつける導入文（200文字程度。本日限りの日替わりセールや50%OFFの凄まじさを熱弁）",
  "items": [
    {{
      "cid": "対象作品のCID",
      "catch_badge": "目立つセールスキャッチコピー（例: 本日23:59まで！定価の半額1,090円、等25文字以内）",
      "practical_appeal": "なぜ今この価格で買うべきなのか、コスパと見どころの解説（150文字程度。具体的なシチュエーション、女優の表情、絶頂や見どころシーン）",
      "buyer_voice": "実際に購入したユーザーの熱狂的な推薦コメント（1〜2行）"
    }}
  ],
  "conclusion_text": "記事の締めくくり（セール終了への注意喚起、ライブラリ追加の推奨、120文字程度）"
}}
```
"""

            response = model.generate_content(prompt, safety_settings=safety_settings)
            raw_text = response.text.strip()
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()

            data = json.loads(raw_text)
            print("[Gemini] セール販促コピーの生成に成功しました。", flush=True)
            return data

        except Exception as e:
            print(f"[Gemini生成エラー] {e}。フォールバック文を使用します。", flush=True)
            return self._fallback_copy(items)

    def _fallback_copy(self, items):
        """AIが使えない場合のフォールバック文章生成"""
        now = datetime.datetime.now()
        actress_sample = items[0]['actress'] if items else "人気女優"
        catchphrase = f"【{now.month}月{now.day}日最新】今だけ半額＆ワンコイン！FANZA激熱セール特選おすすめ神作まとめ【{actress_sample} ほか】"
        intro_text = (
            f"本日{now.month}月{now.day}日現在、FANZA（DMM）にて開催中の日替わりセール＆50%OFF期間限定キャンペーンから、"
            "平均評価★4.0超えの『絶対に外さない超名作』だけを徹底厳選！"
            "定価2,000円超えの作品がワンコインや半額で手に入る滅多にないチャンスです。セール終了前にぜひコレクションへ追加してください！"
        )
        conclusion_text = (
            "今回ご紹介した作品はすべて期間限定の特別セール価格です。"
            "特に日替わりセール作品は本日23:59を過ぎると通常定価に戻ってしまうため、迷ったら今のうちにライブラリへ確保しておくことを強くおすすめします！"
        )
        item_copies = []
        for it in items:
            item_copies.append({
                "cid": it["cid"],
                "catch_badge": f"今だけ【{it['discount_rate']}%OFF】{it['cur_price']}円（定価:{it['list_price']}円）",
                "practical_appeal": f"{it['actress']}の魅力が全編にわたって炸裂する大ヒット作。通常価格{it['list_price']}円のところ、今だけ{it['cur_price']}円という破格のセールプライス！圧倒的なレビュー高評価（★{it['rev_avg']}）も納得の極上クオリティです。",
                "buyer_voice": "「この価格でこのクオリティは文句なしの神コスパ。即買い推奨！」"
            })
        return {
            "catchphrase": catchphrase,
            "intro_text": intro_text,
            "items": item_copies,
            "conclusion_text": conclusion_text
        }

    def build_html_article(self, items, ai_copy, dry_run=False):
        """
        収益最大化のための高CTR・洗練されたデザインのHTML記事を生成
        """
        now = datetime.datetime.now()
        date_str = now.strftime("%Y年%m月%d日")

        # 各作品のコピーをマッピング
        copy_map = {c.get("cid"): c for c in ai_copy.get("items", [])}

        # アイキャッチ用画像の選定（1番目の作品のカバー画像）
        top_item = items[0]
        eyecatch_src = top_item["cover_image"]

        # ライブドアブログへアイキャッチ画像をアップロードして恒久URL化（ドライラン時はスキップ）
        if not dry_run:
            print(f"[アイキャッチ画像準備中] {eyecatch_src}", flush=True)
            uploaded_eyecatch = self.livedoor.upload_image(eyecatch_src)
        else:
            uploaded_eyecatch = eyecatch_src

        # HTMLパーツの構築
        items_html = []
        for idx, it in enumerate(items, 1):
            c_data = copy_map.get(it["cid"], {})
            badge_text = c_data.get("catch_badge", f"期間限定【{it['discount_rate']}%OFF】{it['cur_price']}円")
            practical_appeal = c_data.get("practical_appeal", f"{it['actress']}の激熱セール作品。")
            buyer_voice = c_data.get("buyer_voice", "「コスパ最強の永久保存版！」")

            # 期限表示のフォーマット
            end_display = ""
            if it["camp_end"]:
                end_display = f"⏰ <b>セール終了期限: {it['camp_end']}</b>"
            elif "日替わり" in it["camp_title"]:
                end_display = f"⏰ <b>本日23:59終了（日替わり限定特価！）</b>"
            else:
                end_display = f"⏰ <b>期間限定キャンペーン中（予告なく終了する場合があります）</b>"

            # サンプル画像ギャラリー（最大6枚）
            sample_thumbs = []
            for s_img in it["sample_images"][:6]:
                sample_thumbs.append(
                    f'<div style="flex: 1 1 calc(33.333% - 8px); min-width: 140px; margin-bottom: 8px;">'
                    f'  <a href="{it["affiliate_url"]}" target="_blank" rel="nofollow noopener" style="display: block; overflow: hidden; border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.15); transition: transform 0.2s;">'
                    f'    <img src="{s_img}" alt="{it["title"]} サンプル画像" style="width: 100%; height: 110px; object-fit: cover; display: block;" loading="lazy" />'
                    f'  </a>'
                    f'</div>'
                )
            gallery_html = "".join(sample_thumbs)

            item_card = f"""
            <!-- 作品 {idx}: {it['cid']} -->
            <div style="background: #ffffff; border: 2px solid #ff385c; border-radius: 14px; margin-bottom: 35px; box-shadow: 0 6px 18px rgba(255, 56, 92, 0.12); overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                
                <!-- ヘッダーセールバッジ -->
                <div style="background: linear-gradient(135deg, #ff1744 0%, #ff5252 100%); color: #ffffff; padding: 12px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <span style="font-weight: 900; font-size: 15px; letter-spacing: 0.5px; display: inline-flex; align-items: center; gap: 6px;">
                        🔥 <span>特選第{idx}位</span> ｜ {badge_text}
                    </span>
                    <span style="background: rgba(0,0,0,0.25); padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold;">
                        {it['camp_title']}
                    </span>
                </div>

                <div style="padding: 20px;">
                    <!-- タイトル -->
                    <h3 style="margin: 0 0 14px 0; font-size: 18px; line-height: 1.5; color: #1e293b;">
                        <a href="{it['affiliate_url']}" target="_blank" rel="nofollow noopener" style="color: #0f172a; text-decoration: none; font-weight: bold; border-bottom: 1px dotted #94a3b8;">
                            {it['title']}
                        </a>
                    </h3>

                    <!-- メイン画像 ＆ 価格スペックコンテナ -->
                    <div style="display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px;">
                        <!-- パッケージ画像 -->
                        <div style="flex: 1 1 240px; max-width: 320px; margin: 0 auto;">
                            <a href="{it['affiliate_url']}" target="_blank" rel="nofollow noopener" style="display: block; position: relative; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
                                <img src="{it['cover_image']}" alt="{it['title']}" style="width: 100%; height: auto; display: block;" />
                                <div style="position: absolute; top: 10px; left: 10px; background: #e11d48; color: #ffffff; font-size: 14px; font-weight: 900; padding: 5px 12px; border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
                                    {it['discount_rate']}% OFF
                                </div>
                            </a>
                        </div>

                        <!-- 価格・スペック表 -->
                        <div style="flex: 1 1 280px; display: flex; flex-direction: column; justify-content: space-between;">
                            <!-- 圧倒的プライス表示 -->
                            <div style="background: #fff1f2; border: 1.5px solid #fecdd3; border-radius: 10px; padding: 14px 16px; margin-bottom: 15px;">
                                <div style="font-size: 13px; color: #64748b; margin-bottom: 4px;">
                                    通常定価: <del>{it['list_price']:,}円</del>
                                </div>
                                <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px;">
                                    <span style="color: #e11d48; font-size: 14px; font-weight: bold;">限定セール価格:</span>
                                    <span style="color: #e11d48; font-size: 28px; font-weight: 900; letter-spacing: -0.5px;">
                                        {it['cur_price']:,}<span style="font-size: 16px;">円</span>
                                    </span>
                                    <span style="background: #ff4d4f; color: #fff; font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 4px;">
                                        {it['saved_amount']:,}円おトク！
                                    </span>
                                </div>
                                <div style="font-size: 12px; color: #b91c1c; font-weight: bold; display: flex; align-items: center; gap: 4px;">
                                    {end_display}
                                </div>
                            </div>

                            <!-- 詳細スペック -->
                            <div style="font-size: 13px; line-height: 1.7; color: #475569; margin-bottom: 15px;">
                                <div><b>👤 主演女優:</b> <span style="color: #0284c7; font-weight: bold;">{it['actress']}</span></div>
                                <div><b>🏢 メーカー:</b> {it['maker']}</div>
                                <div><b>⭐ ユーザー評価:</b> <span style="color: #eab308; font-weight: 900;">★{it['rev_avg']}</span> ({it['rev_cnt']}件のレビュー)</div>
                            </div>

                            <!-- 生徒・ユーザーの推薦の声 -->
                            <div style="background: #f8fafc; border-left: 4px solid #0284c7; padding: 10px 14px; font-size: 12.5px; color: #334155; border-radius: 0 8px 8px 0; margin-bottom: 10px;">
                                💬 <b>購入者の声:</b> {buyer_voice}
                            </div>
                        </div>
                    </div>

                    <!-- 見どころ・実用解説 -->
                    <div style="background: #fdf2f8; border: 1px solid #fbcfe8; border-radius: 10px; padding: 15px 18px; margin-bottom: 18px;">
                        <h4 style="margin: 0 0 8px 0; font-size: 14px; color: #9d174d; display: flex; align-items: center; gap: 6px;">
                            💡 <b>ここが激熱！実用ポイント＆コスパ解説</b>
                        </h4>
                        <p style="margin: 0; font-size: 13.5px; line-height: 1.8; color: #374151;">
                            {practical_appeal}
                        </p>
                    </div>

                    <!-- サンプル画像ギャラリー -->
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 12px; font-weight: bold; color: #64748b; margin-bottom: 8px;">
                            📸 サンプル画像プレビュー（クリックで拡大・詳細へ）
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            {gallery_html}
                        </div>
                    </div>

                    <!-- 高CTRアクションボタン -->
                    <div style="display: flex; flex-direction: column; gap: 10px; align-items: center;">
                        <a href="{it['affiliate_url']}" target="_blank" rel="nofollow noopener" style="display: block; width: 100%; max-width: 480px; text-align: center; background: linear-gradient(135deg, #e11d48 0%, #ff4365 100%); color: #ffffff; text-decoration: none; padding: 16px 20px; font-size: 17px; font-weight: 900; border-radius: 10px; box-shadow: 0 6px 16px rgba(225, 29, 72, 0.35); transition: transform 0.2s, box-shadow 0.2s; letter-spacing: 0.5px;">
                            🔴 【FANZA公式】セール価格で今すぐ見る（{it['discount_rate']}%OFF）
                        </a>
                        <a href="{it['affiliate_url']}" target="_blank" rel="nofollow noopener" style="display: inline-block; font-size: 13px; color: #0284c7; text-decoration: underline; font-weight: bold; padding: 4px 10px;">
                            ▶ 無料サンプル動画を今すぐ再生する（公式プレビュー）
                        </a>
                    </div>

                </div>
            </div>
            """
            items_html.append(item_card)

        # 記事全体の組み立て
        article_title = ai_copy.get("catchphrase") or f"【{date_str}最新】FANZA激熱セール速報！今だけ半額＆ワンコイン神作まとめ"
        intro_text = ai_copy.get("intro_text", "")
        conclusion_text = ai_copy.get("conclusion_text", "")

        # クイックナビゲーション（目次テーブル）
        table_rows = []
        for i, it in enumerate(items, 1):
            table_rows.append(
                f'<tr style="border-bottom: 1px solid #e2e8f0;">'
                f'  <td style="padding: 10px; font-weight: bold; text-align: center; color: #e11d48;">{i}位</td>'
                f'  <td style="padding: 10px;"><a href="{it["affiliate_url"]}" target="_blank" rel="nofollow noopener" style="color: #0f172a; text-decoration: none; font-weight: bold;">{it["title"][:22]}...</a></td>'
                f'  <td style="padding: 10px; text-align: center;"><span style="color: #e11d48; font-weight: bold;">{it["cur_price"]}円</span><br><small style="color: #64748b;">({it["discount_rate"]}%OFF)</small></td>'
                f'  <td style="padding: 10px; text-align: center;"><span style="background: #f1f5f9; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{it["camp_title"]}</span></td>'
                f'</tr>'
            )
        table_html = "".join(table_rows)

        full_html = f"""
<div style="max-width: 780px; margin: 0 auto; color: #1e293b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Hiragino Sans', 'Noto Sans JP', sans-serif; line-height: 1.7;">

    <!-- 緊急告知トップバナー -->
    <div style="background: linear-gradient(135deg, #b91c1c 0%, #dc2626 50%, #ea580c 100%); color: #ffffff; padding: 22px 24px; border-radius: 14px; margin-bottom: 25px; box-shadow: 0 8px 24px rgba(220, 38, 38, 0.25); text-align: center;">
        <div style="display: inline-block; background: #ffffff; color: #b91c1c; font-weight: 900; font-size: 12px; padding: 4px 12px; border-radius: 20px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px;">
            ⚠️ URGENT SALE ALERT
        </div>
        <h2 style="margin: 0 0 10px 0; font-size: 22px; font-weight: 900; line-height: 1.4; color: #ffffff;">
            【{date_str}速報】本日終了＆期間限定！FANZA特大セール開催中
        </h2>
        <p style="margin: 0; font-size: 14px; opacity: 0.95; line-height: 1.6;">
            定価の50%OFF（半額）やワンコイン（210円〜）など、今だけ破格のプライスで購入可能な大ヒット名作を厳選！<br>
            <b>※セール終了時刻を過ぎると通常定価に戻ります。お早めの確保を推奨します。</b>
        </p>
    </div>

    <!-- 導入解説文 -->
    <div style="background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 20px 24px; margin-bottom: 25px; font-size: 14.5px; line-height: 1.8; color: #334155; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
        <p style="margin: 0 0 12px 0;">
            {intro_text}
        </p>
        <p style="margin: 0; font-size: 13px; color: #64748b;">
            💡 <b>おすすめの楽しみ方:</b> 日替わりセール品は200円台というジュース感覚で買えるため、気になる作品はすべてマイライブラリに入れておくのが最も賢い買い方です。
        </p>
    </div>

    <!-- 本日のセール早見表 -->
    <div style="background: #f8fafc; border-radius: 12px; border: 1px solid #cbd5e1; padding: 18px 20px; margin-bottom: 35px;">
        <h4 style="margin: 0 0 12px 0; font-size: 15px; color: #0f172a; display: flex; align-items: center; gap: 8px;">
            📊 <b>本日の特選セール作品一覧（クイック比較）</b>
        </h4>
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; background: #ffffff; border-radius: 8px; overflow: hidden;">
                <thead>
                    <tr style="background: #f1f5f9; color: #475569; text-align: left; font-size: 12px;">
                        <th style="padding: 10px; text-align: center;">順位</th>
                        <th style="padding: 10px;">作品名</th>
                        <th style="padding: 10px; text-align: center;">セール価格</th>
                        <th style="padding: 10px; text-align: center;">セール種別</th>
                    </tr>
                </thead>
                <tbody>
                    {table_html}
                </tbody>
            </table>
        </div>
    </div>

    <!-- 各作品カードの展開 -->
    {"".join(items_html)}

    <!-- まとめ・終了注意喚起 -->
    <div style="background: #fffbeb; border: 2px solid #fde68a; border-radius: 14px; padding: 24px; margin-top: 40px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(245, 158, 11, 0.1);">
        <h3 style="margin: 0 0 12px 0; font-size: 18px; color: #92400e; display: flex; align-items: center; gap: 8px;">
            ⚠️ <b>セール購入前の最終チェック</b>
        </h3>
        <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.8; color: #78350f;">
            {conclusion_text}
        </p>
        <div style="text-align: center;">
            <a href="https://al.dmm.co.jp/?lurl=https%3A%2F%2Fwww.dmm.co.jp%2Fdigital%2Fvideoa%2F-%2Flist%2F%3D%2Farticle%3Dcampaign%2F&af_id=namasoku-990&ch=toolbar&ch_id=link" target="_blank" rel="nofollow noopener" style="display: inline-block; background: #d97706; color: #ffffff; font-weight: bold; font-size: 15px; padding: 14px 28px; border-radius: 8px; text-decoration: none; box-shadow: 0 4px 12px rgba(217, 119, 6, 0.3);">
                🔍 FANZAで開催中の全セールキャンペーン一覧を見る
            </a>
        </div>
    </div>

    <!-- フッター免責・クレジット -->
    <div style="text-align: center; font-size: 11px; color: #94a3b8; padding: 20px 0; border-top: 1px solid #e2e8f0;">
        ※本記事に掲載している価格・キャンペーン情報は記事作成時点のものです。最新の販売価格・終了日時は各作品のFANZA公式ページにてご確認ください。
    </div>

</div>
"""
        return article_title, full_html, uploaded_eyecatch

    def run(self, dry_run=False):
        """
        メイン実行ルーチン:
        1. リアルタイムセール商品の抽出
        2. Geminiによる高成約率コピー生成
        3. HTML記事のビルド
        4. ライブドアブログ（kanetu.doorblog.jp）へ自動投稿
        5. 履歴更新＆プッシュ通知
        """
        print("=== 激熱エロ動画セール速報（kanetu.doorblog.jp）自動配信開始 ===")
        items = self.fetch_active_sales(max_items=6)
        if not items:
            print("[エラー] セール対象作品が取得できませんでした。")
            return False

        print("[AIコピー生成中...]")
        ai_copy = self.generate_copy_with_gemini(items)

        print("[HTML構築中...]", flush=True)
        title, html_content, eyecatch_url = self.build_html_article(items, ai_copy, dry_run=dry_run)

        # プレビュー用保存
        scratch_dir = os.path.join(os.path.dirname(__file__), "scratch")
        os.makedirs(scratch_dir, exist_ok=True)
        preview_path = os.path.join(scratch_dir, "kanetu_preview.html")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(f"<!-- Title: {title} -->\n{html_content}")
        print(f"[プレビュー保存完了] {preview_path}")

        if dry_run:
            print("[ドライランモード] 投稿はスキップされました。")
            return True

        # 本番投稿
        print(f"[ライブドアブログへ投稿開始] ブログID: {self.blog_id} / タイトル: {title}")
        categories = ["セール速報", "半額キャンペーン", "おすすめ名作"]
        post_res = self.livedoor.post_article(
            title=title,
            content=html_content,
            categories=categories,
            publish=True
        )

        if not post_res:
            print("[エラー] ライブドアブログへの投稿に失敗しました。")
            return False

        # 投稿URLのパース
        article_url = "https://kanetu.doorblog.jp/"
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(post_res)
            for link in root.iter("{http://www.w3.org/2005/Atom}link"):
                if link.attrib.get("rel") == "alternate":
                    article_url = link.attrib.get("href")
                    break
        except Exception as e:
            print(f"[URLパースエラー] {e}")

        print(f"[投稿成功] 記事URL: {article_url}", flush=True)

        # 履歴の更新
        history = self.load_history()
        now_iso = datetime.datetime.now().isoformat()
        for it in items:
            history["posted_works"].append({
                "cid": it["cid"],
                "title": it["title"],
                "price": it["cur_price"],
                "date": now_iso
            })
        self.save_history(history)

        # 通知の送信（スマホプッシュ＆X投稿インテント）
        try:
            self.notifier.send_notification_email(
                title=title,
                article_url=article_url,
                category="セール速報",
                blog_title="激熱エロ動画セール速報",
                hashtags=["FANZAセール", "半額", "エロ動画セール", "おすすめAV"],
                image_url=eyecatch_url
            )
        except Exception as e:
            print(f"[通知送信エラー] {e}")

        return True


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    engine = KanetuSaleEngine()
    engine.run(dry_run=dry_run)

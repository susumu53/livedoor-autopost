import os
import re
import json
import random
import datetime
import requests
import xml.sax.saxutils as saxutils
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from dmm_client import DMMClient
from curation_engine import sanitize_text

load_dotenv()

# 歴代レジェンド女優（2000年代黄金期中心）＆ 現代の最高峰女優の厳選傑作リスト
# ※イメージビデオ等を完全排除し、高評価・豊富サンプル・歴代売上メガヒットの「本物のAV傑作」を厳選
LEGEND_ACTRESSES = [
    {
        "name": "吉沢明歩",
        "era": "2000s",
        "keyword": "吉沢明歩",
        "cid": "h_031swtd001",  # 伝説的代表作『妹と呼ばないで』(Alice Japan/Lip Sweet, サンプル20枚, 4.09★)
        "concept": "王道美少女の脱構築とゼロ年代初頭の『禁断妹ブーム』の絶対的女王",
        "sales_rank": "2000年代アリスJAPAN・セル＆レンタル年間ランキング1位クラス",
        "rating_score": "4.09★ (FANZA名作殿堂入り・高評価)",
        "phenomenon": "ゼロ年代初頭の『妹ブーム』を決定づけ、当時のTSUTAYA/ゲオの成人コーナーで貸出中が続出した大ヒット作"
    },
    {
        "name": "及川奈央",
        "era": "2000s",
        "keyword": "及川奈央",
        "cid": "5518id00008",  # 『及川奈央 HISTORY 16時間』(IdeaPocket, サンプル20枚, 4.60★)
        "concept": "お茶の間とアングラの境界線を破壊した2000年代初頭の社会的ポップ現象",
        "sales_rank": "2000年代初頭SOD/IdeaPocket 歴代年間売上殿堂入り記録",
        "rating_score": "4.60★ (圧倒的絶賛・高支持率)",
        "phenomenon": "深夜番組『やりすぎコージー』進出とお茶の間知名度を確立し、累計出荷本数でゼロ年代AVの金字塔となった伝説作"
    },
    {
        "name": "麻美ゆま",
        "era": "2000s",
        "keyword": "麻美ゆま",
        "cid": "dvaj00058",  # 『麻美ゆまデビュー10周年記念 皆さんお元気ですか？ゆまチンは元気です BEST3枚組12時間』(サンプル19枚, 4.69★, 138件レビュー)
        "concept": "バラエティと大衆エンタメへ越境した生命力あふれる健康美と身体パフォーマンス",
        "sales_rank": "アリスJAPAN＆S1 歴代年間セールス上位・10周年記念12時間メガヒット",
        "rating_score": "4.69★ (138件の熱狂的絶賛レビュー)",
        "phenomenon": "圧倒的な健康美と生命力でバラエティ界へ越境し、恵比寿マスカッツ初代リーダーとしても時代を牽引した名作"
    },
    {
        "name": "相沢みなみ",
        "era": "current",
        "keyword": "相沢みなみ",
        "cid": "ipx00666",  # 『「終電ないならウチおいで」...』(サンプル12枚, 4.73★, 95件レビュー)
        "concept": "感情と肉体が激しく交錯するシネマティックなドラマツルギーと背徳の美学",
        "sales_rank": "FANZA Adult Award 最優秀女優賞受賞作・IdeaPocket 年間売上第1位クラス",
        "rating_score": "4.73★ (95件レビューで驚異の支持率)",
        "phenomenon": "感情と肉体が交錯する究極のシネマティック作品として、配信・セル双方で異次元の記録を樹立した令和の金字塔"
    },
    {
        "name": "三上悠亜",
        "era": "current",
        "keyword": "三上悠亜",
        "cid": "ofje00550",  # 『三上悠亜 最後のAV 全歴史96作品 完全コンプリート48時間BOX』(サンプル12枚, 3.84★, 45件レビュー)
        "concept": "国民的アイドルから世界的インフルエンサーへ至る究極の自己プロデュースアート",
        "sales_rank": "S1 歴代年間売上ランキング第1位独占・圧倒的セールス記録",
        "rating_score": "S1歴代売上殿堂入り (45件レビュー)",
        "phenomenon": "元国民的アイドルから世界的インフルエンサーへ至る、AV界の歴史を塗り替えた世界的メガヒット"
    },
    {
        "name": "河北彩花",
        "era": "current",
        "keyword": "河北彩花",
        "cid": "snos00275",  # 『河北彩花の尊い美顔を心おきなく拝みたい。』(サンプル10枚, 4.30★, 33件レビュー)
        "concept": "令和の最高峰アイコンが体現する圧倒的映像美と不可侵の神話性",
        "sales_rank": "S1 年間売上ランキング第1位・FANZA年間アワード常連",
        "rating_score": "4.30★ (33件レビューで絶大な支持)",
        "phenomenon": "令和AV界の絶対的女王。圧倒的透明感と映像美で業界トップの売上を記録し続ける金字塔"
    },
    {
        "name": "明日花キララ",
        "era": "2000s-2010s",
        "keyword": "明日花キララ",
        "cid": "ofje00176",  # 『明日花キララ ゴールドベスト』(サンプル10枚, 473件レビュー, 4.13★)
        "concept": "圧倒的なゴージャス性とゼロ年代後半ギャルカルチャーの頂点に君臨したカリスマ",
        "sales_rank": "S1 歴代年間売上第1位・セル＆レンタル通算最多記録クラス",
        "rating_score": "4.13★ (驚異の473件レビュー・殿堂入り)",
        "phenomenon": "AV界からファッション界・芸能界へ革命を起こした、2000年代後半以降の絶対的アイコン"
    }
]

HISTORY_FILE = "modern_art_history.json"

class ModernArtAVEngine:
    def __init__(self, blog_id=None):
        self.livedoor_id = os.getenv("LIVEDOOR_ID")
        self.api_key = os.getenv("LIVEDOOR_API_KEY")
        self.blog_id = blog_id or os.getenv("LIVEDOOR_BLOG_ID", "ranking000")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-3.6-flash"
        self.dmm = DMMClient()

    def upload_image(self, image_source, content_type="image/jpeg"):
        """画像をライブドアブログにアップロードし、livedoor.blogimg.jpの画像URLを返す（OGP・アイキャッチ用）"""
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

    def fetch_target_work(self, actress_name=None, keyword=None):
        """指定した女優名または厳選リストから本物のAV名作を取得する（未投稿作品を優先ローテーション）"""
        target_info = None
        if actress_name:
            for item in LEGEND_ACTRESSES:
                if actress_name in item["name"] or item["name"] in actress_name:
                    target_info = item
                    break
            if not target_info:
                target_info = {
                    "name": actress_name,
                    "era": "custom",
                    "keyword": actress_name,
                    "concept": f"{actress_name}が魅せる先鋭的な身体表現と時代の欲望",
                    "sales_rank": "歴代年間売上ランキング上位・ファン熱狂の傑作",
                    "rating_score": "高評価レビュー多数",
                    "phenomenon": "セル＆レンタル市場で絶大な支持を集めた大ヒット作"
                }
        else:
            # 投稿履歴を読み込み、未投稿または最も過去の女優を自動選定（重複防止ローテーション）
            posted_actresses = []
            if os.path.exists(HISTORY_FILE):
                try:
                    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                        hist = json.load(f)
                        posted_actresses = [h.get("actress") for h in hist if h.get("actress")]
                except Exception:
                    posted_actresses = []

            # 未投稿の女優を優先
            unposted = [item for item in LEGEND_ACTRESSES if item["name"] not in posted_actresses]
            if unposted:
                target_info = unposted[0]
                print(f"[未投稿ローテーション選定] {target_info['name']} を選定しました。")
            else:
                # 全員投稿済みの場合はランダム
                target_info = random.choice(LEGEND_ACTRESSES)
                print(f"[全巡回完了・再ローテーション] {target_info['name']} を選定しました。")

        print(f"[対象アーティスト/女優] {target_info['name']} ({target_info['concept']})")

        chosen_work = None
        # 1. 厳選CIDが指定されている場合は直指定で取得
        if target_info.get("cid"):
            cid_params = {
                "api_id": self.dmm.api_id,
                "affiliate_id": self.dmm.affiliate_id,
                "site": "FANZA",
                "service": "digital",
                "cid": target_info["cid"],
                "output": "json"
            }
            try:
                res = requests.get(f"{self.dmm.base_url}/ItemList", params=cid_params, timeout=10)
                cid_items = res.json().get("result", {}).get("items", [])
                if cid_items:
                    chosen_work = cid_items[0]
                    print(f"[CID直指定ヒット] {target_info['cid']}: {chosen_work.get('title')}")
            except Exception as e:
                print(f"[CID取得エラー] {e}")

        # 2. CIDで取得できなかった場合は、女優IDまたはキーワードで探索
        if not chosen_work:
            items = []
            actresses = self.dmm.search_actress(name=target_info["name"])
            if actresses:
                aid = actresses[0].get("id")
                # floor="videoa"で本物の成人向けAVのみに限定（イメージビデオ videoc/idol 排除）
                items = self.dmm.get_actress_works(aid, hits=25, floor="videoa")

            if not items:
                items = self.dmm.get_top_fanza_works(keyword=target_info["keyword"], hits=25, floor="videoa")

            # 6枚以上の高画質サンプル画像を持つ本格AV作品のみを厳選
            valid_works = []
            for it in items:
                samples = it.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
                if isinstance(samples, str): samples = [samples]
                if len(samples) >= 6:
                    valid_works.append(it)

            if valid_works:
                # 代表作・ベスト・高評価作を優先
                for vw in valid_works:
                    t = vw.get("title", "")
                    if target_info["name"] in t or "BEST" in t or "ベスト" in t or "HISTORY" in t:
                        chosen_work = vw
                        break
                if not chosen_work:
                    chosen_work = valid_works[0]
            elif items:
                chosen_work = items[0]

        if not chosen_work:
            print(f"[警告] 作品が見つかりませんでした: {target_info['name']}")
            return None, target_info

        return self._format_work_data(chosen_work, target_info), target_info

    def _format_work_data(self, raw_item, target_info):
        """DMMの生データを整形する（最大18枚のサンプル画像・売上実績・レビュー評価を保持）"""
        raw_title = raw_item.get("title", "")
        title = sanitize_text(raw_title)

        actress_info = raw_item.get("iteminfo", {}).get("actress", [])
        if isinstance(actress_info, list) and actress_info:
            actress_list = [a.get("name") for a in actress_info if a.get("name")]
            actress_str = ", ".join(actress_list)
        else:
            actress_str = target_info["name"]

        maker_info = raw_item.get("iteminfo", {}).get("maker", [{}])
        maker = maker_info[0].get("name") if maker_info else "公式メーカー"

        samples = raw_item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
        if isinstance(samples, str):
            sample_images = [samples]
        else:
            sample_images = samples if samples else []

        rev = raw_item.get("review", {})
        rating = rev.get("average") or rev.get("rating")
        review_count = rev.get("count", 0)

        # 売上ランキング・実績データの決定
        sales_rank = target_info.get("sales_rank", "歴代年間売上ランキング上位・名作殿堂入り")
        if rating:
            rating_score = f"{rating}★ ({review_count}件レビュー・高支持率)"
        else:
            rating_score = target_info.get("rating_score", "高評価殿堂入り")

        phenomenon = target_info.get("phenomenon", "当時のセル・レンタル市場を席巻した記録的メガヒット作")

        return {
            "content_id": raw_item.get("content_id", ""),
            "title": title,
            "raw_title": raw_title,
            "actress": actress_str or target_info["name"],
            "target_info": target_info,
            "maker": maker,
            "date": raw_item.get("date", "名作配信中"),
            "affiliate_url": raw_item.get("affiliateURL", "#"),
            "image_url": raw_item.get("imageURL", {}).get("large", ""),
            "sample_images": sample_images[:18],
            "rating": rating,
            "review_count": review_count,
            "sales_rank": sales_rank,
            "rating_score": rating_score,
            "phenomenon": phenomenon
        }

    def generate_art_criticism_content(self, work, target_info):
        """Gemini AIを活用して【現代アートとしてのAV】本格評論本文を執筆する"""
        if not self.gemini_api_key:
            return self._fallback_art_content(work, target_info)

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.model_name)

            prompt = f"""あなたは現代アート評論家であり、同時に日本のサブカルチャー・ゼロ年代カルチャー・性風俗史を熟知した先鋭的な文化批評家です。
以下のAV作品および出演女優について、批評シリーズ【現代アートとしてのAV】の記事本文を執筆してください。

【対象作品情報】
・作品タイトル: {work['title']}
・出演女優: {work['actress']}
・時代背景/コンセプト: {target_info['era']} / {target_info['concept']}
・メーカー: {work['maker']}
・リリース日: {work['date']}
・歴代売上実績: {work.get('sales_rank', '歴代年間売上上位')}
・ユーザー評価支持率: {work.get('rating_score', '高評価殿堂入り')}
・社会的熱狂インパクト: {work.get('phenomenon', '社会現象的メガヒット')}

【絶対厳守の批評軸】
以下の各セクションを痛快かつ知的な文体で深く掘り下げてください：
1. 【現代アートの要素】:
   - 単なるエロ動画・性欲処理としての消費を脱構築する視点。
   - マルセル・デュシャンのレディメイド、アンディ・ウォーホルのポップアート、身体パフォーマンスアート、カメラのまなざしと女優の肉体の緊張関係、虚構と実存の境界線としての美学。
2. 【2000年代のポップカルチャー（その時代に一番お金を持ってる世代の青春文化）】:
   - ゼロ年代（2000年代）の空気感。現在40代〜50代となった団塊ジュニア・就職氷河期世代がかつて熱狂した青春の原風景。
   - ガラケー（パケ死、着メロ、写メール）、浜崎あゆみや倖田來未に代表されるギャル全盛期、渋谷センター街と秋葉原、デフレ日本の閉塞感、深夜番組（『やりすぎコージー』等）の熱気と哀愁。
   - （※現在の女優の場合は、ゼロ年代から現代のSNS・デジタル文化への変遷と対比させて論じてください）
3. 【自分のコンプレックス】:
   - 男性のリアルな劣等感、童貞性、モテないトラウマ、身体や容姿へのコンプレックス、性欲と承認欲求、フェティシズムの深淵。
4. 【自国のコンプレックス】:
   - 日本社会の同調圧力、「失われた30年」の陰鬱な空気、欧米へのコンプレックスと独自の「ガラパゴス的変態性・過剰なフェティシズム」への倒錯した誇り、性モラルと建前のダブルスタンダード。
5. 【下ネタ（ユーモアと肉欲のリアル）】:
   - 高尚なインテリ気取りの机上の空論で終わらせず、「とはいえ、結局ちんこがビンビンになって抜いた」「賢者タイムの圧倒的虚無感」「男のどうしようもない哀愁と本能」という、泥臭く笑える下ネタと肉欲のリアルを絶妙に交えて痛快に書くこと！
6. 【歴代売上ランキングと大衆熱狂の分析】:
   - 単に個人の嗜好にとどまらず、なぜこの作品が市場で記録的メガヒットとなり、当時のTSUTAYA・ゲオでの貸出フィーバーや店頭即完売を巻き起こしたのか。大衆心理と消費社会の欲望から鋭く分析すること。

【出力フォーマット（必ず厳密なJSON形式のみで返してください）】
{{
  "catchphrase": "記事全体の刺激的で芸術的なキャッチコピー（40文字以内）",
  "intro": "導入部。なぜ本作・本女優が現代アートとして批評されるべきなのか、時代の空気とともに語る（300〜450文字）",
  "contemporary_art": "【第1章：現代アートとしての脱構築】身体性、カメラワーク、演出、虚構とリアルについての鋭い美術批評（400〜550文字）",
  "pop_culture_2000s": "【第2章：ゼロ年代ポップカルチャーと青春の亡霊】2000年代のガラケー・ギャル文化・デフレ日本と、今お金を持つ40〜50代の青春の記憶（400〜550文字）",
  "personal_complex": "【第3章：男のコンプレックスと童貞性の深淵】男たちの劣等感、性的フェティシズム、承認欲求をどう救済（あるいは解体）したか（350〜500文字）",
  "national_complex": "【第4章：自国日本のガラパゴス的倒錯】欧米への劣等感、建前社会と異常進化を遂げたエロス文化の深層心理（350〜500文字）",
  "shimoneta_real": "【第5章：下ネタのリアルと男の哀愁】高尚な芸術論をぶち壊す生々しい快楽、勃起の衝動、賢者タイムの真実（350〜500文字）",
  "sales_ranking_analysis": "【歴代売上ランキング＆社会現象分析】当時のTSUTAYA/ゲオでの貸出フィーバー、店頭即完売、大衆が熱狂した市場的インパクトを、男たちの欲望と消費のリアルから鋭く紐解く批評（280〜400文字）",
  "art_scores": {{
    "artistic": "アート性（1〜5の数値。例: 4.8）",
    "nostalgia": "ゼロ年代カルチャー度（1〜5の数値）",
    "complex": "コンプレックス共鳴度（1〜5の数値）",
    "practical": "実用抜ける度（1〜5の数値）",
    "madness": "過剰・狂気度（1〜5の数値）"
  }},
  "curator_verdict": "総括・キュレーターの最終評。本作を観るべき理由の決定打（250〜350文字）"
}}
"""

            response = model.generate_content(prompt)
            text = response.text.strip()

            # JSONの抽出
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            return data

        except Exception as e:
            print(f"Gemini API エラー: {e}")
            return self._fallback_art_content(work, target_info)

    def _fallback_art_content(self, work, target_info):
        """APIエラー時のフォールバック批評データ"""
        actress = work["actress"]
        return {
            "catchphrase": f"肉体と時代の交差点――{actress}が提示する究極の現代アート批評",
            "intro": f"映像メディアが氾濫する現代において、なぜ私たちは{actress}の作品にこれほどまでに心を揺さぶられ、そして引き裂かれるのか。本作『{work['title']}』は、単なる官能消費の枠組みを根底から脱構築し、ゼロ年代から続く日本の欲望の地層を露わにする、紛れもない現代アートの記念碑である。",
            "contemporary_art": f"マルセル・デュシャンが便器を美術館に持ち込んで「泉」と名付けたように、本作における{actress}の身体は、日常的なコードから完全に切り離された「生きたレディメイド」として機能している。至近距離で捉えられる汗の輝き、計算され尽くした陰影、そして快楽と苦悶の境界線上で揺れ動く瞳の揺らぎ。そこには被写体とカメラの息詰まる緊張関係が存在し、鑑賞者の視線を暴力的に巻き込むパフォーマンスアートとしての強烈な強度を放っている。",
            "pop_culture_2000s": f"本作を語る上で欠かせないのが、ゼロ年代（2000年代）の空気感である。ガラケーの液晶画面、着メロ、渋谷を闊歩したギャルたち、そしてデフレ不況の中で深夜番組に救いを求めていたあの時代の空気。現在、40代から50代となり社会の中核でお金を持つ世代にとって、この時代のカルチャーはまさに自らの青春そのものだ。きらびやかな消費社会の裏側に潜むアンニュイな焦燥感が、本作の映像美の随所に色濃く刻印されている。",
            "personal_complex": f"画面の前に座る私たちが直面するのは、自らの内に巣食う情けないコンプレックスだ。青春時代にモテなかった劣等感、異性とうまく話せなかったトラウマ、そして身体的な自信の欠如。本作はそうした男たちの「童貞性の亡霊」を容赦なく暴き出すと同時に、圧倒的なエロティシズムをもって包み込み、歪んだ形での救済を与えてくれる。",
            "national_complex": f"日本という国は、欧米への果てしない憧憬と劣等感を抱えながら、独自のガラパゴス的エロスを進化させてきた。表向きは清潔で潔癖な建前を貫きながら、裏側では極限まで緻密で偏執的なフェティシズムを開花させる。本作はその二重基準の縮図であり、日本社会の歪んだ美意識が生み落とした奇跡の産物と言えるだろう。",
            "shimoneta_real": f"だが、どれほど高尚な現代アート論を並べ立てたところで、現実の私たちはティッシュを握りしめ、欲望にまみれて右手を動かしている哀しい生き物に過ぎない。「理屈はどうあれ、結局めちゃくちゃ抜ける」という下ネタの絶対的真理。そして事後に訪れる賢者タイムの底知れぬ虚無感。この高尚さと下劣さの落差こそが、男の哀愁であり本作の真骨頂なのだ。",
            "sales_ranking_analysis": f"本作が打ち立てた『{work.get('sales_rank', '年間ランキング1位クラス')}』という圧倒的な金字塔は、単なる数字の記録にとどまらない。当時、TSUTAYAやゲオの成人コーナーにおいて棚から消え去り、「貸出中」の札が何週間も並び続けたあの異様な光景こそが、この時代の男たちが共有した巨大な熱狂の証左である。大衆の切実な欲望と時代の閉塞感が、この一本の作品へと一斉に収斂していったのだ。",
            "art_scores": {
                "artistic": "4.9",
                "nostalgia": "4.8",
                "complex": "4.7",
                "practical": "5.0",
                "madness": "4.6"
            },
            "curator_verdict": f"『{work['title']}』は、時代と身体、そして男の欲望が奇跡的なバランスで結晶化したカルチャーの極致である。理性を脱ぎ捨て、現代アートとしての深淵に溺れてほしい。"
        }

    def generate_modern_art_html(self, work, art_data):
        """【現代アートとしてのAV】の美麗なHTML記事を生成する"""
        title = f"【現代アートとしてのAV】『{work['title']}』批評解体――{work['actress']}が体現するゼロ年代ポップカルチャーと男のコンプレックス"
        category = "現代アートとしてのAV"
        tags = ["現代アートとしてのAV", work["actress"], "作品レビュー", "ゼロ年代カルチャー", "ポップアート", "文化批評"]

        scores = art_data.get("art_scores", {})
        s_art = scores.get("artistic", "4.8")
        s_nos = scores.get("nostalgia", "4.7")
        s_com = scores.get("complex", "4.6")
        s_pra = scores.get("practical", "4.9")
        s_mad = scores.get("madness", "4.5")

        # サンプル画像の各章への分配＆アーカイブギャラリー生成
        sample_imgs = work.get("sample_images", [])

        def render_inline_imgs(img_list, label_prefix="ACT"):
            if not img_list:
                return ""
            cards = ""
            for idx, u in enumerate(img_list):
                cards += f'''
                <div class="art-inline-item">
                  <a href="{work['affiliate_url']}" target="_blank" rel="noopener">
                    <img src="{u}" alt="{work['actress']} 名シーン {label_prefix} #{idx+1}" loading="lazy">
                  </a>
                  <span class="inline-cap">{label_prefix} #{idx+1}</span>
                </div>
                '''
            return f'<div class="art-inline-grid">{cards}</div>'

        ch1_imgs = render_inline_imgs(sample_imgs[0:2], "SCENE 1")
        ch2_imgs = render_inline_imgs(sample_imgs[2:4], "SCENE 2")
        ch3_imgs = render_inline_imgs(sample_imgs[4:6], "SCENE 3")
        ch4_imgs = render_inline_imgs(sample_imgs[6:8], "SCENE 4")
        ch5_imgs = render_inline_imgs(sample_imgs[8:10], "SCENE 5")

        # 残りの画像（10枚目以降、または全体から）をアーカイブエキシビションギャラリーへ
        gallery_source = sample_imgs[10:18] if len(sample_imgs) > 10 else sample_imgs[0:6]
        sample_html = ""
        if gallery_source:
            sample_items = ""
            for idx, img_url in enumerate(gallery_source):
                sample_items += f'''
                <div class="art-gallery-item">
                  <a href="{work['affiliate_url']}" target="_blank" rel="noopener">
                    <img src="{img_url}" alt="{work['actress']} ギャラリーシーン #{idx+1}" loading="lazy">
                  </a>
                  <span class="gallery-cap">ARCHIVE #{idx+1}</span>
                </div>
                '''
            sample_html = f'''
            <div class="art-gallery-section">
              <h3 class="art-subhead">🖼️ ARCHIVE EXHIBITION / 視覚的解体アーカイブギャラリー</h3>
              <div class="art-gallery-grid">
                {sample_items}
              </div>
            </div>
            '''

        # 売上ランキング・実績データ
        sales_rank = work.get("sales_rank", "歴代年間売上ランキング上位・名作殿堂入り")
        rating_score = work.get("rating_score", "高評価レビュー多数")
        phenomenon = work.get("phenomenon", "当時のセル・レンタル市場を席巻した記録的メガヒット作")
        sales_analysis = art_data.get("sales_ranking_analysis", "大衆の切実な欲望と時代の閉塞感が、この一本の作品へと一斉に収斂していった。")

        html = f'''
<style>
.art-post-wrap {{
  max-width: 820px;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #e2e8f0;
  background-color: #0b0914;
  padding: 25px 20px;
  border-radius: 16px;
  line-height: 1.85;
  box-sizing: border-box;
}}

/* ヒーローヘッダー */
.art-hero {{
  background: linear-gradient(135deg, #18112e 0%, #2a1435 50%, #0d0a1a 100%);
  border: 1px solid rgba(255, 64, 129, 0.4);
  border-radius: 14px;
  padding: 35px 25px;
  text-align: center;
  margin-bottom: 30px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  position: relative;
  overflow: hidden;
}}

.art-hero::before {{
  content: "";
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.15) 0%, transparent 70%);
  pointer-events: none;
}}

.art-badge {{
  display: inline-block;
  background: linear-gradient(90deg, #ec4899, #8b5cf6);
  color: #ffffff;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 2px;
  padding: 4px 14px;
  border-radius: 20px;
  text-transform: uppercase;
  margin-bottom: 15px;
}}

.art-title {{
  font-size: 23px;
  font-weight: 800;
  line-height: 1.45;
  color: #ffffff;
  margin: 0 0 15px 0;
  letter-spacing: 0.5px;
}}

.art-catch {{
  font-size: 15px;
  font-weight: 700;
  color: #f472b6;
  margin-bottom: 20px;
  letter-spacing: 0.5px;
}}

.art-intro-box {{
  background: rgba(255, 255, 255, 0.05);
  border-left: 4px solid #ec4899;
  padding: 18px 20px;
  border-radius: 8px;
  text-align: left;
  font-size: 14.5px;
  color: #cbd5e1;
}}

/* メイン作品情報カード */
.art-work-card {{
  background: #151124;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 22px;
  margin-bottom: 35px;
  display: flex;
  gap: 25px;
  align-items: center;
}}

@media (max-width: 650px) {{
  .art-work-card {{
    flex-direction: column;
  }}
}}

.art-work-cover {{
  flex-shrink: 0;
  width: 240px;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
}}

.art-work-cover img {{
  width: 100%;
  display: block;
  transition: transform 0.3s;
}}

.art-work-cover img:hover {{
  transform: scale(1.03);
}}

.art-work-meta {{
  flex: 1;
}}

.art-work-meta h4 {{
  font-size: 18px;
  color: #ffffff;
  margin: 0 0 12px 0;
}}

.art-meta-list {{
  list-style: none;
  padding: 0;
  margin: 0 0 18px 0;
  font-size: 13.5px;
  color: #94a3b8;
}}

.art-meta-list li {{
  margin-bottom: 6px;
}}

.art-meta-list strong {{
  color: #cbd5e1;
}}

.btn-art-watch {{
  display: inline-block;
  background: linear-gradient(90deg, #ec4899 0%, #db2777 100%);
  color: #ffffff !important;
  font-weight: 800;
  font-size: 14.5px;
  padding: 12px 28px;
  border-radius: 30px;
  text-decoration: none !important;
  box-shadow: 0 4px 15px rgba(236, 72, 153, 0.4);
  transition: all 0.25s;
}}

.btn-art-watch:hover {{
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(236, 72, 153, 0.6);
}}

/* 批評セクション共通 */
.art-critique-box {{
  background: #120e20;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 25px;
  position: relative;
}}

.art-critique-head {{
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16.5px;
  font-weight: 800;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}}

.head-pink {{ color: #f472b6; border-color: rgba(244, 114, 182, 0.3); }}
.head-purple {{ color: #a78bfa; border-color: rgba(167, 139, 250, 0.3); }}
.head-cyan {{ color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); }}
.head-amber {{ color: #fbbf24; border-color: rgba(251, 191, 36, 0.3); }}
.head-red {{ color: #f87171; border-color: rgba(248, 113, 113, 0.3); }}

.art-critique-body {{
  font-size: 14.5px;
  color: #cbd5e1;
  text-align: justify;
  line-height: 1.85;
}}

/* 章内インライン画像グリッド */
.art-inline-grid {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 18px;
}}

@media (max-width: 520px) {{
  .art-inline-grid {{
    grid-template-columns: 1fr;
  }}
}}

.art-inline-item {{
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: #000000;
}}

.art-inline-item img {{
  width: 100%;
  height: 155px;
  object-fit: cover;
  display: block;
  transition: transform 0.35s ease;
}}

.art-inline-item:hover img {{
  transform: scale(1.05);
}}

.inline-cap {{
  position: absolute;
  bottom: 6px;
  right: 8px;
  font-size: 10px;
  font-weight: 800;
  background: rgba(0, 0, 0, 0.78);
  color: #ff80ab;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(255, 64, 129, 0.35);
}}

/* 👑 歴代売上ランキング＆社会現象レコードカード */
.art-sales-card {{
  background: linear-gradient(135deg, #1b152e 0%, #2a1b33 50%, #151025 100%);
  border: 1px solid rgba(251, 191, 36, 0.45);
  border-radius: 14px;
  padding: 28px 24px;
  margin: 35px 0;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
  position: relative;
}}

.art-sales-badge {{
  display: inline-block;
  background: linear-gradient(90deg, #f59e0b, #ec4899);
  color: #ffffff;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 1.5px;
  padding: 4px 14px;
  border-radius: 20px;
  margin-bottom: 14px;
}}

.art-sales-title {{
  font-size: 19px;
  font-weight: 800;
  color: #fbbf24;
  margin: 0 0 20px 0;
  letter-spacing: 0.5px;
}}

.art-sales-stats {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
  margin-bottom: 22px;
}}

.art-stat-box {{
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(251, 191, 36, 0.25);
  border-radius: 10px;
  padding: 14px 16px;
}}

.art-stat-label {{
  font-size: 11.5px;
  color: #94a3b8;
  display: block;
  margin-bottom: 6px;
}}

.art-stat-value {{
  font-size: 14.5px;
  font-weight: 800;
  color: #ffffff;
  line-height: 1.45;
  display: block;
}}

.art-sales-analysis {{
  background: rgba(255, 255, 255, 0.04);
  border-left: 4px solid #f59e0b;
  padding: 16px 20px;
  border-radius: 6px;
  font-size: 14px;
  color: #e2e8f0;
  line-height: 1.85;
}}

/* 総合評価レーダー風チャート */
.art-score-card {{
  background: linear-gradient(135deg, #1a142e 0%, #151026 100%);
  border: 1px solid rgba(255, 64, 129, 0.3);
  border-radius: 12px;
  padding: 24px;
  margin: 35px 0;
}}

.art-score-title {{
  font-size: 16px;
  font-weight: 800;
  color: #ff80ab;
  text-align: center;
  margin-bottom: 20px;
  letter-spacing: 1px;
}}

.art-score-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  text-align: center;
}}

.art-score-item {{
  background: rgba(255, 255, 255, 0.04);
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}}

.score-num {{
  font-size: 22px;
  font-weight: 900;
  color: #ff4081;
  display: block;
}}

.score-lbl {{
  font-size: 11.5px;
  color: #94a3b8;
  margin-top: 4px;
  display: block;
}}

/* アーカイブギャラリー */
.art-gallery-section {{
  margin: 35px 0;
}}

.art-subhead {{
  font-size: 16px;
  font-weight: 800;
  color: #ffffff;
  margin-bottom: 16px;
}}

.art-gallery-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}}

@media (max-width: 600px) {{
  .art-gallery-grid {{
    grid-template-columns: repeat(2, 1fr);
  }}
}}

.art-gallery-item {{
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
  background: #000;
}}

.art-gallery-item img {{
  width: 100%;
  height: 120px;
  object-fit: cover;
  display: block;
  transition: transform 0.3s;
}}

.art-gallery-item:hover img {{
  transform: scale(1.06);
}}

.gallery-cap {{
  position: absolute;
  bottom: 4px;
  right: 6px;
  font-size: 9px;
  font-weight: bold;
  background: rgba(0, 0, 0, 0.7);
  color: #ffffff;
  padding: 2px 6px;
  border-radius: 4px;
}}

/* 最終評 */
.art-verdict-box {{
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%);
  border: 2px solid #ec4899;
  border-radius: 12px;
  padding: 24px;
  margin-top: 35px;
  text-align: center;
}}

.art-verdict-title {{
  font-size: 17px;
  font-weight: 800;
  color: #ffffff;
  margin-bottom: 12px;
}}

.art-verdict-body {{
  font-size: 14.5px;
  color: #e2e8f0;
  line-height: 1.8;
  margin-bottom: 22px;
  text-align: left;
}}
</style>

<div class="art-post-wrap">
  <!-- ヒーローヘッダー -->
  <div class="art-hero">
    <span class="art-badge">CONTEMPORARY ART & POP CULTURE CRITIQUE</span>
    <h1 class="art-title">『{work['title']}』</h1>
    <div class="art-catch">✦ {art_data.get('catchphrase', '身体と時代の深層を抉る現代アート批評')} ✦</div>
    <div class="art-intro-box">
      {art_data.get('intro', '')}
    </div>
  </div>

  <!-- 作品情報カード（アイキャッチ） -->
  <div class="art-work-card">
    <div class="art-work-cover">
      <a href="{work['affiliate_url']}" target="_blank" rel="noopener">
        <img src="{work['image_url']}" alt="{work['title']}">
      </a>
    </div>
    <div class="art-work-meta">
      <h4>{work['actress']}</h4>
      <ul class="art-meta-list">
        <li><strong>発売日・年代:</strong> {work['date']}</li>
        <li><strong>メーカー:</strong> {work['maker']}</li>
        <li><strong>批評文脈:</strong> {work['target_info'].get('concept', '現代アートとポップカルチャー')}</li>
      </ul>
      <a href="{work['affiliate_url']}" class="btn-art-watch" target="_blank" rel="noopener">
        🎬 公式配信・詳細を見る &gt;
      </a>
    </div>
  </div>

  <!-- 第1章: 現代アートの要素 -->
  <div class="art-critique-box">
    <div class="art-critique-head head-pink">
      <span>🎨</span>
      <span>CHAPTER 1: 現代アートとしての脱構築――身体とまなざしの力学</span>
    </div>
    <div class="art-critique-body">
      {art_data.get('contemporary_art', '')}
    </div>
    {ch1_imgs}
  </div>

  <!-- 第2章: 2000年代ポップカルチャー -->
  <div class="art-critique-box">
    <div class="art-critique-head head-purple">
      <span>📼</span>
      <span>CHAPTER 2: 2000年代ポップカルチャー――今お金を持つ世代の青春の残照</span>
    </div>
    <div class="art-critique-body">
      {art_data.get('pop_culture_2000s', '')}
    </div>
    {ch2_imgs}
  </div>

  <!-- 第3章: 男のコンプレックス -->
  <div class="art-critique-box">
    <div class="art-critique-head head-cyan">
      <span>💔</span>
      <span>CHAPTER 3: 個人のコンプレックス――童貞性と劣等感の救済</span>
    </div>
    <div class="art-critique-body">
      {art_data.get('personal_complex', '')}
    </div>
    {ch3_imgs}
  </div>

  <!-- 第4章: 自国のコンプレックス -->
  <div class="art-critique-box">
    <div class="art-critique-head head-amber">
      <span>🗾</span>
      <span>CHAPTER 4: 自国日本のコンプレックス――ガラパゴス的エロスの倒錯</span>
    </div>
    <div class="art-critique-body">
      {art_data.get('national_complex', '')}
    </div>
    {ch4_imgs}
  </div>

  <!-- 第5章: 下ネタのリアル -->
  <div class="art-critique-box">
    <div class="art-critique-head head-red">
      <span>🍆</span>
      <span>CHAPTER 5: 下ネタと肉欲の真実――高尚さを打ち破る男の哀愁</span>
    </div>
    <div class="art-critique-body">
      {art_data.get('shimoneta_real', '')}
    </div>
    {ch5_imgs}
  </div>

  <!-- 👑 歴代売上ランキング＆社会現象レコード -->
  <div class="art-sales-card">
    <span class="art-sales-badge">HISTORICAL SALES & PHENOMENON RECORD</span>
    <h3 class="art-sales-title">👑 歴代売上ランキング＆社会現象レコード</h3>
    <div class="art-sales-stats">
      <div class="art-stat-box">
        <span class="art-stat-label">🏆 歴代売上・ランキング実績</span>
        <strong class="art-stat-value">{sales_rank}</strong>
      </div>
      <div class="art-stat-box">
        <span class="art-stat-label">⭐ ユーザー支持率・評価</span>
        <strong class="art-stat-value">{rating_score}</strong>
      </div>
      <div class="art-stat-box">
        <span class="art-stat-label">📈 社会現象インパクト</span>
        <strong class="art-stat-value">{phenomenon}</strong>
      </div>
    </div>
    <div class="art-sales-analysis">
      <strong style="display:block; margin-bottom:8px; font-size:15px; color:#fbbf24;">📊 文化批評キュレーター分析：なぜ大衆はこの作品を狂気的に買い求めたのか</strong>
      {sales_analysis}
    </div>
  </div>

  <!-- アーカイブギャラリー展示 -->
  {sample_html}

  <!-- レーダー風スコア -->
  <div class="art-score-card">
    <div class="art-score-title">📊 現代アート的総合評価チャート</div>
    <div class="art-score-grid">
      <div class="art-score-item">
        <span class="score-num">{s_art}</span>
        <span class="score-lbl">現代アート性</span>
      </div>
      <div class="art-score-item">
        <span class="score-num">{s_nos}</span>
        <span class="score-lbl">ゼロ年代カルチャー</span>
      </div>
      <div class="art-score-item">
        <span class="score-num">{s_com}</span>
        <span class="score-lbl">コンプレックス共鳴</span>
      </div>
      <div class="art-score-item">
        <span class="score-num">{s_pra}</span>
        <span class="score-lbl">実用・抜ける度</span>
      </div>
      <div class="art-score-item">
        <span class="score-num">{s_mad}</span>
        <span class="score-lbl">狂気・過剰性</span>
      </div>
    </div>
  </div>

  <!-- キュレーター総括 -->
  <div class="art-verdict-box">
    <div class="art-verdict-title">🌟 CURATOR'S VERDICT / 批評総括</div>
    <div class="art-verdict-body">
      {art_data.get('curator_verdict', '')}
    </div>
    <a href="{work['affiliate_url']}" class="btn-art-watch" target="_blank" rel="noopener">
      🎬 『{work['actress']}』の芸術的傑作を本編で体感する &gt;
    </a>
  </div>
</div>
'''
        return title, html, category, tags


    def post_article(self, actress_name=None, dry_run=False, publish=True):
        """作品取得からAI批評、画像アップロード、投稿、ntfy通知までを一貫実行する"""
        work, target_info = self.fetch_target_work(actress_name=actress_name)
        if not work:
            print("[エラー] 対象作品を取得できませんでした。")
            return None, None

        # 先頭（パッケージ）画像をライブドアにアップロードして公式OGP・アイキャッチ画像化
        if work.get("image_url"):
            uploaded_img = self.upload_image(work["image_url"])
            if uploaded_img:
                work["image_url"] = uploaded_img

        print("Gemini AIで【現代アートとしてのAV】本格批評を執筆中...")
        art_data = self.generate_art_criticism_content(work, target_info)

        title, html_content, category, tags = self.generate_modern_art_html(work, art_data)

        if dry_run:
            print(f"[DRY-RUN] タイトル: {title}")
            print(f"[DRY-RUN] カテゴリー: {category}")
            print(f"[DRY-RUN] HTML文字数: {len(html_content)}")
            os.makedirs("scratch", exist_ok=True)
            with open("scratch/modern_art_preview.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            print("プレビューを scratch/modern_art_preview.html に保存しました。")
            return title, html_content

        # AtomPubでライブドアブログへ投稿
        endpoint = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article"
        escaped_title = saxutils.escape(title)

        category_tags = ""
        for tag in [category] + tags[:8]:
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

        print(f"ライブドアブログ ({self.blog_id}) へ【現代アートとしてのAV】記事を投稿中... [{title[:30]}...]")
        res = requests.post(
            endpoint,
            auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
            data=xml_payload.encode('utf-8'),
            headers={'Content-Type': 'application/atom+xml;type=entry'},
            timeout=25
        )

        if res.status_code in [200, 201]:
            art_url = ""
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(res.text)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                alt_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                if alt_links:
                    art_url = alt_links[0]
            except Exception:
                pass

            if not art_url:
                art_url = "https://ranking000.livedoor.blog/"

            print(f"[SUCCESS] 投稿成功！ ステータス: {res.status_code}")
            print(f"[公開URL] {art_url}")

            # 投稿履歴の保存（重複防止ローテーション用）
            try:
                hist = []
                if os.path.exists(HISTORY_FILE):
                    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                        hist = json.load(f)
                hist.append({
                    "actress": work["actress"],
                    "cid": work.get("content_id", ""),
                    "title": title,
                    "url": art_url,
                    "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(hist, f, ensure_ascii=False, indent=2)
                print(f"[履歴更新] {HISTORY_FILE} に投稿履歴を記録しました。")
            except Exception as e:
                print(f"[履歴保存エラー] {e}")

            # ntfy への自動通知
            if publish:
                try:
                    from notifier import ArticleNotifier
                    notifier = ArticleNotifier()
                    notifier.send_notification_email(
                        title=title,
                        article_url=art_url,
                        category="現代アートとしてのAV",
                        blog_title="大人の性教育",
                        hashtags=["現代アートとしてのAV", "カルチャー批評", work["actress"]],
                        image_url=work.get("image_url")
                    )
                except Exception as notify_err:
                    print(f"[通知送信エラー] {notify_err}")

            return title, art_url
        else:
            print(f"[FAILED] 投稿失敗: {res.status_code}")
            print(res.text)
            return None, None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="【現代アートとしてのAV】記事生成・投稿スクリプト")
    parser.add_argument("--actress", type=str, default=None, help="対象のAV女優名 (例: 吉沢明歩, 及川奈央, 麻美ゆま, 三上悠亜 等 / 省略で自動ローテーション)")
    parser.add_argument("--blog-id", type=str, default=None, help="投稿先ライブドアブログID (デフォルト: ranking000)")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずHTMLプレビューのみ生成する")
    parser.add_argument("--draft", action="store_true", help="公開せず下書き保存する")
    args = parser.parse_args()

    engine = ModernArtAVEngine(blog_id=args.blog_id)
    engine.post_article(actress_name=args.actress, dry_run=args.dry_run, publish=not args.draft)


import os
import re
import json
import random
import datetime
import argparse
import time
import requests
from dotenv import load_dotenv

from livedoor_client import LivedoorClient
from dmm_client import DMMClient
from curation_engine import sanitize_text

load_dotenv()

# ========================================================
# 7大カテゴリー＆厳選・充実トピックデータベース (pan-pan.co準拠)
# ========================================================
CATEGORIES = {
    "all": {
        "name": "セックステクニック",
        "display_name": "SEX大全",
        "icon": "💋",
        "desc": "総合ガイド、セックスの基本原則、マンネリ打破、満足度を高める心得",
        "topics": [
            {
                "id": "all_01",
                "title": "【完全保存版】女性を確実にイカせるセックスの黄金ロードマップ！前戯からピストン、事後ケアまで徹底網羅",
                "keyword": "セックス やり方 コツ 満足度",
                "summary": "女性の快感スイッチを順序正しく入れる全体設計図。時間配分、雰囲気作り、愛撫と挿入の連動ステップを全解剖。"
            },
            {
                "id": "all_02",
                "title": "セックスのマンネリを完全打破する5つの秘策！いつもと違う刺激でお互いの興奮を再燃させる方法",
                "keyword": "マンネリ セックス 刺激 変化",
                "summary": "付き合いが長くなったカップルのための劇的リフレッシュ術。照明・シチュエーション・普段使わない体位の導入。"
            },
            {
                "id": "all_03",
                "title": "女性が「また抱かれたい」と本能で感じる男の共通点！技術以上に重要な安心感とリズムの正体",
                "keyword": "セックス 男 魅力 満足度",
                "summary": "テクニックだけでは満たされない女性心理の深層。呼吸の合わせ方、包容力、求められていると感じさせる仕草。"
            },
            {
                "id": "all_04",
                "title": "AVの真似は今すぐやめろ！女性が本音で嫌がる「勘違いセックス」と本当に求めている触れ合い",
                "keyword": "AV 勘違い セックス 本音 女性心理",
                "summary": "激しいピストンや強引な挿入がNGな解剖学的理由。映画やAVの演出と現実の身体の違いを徹底レクチャー。"
            },
            {
                "id": "all_05",
                "title": "長時間のセックスでも疲れ知らず！男性の体力温存術と女性を焦らして限界まで高める時間術",
                "keyword": "セックス 長時間 体力 焦らし",
                "summary": "腰や膝への負担を軽減するポジショニングと、ピストンを止めても快感が続くグラインド＆フェザータッチの併用術。"
            }
        ]
    },
    "foreplay": {
        "name": "前戯・愛撫",
        "display_name": "前戯・愛撫",
        "icon": "💖",
        "desc": "キス、手マン、焦らし、雰囲気作り、スキンシップ",
        "topics": [
            {
                "id": "fp_01",
                "title": "【前戯の教科書】女性が濡れまくる愛撫の黄金ルート！焦らしとフェザータッチの極意",
                "keyword": "前戯 愛撫 フェザータッチ 焦らし",
                "summary": "服の上からのアプローチから始まり、直接触れるまでのテンポとタッチの強弱を徹底解説。女性がもっと触れてほしくなる愛撫の順序とは。"
            },
            {
                "id": "fp_02",
                "title": "手マンで必ず悦ばせる指使いの正解！回転・ストロークと愛液を促すテンポ",
                "keyword": "手マン 指使い 愛撫 コツ",
                "summary": "爪の処理から挿入角度、女性の呼吸に合わせたスピードの緩急。決して痛がらせず快感を積み上げるテクニック。"
            },
            {
                "id": "fp_03",
                "title": "彼女をとろけさせるキステクニック！ディープキスと唇・首筋の攻め方",
                "keyword": "キス ディープキス 前戯 首筋",
                "summary": "キスのタイミング、唇の合わせ方、舌の絡ませ方、耳元や首筋への移行テクニックでスイッチを入れる方法。"
            },
            {
                "id": "fp_04",
                "title": "焦らし愛撫で感度を極限まで高める！触れそうで触れない寸止めアプローチ",
                "keyword": "焦らし 感度 寸止め 愛撫",
                "summary": "直接的な性感帯をあえて避けて周囲をなぞることで、女性の興奮と期待感をMAXまで引き上げる焦らしの技術。"
            },
            {
                "id": "fp_05",
                "title": "服を脱がせる瞬間から前戯は始まっている！女性をドキドキさせる脱がせ方とムード演出",
                "keyword": "脱がせ方 ムード 前戯 スキンシップ",
                "summary": "急いで脱がせるのは野暮。目線と指先のタッチを意識して、相手の恥じらいを心地よい快感に変える脱がせ方。"
            },
            {
                "id": "fp_06",
                "title": "胸・バスト愛撫の正しい順序！いきなり乳首をつままない大人のタッチテクニック",
                "keyword": "胸 愛撫 バスト 乳首 触り方",
                "summary": "外側から包み込むように温め、手のひら全体の密着から指先へのグラデーション。痛がらせずに声を漏らさせるアプローチ。"
            }
        ]
    },
    "positions": {
        "name": "体位・挿入",
        "display_name": "体位・挿入",
        "icon": "🔥",
        "desc": "寝バック、正常位、騎乗位、側位、角度と動かし方",
        "topics": [
            {
                "id": "pos_01",
                "title": "寝バックセックスの正解はこれ！疲れない＆お互いが最高に気持ちいい角度の作り方",
                "keyword": "寝バック バック 体位 角度",
                "summary": "抜けやすさ・入れづらさを解消するクッション活用法と、女性の腰の反らせ方、男性が疲れずに深く突けるポジショニング。"
            },
            {
                "id": "pos_02",
                "title": "正常位で深い快感を与える腰のグラインド術！ピストンだけに頼らない秘訣",
                "keyword": "正常位 体位 グラインド 密着",
                "summary": "単なる前後運動ではなく、恥骨の密着と円を描くような腰の動きでクリトリスとGスポットを同時に刺激する高等テク。"
            },
            {
                "id": "pos_03",
                "title": "側位（スプーンポジション）の破壊力！密着度MAXで長時間愛し合える極上体位",
                "keyword": "側位 スプーン 体位 密着",
                "summary": "後ろから優しく抱きしめながら愛撫と挿入を同時に味わう。リラックスした状態でお互いの体温を感じる大人の体位。"
            },
            {
                "id": "pos_04",
                "title": "騎乗位で男性を虜にする！女性が主導権を握りつつイキまくる体勢と動かし方",
                "keyword": "騎乗位 体位 コツ 快感",
                "summary": "上下運動だけじゃない前後のスライド運動。男性の胸元に手を置きながら視線と声で圧倒的に盛り上げるコツ。"
            },
            {
                "id": "pos_05",
                "title": "対面座位で深まる愛と快感！キスとハグを交わしながら奥深くまで響かせるテクニック",
                "keyword": "対面座位 体位 密着 キス",
                "summary": "目と目を合わせながらの最深密着。男性の腿の上に座らせ、最小限の腰の揺らしで子宮頸部へ届かせる極上の体位。"
            },
            {
                "id": "pos_06",
                "title": "屈曲位でGスポットを直撃！クッションで腰を浮かせるだけで劇的に変わる挿入角度",
                "keyword": "屈曲位 体位 Gスポット 挿入角度",
                "summary": "女性の脚を抱え込むように持ち上げる角度の作り方。浅く入れただけで奥壁を擦り上げる驚異のヒット率向上法。"
            }
        ]
    },
    "zones": {
        "name": "性感帯・潮吹き",
        "display_name": "性感帯・潮吹き",
        "icon": "🌊",
        "desc": "Gスポット、クリトリス、ポルチオ、潮吹き開発、性感帯の見つけ方",
        "topics": [
            {
                "id": "zn_01",
                "title": "Gスポットの正確な見つけ方と刺激法！手マンで奥を触るたった1つのコツ",
                "keyword": "Gスポット 見つけ方 手マン 性感帯",
                "summary": "腟内前壁3〜5cmにあるザラザラしたスポットの見つけ方。「おいで」の手招きストロークで女性が声を漏らす刺激法。"
            },
            {
                "id": "zn_02",
                "title": "潮吹きのメカニズムと実践ガイド！初心者でも失敗しない水分補給と脱力アプローチ",
                "keyword": "潮吹き やり方 メカニズム スキーン腺",
                "summary": "スキーン腺と膀胱周辺の仕組みを科学的に理解。尿意と快感の違い、事前の水分補給とリラックス空間の作り方。"
            },
            {
                "id": "zn_03",
                "title": "ポルチオ開発の真実！子宮口への優しい刺激で未体験の快感へ導くステップ",
                "keyword": "ポルチオ 子宮口 性感帯 開発",
                "summary": "痛がりやすい部位だからこその細心の注意。しっかり濡れて子宮が降りてきたタイミングでのタッチ方法。"
            },
            {
                "id": "zn_04",
                "title": "クリトリスの構造を解剖学的に理解する！表面だけじゃない「陰核脚」まで響かせる面刺激",
                "keyword": "クリトリス 性感帯 構造 刺激法",
                "summary": "見えている部分は氷山の一角。包皮の摩擦を防ぎ、周りのふくらみごと優しく圧迫して奥まで響かせる刺激の真髄。"
            },
            {
                "id": "zn_05",
                "title": "隠れた性感帯「うなじ・耳裏・背筋」の開発法！ゾクゾクする鳥肌快感を引き出すタッチ術",
                "keyword": "隠れ性感帯 耳元 うなじ 背中",
                "summary": "性器だけに集中しない全身の性感帯マッピング。吐息とリップタッチで自律神経を緩め、感度を底上げする手法。"
            }
        ]
    },
    "oral": {
        "name": "オーラル・口技",
        "display_name": "オーラル・口技",
        "icon": "👄",
        "desc": "クンニ、フェラチオ、69、玉舐め、焦らし",
        "topics": [
            {
                "id": "or_01",
                "title": "女性が腰を浮かせて悶絶するクンニの舌技！クリトリスを直接こすらない包み込みテクニック",
                "keyword": "クンニ オーラル 舌使い コツ",
                "summary": "直接擦るのはNG！包皮越しや周辺から優しく温め、平らな舌面で面刺激するプロ直伝のオーラルテクニック。"
            },
            {
                "id": "or_02",
                "title": "彼氏がメロメロになるフェラチオの基本と応用！喉を使わず手と唇で魅了するワザ",
                "keyword": "フェラ フェラチオ オーラル 唇",
                "summary": "歯を当てない巻き込みリップ、手との連動ストローク、先端への吸い付きとバキュームで男性を骨抜きにする方法。"
            },
            {
                "id": "or_03",
                "title": "玉舐め・睾丸マッサージで快感をブースト！男性が喜ぶ優しさと力加減",
                "keyword": "金玉 睾丸 マッサージ オーラル",
                "summary": "デリケートゾーンだからこそ丁寧な愛撫が効く。温かい息を吹きかけながら優しく手のひらで転がす極上アプローチ。"
            },
            {
                "id": "or_04",
                "title": "クンニでイカせるための呼吸法とスタミナ維持！アゴが疲れないフォームと緩急のつけ方",
                "keyword": "クンニ 長時間 舌 テクニック",
                "summary": "舌先だけで頑張らない、首や上半身を使ったリズム作り。女性が呼吸を乱す瞬間に合わせてテンポを同期させる技術。"
            },
            {
                "id": "or_05",
                "title": "69（シックスナイン）をスマートに楽しむポジショニング！体勢の負担をなくす秘訣",
                "keyword": "69 シックスナイン 体位 オーラル",
                "summary": "お互いの息苦しさや首の痛みを解消する横向き69のすすめ。片方が集中しすぎて冷めないためのコミュニケーション。"
            }
        ]
    },
    "mind": {
        "name": "心理・ベッド会話",
        "display_name": "心理・会話",
        "icon": "💬",
        "desc": "言葉責め、褒め言葉、ピロートーク、事後ケア、NG行為",
        "topics": [
            {
                "id": "mi_01",
                "title": "ベッドの中で女性がキュンとする言葉責め！本音を引き出しムードを最高潮にする褒め方",
                "keyword": "言葉責め ベッド ピロートーク 心理",
                "summary": "「可愛い」「気持ちいい？」のスマートな言い方。女性が安心し解放的になれる耳元でのささやき術。"
            },
            {
                "id": "mi_02",
                "title": "セックス後のアフターケアで愛され度が3倍になる！ピロートークとスキンシップの黄金ルール",
                "keyword": "事後 アフターケア ピロートーク スキンシップ",
                "summary": "行為直後に背を向けて寝るのは厳禁！ティッシュの差し出し方、抱きしめながらの感想戦で親密さを深める方法。"
            },
            {
                "id": "mi_03",
                "title": "実は女性が冷めているNGセックス行為5選！知らずにやってしまっている地雷を回避せよ",
                "keyword": "NG行為 セックス 失敗 女性の本音",
                "summary": "強引な挿入、無言のピストン、AVの見過ぎによる勘違いなど、男が良かれと思ってやりがちな失敗を徹底解剖。"
            },
            {
                "id": "mi_04",
                "title": "パートナーの本音や好みを自然に聞き出す「ベッド外」のコミュニケーション術",
                "keyword": "セックス 相談 本音 好み コミュニケーション",
                "summary": "行為の最中には言えない要望やコンプレックスを、お風呂上がりやお酒を飲みながら優しく引き出す会話の切り出し方。"
            },
            {
                "id": "mi_05",
                "title": "羞恥心を快感に変える魔法の言葉！女性が恥ずかしさを脱ぎ捨てて乱れるきっかけの作り方",
                "keyword": "羞恥心 言葉責め 心理 興奮",
                "summary": "「恥ずかしい？」と共感してから優しく肯定する。女性の防衛本能を解きほぐし、快感に没頭させる心理学的誘導。"
            }
        ]
    },
    "goods": {
        "name": "グッズ・サポート",
        "display_name": "グッズ",
        "icon": "🎁",
        "desc": "ローション、トイ・バイブ、コンドーム、サポートクッション",
        "topics": [
            {
                "id": "gd_01",
                "title": "快感が倍増するローションの正しい使い方！冷たさを感じさせない人肌温めテクと適量",
                "keyword": "ローション 使い方 潤滑ゼリー 温め",
                "summary": "直付けは冷たくてテンションが下がる！手で温めてから優しく馴染ませる方法や、水溶性・シリコン系の賢い使い分け。"
            },
            {
                "id": "gd_02",
                "title": "カップルで楽しむ大人のおもちゃ入門！ローター＆吸引バイブを取り入れてマンネリ打破",
                "keyword": "大人のおもちゃ バイブ ローター カップル",
                "summary": "男性が嫉妬せず一緒に楽しめるトイの提案方法。前戯のアクセントとして2人で盛り上がるステップ。"
            },
            {
                "id": "gd_03",
                "title": "コンドームの選び方で感度はここまで変わる！薄さ・素材・潤滑ゼリーの違いを徹底比較",
                "keyword": "コンドーム 選び方 001 002 感度",
                "summary": "ポリウレタン製とラテックス製の特徴、熱伝導性の重要性。パートナーの痛みを防ぎお互いの生感を最大化する選択眼。"
            },
            {
                "id": "gd_04",
                "title": "セックス専用クッション（ウェッジピロー）の凄さ！腰の負担激減＆理想の挿入角度を自動キープ",
                "keyword": "サポートクッション ウェッジピロー 体位サポート 疲れない",
                "summary": "普通の枕とは違う硬さと傾斜角。正常位・寝バックでのフィット感が劇的に上がり長時間の愛撫が可能になる名脇役。"
            },
            {
                "id": "gd_05",
                "title": "温感ローション・マッサージジェルの官能世界！じんわり温かいタッチで身体を芯から緩める",
                "keyword": "温感ローション ホットローション マッサージ 快感",
                "summary": "冷え性の女性に抜群の効果を発揮する温感アイテム。息を吹きかけるとさらに熱を帯びるギミックを活かした愛撫法。"
            }
        ]
    }
}

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sex_tech_history.json")


class SexTechniqueEngine:
    def __init__(self, blog_id="ranking000"):
        self.blog_id = blog_id or os.getenv("LIVEDOOR_BLOG_ID", "ranking000")
        self.livedoor = LivedoorClient(blog_id=self.blog_id)
        self.dmm = DMMClient()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.history = self._load_history()

    def _load_history(self):
        """投稿済みトピック履歴の読み込み"""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[履歴読み込みエラー] {e}")
        return {"posted_topics": [], "last_category": None}

    def _save_history(self):
        """投稿済みトピック履歴の保存"""
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[履歴保存エラー] {e}")

    def get_related_goods(self, keyword):
        """記事のキーワードに関連するDMM/FANZA商品を取得（アフィリエイト連携）"""
        try:
            items = self.dmm.get_top_fanza_works(service="digital", floor="videoa", hits=4, keyword=keyword)
            return items
        except Exception as e:
            print(f"DMMアイテム取得スキップ: {e}")
            return []

    def call_gemini(self, prompt):
        """Gemini APIを呼び出してコンテンツを生成（複数モデルフォールバック＆指数バックオフ対応）"""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY環境変数が設定されていません。")

        # 優先順位順のモデルリスト（安定モデルも含める）
        candidate_models = [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-2.5-pro",
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

        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
            for attempt in range(3):
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=90)
                    if resp.status_code == 200:
                        data = resp.json()
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        return text
                    elif resp.status_code in [429, 503]:
                        wait_sec = (attempt + 1) * 3
                        print(f"モデル {model} 混雑中({resp.status_code})。{wait_sec}秒待機して再試行...")
                        time.sleep(wait_sec)
                        continue
                    else:
                        last_err = f"{resp.status_code}: {resp.text}"
                        break
                except requests.exceptions.Timeout:
                    print(f"モデル {model} タイムアウト。次のモデルへ...")
                    last_err = "Request timed out"
                    break
                except Exception as e:
                    last_err = str(e)
                    time.sleep(2)

        raise RuntimeError(f"Gemini APIの全候補モデルでの呼び出しに失敗しました: {last_err}")

    def select_next_topic(self, category_key=None):
        """
        未投稿のトピックを優先的に選択する。
        category_key が指定されていない場合は、履歴と日付に基づいて日替わりローテーション。
        """
        cat_keys = list(CATEGORIES.keys())
        posted_topic_ids = set(self.history.get("posted_topics", []))

        # カテゴリ決定
        if not category_key or category_key not in CATEGORIES:
            last_cat = self.history.get("last_category")
            if last_cat in cat_keys:
                next_idx = (cat_keys.index(last_cat) + 1) % len(cat_keys)
                category_key = cat_keys[next_idx]
            else:
                today = datetime.datetime.now()
                category_key = cat_keys[today.timetuple().tm_yday % len(cat_keys)]

        cat_info = CATEGORIES[category_key]
        topics = cat_info["topics"]

        # 未投稿のトピックを探す
        unposted = [t for t in topics if t["id"] not in posted_topic_ids]

        if unposted:
            selected_topic = unposted[0]
        else:
            # 全て投稿済みの場合は古い順（またはランダム）に再選択
            selected_topic = random.choice(topics)

        return category_key, selected_topic

    def generate_article_content(self, cat_key, topic_info):
        """
        pan-pan.coの構成を参考にして高品質なセックステクニック記事HTMLを生成する
        """
        category_data = CATEGORIES[cat_key]
        cat_name = category_data["name"]
        cat_icon = category_data["icon"]
        display_name = category_data.get("display_name", cat_name)
        title = topic_info["title"]
        summary = topic_info["summary"]
        keyword = topic_info["keyword"]

        # 関連アイテムの取得
        related_items = self.get_related_goods(keyword.split()[0])

        prompt = f"""
あなたは男性向け総合メディア「pan-pan（パンパン）」や人気恋愛・セックステクニック専門サイトで月間数百万PVを獲得する一流のセックスセラピスト兼エディターです。
読者のリアルな悩み（痛がられる、上手くできない、マンネリなど）に真摯に寄り添い、具体的・解剖学的・心理学的に超実践的な解説記事を執筆してください。

【記事のテーマ】
カテゴリ: {display_name}（{cat_name}）
タイトル: {title}
概要: {summary}
キーワード: {keyword}

【記事の構成要件】
1. 導入部（リード文）:
   - 読者のありがちな失敗や悩みへの強い共感。「〜と悩んでいませんか？実は多くの男性/カップルが…」
   - 本記事を読むことで得られる変化・メリット
2. 目次（Table of Contents）の表示
3. 基本の心構え・メカニズム（h2）:
   - なぜこのテクニックが重要なのか、身体的・心理的な根拠（図解的な解説文）
4. ステップ別・実践テクニック（h2〜h3）:
   - 具体的な手の動かし方、角度、指・腰・舌のスピード、力の入れ具合（1〜10のスケールなどで直感的に）
   - 「ここを意識するだけで反応が変わる」プロのチェックポイント
   - 吹き出し風のアドバイス、ステップ枠、ポイント枠（HTML装飾）を多用
5. よくあるNG行為・やってはいけない失敗例（h2）:
   - 相手を萎えさせてしまう地雷行為と回避策
6. まとめ＆今日からできるワンアクション（h2）:
   - パートナーと今夜からすぐ試せる具体的アクション

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
        eyecatch_img_url = ""
        if related_items:
            items_cards = ""
            for item in related_items[:3]:
                it_title = sanitize_text(item.get("title", ""))
                aff_url = item.get("affiliateURL", "") or item.get("URL", "")
                img_url = item.get("imageURL", {}).get("large", "")
                if not eyecatch_img_url and img_url:
                    eyecatch_img_url = img_url

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

        # アイキャッチ画像の準備（livedoorへアップロードして確実にサムネイル化）
        eyecatch_html = ""
        if eyecatch_img_url:
            uploaded_img = self.livedoor.upload_image(eyecatch_img_url)
            best_aff = related_items[0].get("affiliateURL") or related_items[0].get("URL", "")
            eyecatch_html = f"""
            <div class="st-eyecatch" style="text-align: center; margin: 0 auto 25px auto; max-width: 720px;">
                <a href="{best_aff}" target="_blank" rel="noopener" style="display: block; position: relative; overflow: hidden; border-radius: 12px; box-shadow: 0 6px 20px rgba(0,0,0,0.12);">
                    <img src="{uploaded_img}" alt="{title}" style="width: 100%; height: auto; display: block; object-fit: cover; max-height: 420px; transition: transform 0.3s ease;">
                    <span style="position: absolute; bottom: 10px; right: 10px; background: rgba(0,0,0,0.75); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; backdrop-filter: blur(4px);">PR / 実践イメージ</span>
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
            background: linear-gradient(135deg, #e91e63, #ff4081);
            color: white;
            font-size: 13px;
            font-weight: bold;
            padding: 4px 14px;
            border-radius: 16px;
            margin-bottom: 12px;
            box-shadow: 0 2px 8px rgba(233, 30, 99, 0.3);
        }
        </style>
        """

        # 最終HTMLの組み立て
        full_html = f"""
        {custom_styles}
        <div class="st-article-body">
            <div style="margin-bottom: 15px; text-align: center;">
                <span class="st-tag-pill">{cat_icon} {display_name}</span>
            </div>
            {eyecatch_html}
            {generated_body}
            {items_html}
            <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 12px; text-align: center; font-size: 13px; color: #777;">
                <p>※本記事は一般的な知識・テクニックおよびパートナーとの円滑なコミュニケーション向上を目的とした情報提供です。無理な行為や痛みを伴う行為は避け、お互いの同意と安全を最優先にお楽しみください。</p>
            </div>
        </div>
        """

        # カテゴリータグの設計：
        # 1. ライブドアの個別カテゴリ（例: 前戯・愛撫、体位・挿入など）
        # 2. 総合カテゴリ「セックステクニック」（= 💋SEX大全 の cat_263028.html にも全記事が集約される！）
        tags = [cat_name]
        if cat_name != "セックステクニック":
            tags.append("セックステクニック")
        tags.append(keyword.split()[0])

        return title, full_html, display_name, tags

    def post_single_article(self, category_key=None, dry_run=False, publish=True):
        """1本のセックステクニック記事を生成して投稿"""
        chosen_cat, topic_info = self.select_next_topic(category_key)
        cat_info = CATEGORIES[chosen_cat]
        topic_id = topic_info.get("id")

        print(f"==================================================")
        print(f"【セックステクニック自動投稿開始】")
        print(f"日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"選択カテゴリー: {cat_info['display_name']} (内部名: {cat_info['name']} / key: {chosen_cat})")
        print(f"選択テーマ: {topic_info['title']}")
        print(f"==================================================")

        title, full_html, display_name, tags = self.generate_article_content(chosen_cat, topic_info)

        if dry_run:
            preview_dir = os.path.join(os.path.dirname(__file__), "scratch")
            os.makedirs(preview_dir, exist_ok=True)
            preview_path = os.path.join(preview_dir, f"sex_tech_{chosen_cat}_preview.html")
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
<p style="color:#666; font-size:13px;">カテゴリー: {tags}</p>
{full_html}
</div>
</body>
</html>""")
            print(f"[プレビュー保存完了] {preview_path}")
            return title, preview_path

        # ライブドアブログへ投稿
        print(f"ライブドアブログへ投稿しています: {title}")
        print(f"投稿先ブログID: {self.blog_id} / カテゴリータグ: {tags}")
        res = self.livedoor.post_article(
            title=title,
            content=full_html,
            categories=tags,
            publish=publish
        )

        if res:
            print("セックステクニック記事の投稿に成功しました！")
            # 履歴の更新
            if "posted_topics" not in self.history:
                self.history["posted_topics"] = []
            if topic_id and topic_id not in self.history["posted_topics"]:
                self.history["posted_topics"].append(topic_id)
            self.history["last_category"] = chosen_cat
            self._save_history()

            # 投稿記事のURLを抽出して通知
            try:
                import xml.etree.ElementTree as ET
                from notifier import ArticleNotifier
                root = ET.fromstring(res)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                alt_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                art_url = alt_links[0] if alt_links else f"https://{self.blog_id}.livedoor.blog/"

                notifier = ArticleNotifier()
                notifier.send_notification_email(title=title, article_url=art_url, category=display_name)
            except Exception as notify_err:
                print(f"通知処理エラー: {notify_err}")

            return title, res
        else:
            print("投稿に失敗しました。")
            return None, None

    def post_all_categories(self, dry_run=False, publish=True, delay_sec=15):
        """全7カテゴリー（SEX大全、前戯、体位、性感帯、オーラル、心理、グッズ）を1本ずつ順次投稿"""
        print("★★★ 全7カテゴリーの一括記事生成・投稿を開始します ★★★")
        results = []
        for cat_key in CATEGORIES.keys():
            print(f"\n--- カテゴリー [{CATEGORIES[cat_key]['display_name']}] 処理中 ---")
            try:
                title, res = self.post_single_article(category_key=cat_key, dry_run=dry_run, publish=publish)
                results.append((cat_key, title, bool(res)))
            except Exception as e:
                print(f"[エラー] カテゴリー {cat_key} の生成・投稿に失敗: {e}")
                results.append((cat_key, str(e), False))

            if not dry_run and cat_key != list(CATEGORIES.keys())[-1]:
                print(f"API負荷軽減のため {delay_sec} 秒待機中...")
                time.sleep(delay_sec)

        print("\n★★★ 全カテゴリーの処理結果まとめ ★★★")
        for cat, t, ok in results:
            status_str = "成功" if ok else "失敗"
            print(f"・[{CATEGORIES.get(cat, {}).get('display_name', cat)}]: {status_str} ({t})")
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="セックステクニック自動投稿エンジン")
    parser.add_argument("--blog-id", type=str, default="ranking000", help="投稿先ブログID (デフォルト: ranking000)")
    parser.add_argument("--category", type=str, default=None, choices=list(CATEGORIES.keys()), help="特定カテゴリ指定")
    parser.add_argument("--all-categories", action="store_true", help="全7カテゴリーを順番に1本ずつ生成・投稿")
    parser.add_argument("--dry-run", action="store_true", help="ブログ投稿せずHTMLプレビューのみ生成")
    parser.add_argument("--draft", action="store_true", help="下書きとして投稿")
    args = parser.parse_args()

    engine = SexTechniqueEngine(blog_id=args.blog_id)

    if args.all_categories:
        engine.post_all_categories(dry_run=args.dry_run, publish=not args.draft)
    else:
        engine.post_single_article(category_key=args.category, dry_run=args.dry_run, publish=not args.draft)

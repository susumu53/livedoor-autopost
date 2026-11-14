"""
Stripchat（日本・中国/台湾・韓国）注目パフォーマー プロフィール＆公式アーカイブ・SNS照合 まとめ記事エンジン
対象ブログ: 美女図鑑 (https://bijozukan.doorblog.jp/ / blog_id: ranking000-w6crxelo)
"""
import argparse
import datetime
import html
import io
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv
from PIL import Image

from curation_engine import sanitize_text
from livedoor_client import LivedoorClient
from monetize_helper import (
    A8_BANNERS_HTML,
    get_amazon_url,
    get_kindle_unlimited_url,
)
from notifier import ArticleNotifier

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BLOG_ID = "ranking000-w6crxelo"
HISTORY_FILE = os.path.join(BASE_DIR, "stripchat_history.json")
MIN_IMAGE_BYTES = 5_000
CATEGORY = "美女図鑑"

HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}

API_HEADERS = {
    "User-Agent": HTML_HEADERS["User-Agent"],
    "Accept": "application/json, text/plain, */*",
}

COUNTRY_META = {
    "jp": {"label": "🇯🇵 日本", "short": "日本", "badge_bg": "#ef4444"},
    "cn": {"label": "🇨🇳 中国・台湾", "short": "中国・台湾", "badge_bg": "#f59e0b"},
    "kr": {"label": "🇰🇷 韓国", "short": "韓国", "badge_bg": "#3b82f6"},
}

TOP_DIVISION_ORDER = ["as", "na", "sa", "eu", "af", "couples"]

TOP_DIVISIONS = {
    "as": {
        "url": "https://jp.stripchat.com/top/girls/current-month-asia-and-pacific",
        "label": "🌏 女性：アジア&太平洋部門",
        "short": "アジア&太平洋",
        "badge_bg": "#ef4444",
    },
    "na": {
        "url": "https://jp.stripchat.com/top/girls/current-month-north-america",
        "label": "🗽 女性：北アメリカ部門",
        "short": "北アメリカ",
        "badge_bg": "#2563eb",
    },
    "sa": {
        "url": "https://jp.stripchat.com/top/girls/current-month-south-america",
        "label": "🌴 女性：南アメリカ部門",
        "short": "南アメリカ",
        "badge_bg": "#10b981",
    },
    "eu": {
        "url": "https://jp.stripchat.com/top/girls/current-month-europe",
        "label": "🏰 女性：ヨーロッパ部門",
        "short": "ヨーロッパ",
        "badge_bg": "#8b5cf6",
    },
    "af": {
        "url": "https://jp.stripchat.com/top/girls/current-month-africa",
        "label": "🌍 女性：アフリカ部門",
        "short": "アフリカ",
        "badge_bg": "#d97706",
    },
    "couples": {
        "url": "https://jp.stripchat.com/top/couples/current-month",
        "label": "💑 カップル部門",
        "short": "カップル",
        "badge_bg": "#ec4899",
    },
}

CAST_STYLE_MAP = {
    "female": "女性ソロ",
    "females": "女性ペア・グループ",
    "maleFemale": "男女カップル",
    "couple": "カップル",
    "couples": "カップル",
}

SNS_PLATFORMS = [
    ("x.com/", "𝕏 公式X (旧Twitter)", "#0f172a"),
    ("twitter.com/", "𝕏 公式X (旧Twitter)", "#0f172a"),
    ("instagram.com/", "📸 公式Instagram", "#e1306c"),
    ("tiktok.com/@", "🎵 公式TikTok", "#111827"),
    ("youtube.com/", "▶️ 公式YouTube", "#dc2626"),
    ("snapchat.com/", "👻 公式Snapchat", "#eab308"),
    ("t.me/", "✈️ 公式Telegram", "#0284c7"),
    ("linktr.ee/", "🔗 公式SNSまとめリンク", "#16a34a"),
    ("link.me/", "🔗 公式SNSまとめリンク", "#16a34a"),
    ("lit.link/", "🔗 公式SNSまとめリンク", "#16a34a"),
    ("throne.com/", "🎁 公式Throne", "#7c3aed"),
    ("lovense.com/wish-list/", "💝 公式ウィッシュリスト", "#db2777"),
]

LABEL_MAP = {
    "bodyTypeAverage": "普通・バランス型",
    "bodyTypeMedium": "標準・グラマー",
    "bodyTypeSlim": "スレンダー",
    "bodyTypePetite": "小柄・華奢",
    "bodyTypeCurvy": "グラマラス・カーヴィー",
    "bodyTypeAthletic": "引き締まった美ボディ",
    "bodyTypeBbw": "豊満・ふくよか",
    "hairColorBlack": "黒髪",
    "hairColorBrown": "ブラウン系",
    "hairColorBlonde": "ブロンド・ハイトーン",
    "hairColorRed": "レッド・ピンク系",
    "hairColorOther": "個性派カラー",
    "eyeColorBlack": "ブラック",
    "eyeColorBrown": "ブラウン",
    "eyeColorBlue": "ブルー",
    "eyeColorGreen": "グリーン",
    "eyeColorHazel": "ヘーゼル",
    "ja": "日本語",
    "zh": "中国語",
    "ko": "韓国語",
    "en": "英語",
    "es": "スペイン語",
    "fr": "フランス語",
    "pt": "ポルトガル語",
    "de": "ドイツ語",
    "it": "イタリア語",
    "ru": "ロシア語",
    "ar": "アラビア語",
}

SAFE_INTERESTS_MAP = {
    "anime": "アニメ",
    "cosplay": "コスプレ",
    "dancing": "ダンス",
    "singing": "歌・カラオケ",
    "karaoke": "カラオケ",
    "music": "音楽鑑賞",
    "k-pop": "K-POP",
    "electronic": "エレクトロニック音楽",
    "musical": "ミュージカル",
    "movies": "映画鑑賞",
    "gaming": "ゲーム",
    "video-games": "テレビゲーム",
    "fitness": "フィットネス",
    "yoga": "ヨガ",
    "cooking": "料理",
    "travel": "旅行",
    "fashion": "ファッション",
    "makeup": "メイク",
    "photography": "写真・カメラ",
    "art": "アート",
    "drawing": "イラスト",
    "reading": "読書",
    "comic-books": "マンガ・コミック",
    "cats": "猫好き",
    "dogs": "犬好き",
    "pets": "ペット",
    "sushi": "お寿司",
    "sweet-tooth": "スイーツ",
    "coffee": "カフェ・コーヒー",
    "wine": "ワイン",
    "napping": "お昼寝",
    "shopping": "ショッピング",
    "historical": "歴史",
    "poetry": "詩・文学",
    "asmr": "ASMR",
    "roleplay": "ロールプレイ",
}

SAFE_TAGS_MAP = {
    "ethnicityAsian": "アジアン美女",
    "doCosplay": "コスプレ配信",
    "doEroticDance": "ダンスパフォーマンス",
    "doTalk": "トーク・雑談",
    "doYoga": "ヨガ・ストレッチ",
    "autoTagHd": "高画質HD対応",
    "autoTagVr": "VR対応",
    "tagLanguageJapanese": "日本語配信",
    "tagLanguageChinese": "中国語配信",
    "tagLanguageKorean": "韓国語配信",
}

# 一般ブログである美女図鑑で禁止・ブロックすべき露骨な語句
STRIPCHAT_NG_WORDS = [
    "精子", "中出し", "無修正", "モロ", "潮吹き", "アナル", "乱交", "フェラ", "パイズリ",
    "手コキ", "バイブ", "ローター", "オナニー", "ちんぽ", "まんこ", "エロ配信", "ノーパン",
    "肉棒", "插入", "喷水", "骚逼", "高潮", "自慰", "口交", "内射", "阴茎", "阴道", "内窥镜", "内窺鏡",
    "做爱", "打飞机", "丝袜诱惑", "露点", "裸聊", "大尺度", "情色", "淫水", "小穴", "濕濕", "哪裡舔", "舔",
    "裸体", "诱惑", "大屁股", "菊花", "骚", "绿帽", "小便池", "男厕", "阴蒂", "乳头", "合集",
    "분수", "자위", "야동", "보지", "자지", "섹스", "노출",
    "fuck", "cock", "dick", "pussy", "cum", "squirt", "blowjob", "deepthroat",
    "handjob", "footjob", "titty", "anal", "bdsm", "bondage", "fisting", "dp",
    "gangbang", "jerk", "cuckold", "facial", "rimming", "orgasm", "masturbate",
    "dildo", "vibrator", "sex", "nude", "naked", "porn", "xxx", "erotic", "boob", "asshole",
]


def has_unsafe_word(text):
    if not text:
        return False
    low = text.lower()
    return any(w in low for w in STRIPCHAT_NG_WORDS) or any(w in text for w in ("乱暴", "調教", "強制", "辱め"))


def clean_stripchat_text(text, max_len=120):
    """NGワード・露骨表現を除去または安全な文言へ丸める"""
    if not text:
        return ""
    if has_unsafe_word(text):
        return ""
    out = sanitize_text(text)
    out = re.sub(r"https?://\S+", "", out)
    out = re.sub(r"\s+", " ", out).strip(" ・/!！◎~～")
    if len(out) > max_len:
        out = out[:max_len] + "…"
    return out


class StripchatCurationEngine:
    def __init__(self, blog_id=DEFAULT_BLOG_ID):
        self.blog_id = blog_id
        self.livedoor = LivedoorClient(blog_id=blog_id)
        self.amazon_tag = os.getenv("AMAZON_ASSOCIATE_TAG", "blogseesaa090-22")

    # ------------------------------------------------------------------ 履歴管理
    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data.setdefault("current_vol", 1)
                    data.setdefault("current_top_vol", 1)
                    data.setdefault("top_division_idx", 0)
                    data.setdefault("posted_usernames", [])
                    data.setdefault("skipped_usernames", {})
                    data.setdefault("posted_articles", [])
                    return data
            except Exception as e:
                print(f"[履歴読み込みエラー] {e}")
        return {
            "current_vol": 1,
            "current_top_vol": 1,
            "top_division_idx": 0,
            "posted_usernames": [],
            "skipped_usernames": {},
            "posted_articles": [],
        }

    def save_history(self, data):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ HTTP/JSONヘルパー
    def _extract_preloaded_state(self, url):
        """jp.stripchat.com ページの __PRELOADED_STATE__ JSON を解析して返す"""
        try:
            res = requests.get(url, headers=HTML_HEADERS, timeout=20)
            if res.status_code != 200:
                print(f"[HTML取得失敗] {url} -> HTTP {res.status_code}")
                return None
            decoder = json.JSONDecoder()
            for s in re.findall(r"<script[^>]*>(.*?)</script>", res.text, re.S):
                stripped = s.lstrip()
                if stripped.startswith("window.__PRELOADED_STATE__") or (len(stripped) > 50_000 and '"viewCam"' in stripped):
                    idx = stripped.find("{")
                    if idx != -1:
                        data, _ = decoder.raw_decode(stripped, idx)
                        return data
        except Exception as e:
            print(f"[PRELOADED_STATE解析エラー] {url}: {e}")
        return None

    def _fetch_api_models(self, filter_tag=None, limit=60, offset=0):
        """Stripchat API /api/front/models から配信中モデル一覧を取得する"""
        params = {"limit": limit, "offset": offset, "primaryTag": "girls"}
        if filter_tag:
            params["filterGroupTags"] = json.dumps([[filter_tag]])
        try:
            res = requests.get(
                "https://stripchat.com/api/front/models",
                params=params,
                headers=API_HEADERS,
                timeout=20,
            )
            if res.status_code == 200:
                return res.json().get("models", [])
        except Exception as e:
            print(f"[Stripchat APIエラー] {filter_tag}: {e}")
        return []

    def _fetch_search_models(self, query):
        """jp.stripchat.com/search/models/{query} からオフライン含むモデル検索結果を取得"""
        state = self._extract_preloaded_state(f"https://jp.stripchat.com/search/models/{query}")
        if not state:
            return []
        return state.get("modelSearch", {}).get("models", [])

    # ------------------------------------------------------------------ 候補抽出
    def _pick_region_candidates(self, region_key, posted_set, skipped_set, target=6):
        """指定地域（jp / cn / kr）から未掲載の女性パフォーマー候補を抽出する"""
        found = []
        seen = set()

        def add_model(m, source_label):
            uname = (m.get("username") or "").strip()
            if not uname:
                return
            key = uname.lower()
            if key in seen or key in posted_set or key in skipped_set:
                return
            gender = m.get("gender") or m.get("broadcastGender") or "female"
            if gender != "female":
                return
            seen.add(key)
            found.append({
                "username": uname,
                "region_key": region_key,
                "country": (m.get("country") or "").lower(),
                "viewers_count": int(m.get("viewersCount") or 0),
                "avatar_url": m.get("avatarUrl") or "",
                "preview_url": m.get("previewUrl") or m.get("previewUrlThumbSmall") or "",
                "source_label": source_label,
                "is_live": bool(m.get("isLive")),
            })

        if region_key == "jp":
            for m in self._fetch_api_models("tagLanguageJapanese", limit=60):
                add_model(m, "日本語配信ランキング")
            for m in self._fetch_api_models("ethnicityAsian", limit=80):
                if (m.get("country") or "").lower() == "jp":
                    add_model(m, "アジア人気ランキング(JP)")
            if len(found) < target:
                for q in ("japanese", "tokyo", "osaka", "yui", "sakura"):
                    for m in self._fetch_search_models(q):
                        if (m.get("country") or "").lower() == "jp":
                            add_model(m, f"検索照合({q})")
        elif region_key == "cn":
            for m in self._fetch_api_models("tagLanguageChinese", limit=60):
                add_model(m, "中国語配信ランキング")
            for m in self._fetch_api_models("ethnicityAsian", limit=80):
                if (m.get("country") or "").lower() in ("cn", "tw", "hk"):
                    add_model(m, "アジア人気ランキング(CN/TW)")
            if len(found) < target:
                for q in ("chinese", "taiwan"):
                    for m in self._fetch_search_models(q):
                        if (m.get("country") or "").lower() in ("cn", "tw", "hk"):
                            add_model(m, f"検索照合({q})")
        elif region_key == "kr":
            for m in self._fetch_api_models("tagLanguageKorean", limit=60):
                add_model(m, "韓国語配信ランキング")
            for off in (0, 60, 120, 180):
                for m in self._fetch_api_models("ethnicityAsian", limit=60, offset=off):
                    if (m.get("country") or "").lower() == "kr":
                        add_model(m, "アジア人気ランキング(KR)")
            for q in ("korean", "korea", "seoul", "seulgi", "yuna", "jiyeon", "soyeon", "kim"):
                if len(found) >= target * 2:
                    break
                for m in self._fetch_search_models(q):
                    c = (m.get("country") or "").lower()
                    langs = m.get("languages") or []
                    if c == "kr" or "ko" in langs or ("korean" in (m.get("username") or "").lower() and c in ("", "kr")):
                        add_model(m, f"韓国モデル照合({q})")

        found.sort(
            key=lambda x: (
                1 if x["country"] in ("jp", "cn", "tw", "hk", "kr") else 0,
                1 if x["is_live"] else 0,
                x["viewers_count"],
            ),
            reverse=True,
        )
        return found[:target]

    def fetch_asian_candidates_by_region(self, per_region=6):
        """日本・中国/台湾・韓国の地域別候補マップを返す"""
        history = self.load_history()
        posted_set = {u.lower() for u in history.get("posted_usernames", [])}
        skipped_set = {u.lower() for u in history.get("skipped_usernames", {})}

        pool = {}
        for rk in ("jp", "cn", "kr"):
            pool[rk] = self._pick_region_candidates(rk, posted_set, skipped_set, target=per_region)
            print(f"[候補抽出 {COUNTRY_META[rk]['label']}] {len(pool[rk])}名: {[c['username'] for c in pool[rk]]}")
        return pool

    def _pick_top_division_candidates(self, div_key, posted_set, skipped_set, target=30):
        """人気キャスト（女性5部門・カップル部門）の月間ランキングページから未掲載候補を抽出する"""
        meta = TOP_DIVISIONS[div_key]
        state = self._extract_preloaded_state(meta["url"])
        if not state:
            return []

        items = []
        for qval in (state.get("topModels") or {}).get("queries", {}).values():
            cand_items = (qval.get("data") or {}).get("items") or []
            if cand_items:
                items = cand_items
                break

        allowed_genders = ("female", "females", "maleFemale", "couple", "couples")
        found = []
        seen = set()
        for idx, it in enumerate(items, 1):
            m = it.get("model") or {}
            uname = (m.get("username") or "").strip()
            if not uname or has_unsafe_word(uname):
                continue
            key = uname.lower()
            if key in seen or key in posted_set or key in skipped_set:
                continue
            gender = m.get("gender") or m.get("broadcastGender") or "female"
            if gender not in allowed_genders:
                continue
            seen.add(key)
            pos = int(it.get("position") or idx)
            pts = int(it.get("stripPoints") or 0)
            best = int(m.get("topBestPlace") or pos)
            found.append({
                "username": uname,
                "region_key": div_key,
                "division_key": div_key,
                "country": (m.get("country") or "").lower(),
                "viewers_count": pts,
                "rank_position": pos,
                "strip_points": pts,
                "top_best_place": best,
                "avatar_url": m.get("avatarUrl") or "",
                "preview_url": m.get("previewUrlThumbBig") or m.get("previewUrlThumbSmall") or "",
                "source_label": f"{meta['short']} {pos}位 ({pts:,}pt)",
                "is_live": bool(m.get("isLive")),
            })
            if len(found) >= target:
                break
        return found

    def fetch_top_cast_candidates(self, divisions, per_division=30):
        """指定した人気キャスト部門ごとの候補マップを返す"""
        history = self.load_history()
        posted_set = {u.lower() for u in history.get("posted_usernames", [])}
        skipped_set = {u.lower() for u in history.get("skipped_usernames", {})}

        with ThreadPoolExecutor(max_workers=min(6, max(1, len(divisions)))) as pool:
            futures = {
                dk: pool.submit(self._pick_top_division_candidates, dk, posted_set, skipped_set, per_division)
                for dk in divisions
            }
            out = {dk: futures[dk].result() for dk in divisions}

        for dk in divisions:
            cands = out.get(dk, [])
            print(f"[人気候補 {TOP_DIVISIONS[dk]['label']}] {len(cands)}組: {[c['username'] for c in cands[:5]]}")
        return out

    # ------------------------------------------------------------------ SNS・画像照合
    def search_sns_and_images(self, username):
        """Yahoo!リアルタイム検索・Yahoo!画像検索でユーザー名を照合し、SNS投稿・補助画像を取得する"""
        tweets = []
        fallback_imgs = []
        try:
            r = requests.get(
                "https://search.yahoo.co.jp/realtime/search",
                params={"p": f"Stripchat {username}", "ei": "UTF-8"},
                headers=HTML_HEADERS,
                timeout=12,
            )
            m = re.search(r"__NEXT_DATA__[^>]*>(.*?)</script>", r.text)
            if m:
                d = json.loads(m.group(1))
                entries = d.get("props", {}).get("pageProps", {}).get("pageData", {}).get("timeline", {}).get("entry", [])
                for e in entries[:5]:
                    raw_body = re.sub(r"\t?(?:START|END)\t?", "", e.get("displayTextBody", ""))
                    if username.lower() not in raw_body.lower():
                        continue
                    body = clean_stripchat_text(raw_body, max_len=70)
                    screen = e.get("screenName", "")
                    turl = re.sub(r"\?.*$", "", e.get("url", ""))
                    if screen and body:
                        tweets.append({
                            "screen_name": screen,
                            "text": body,
                            "likes": int(e.get("likesCount") or 0),
                            "url": turl or f"https://x.com/{screen}",
                        })
                    for med in e.get("media", []):
                        mu = med.get("item", {}).get("mediaUrl") or med.get("metaImageUrl")
                        if mu and mu not in fallback_imgs:
                            fallback_imgs.append(mu)
        except Exception as e:
            print(f"[SNS照合スキップ] {username}: {e}")

        if len(fallback_imgs) < 2:
            try:
                r_img = requests.get(
                    "https://search.yahoo.co.jp/image/search",
                    params={"p": f"Stripchat {username}"},
                    headers=HTML_HEADERS,
                    timeout=10,
                )
                y_urls = list(dict.fromkeys(re.findall(r"https://msp\.c\.yimg\.jp/images/v2/[A-Za-z0-9/_.-]+", r_img.text)))
                for yu in y_urls[:6]:
                    if yu not in fallback_imgs:
                        fallback_imgs.append(yu)
            except Exception:
                pass
        return tweets, fallback_imgs

    def extract_sns_links(self, username, prof_state):
        """Stripchat公式プロフィール・Yahoo!検索から各ライバーの公式SNSおよび検索リンクを抽出する"""
        links = []
        seen = set()
        norm_u = re.sub(r"[^a-z0-9]", "", username.lower())
        blocked_paths = ("/status/", "/search", "/hashtag", "/explore", "/p/", "/reel/", "/discover", "/popular", "/tag")

        def add_direct_link(url):
            clean_u = re.sub(r"[\\\"\'\),\s]+$", "", url.strip())
            clean_u = re.sub(r"\?(?:xtok|_?utm_[^=]+).*$", "", clean_u)
            low_u = clean_u.lower()
            if any(bad in low_u for bad in blocked_paths):
                return
            matched_meta = None
            for dom, p_label, p_bg in SNS_PLATFORMS:
                if dom in low_u:
                    matched_meta = (dom, p_label, p_bg)
                    break
            if not matched_meta:
                return
            dom, p_label, p_bg = matched_meta
            key = re.sub(r"^https?://(?:www\.)?", "", low_u).rstrip("/")
            if key in seen:
                return
            seen.add(key)
            label = p_label
            if dom not in ("lovense.com/wish-list/", "snapchat.com/"):
                handle_m = re.search(r"/(@?[A-Za-z0-9_.\-]+)$", clean_u.rstrip("/"))
                if handle_m:
                    label = f"{p_label} ({handle_m.group(1)})"
            links.append({"url": clean_u, "label": label, "bg": p_bg, "is_direct": True})

        # 1. Stripchat公式プロフィール内データ (viewCam / userPanels / profile / profilePage)
        if prof_state:
            blob = json.dumps(
                {k: prof_state.get(k) for k in ("viewCam", "userPanels", "profile", "profilePage")},
                ensure_ascii=False,
            )
            for u in re.findall(r"https?://[^\s\"'<>\\]+", blob):
                add_direct_link(u)

        # 2. Yahoo!検索による同一ハンドル名の公式SNS照合 (誤一致防止のため8文字以上の完全一致に限定)
        if len(norm_u) >= 8:
            try:
                q = f'"{username}" (site:x.com OR site:instagram.com OR site:tiktok.com OR site:linktr.ee OR site:link.me)'
                r = requests.get(
                    "https://search.yahoo.co.jp/search",
                    params={"p": q, "ei": "UTF-8"},
                    headers=HTML_HEADERS,
                    timeout=10,
                )
                target_ids = {username.lower(), f"xxx{username.lower()}"}
                for u in re.findall(
                    r"https?://(?:www\.)?(?:x\.com|twitter\.com|instagram\.com|tiktok\.com|linktr\.ee|link\.me)/@?[A-Za-z0-9_.\-]+",
                    r.text,
                ):
                    tail = u.rstrip("/").split("/")[-1].lstrip("@").lower()
                    if tail in target_ids:
                        add_direct_link(u)
            except Exception as e:
                print(f"[SNSリンク検索スキップ] {username}: {e}")

        # 3. 全キャスト共通のSNS検索・反響確認ショートカットリンク
        links.append({
            "url": f"https://x.com/search?q={urllib.parse.quote(username)}",
            "label": f"𝕏 X(Twitter)で「{username}」を検索",
            "bg": "#475569",
            "is_direct": False,
        })
        links.append({
            "url": f"https://search.yahoo.co.jp/realtime/search?p={urllib.parse.quote('Stripchat ' + username)}",
            "label": "🔍 SNSリアルタイム反響を見る",
            "bg": "#64748b",
            "is_direct": False,
        })
        return links

    def upload_image_safe(self, img_url):
        """画像をダウンロードし、WebP/PNG等もJPEGへ変換してlivedoor.blogimg.jpへアップロードする"""
        if not img_url:
            return None
        try:
            r = requests.get(img_url, headers={"User-Agent": HTML_HEADERS["User-Agent"]}, timeout=15)
            ct = r.headers.get("Content-Type", "").split(";")[0].lower()
            if r.status_code != 200 or not ct.startswith("image/") or len(r.content) < MIN_IMAGE_BYTES:
                return None

            raw_bytes = r.content
            upload_ct = ct
            # ライブドア AtomPub /image は WebP を 400 で拒否するため JPEG に変換する
            if ct in ("image/webp", "image/png", "image/avif", "image/bmp"):
                im = Image.open(io.BytesIO(raw_bytes))
                if im.width < 180 or im.height < 180:
                    return None
                if im.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    if im.mode == "P":
                        im = im.convert("RGBA")
                    bg.paste(im, mask=im.split()[-1] if im.mode in ("RGBA", "LA") else None)
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=92)
                raw_bytes = buf.getvalue()
                upload_ct = "image/jpeg"

            uploaded = self.livedoor.upload_image(raw_bytes, content_type=upload_ct)
            if isinstance(uploaded, str) and "livedoor.blogimg.jp" in uploaded:
                return uploaded
        except Exception as e:
            print(f"[画像アップロードエラー] {img_url}: {e}")
        return None

    # ------------------------------------------------------------------ 詳細プロフィール＆アーカイブ照合
    def enrich_model(self, candidate, require_asian=True):
        """パフォーマー1組分の公式プロフィール・フォトアルバム・動画アーカイブ・SNS照合データを収集する"""
        uname = candidate["username"]
        if has_unsafe_word(uname):
            return None, "ユーザー名に安全フィルタ該当語句を含むため除外"
        base = f"https://jp.stripchat.com/{uname}"

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_prof = pool.submit(self._extract_preloaded_state, f"{base}/profile")
            f_phot = pool.submit(self._extract_preloaded_state, f"{base}/photos")
            f_vid = pool.submit(self._extract_preloaded_state, f"{base}/videos")
            prof_state = f_prof.result()
            phot_state = f_phot.result()
            vid_state = f_vid.result()

        if not prof_state:
            return None, "プロフィールページ取得失敗"

        vc = prof_state.get("viewCam", {})
        model = vc.get("model") or {}
        if not model or model.get("isDeleted") or model.get("isBlocked"):
            return None, "アカウント削除・非公開"

        gender = model.get("gender") or model.get("broadcastGender") or "female"
        if require_asian:
            if gender != "female":
                return None, f"女性単体アカウントではない ({gender})"
        elif gender not in CAST_STYLE_MAP:
            return None, f"対象外の配信スタイル ({gender})"

        tags = vc.get("tags") or []
        ethnicity = model.get("ethnicity") or ""
        raw_langs = model.get("languages") or []
        country_code = (model.get("country") or candidate.get("country") or "").lower()

        rk = candidate["region_key"]
        if require_asian:
            # 国籍コード優先（他国コードが入っている場合は除外し、アジア人タグもチェック）
            expected_codes = {
                "jp": ("jp", ""),
                "cn": ("cn", "tw", "hk", ""),
                "kr": ("kr", ""),
            }[rk]
            if country_code not in expected_codes:
                return None, f"対象国コード不一致 ({country_code} != {rk})"

            is_asian = (
                "ethnicityAsian" in tags
                or ethnicity == "ethnicityAsian"
                or country_code in ("jp", "cn", "tw", "hk", "kr")
            )
            if not is_asian:
                return None, f"アジア圏パフォーマーではない (country={country_code}, hair={model.get('hairColor')})"
            if rk == "kr" and country_code == "" and "ko" not in raw_langs and (set(raw_langs) & {"de", "fr", "es", "ru", "pt", "it"}):
                return None, f"韓国語・韓国籍の根拠不足 (langs={raw_langs})"

        counters = vc.get("userMediaCounters") or {}
        photos_count = int(counters.get("photosCount") or 0)
        videos_count = int(counters.get("videosCount") or 0)
        favorited = int(model.get("favoritedCount") or 0)

        langs = [LABEL_MAP[l] for l in raw_langs if l in LABEL_MAP]

        # 高画質公開フォト（非ヌード優先） → 動画カバー → アバターの順で集める
        raw_photos = []
        if phot_state:
            col_map = (phot_state.get("albums") or {}).get("collection") or {}
            safe_free, safe_other = [], []
            for album_list in col_map.values():
                if not isinstance(album_list, list):
                    continue
                for alb in album_list:
                    is_free = alb.get("accessMode") == "free"
                    for ph in alb.get("photos") or []:
                        if ph.get("isHidden") or ph.get("isDeleted"):
                            continue
                        u = ph.get("urlPreview") or ph.get("url") or ph.get("urlThumb")
                        if not u:
                            continue
                        if is_free and not ph.get("isNudeContent"):
                            safe_free.append(u)
                        elif not ph.get("isNudeContent"):
                            safe_other.append(u)
            for u in safe_free + safe_other:
                if u not in raw_photos:
                    raw_photos.append(u)

        # 過去動画アーカイブの収集（安全なタイトル・日付のテキスト情報のみ取得、動画キャプチャ画像は除外）
        videos_list = []
        if vid_state:
            vid_map = ((vid_state.get("videos") or {}).get("videos")) or {}
            for vlist in vid_map.values():
                if not isinstance(vlist, list):
                    continue
                for v in vlist:
                    if v.get("isHidden") or v.get("isDeleted"):
                        continue
                    safe_title = clean_stripchat_text(v.get("title") or "", max_len=45)
                    v_date = (v.get("createdAt") or "")[:10]
                    v_dur = int(v.get("duration") or 0)
                    videos_list.append({
                        "title": safe_title or f"{uname} 最新アーカイブ配信 ({v_date})" if v_date else f"{uname} 公式アーカイブ映像",
                        "date": v_date,
                        "duration": v_dur,
                    })

        avatar = model.get("avatarUrl") or candidate.get("avatar_url") or ""
        if avatar and avatar not in raw_photos:
            raw_photos.append(avatar)

        sns_tweets, search_imgs = self.search_sns_and_images(uname)
        for si in search_imgs:
            if si not in raw_photos:
                raw_photos.append(si)
        sns_links = self.extract_sns_links(uname, prof_state)

        hosted_images = []
        for u in raw_photos[:12]:
            up = self.upload_image_safe(u)
            if up and up not in hosted_images:
                hosted_images.append(up)
                if len(hosted_images) >= 3:
                    break

        if not hosted_images:
            return None, "有効な公開画像が取得・アップロードできませんでした"

        # 趣味・特徴タグは一般ブログ向け安全リストのみ日本語化して表示
        safe_interests = []
        for it in model.get("interests") or []:
            mapped = SAFE_INTERESTS_MAP.get(it)
            if mapped and mapped not in safe_interests:
                safe_interests.append(mapped)
        for tg in tags:
            mapped = SAFE_TAGS_MAP.get(tg)
            if mapped and mapped not in safe_interests:
                safe_interests.append(mapped)

        div_key = candidate.get("division_key")
        meta = TOP_DIVISIONS[div_key] if (div_key and div_key in TOP_DIVISIONS) else COUNTRY_META[rk]
        default_lang = "英語 / 多言語" if div_key else meta["short"]
        raw_age = model.get("age")
        safe_age = raw_age if isinstance(raw_age, int) and 18 <= raw_age <= 75 else None

        return {
            "username": uname,
            "region_key": rk,
            "division_key": div_key,
            "region_label": meta["label"],
            "short_label": meta["short"],
            "badge_bg": meta["badge_bg"],
            "rank_position": candidate.get("rank_position"),
            "strip_points": int(candidate.get("strip_points") or 0),
            "top_best_place": candidate.get("top_best_place"),
            "cast_style": CAST_STYLE_MAP.get(gender, "女性パフォーマー"),
            "profile_url": base,
            "age": safe_age,
            "country_code": country_code.upper() if country_code else meta["short"],
            "languages_str": " / ".join(langs) if langs else default_lang,
            "body_type": LABEL_MAP.get(model.get("bodyType"), "魅力的スタイル"),
            "hair_color": LABEL_MAP.get(model.get("hairColor"), "—"),
            "eye_color": LABEL_MAP.get(model.get("eyeColor"), "—"),
            "interests": safe_interests[:5],
            "favorited_count": favorited,
            "photos_count": photos_count,
            "videos_count": videos_count,
            "topic": clean_stripchat_text(vc.get("topic") or "", max_len=65),
            "description": clean_stripchat_text(model.get("description") or "", max_len=140),
            "images": hosted_images,
            "videos": videos_list[:4],
            "sns_links": sns_links,
            "sns_tweets": sns_tweets[:2],
            "source_label": candidate.get("source_label", ""),
        }, None

    # ------------------------------------------------------------------ HTML記事生成
    def _build_commentary(self, m):
        """プロフィールとアーカイブ照合結果をもとに紹介コメントを作成する"""
        if m.get("division_key"):
            parts = [
                f"「{m['username']}」さんは<strong>{m['region_label']}</strong>で今月<strong>{m['rank_position']}位</strong>"
                f"（{m['strip_points']:,} pt）にランクインしている注目キャスト（{m['cast_style']}）で、"
                f"公式ファン登録数は<strong>{m['favorited_count']:,}人</strong>を記録しています。"
            ]
        else:
            parts = [
                f"「{m['username']}」さんは{m['region_label'].split()[-1]}を拠点に活動する注目クリエイターで、"
                f"公式ファン登録数は<strong>{m['favorited_count']:,}人</strong>を記録しています。"
            ]
        if m["photos_count"] or m["videos_count"]:
            parts.append(
                f"公開アーカイブには写真<strong>{m['photos_count']}枚</strong>・動画<strong>{m['videos_count']}本</strong>が登録されており、"
            )
        else:
            parts.append("ライブ配信とフォトコンテンツを中心に人気を集めており、")

        if m["interests"]:
            parts.append(f"特徴・関心ジャンルは「{'・'.join(m['interests'][:4])}」などが挙げられます。")
        else:
            parts.append(f"{m['body_type']}のスタイルと親しみやすい雰囲気が大きな魅力です。")

        if m["sns_tweets"]:
            parts.append(f"X（旧Twitter）でもユーザーからの言及（@{m['sns_tweets'][0]['screen_name']}）が確認できており、SNS経由の注目度も高めです。")
        elif m["videos"]:
            parts.append(f"公開アーカイブ内の『{m['videos'][0]['title']}』をはじめ、多彩なコンテンツが楽しめます。")
        return "".join(parts)

    def generate_curation_html(self, models, vol, mode="asian", division="all"):
        """まとめ記事（日中韓アジア美女 / 人気キャスト女性5部門＋カップル）のHTML・タイトル・タグを生成する"""
        e = html.escape
        date_str = datetime.date.today().strftime("%Y年%m月%d日")
        is_top = mode == "top"

        if is_top and division in TOP_DIVISIONS:
            div_meta = TOP_DIVISIONS[division]
            title = f"【世界人気キャスト図鑑 Vol.{vol}】{div_meta['label']} 上位{len(models)}組まとめ｜プロフィール＆アーカイブ照合"
            badge_top = f"STRIPCHAT TOP RANKING DIGEST Vol.{vol}"
            sub_meta = f"更新日: {date_str} ｜ 対象部門: {div_meta['label']}"
            intro = (
                f"Stripchat公式の月間人気ランキング「{div_meta['label']}」で上位を席巻する注目キャスト{len(models)}組をピックアップ！"
                "公式ランキング順位・獲得ポイントに加えて、公開プロフィール・フォトアルバム・過去動画アーカイブ・SNS照合データをまとめました。"
            )
            toc_title = f"📑 {div_meta['label']} 上位{len(models)}組 目次"
            monetize_title = "📚 世界の人気美女＆海外写真集ストアをお得にチェック"
            amz_kw = "海外 モデル 写真集 グラビア 人気"
            footer_title = f"美女図鑑 世界人気キャストまとめ Vol.{vol}"
            tags = ["美女図鑑", "Stripchat", "人気キャスト", div_meta["short"], "ライブ配信"] + [m["username"] for m in models[:4]]
        elif is_top:
            title = f"【世界人気キャスト図鑑 Vol.{vol}】女性5部門（アジア・北米・南米・欧州・アフリカ）＆カップル上位{len(models)}組まとめ｜プロフィール＆アーカイブ照合"
            badge_top = f"STRIPCHAT GLOBAL TOP 6 DIVISIONS Vol.{vol}"
            sub_meta = f"更新日: {date_str} ｜ 対象部門: 🌏アジア・🗽北米・🌴南米・🏰欧州・🌍アフリカ・💑カップル"
            intro = (
                f"Stripchatの公式人気キャストランキング「女性5地域部門（アジア&太平洋・北アメリカ・南アメリカ・ヨーロッパ・アフリカ）」および「カップル部門」から、"
                f"各部門を代表する注目キャスト計{len(models)}組を厳選まとめ！各部門のランキング順位・プロフィール・公開アーカイブ・SNS言及を一挙に照合しました。"
            )
            toc_title = f"📑 女性5部門＋カップル 人気キャスト {len(models)}組 目次"
            monetize_title = "📚 世界の人気美女＆海外写真集ストアをお得にチェック"
            amz_kw = "海外 モデル 写真集 グラビア 人気"
            footer_title = f"美女図鑑 世界人気キャストまとめ Vol.{vol}"
            tags = ["美女図鑑", "Stripchat", "人気キャスト", "カップル配信", "世界の美女"] + [m["username"] for m in models[:4]]
        else:
            title = f"【アジア美女図鑑 Vol.{vol}】世界のライブ配信で話題の日・中・韓美女{len(models)}選まとめ｜プロフィール＆アーカイブ徹底照合"
            badge_top = f"ASIAN CREATOR &amp; ARCHIVE DIGEST Vol.{vol}"
            sub_meta = f"更新日: {date_str} ｜ 対象地域: 🇯🇵日本・🇨🇳中国/台湾・🇰🇷韓国"
            intro = (
                f"日本・中国（台湾含む）・韓国のグローバル配信コミュニティで高い人気を集めている美女クリエイター{len(models)}名を厳選ピックアップ！"
                "公式プロフィール情報に加えて、公開フォトアルバム・過去動画アーカイブ・SNS（X）での話題性をまとめて照合しました。"
            )
            toc_title = f"📑 今回紹介する日・中・韓美女 {len(models)}名 目次"
            monetize_title = "📚 アジア美女の写真集＆人気ストアをお得にチェック"
            amz_kw = "アジア 美女 写真集 コスプレ 人気"
            footer_title = f"美女図鑑 アジアクリエイターまとめ Vol.{vol}"
            tags = ["美女図鑑", "アジア美女", "ライブ配信", "韓国美女", "中国美女"] + [m["username"] for m in models[:4]]

        amz_photo = get_amazon_url(amz_kw, self.amazon_tag)
        amz_sub = get_amazon_url("グラビア デジタル写真集 トレンド", self.amazon_tag)
        kindle_url = get_kindle_unlimited_url(self.amazon_tag)

        style = """
<style>
.sc-wrap{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans",Meiryo,sans-serif;color:#1f2937;max-width:840px;margin:0 auto;line-height:1.8}
.sc-hero{background:linear-gradient(135deg,#0f172a 0%,#312e81 55%,#be185d 100%);color:#fff;padding:30px 22px;border-radius:16px;text-align:center;margin-bottom:26px;box-shadow:0 10px 28px rgba(15,23,42,.2)}
.sc-badge-top{display:inline-block;background:rgba(255,255,255,.18);padding:5px 15px;border-radius:20px;font-size:12px;font-weight:bold;letter-spacing:1px;margin-bottom:10px}
.sc-hero h1{font-size:23px;line-height:1.45;margin:8px 0 12px}
.sc-intro{background:rgba(255,255,255,.12);border-radius:10px;padding:14px 16px;font-size:14px;text-align:left}
.sc-toc{background:#f8fafc;border:2px solid #e2e8f0;border-radius:14px;padding:18px 20px;margin-bottom:32px}
.sc-toc-title{font-size:16px;font-weight:bold;color:#1e293b;margin-bottom:12px}
.sc-toc-list{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.sc-toc-list a{display:flex;align-items:center;gap:8px;padding:10px 12px;background:#fff;border:1px solid #cbd5e1;border-radius:10px;color:#1e293b;text-decoration:none;font-weight:bold;font-size:13.5px}
.sc-card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:22px;margin-bottom:34px;box-shadow:0 6px 20px rgba(0,0,0,.05)}
.sc-card-head{display:flex;align-items:center;flex-wrap:wrap;gap:10px;border-bottom:2px solid #f1f5f9;padding-bottom:12px;margin-bottom:16px}
.sc-num{background:linear-gradient(135deg,#ec4899,#8b5cf6);color:#fff;font-weight:bold;font-size:13px;padding:4px 12px;border-radius:18px}
.sc-country{color:#fff;font-weight:bold;font-size:12px;padding:4px 11px;border-radius:16px}
.sc-name{font-size:21px;font-weight:bold;color:#0f172a}
.sc-fav{margin-left:auto;font-size:13px;font-weight:bold;color:#db2777;background:#fdf2f8;padding:4px 12px;border-radius:14px}
.sc-main-img{text-align:center;margin-bottom:14px}
.sc-main-img img{max-width:100%;max-height:540px;object-fit:contain;border-radius:12px;box-shadow:0 6px 18px rgba(0,0,0,.12)}
.sc-sub-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:16px}
.sc-sub-grid img{width:100%;height:190px;object-fit:cover;border-radius:10px;border:1px solid #e2e8f0}
.sc-table{width:100%;border-collapse:collapse;font-size:13.5px;margin-bottom:16px}
.sc-table th{background:#f1f5f9;width:28%;text-align:left;padding:9px 12px;border:1px solid #e2e8f0;color:#334155}
.sc-table td{padding:9px 12px;border:1px solid #e2e8f0}
.sc-comment{background:#fdf2f8;border-left:4px solid #ec4899;border-radius:8px;padding:13px 16px;font-size:14px;margin-bottom:14px}
.sc-archive-box{background:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;padding:13px 16px;margin-bottom:14px;font-size:13px}
.sc-archive-box ul{margin:6px 0 0;padding-left:18px}
.sc-sns-box{background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;padding:12px 15px;margin-bottom:14px}
.sc-sns-title{font-size:13.5px;font-weight:bold;color:#0369a1;margin-bottom:8px}
.sc-sns-list{display:flex;flex-wrap:wrap;gap:8px}
.sc-sns-btn{display:inline-flex;align-items:center;padding:6px 12px;border-radius:18px;color:#fff!important;text-decoration:none;font-size:12.5px;font-weight:bold;text-shadow:0 1px 2px rgba(0,0,0,.25)}
.sc-btn{display:block;background:linear-gradient(135deg,#ec4899,#f43f5e);color:#fff!important;text-decoration:none;font-weight:bold;text-align:center;padding:12px 16px;border-radius:26px;font-size:15px}
.sc-monetize{background:linear-gradient(135deg,#fffbeb,#fef3c7);border:2px solid #f59e0b;border-radius:14px;padding:20px;margin:30px 0;text-align:center}
.sc-monetize-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:12px}
.sc-monetize-grid a{display:block;padding:12px 14px;border-radius:25px;font-weight:bold;font-size:14px;text-decoration:none;color:#fff!important}
.sc-footer{background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:22px;text-align:center;font-size:13px;color:#64748b}
</style>
"""

        toc_items = []
        for i, m in enumerate(models, 1):
            short_txt = m.get("short_label") or COUNTRY_META[m["region_key"]]["short"]
            rank_txt = f" {m['rank_position']}位" if m.get("rank_position") else ""
            toc_items.append(
                f'<li><a href="#sc-{i}"><span>#{i}</span>'
                f'<span style="background:{m["badge_bg"]};color:#fff;font-size:11px;padding:2px 7px;border-radius:10px;">{e(short_txt)}{e(rank_txt)}</span>'
                f'<span>{e(m["username"])}</span></a></li>'
            )
        toc_html = "".join(toc_items)

        cards = []
        for idx, m in enumerate(models, 1):
            main_img = m["images"][0]
            sub_imgs = m["images"][1:]
            sub_html = ""
            if sub_imgs:
                sub_tags = "".join(
                    f'<a href="{e(m["profile_url"])}" target="_blank" rel="nofollow noopener">'
                    f'<img src="{e(u)}" alt="{e(m["username"])} サブ画像"></a>'
                    for u in sub_imgs
                )
                sub_html = f'<div class="sc-sub-grid">{sub_tags}</div>'

            if m.get("division_key"):
                rows = [
                    ("人気ランキング部門", f"{e(m['region_label'])}（今月 {m['rank_position']}位 / {m['strip_points']:,} pt）"),
                    ("配信スタイル / 言語", f"{e(m['cast_style'])}（対応言語: {e(m['languages_str'])}）"),
                ]
            else:
                rows = [
                    ("活動国・言語", f"{e(m['region_label'])}（対応言語: {e(m['languages_str'])}）"),
                ]
            rows.extend([
                ("年齢 / スタイル", f"{m['age']}歳 / {e(m['body_type'])}" if m.get("age") else e(m["body_type"])),
                ("髪色・瞳", f"{e(m['hair_color'])} / {e(m['eye_color'])}"),
                ("公開アーカイブ規模", f"写真 {m['photos_count']}点 / 動画 {m['videos_count']}本"),
            ])
            if m["interests"]:
                rows.append(("趣味・特徴", e("、".join(m["interests"]))))

            sns_links = m.get("sns_links") or []
            direct_sns = [s for s in sns_links if s.get("is_direct")]
            if direct_sns:
                sns_row_val = " / ".join(
                    f'<a href="{e(s["url"])}" target="_blank" rel="nofollow noopener">{e(s["label"])}</a>'
                    for s in direct_sns
                )
            elif sns_links:
                s0 = sns_links[0]
                sns_row_val = f'<a href="{e(s0["url"])}" target="_blank" rel="nofollow noopener">{e(s0["label"])}</a>'
            else:
                sns_row_val = "—"
            rows.append(("公式SNS / 関連リンク", sns_row_val))
            table_rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)

            sns_box_html = ""
            if sns_links:
                sns_btns = "".join(
                    f'<a href="{e(s["url"])}" class="sc-sns-btn" style="background:{s["bg"]};" '
                    f'target="_blank" rel="nofollow noopener">{e(s["label"])}</a>'
                    for s in sns_links
                )
                sns_box_html = (
                    '<div class="sc-sns-box">'
                    '<div class="sc-sns-title">🔗 公式SNS・関連リンク</div>'
                    f'<div class="sc-sns-list">{sns_btns}</div>'
                    '</div>'
                )

            archive_items = []
            for v in m["videos"]:
                d_label = f"（{v['date']}）" if v.get("date") else ""
                archive_items.append(f"<li>🎬 <strong>公式動画アーカイブ:</strong> 『{e(v['title'])}』{e(d_label)}</li>")
            for tw in m["sns_tweets"]:
                archive_items.append(
                    f'<li>𝕏 <strong>SNS照合 (@{e(tw["screen_name"])}):</strong> '
                    f'<a href="{e(tw["url"])}" target="_blank" rel="nofollow noopener">{e(tw["text"])}</a>（♥ {tw["likes"]:,}）</li>'
                )
            if not archive_items and m.get("topic"):
                archive_items.append(f"<li>💬 <strong>配信トピック:</strong> {e(m['topic'])}</li>")

            archive_html = ""
            if archive_items:
                archive_html = (
                    '<div class="sc-archive-box">'
                    '<strong>🗂️ 公式アーカイブ＆SNS照合データ</strong>'
                    f'<ul>{"".join(archive_items)}</ul>'
                    '</div>'
                )

            rank_badge = f" ｜ 今月 {m['rank_position']}位" if m.get("rank_position") else ""
            cards.append(f"""
  <div class="sc-card" id="sc-{idx}">
    <div class="sc-card-head">
      <span class="sc-num">#{idx}</span>
      <span class="sc-country" style="background:{m['badge_bg']};">{e(m['region_label'])}{e(rank_badge)}</span>
      <span class="sc-name">{e(m['username'])}</span>
      <span class="sc-fav">♥ 登録 {m['favorited_count']:,}人</span>
    </div>
    <div class="sc-main-img">
      <a href="{e(m['profile_url'])}" target="_blank" rel="nofollow noopener">
        <img src="{e(main_img)}" alt="{e(m['username'])}">
      </a>
    </div>
    {sub_html}
    <table class="sc-table">{table_rows}</table>
    <div class="sc-comment">{self._build_commentary(m)}</div>
    {archive_html}
    {sns_box_html}
    <a href="{e(m['profile_url'])}" class="sc-btn" target="_blank" rel="nofollow noopener">
      ✨ 「{e(m['username'])}」の公式プロフィール＆公開アルバムを確認する ＞
    </a>
  </div>""")

        monetize_html = f"""
  <div class="sc-monetize">
    <h3 style="margin:0 0 8px;color:#92400e;font-size:18px;">{e(monetize_title)}</h3>
    <p style="margin:0 0 10px;font-size:13px;color:#78350f;">話題のデジタル写真集やKindle Unlimited読み放題・おすすめサービスはこちらからご覧いただけます。</p>
    <div class="sc-monetize-grid">
      <a href="{e(amz_photo)}" target="_blank" rel="nofollow noopener" style="background:linear-gradient(135deg,#f59e0b,#d97706);">📦 Amazonで人気の写真集・関連作品を見る</a>
      <a href="{e(kindle_url)}" target="_blank" rel="nofollow noopener" style="background:linear-gradient(135deg,#2563eb,#1d4ed8);">📚 Kindle Unlimited（30日間無料）で読み放題</a>
      <a href="{e(amz_sub)}" target="_blank" rel="nofollow noopener" style="background:linear-gradient(135deg,#059669,#047857);">🎁 グラビア最新トレンド・関連雑誌を見る</a>
    </div>
    {A8_BANNERS_HTML}
  </div>"""

        full_html = f"""{style}
<div class="sc-wrap">
  <div class="sc-hero">
    <span class="sc-badge-top">{badge_top}</span>
    <h1>{e(title)}</h1>
    <div style="font-size:12.5px;opacity:0.85;margin-bottom:12px;">{e(sub_meta)}</div>
    <div class="sc-intro">{e(intro)}</div>
  </div>
  <div class="sc-toc">
    <div class="sc-toc-title">{e(toc_title)}</div>
    <ul class="sc-toc-list">{toc_html}</ul>
  </div>
  {"".join(cards)}
  {monetize_html}
  <div class="sc-footer">
    <p style="margin:0 0 6px;"><strong>{e(footer_title)}</strong></p>
    <p style="margin:0;">※掲載データは記事作成時点（{date_str}）の公開プロフィール・公式人気ランキング・公開アーカイブ情報に基づいています。最新の配信予定やアルバム詳細は各公式ページにてご確認ください。</p>
  </div>
</div>"""

        return title, full_html, CATEGORY, tags

    # ------------------------------------------------------------------ 実行・投稿・通知
    def _collect_from_pool(self, group_keys, candidate_pool, target_count, per_group_goal, require_asian, history, dry_run):
        """候補プールから各グループの目標人数分だけ詳細照合・画像アップロードを行って抽出する"""
        labels = TOP_DIVISIONS if not require_asian else COUNTRY_META
        enriched_by_group = {gk: [] for gk in group_keys}

        for gk in group_keys:
            for c in candidate_pool.get(gk, []):
                if len(enriched_by_group[gk]) >= per_group_goal:
                    break
                print(f"--- 照合中 [{labels[gk]['label']}]: {c['username']} ({c['source_label']})")
                info, reason = self.enrich_model(c, require_asian=require_asian)
                if info:
                    enriched_by_group[gk].append(info)
                    print(f"    ✔ 採用 ({gk.upper()} {len(enriched_by_group[gk])}/{per_group_goal}): {info['username']} [画像{len(info['images'])}枚 / 動画{len(info['videos'])}件]")
                else:
                    print(f"    × スキップ: {c['username']} ({reason})")
                    if not dry_run:
                        history.setdefault("skipped_usernames", {})[c["username"]] = reason

        all_enriched = []
        used_names = set()
        for i in range(per_group_goal):
            for gk in group_keys:
                if i < len(enriched_by_group[gk]):
                    m = enriched_by_group[gk][i]
                    all_enriched.append(m)
                    used_names.add(m["username"].lower())

        if len(all_enriched) < target_count:
            leftovers = []
            max_rem = max((len(v) for v in candidate_pool.values()), default=0)
            for i in range(max_rem):
                for gk in group_keys:
                    if i < len(candidate_pool.get(gk, [])):
                        c = candidate_pool[gk][i]
                        if c["username"].lower() not in used_names:
                            leftovers.append(c)
            for c in leftovers:
                if len(all_enriched) >= target_count:
                    break
                gk = c["region_key"]
                print(f"--- 補充照合 [{labels[gk]['label']}]: {c['username']}")
                info, reason = self.enrich_model(c, require_asian=require_asian)
                if info:
                    all_enriched.append(info)
                    used_names.add(info["username"].lower())
                    print(f"    ✔ 補充採用 ({len(all_enriched)}/{target_count}): {info['username']}")
                elif not dry_run:
                    history.setdefault("skipped_usernames", {})[c["username"]] = reason
        return all_enriched

    def _publish_curation_article(self, models, history, vol, mode="asian", division="all", next_division_idx=None, dry_run=False):
        """HTML生成・プレビュー保存または本番投稿・履歴保存・ntfy通知を行う"""
        title, html_content, category, tags = self.generate_curation_html(models, vol=vol, mode=mode, division=division)

        if dry_run:
            prefix = "stripchat_top" if mode == "top" else "stripchat"
            preview_path = os.path.join(BASE_DIR, "scratch", f"{prefix}_vol{vol}_preview.html")
            os.makedirs(os.path.dirname(preview_path), exist_ok=True)
            with open(preview_path, "w", encoding="utf-8") as f:
                f.write(f"<html><head><meta charset='utf-8'><title>{html.escape(title)}</title></head><body>{html_content}</body></html>")
            print(f"[DRY-RUN] タイトル: {title}")
            print(f"[DRY-RUN] プレビュー保存: {preview_path}")
            return True

        res_xml = self.livedoor.post_article(title, html_content, categories=[category] + tags, publish=True)
        if not res_xml:
            print("[エラー] ライブドアブログへの記事投稿に失敗しました。")
            return False

        article_url = "https://bijozukan.doorblog.jp/"
        try:
            root = ET.fromstring(res_xml)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            alt_links = [l.attrib.get("href") for l in root.findall("atom:link", ns) if l.attrib.get("rel") == "alternate"]
            if alt_links:
                article_url = alt_links[0]
        except Exception:
            pass

        usernames_posted = [m["username"] for m in models]
        vol_key = "current_top_vol" if mode == "top" else "current_vol"
        history[vol_key] = vol + 1
        if next_division_idx is not None:
            history["top_division_idx"] = next_division_idx
        history.setdefault("posted_usernames", []).extend(usernames_posted)
        history.setdefault("posted_articles", []).append({
            "mode": mode,
            "division": division,
            "vol": vol,
            "title": title,
            "url": article_url,
            "count": len(models),
            "usernames": usernames_posted,
            "posted_at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        self.save_history(history)
        print(f"🎉 [SUCCESS] まとめ記事 Vol.{vol} 公開完了: {article_url}")

        hero_img = models[0]["images"][0]
        try:
            hashtags = (
                ["美女図鑑", "Stripchat", "人気キャスト", "ライブ配信"]
                if mode == "top"
                else ["美女図鑑", "アジア美女", "ライブ配信", "美人まとめ"]
            )
            ArticleNotifier().send_notification_email(
                title=title,
                article_url=article_url,
                category=category,
                blog_title="美女図鑑",
                hashtags=hashtags,
                image_url=hero_img,
            )
        except Exception as e:
            print(f"[通知送信エラー] {e}")

        return True

    def run_curation_post(self, count=6, dry_run=False):
        """日本人・中国人・韓国人のまとめ記事を1本作成し、投稿とntfy通知を行う"""
        history = self.load_history()
        vol = int(history.get("current_vol", 1))
        group_keys = ("jp", "cn", "kr")
        region_pool = self.fetch_asian_candidates_by_region(per_region=max(6, (count // 3) + 4))
        per_region_goal = max(1, count // 3)

        all_enriched = self._collect_from_pool(
            group_keys, region_pool, count, per_region_goal, require_asian=True, history=history, dry_run=dry_run
        )
        if len(all_enriched) < 3:
            print(f"[エラー] 記事化可能な候補が不足しています ({len(all_enriched)}名)")
            if not dry_run:
                self.save_history(history)
            return False

        return self._publish_curation_article(all_enriched, history, vol=vol, mode="asian", division="asian", dry_run=dry_run)

    def run_top_cast_post(self, count=6, division="all", dry_run=False):
        """人気キャスト（女性5部門＋カップル）を元ネタにしたまとめ記事を1本作成・投稿する"""
        history = self.load_history()
        vol = int(history.get("current_top_vol", 1))
        next_idx = None

        if division == "rotate":
            idx = int(history.get("top_division_idx", 0)) % len(TOP_DIVISION_ORDER)
            target_division = TOP_DIVISION_ORDER[idx]
            next_idx = (idx + 1) % len(TOP_DIVISION_ORDER)
            group_keys = [target_division]
            per_group_goal = count
        elif division in TOP_DIVISIONS:
            target_division = division
            group_keys = [division]
            per_group_goal = count
        else:
            target_division = "all"
            group_keys = list(TOP_DIVISION_ORDER)
            per_group_goal = max(1, count // len(group_keys))

        cand_pool = self.fetch_top_cast_candidates(group_keys, per_division=max(30, per_group_goal * 4))
        all_enriched = self._collect_from_pool(
            group_keys, cand_pool, count, per_group_goal, require_asian=False, history=history, dry_run=dry_run
        )
        if len(all_enriched) < 3:
            print(f"[エラー] 人気キャスト候補が不足しています ({len(all_enriched)}組)")
            if not dry_run:
                self.save_history(history)
            return False

        return self._publish_curation_article(
            all_enriched,
            history,
            vol=vol,
            mode="top",
            division=target_division,
            next_division_idx=next_idx,
            dry_run=dry_run,
        )

    def refresh_published_articles(self):
        """stripchat_history.json にある公開済み記事を最新データ・動画埋め込みHTMLで上書き更新する"""
        history = self.load_history()
        articles = history.get("posted_articles") or []
        if not articles:
            print("[更新対象なし] posted_articles が空です。")
            return False

        top_rank_map = {}
        if any((a.get("mode") == "top") for a in articles):
            for dk in TOP_DIVISION_ORDER:
                for c in self._pick_top_division_candidates(dk, set(), set(), target=50):
                    top_rank_map[c["username"].lower()] = c

        all_ok = True
        for art in articles:
            url = art.get("url", "")
            m_id = re.search(r"/archives/(\d+)\.html", url)
            if not m_id:
                print(f"[スキップ] 記事IDを特定できません: {url}")
                continue
            article_id = m_id.group(1)
            mode = art.get("mode") or "asian"
            division = art.get("division") or ("asian" if mode == "asian" else "all")
            vol = int(art.get("vol", 1))
            usernames = art.get("usernames") or []
            print(f"=== 記事更新再照合中: ID={article_id} ({mode} Vol.{vol}) ===")

            refreshed_models = []
            for idx, uname in enumerate(usernames):
                if mode == "top":
                    fallback_dk = division if division in TOP_DIVISIONS else TOP_DIVISION_ORDER[idx % len(TOP_DIVISION_ORDER)]
                    cand = top_rank_map.get(uname.lower()) or {
                        "username": uname,
                        "region_key": fallback_dk,
                        "division_key": fallback_dk,
                        "country": "",
                        "rank_position": 1,
                        "strip_points": 0,
                        "source_label": TOP_DIVISIONS[fallback_dk]["short"],
                    }
                    info, reason = self.enrich_model(cand, require_asian=False)
                else:
                    rk = ("jp", "cn", "kr")[idx % 3]
                    cand = {"username": uname, "region_key": rk, "country": "", "source_label": "アーカイブ再照合"}
                    info, reason = self.enrich_model(cand, require_asian=True)

                if info:
                    print(f"    ✔ 更新データ準備完了: {uname} [画像{len(info['images'])}枚 / 動画{len(info['videos'])}件]")
                    refreshed_models.append(info)
                else:
                    print(f"    ⚠ 取得スキップ: {uname} ({reason})")

            if len(refreshed_models) < 3:
                print(f"[エラー] ID={article_id} の再取得モデル数が不足しています ({len(refreshed_models)})")
                all_ok = False
                continue

            title, html_content, category, tags = self.generate_curation_html(
                refreshed_models, vol=vol, mode=mode, division=division
            )
            res = self.livedoor.update_article(
                article_id, title, html_content, categories=[category] + tags, publish=True
            )
            if not res:
                all_ok = False

        return all_ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stripchat まとめ記事自動投稿エンジン（人気キャスト女性5部門＋カップル / 日中韓）")
    ap.add_argument("--count", type=int, default=6, help="まとめ記事の掲載組数 (デフォルト: 6)")
    ap.add_argument("--mode", choices=["top", "asian", "top-rotate"], default="top", help="記事モード: top(人気キャスト5部門+カップル), top-rotate(部門別ローテ), asian(日中韓)")
    ap.add_argument("--division", choices=["all", "as", "na", "sa", "eu", "af", "couples", "rotate"], default="all", help="topモード時の対象部門")
    ap.add_argument("--refresh-published", action="store_true", help="公開済みVol.1記事を動画埋め込み版HTMLで上書き更新")
    ap.add_argument("--dry-run", action="store_true", help="投稿せず scratch/ にプレビューHTMLを保存")
    ap.add_argument("--blog-id", type=str, default=DEFAULT_BLOG_ID, help="対象ブログID")
    args = ap.parse_args()

    engine = StripchatCurationEngine(blog_id=args.blog_id)
    if args.refresh_published:
        ok = engine.refresh_published_articles()
    elif args.mode == "asian":
        ok = engine.run_curation_post(count=args.count, dry_run=args.dry_run)
    elif args.mode == "top-rotate":
        ok = engine.run_top_cast_post(count=args.count, division="rotate", dry_run=args.dry_run)
    else:
        ok = engine.run_top_cast_post(count=args.count, division=args.division, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)

"""
美女図鑑（bijozukan.doorblog.jp）個別プロフィール記事 自動生成エンジン

情報源:
  - 人選び・作品・画像 : DMM.com API（一般向け 写真集フロア ebook/photo）※出演者IDで完全一致
  - プロフィール       : Wikipedia（インフォボックス・冒頭要約）
  - 公式SNS            : Wikidata（X / Instagram / TikTok / YouTube）
  - 最近の話題         : Google ニュース RSS（見出しとリンクのみ）
  - 本文               : Gemini（上記で集めた事実のみを材料に執筆）

使い方:
  python bijozukan_profile_engine.py                # 自動で1人選んで投稿
  python bijozukan_profile_engine.py --dry-run      # 投稿せず scratch/ にHTMLプレビューを保存
  python bijozukan_profile_engine.py --name 菊地姫奈 --dry-run
"""
import os
import re
import sys
import json
import html
import random
import datetime
import argparse
import urllib.parse
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from dmm_client import DMMClient
from wiki_client import WikiClient
from curation_engine import sanitize_text

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "bijozukan_history.json")
DEFAULT_BLOG_ID = "ranking000-w6crxelo"
CATEGORY = "美女図鑑"
MIN_IMAGE_BYTES = 10_000
UA = {"User-Agent": "Mozilla/5.0 (BijozukanBot/1.0)"}

# 美女図鑑はライブドアの一般ブログのため、過激なタイトルの作品は掲載しない
EXCLUDE_TITLE_WORDS = ["ヌード", "ヌレ", "セミヌード", "手ブラ", "限界", "R-18", "R18", "官能", "濡れ"]


def strip_decorations(name):
    """絵文字・イベント告知などを除去した表示名を返す"""
    if not name:
        return ""
    n = re.sub(r"[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200D]", "", name)
    n = re.sub(r"[【\[（(].*?[】\]）)]", "", n)
    n = re.sub(r"\s*[|｜/／▶►].*$", "", n)
    n = re.sub(r"\d{1,2}/\d{1,2}.*$", "", n)
    n = re.sub(r"(撮影会|生誕祭|ワンマン|コミケ|池ハロ|ラグコス|写真集発売|fantia|ファンクラブ).*$", "", n, flags=re.I)
    return n.strip(" *・♡♥")


class BijozukanProfileEngine:
    def __init__(self, blog_id=DEFAULT_BLOG_ID):
        self.livedoor_id = os.getenv("LIVEDOOR_ID")
        self.api_key = os.getenv("LIVEDOOR_API_KEY")
        self.blog_id = blog_id
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.dmm = DMMClient()
        self.wiki = WikiClient()
        # 美女図鑑用アフィリエイトID（未設定なら DMM_AFFILIATE_ID の末尾を -993 に置換）
        base_af = os.getenv("DMM_AFFILIATE_ID", "")
        self.affiliate_id = os.getenv("BIJOZUKAN_AFFILIATE_ID") or (re.sub(r"-\d{3}$", "-993", base_af) if base_af else None)
        self.history = self.load_history()

    # ------------------------------------------------------------------ 履歴
    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[履歴読み込みエラー] {e}")
        return {"profiles": [], "skipped": {}}

    def save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def posted_names(self):
        return {p["name"] for p in self.history.get("profiles", [])}

    # ------------------------------------------------------------------ 画像
    def fetch_image(self, url):
        """画像をダウンロードし、十分なサイズがあれば (bytes, content_type) を返す"""
        if not url:
            return None
        try:
            r = requests.get(url, headers=UA, timeout=15)
            ct = r.headers.get("Content-Type", "")
            if r.status_code == 200 and ct.startswith("image/") and len(r.content) >= MIN_IMAGE_BYTES:
                return r.content, ct.split(";")[0]
        except Exception as e:
            print(f"[画像取得エラー] {url}: {e}")
        return None

    def upload_image(self, url):
        """画像をライブドアの画像サーバーへ保存して URL を返す（失敗時 None）"""
        got = self.fetch_image(url)
        if not got:
            return None
        data, ct = got
        try:
            resp = requests.post(
                f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/image",
                auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
                data=data, headers={"Content-Type": ct}, timeout=30,
            )
            if resp.status_code in (200, 201):
                root = ET.fromstring(resp.text)
                for elem in root.iter():
                    if elem.tag.endswith("content") and "src" in elem.attrib:
                        return elem.attrib["src"]
            print(f"[画像アップロード失敗] HTTP {resp.status_code}")
        except Exception as e:
            print(f"[画像アップロードエラー] {e}")
        return None

    # ------------------------------------------------------------------ 人選び
    def _is_clean_title(self, title):
        return not any(w in title for w in EXCLUDE_TITLE_WORDS)

    def discover_candidates(self, limit=60, source_type="all"):
        """DMM.com 写真集と FANZA 女優ランキングから出演者候補を集める"""
        seen, candidates = set(), []
        posted = self.posted_names()
        skipped = self.history.get("skipped", {})
        dmm_list, fanza_list, bigirl_list, indie_list = [], [], [], []
        if source_type in ("all", "bigirl"):
            bigirl_list = self.load_bigirl_feed()
            if source_type == "bigirl":
                return bigirl_list[:limit]
        if source_type in ("all", "indie"):
            indie_list = self.discover_indie_accounts()
            if source_type == "indie":
                return indie_list[:limit]
        if source_type in ("all", "gravure"):
            new_items = self.dmm.get_dmm_items(sort="date", hits=60, affiliate_id=self.affiliate_id)
            rank_items = self.dmm.get_dmm_items(sort="rank", hits=60, affiliate_id=self.affiliate_id)
            for a, b in zip(new_items + [None] * len(rank_items), rank_items + [None] * len(new_items)):
                if a: dmm_list.append(("写真集・新着", "gravure", a, "actor"))
                if b: dmm_list.append(("写真集・人気", "gravure", b, "actor"))
        if source_type in ("all", "av"):
            f_rank = self.dmm.get_top_fanza_works(hits=60, sort="rank", affiliate_id=self.affiliate_id)
            f_date = self.dmm.get_top_fanza_works(hits=60, sort="date", affiliate_id=self.affiliate_id)
            for a, b in zip(f_rank + [None] * len(f_date), f_date + [None] * len(f_rank)):
                if a: fanza_list.append(("AV・人気", "av", a, "actress"))
                if b: fanza_list.append(("AV・新着", "av", b, "actress"))
        merged = []
        for i in range(max(len(dmm_list), len(fanza_list), 1)):
            if i < len(dmm_list): merged.append(dmm_list[i])
            if i < len(fanza_list): merged.append(fanza_list[i])
        # 4つのプール（①グラビア写真集 ②AV女優 ③国内外SNS美女 ④bi-girl）を作り、前回の投稿ジャンルと被らないようローテーションする
        gravure_pool, av_pool = [], []
        for source, kind, it, key in merged:
            actors = it.get("iteminfo", {}).get(key, [])
            if len(actors) != 1 or (kind == "gravure" and not self._is_clean_title(it.get("title", ""))):
                continue
            actor = actors[0]
            name = strip_decorations(actor.get("name", ""))
            if not name or name == "----" or name in seen or name in posted or name in skipped:
                continue
            seen.add(name)
            entry = {"name": name, "actor_id": actor.get("id"), "source": source, "kind": kind}
            (gravure_pool if kind == "gravure" else av_pool).append(entry)

        indie_pool = [ind for ind in indie_list if ind["name"] not in seen and not seen.add(ind["name"])]
        bigirl_pool = [b for b in bigirl_list if b["name"] not in seen and not seen.add(b["name"])]

        pools = [("gravure", gravure_pool), ("av", av_pool), ("indie", indie_pool), ("bigirl", bigirl_pool)]
        last_kind = (self.history.get("profiles") or [{}])[-1].get("pool") or (self.history.get("profiles") or [{}])[-1].get("kind")
        order_keys = [k for k, _ in pools]
        if last_kind in order_keys:
            idx = (order_keys.index(last_kind) + 1) % len(pools)
            pools = pools[idx:] + pools[:idx]

        max_pool = max((len(p) for _, p in pools), default=0)
        for i in range(max_pool):
            for pool_name, p in pools:
                if i < len(p):
                    item = dict(p[i])
                    item["pool"] = pool_name
                    candidates.append(item)
                    if len(candidates) >= limit:
                        break
            if len(candidates) >= limit:
                break
        print(f"候補 {len(candidates)} 人（4ジャンル均等ローテーション / 掲載済み {len(posted)} 人・除外 {len(skipped)} 人を除く）")
        return candidates

    def find_actor(self, name, source_type="all", x_id=None, categories=None):
        """名前から DMM.com または FANZA の出演者を【完全一致】で探す"""
        if source_type in ("all", "av"):
            for a in self.dmm.search_actress(name=name):
                raw = a.get("name", "")
                aliases = [x.strip() for x in re.split(r"[（()）]", raw) if x.strip()]
                if name in aliases:
                    return {"name": name, "actor_id": a["id"], "source": "FANZA", "kind": "av", "x_id": x_id, "categories": categories or []}
        if source_type in ("all", "gravure"):
            for it in self.dmm.get_dmm_items(sort="rank", hits=30, keyword=name, affiliate_id=self.affiliate_id):
                for a in it.get("iteminfo", {}).get("actor", []):
                    if strip_decorations(a.get("name", "")) == name:
                        return {"name": name, "actor_id": a.get("id"), "source": "DMM", "kind": "gravure", "x_id": x_id, "categories": categories or []}
        if source_type in ("all", "indie") and not x_id:
            for e in self.search_yahoo_tweets(f"id:{name}", popular=False) or self.search_yahoo_tweets(name, popular=True):
                sx = e.get("screenName", "")
                if sx:
                    return {"name": strip_decorations(e.get("name", "")) or name, "actor_id": sx, "source": "SNS指定", "kind": "indie", "x_id": sx, "categories": []}
        return None

    def load_bigirl_feed(self, feed_path=None):
        """scratch/bigirl_feed.xml（または bigirl_feed.xml）から候補（名前・X ID・カテゴリ）を抽出する"""
        paths = [feed_path] if feed_path else [
            os.path.join(BASE_DIR, "scratch", "bigirl_feed.xml"),
            os.path.join(BASE_DIR, "bigirl_feed.xml"),
        ]
        xml_text = ""
        for p in paths:
            if p and os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    xml_text = f.read()
                break
        if not xml_text:
            return []
        posted = self.posted_names()
        skipped = self.history.get("skipped", {})
        out = []
        items = re.findall(r"<item>\s*<title>(.*?)</title>\s*<link>https?://bi-girl\.net/([^<]+)</link>(.*?)</item>", xml_text, re.S)
        for raw_title, slug, body in items:
            head = re.sub(r"[（(♡].*", "", raw_title).strip()
            parts = re.split(r"\s+", head)
            name = f"{parts[0]} {parts[1]}" if len(parts) >= 2 and re.fullmatch(r"[A-Za-z]+", parts[0]) and re.fullmatch(r"[A-Za-z]+", parts[1]) else parts[0]
            if not name or len(name) < 2 or name in posted or name in skipped:
                continue
            cats = re.findall(r"<category><!\[CDATA\[(.*?)\]\]></category>", body)
            if "裏垢" in cats:
                continue
            pref_type = "av" if "AV女優" in cats else ("gravure" if "グラドル" in cats else "all")
            matched = self.find_actor(name, source_type=pref_type, x_id=slug.strip("/"), categories=cats)
            if not matched and pref_type != "all":
                matched = self.find_actor(name, source_type="all", x_id=slug.strip("/"), categories=cats)
            if matched:
                matched["source"] = f"bi-girl({matched['source']})"
                out.append(matched)
            elif slug:
                # DMM/FANZA に作品がない非商業アカウント（ちゆう、立花繭子、小空Sora、Umeko J、Lindsey Pelas 等）も SNS ルートで候補に追加
                out.append({
                    "name": name,
                    "actor_id": slug.strip("/"),
                    "source": "bi-girl(SNS)",
                    "kind": "indie",
                    "x_id": slug.strip("/"),
                    "categories": cats,
                    "fallback_title": raw_title,
                })
        print(f"[bi-girl RSS] {len(out)} 人の候補を検出（商業＋非商業SNS）")
        return out

    def search_yahoo_tweets(self, query, popular=False):
        """Yahoo!リアルタイム検索から画像付きポスト一覧を取得する"""
        params = {"p": query, "ei": "UTF-8", "mtype": "image"}
        if popular:
            params["md"] = "h"
        try:
            r = requests.get("https://search.yahoo.co.jp/realtime/search", params=params, headers=UA, timeout=12)
            m = re.search(r"__NEXT_DATA__[^>]*>(.*?)</script>", r.text)
            if not m:
                return []
            d = json.loads(m.group(1))
            return d.get("props", {}).get("pageProps", {}).get("pageData", {}).get("timeline", {}).get("entry", [])
        except Exception as e:
            print(f"[Yahooリアルタイム検索エラー] {query}: {e}")
            return []

    def discover_indie_accounts(self, min_likes=200):
        """非商業の国内外コスプレイヤー・グラビア・SNS美女アカウントを人気順で自動発掘する"""
        posted = self.posted_names()
        skipped = self.history.get("skipped", {})
        bad_words = ("AI", "生成", "観察", "まとめ", "相互", "裏垢", "公式", "bot", "Bot", "ニュース", "情報", "bts", "jungkook", "kpop", "army", "⁷")
        queries = [
            ("#コスプレイヤーさんと繋がりたい", ["コスプレイヤー"]),
            ("#グラドル自画撮り部", ["グラビア・自撮り"]),
            ("#撮影会モデル", ["撮影会モデル"]),
            ("#ポートレートモデル", ["ポートレート美女"]),
            ("#被写体モデル", ["被写体モデル"]),
        ]
        found, seen_ids = [], set()
        for q, cats in queries:
            for e in self.search_yahoo_tweets(q, popular=True):
                likes = e.get("likesCount", 0)
                x_id = e.get("screenName", "")
                raw_name = e.get("name", "")
                if likes < min_likes or not x_id or x_id in seen_ids:
                    continue
                if any(bw in raw_name or bw in e.get("displayTextBody", "") for bw in bad_words):
                    continue
                name = strip_decorations(raw_name) or x_id
                if len(name) < 2 or name in posted or name in skipped or f"@{x_id}" in posted:
                    continue
                seen_ids.add(x_id)
                found.append({
                    "name": name,
                    "actor_id": x_id,
                    "source": f"SNS話題(♥{likes})",
                    "kind": "indie",
                    "x_id": x_id,
                    "categories": cats,
                })
        found.sort(key=lambda c: int(re.search(r"\d+", c["source"]).group(0)) if re.search(r"\d+", c["source"]) else 0, reverse=True)
        print(f"[非商業SNS発掘] {len(found)} アカウントを検出")
        return found

    def collect_indie_works(self, x_id, name="", max_works=6):
        """特定Xアカウント（id:xxx）の直近の人気画像ポストを収集して作品カード形式にする"""
        entries = self.search_yahoo_tweets(f"id:{x_id}", popular=False)
        if not entries:
            entries = self.search_yahoo_tweets(f"@{x_id}", popular=False)
        # いいね数順にソート
        entries.sort(key=lambda e: e.get("likesCount", 0), reverse=True)
        works, seen_urls = [], set()
        all_hashtags = []
        display_name = name
        for e in entries:
            if e.get("screenName", "").lower() == x_id.lower() and e.get("name"):
                cleaned = strip_decorations(e["name"])
                if cleaned:
                    display_name = cleaned
            for h in e.get("hashtags", []):
                ht = h.get("text", "")
                if ht and ht not in all_hashtags:
                    all_hashtags.append(ht)
            for m in e.get("media", []):
                img_url = m.get("item", {}).get("mediaUrl") or m.get("metaImageUrl") or ""
                if not img_url or img_url in seen_urls:
                    continue
                seen_urls.add(img_url)
                body = re.sub(r"https?://\S+", "", e.get("displayTextBody", "")).strip()
                body = sanitize_text(re.sub(r"\s+", " ", body))
                ts = e.get("createdAt")
                date_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
                likes = e.get("likesCount", 0)
                rts = e.get("rtCount", 0)
                tweet_url = re.sub(r"\?.*$", "", e.get("url", f"https://x.com/{x_id}"))
                works.append({
                    "title": (body[:36] + "…") if len(body) > 36 else (body or f"{display_name}の注目ポスト"),
                    "date": date_str,
                    "publisher": f"X (@{x_id})",
                    "photographer": f"♥ {likes:,} いいね" + (f" / 🔁 {rts:,} RT" if rts else ""),
                    "genres": all_hashtags[:4],
                    "price": "",
                    "review_avg": None,
                    "review_count": None,
                    "image": img_url,
                    "url": tweet_url,
                })
                break
            if len(works) >= max_works:
                break
        return works, len(entries), all_hashtags[:6], display_name

    def discover_candidates_legacy(self, limit=60):
        """DMM.com 写真集の新着・ランキングから出演者候補を集める"""
        seen, candidates = set(), []
        posted = self.posted_names()
        skipped = self.history.get("skipped", {})
        new_items = self.dmm.get_dmm_items(sort="date", hits=100, affiliate_id=self.affiliate_id)
        rank_items = self.dmm.get_dmm_items(sort="rank", hits=100, affiliate_id=self.affiliate_id)
        # 新着とランキングを交互に並べる
        merged = []
        for a, b in zip(new_items + [None] * len(rank_items), rank_items + [None] * len(new_items)):
            if a: merged.append(("新着", a))
            if b: merged.append(("人気", b))
        for source, it in merged:
            actors = it.get("iteminfo", {}).get("actor", [])
            if len(actors) != 1 or not self._is_clean_title(it.get("title", "")):
                continue
            actor = actors[0]
            name = strip_decorations(actor.get("name", ""))
            if not name or name == "----" or name in seen or name in posted or name in skipped:
                continue
            seen.add(name)
            candidates.append({"name": name, "actor_id": actor.get("id"), "source": source})
            if len(candidates) >= limit:
                break
        print(f"候補 {len(candidates)} 人（掲載済み {len(posted)} 人・除外 {len(skipped)} 人を除く）")
        return candidates

    def find_actor_id(self, name):
        """名前から DMM.com の出演者IDを探す（--name 指定時用）"""
        items = self.dmm.get_dmm_items(sort="rank", hits=30, keyword=name, affiliate_id=self.affiliate_id)
        for it in items:
            for a in it.get("iteminfo", {}).get("actor", []):
                if strip_decorations(a.get("name", "")) == name:
                    return a.get("id")
        return None

    # ------------------------------------------------------------------ 情報収集
    def collect_works(self, actor_id, max_works=6, name=""):
        # name は作品タイトルの重複判定に使用
        items = self.dmm.get_dmm_items(article="actor", article_id=actor_id, sort="date", hits=40, affiliate_id=self.affiliate_id)
        works, titles = [], set()
        costars = {}
        for it in items:
            title = sanitize_text(it.get("title", ""))
            if not self._is_clean_title(title):
                continue
            # 同一作品の別版（vol違い・特別版）は1つにまとめる
            key = re.sub(r"(vol\.?|特別版|豪華版|増量版?|【[^】]*】|[\s\d『』「」]|ページ超?)", "", title.replace(name, ""), flags=re.I)[:7]
            for a in it.get("iteminfo", {}).get("actor", []):
                if a.get("id") != actor_id:
                    costars[strip_decorations(a["name"])] = a.get("id")
            if key in titles:
                continue
            titles.add(key)
            review = it.get("review") or {}
            works.append({
                "title": title,
                "date": (it.get("date") or "")[:10],
                "publisher": (it.get("iteminfo", {}).get("manufacture") or [{}])[0].get("name", ""),
                "photographer": ", ".join(a["name"] for a in it.get("iteminfo", {}).get("author", [])),
                "genres": [g["name"] for g in it.get("iteminfo", {}).get("genre", [])],
                "price": (it.get("prices") or {}).get("price", ""),
                "review_avg": review.get("average"),
                "review_count": review.get("count"),
                "image": (it.get("imageURL") or {}).get("large", ""),
                "url": it.get("affiliateURL") or it.get("URL", ""),
            })
        total = len(items)
        return works[:max_works], total, costars

    def collect_news(self, name, max_items=3):
        """Google ニュース RSS から見出しとリンクのみを取得"""
        try:
            q = urllib.parse.quote(f"\"{name}\"")
            r = requests.get(f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja", headers=UA, timeout=10)
            root = ET.fromstring(r.content)
            news, seen = [], set()
            for item in root.iter("item"):
                title = item.findtext("title", "")
                norm = re.sub(r"[\s（）()]|-[^-]*$", "", title)
                if name not in title or norm in seen:
                    continue
                seen.add(norm)
                pub = item.findtext("pubDate", "")
                try:
                    dt = datetime.datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S")
                    if (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - dt).days > 120:
                        continue
                    pub = dt.strftime("%Y/%m/%d")
                except Exception:
                    pub = ""
                news.append({"title": sanitize_text(title), "url": item.findtext("link", ""), "date": pub})
                if len(news) >= max_items:
                    break
            return news
        except Exception as e:
            print(f"[ニュース取得エラー] {e}")
            return []

    def collect_fanza_works(self, actress_id, max_works=6, name=""):
        """FANZA女優の単体出演作品と公式プロフィール（ActressSearch）を取得する"""
        actress_meta = {}
        found = self.dmm.search_actress(actress_id=actress_id)
        if found:
            a = found[0]
            if a.get("birthday"): actress_meta["生年月日"] = a["birthday"]
            if a.get("prefectures"): actress_meta["出身地"] = a["prefectures"]
            if a.get("blood_type"): actress_meta["血液型"] = f"{a['blood_type']}型"
            if a.get("height"): actress_meta["身長"] = f"{a['height']} cm"
            bwh = [f"{k}{a[v]}" for k, v in (("B", "bust"), ("W", "waist"), ("H", "hip")) if a.get(v)]
            if bwh:
                actress_meta["スリーサイズ"] = " / ".join(bwh) + (f"（{a['cup']}カップ）" if a.get("cup") else "")
            if a.get("hobby"): actress_meta["趣味・特技"] = a["hobby"]
        items = self.dmm.get_actress_works(actress_id, hits=40, floor="videoa", sort="date", affiliate_id=self.affiliate_id)
        if len(items) < 4 and name:
            # 改名女優（例: 坂道みる→miru）はキーワード検索でも補完する
            kw_items = self.dmm.get_top_fanza_works(hits=40, keyword=name, sort="date", affiliate_id=self.affiliate_id)
            seen_cids = {x.get("content_id") for x in items}
            items.extend(x for x in kw_items if x.get("content_id") not in seen_cids)
        works, titles, costars = [], set(), {}
        for it in items:
            actresses = it.get("iteminfo", {}).get("actress", [])
            for ac in actresses:
                if str(ac.get("id")) != str(actress_id):
                    costars[strip_decorations(ac["name"])] = ac.get("id")
            if len(actresses) > 2 or "ベスト" in it.get("title", "") or "総集編" in it.get("title", ""):
                continue
            title = sanitize_text(it.get("title", ""))
            key = re.sub(r"[\s\d【】『』「」]", "", title.replace(name, ""))[:10]
            if key in titles:
                continue
            titles.add(key)
            review = it.get("review") or {}
            works.append({
                "title": title, "date": (it.get("date") or "")[:10],
                "publisher": (it.get("iteminfo", {}).get("maker") or [{}])[0].get("name", ""),
                "photographer": ", ".join(d["name"] for d in it.get("iteminfo", {}).get("director", [])),
                "genres": [g["name"] for g in it.get("iteminfo", {}).get("genre", [])][:5],
                "price": (it.get("prices") or {}).get("price", ""),
                "review_avg": review.get("average"), "review_count": review.get("count"),
                "image": (it.get("imageURL") or {}).get("large", ""),
                "url": it.get("affiliateURL") or it.get("URL", ""),
            })
        return works[:max_works], len(items), costars, actress_meta

    def verify_is_female_beauty(self, name, works):
        """SNS発掘アカウントの1枚目の画像をGeminiに見せ、実在の女性（美女・グラビア・コスプレイヤー）本人か判定する"""
        if not self.gemini_api_key or not works:
            return False, "Geminiキーまたは画像なし"
        got = self.fetch_image(works[0].get("image", ""))
        if not got:
            return False, "判定用画像の取得失敗"
        img_bytes, mime_type = got
        titles = " / ".join(w.get("title", "") for w in works[:3])
        prompt = (
            f"アカウント名: {name}\n投稿文: {titles}\n"
            "この画像と投稿文を見て、このアカウントが『実在する女性（モデル・グラビア・コスプレイヤー・インフルエンサー等の美女本人）』かどうか判定してください。\n"
            "以下のいずれかに該当する場合は必ず false にしてください:\n"
            "- 男性（男性アイドル、K-POP男性メンバー、男性コスプレイヤー、男性カメラマン等）\n"
            "- 2次元イラスト・アニメ画像・VTuber・AI生成画像・風景・食べ物・文字のみ\n"
            "- 他人の画像を転載しているファンアカウントやまとめアカウント\n"
            'JSON形式 {"is_female_beauty": true または false, "reason": "理由"} のみで回答してください。'
        )
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.model_name)
            resp = model.generate_content([prompt, {"mime_type": mime_type, "data": img_bytes}], request_options={"timeout": 60})
            raw = resp.text.strip()
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                data = json.loads(m.group(0))
                return bool(data.get("is_female_beauty")), data.get("reason", "")
        except Exception as e:
            print(f"[画像女性判定エラー] {e}")
        return False, "AI画像判定失敗"

    def build_profile(self, name, actor_id, kind="gravure", x_id=None, categories=None):
        """1人分の素材を集めて品質チェック。合格なら dict、不合格なら (None, 理由)"""
        fanza_meta = {}
        if kind == "indie":
            works, total_works, hashtags, detected_name = self.collect_indie_works(x_id or actor_id, name=name)
            costars = {}
            if hashtags:
                fanza_meta["よく使うハッシュタグ"] = " / ".join(f"#{h}" for h in hashtags[:5])
            fanza_meta["公式Xアカウント"] = f"@{x_id or actor_id}"
        elif kind == "av":
            works, total_works, costars, fanza_meta = self.collect_fanza_works(actor_id, name=name)
        else:
            works, total_works, costars = self.collect_works(actor_id, name=name)
        valid_works = [w for w in works if self.fetch_image(w["image"])]
        if len(valid_works) < 2:
            return None, f"有効な作品画像が不足 ({len(valid_works)}件)"
        if kind == "indie" and not categories:
            ok_beauty, reason_beauty = self.verify_is_female_beauty(name, valid_works)
            if not ok_beauty:
                return None, f"女性本人判定NG ({reason_beauty})"
        wiki = self.wiki.get_profile(name)
        if not wiki and not fanza_meta and total_works < 4 and kind != "indie":
            return None, "プロフィール情報なし かつ 作品数が少ない"
        if fanza_meta:
            if not wiki:
                wiki = {"title": name, "url": "", "summary": "", "extract": "", "infobox": fanza_meta, "sns": []}
            else:
                for k, v in fanza_meta.items():
                    wiki["infobox"].setdefault(k, v)
        if x_id and wiki:
            if not any(s["service"] == "X" for s in wiki.get("sns", [])):
                wiki.setdefault("sns", []).insert(0, {"service": "X", "id": x_id, "url": f"https://x.com/{x_id}"})
        elif x_id and not wiki:
            wiki = {"title": name, "url": "", "summary": "", "extract": "", "infobox": fanza_meta, "sns": [{"service": "X", "id": x_id, "url": f"https://x.com/{x_id}"}]}
        if categories and wiki:
            clean_cats = [c for c in categories if c not in ("裏垢", "外人", "中国")]
            if clean_cats:
                wiki.setdefault("infobox", {}).setdefault("特徴・系統", "、".join(clean_cats))
        news = self.collect_news(name)
        posted_map = {p["name"]: p for p in self.history.get("profiles", [])}
        related = [posted_map[n] for n in costars if n in posted_map][:4]
        return {
            "name": name, "actor_id": actor_id, "kind": kind,
            "works": valid_works, "total_works": total_works,
            "wiki": wiki, "news": news,
            "costars": [n for n in costars if n and n != "----"][:5],
            "related": related,
        }, None

    def build_profile_legacy(self, name, actor_id):
        """1人分の素材を集めて品質チェック。合格なら dict、不合格なら (None, 理由)"""
        works, total_works, costars = self.collect_works(actor_id, name=name)
        valid_works = [w for w in works if self.fetch_image(w["image"])]
        if len(valid_works) < 2:
            return None, f"有効な作品画像が不足 ({len(valid_works)}件)"
        wiki = self.wiki.get_profile(name)
        if not wiki and total_works < 4:
            return None, "Wikipediaなし かつ 作品数が少ない"
        if x_id and wiki:
            if not any(s["service"] == "X" for s in wiki.get("sns", [])):
                wiki.setdefault("sns", []).insert(0, {"service": "X", "id": x_id, "url": f"https://x.com/{x_id}"})
        elif x_id and not wiki:
            wiki = {"title": name, "url": "", "summary": "", "extract": "", "infobox": fanza_meta, "sns": [{"service": "X", "id": x_id, "url": f"https://x.com/{x_id}"}]}
        if categories and wiki:
            clean_cats = [c for c in categories if c not in ("裏垢", "外人", "中国")]
            if clean_cats:
                wiki.setdefault("infobox", {}).setdefault("特徴・系統", "、".join(clean_cats))
        news = self.collect_news(name)
        posted_map = {p["name"]: p for p in self.history.get("profiles", [])}
        related = [posted_map[n] for n in costars if n in posted_map][:4]
        return {
            "name": name,
            "actor_id": actor_id,
            "works": valid_works,
            "total_works": total_works,
            "wiki": wiki,
            "news": news,
            "costars": [n for n in costars if n and n != "----"][:5],
            "related": related,
        }, None

    # ------------------------------------------------------------------ 本文生成
    def _facts_for_ai(self, p):
        facts = {"名前": p["name"], "DMMでの写真集・デジタル写真集の数": p["total_works"]}
        if p["wiki"]:
            facts["Wikipedia要約"] = p["wiki"]["extract"]
            facts["プロフィール"] = p["wiki"]["infobox"]
        facts["最近の作品"] = [{k: w[k] for k in ("title", "date", "publisher", "photographer", "genres", "review_avg", "review_count")} for w in p["works"]]
        if p["costars"]:
            facts["共演者"] = p["costars"]
        if p["news"]:
            facts["最近のニュース見出し"] = [n["title"] for n in p["news"]]
        return facts

    def generate_text(self, p):
        facts = self._facts_for_ai(p)
        n_works = len(p["works"])
        fallback = self._fallback_text(p)
        if not self.gemini_api_key:
            return fallback
        prompt = f"""あなたは一般向け美女紹介ブログ「美女図鑑」の編集者です。
以下の【事実データ】だけを根拠に、{p['name']}さんを紹介する記事の文章を書いてください。

【厳守ルール】
- 事実データにない経歴・数値・エピソードを創作しない（不明な点には触れない）
- 性的・露骨な表現は禁止。ビジュアル、表情、世界観、経歴、作品の見どころを品よく紹介する
- 同じ言い回しを繰り返さない。具体的な作品名・年・出版社など事実を織り込む
- 出力は次のJSONのみ（```json で囲む）

{{
  "catch": "記事冒頭のキャッチコピー（20文字以内。名前は含めない）",
  "intro": "導入文（200〜260文字）。誰で、どんな活動をしていて、今なぜ注目かを伝える",
  "charms": [
    {{"title": "魅力ポイントの見出し（15文字以内）", "body": "解説（120〜180文字）"}},
    {{"title": "...", "body": "..."}},
    {{"title": "...", "body": "..."}}
  ],
  "career": "経歴・活動の流れ（200〜300文字）。データにない場合は作品のリリース歴から語る",
  "works": ["作品1の見どころ紹介（60〜90文字）", "...（全{n_works}作品分、最近の作品の順番どおり）"],
  "faq": [
    {{"q": "読者が検索しそうな質問", "a": "事実データに基づく回答（40〜100文字）"}},
    {{"q": "...", "a": "..."}},
    {{"q": "...", "a": "..."}}
  ],
  "summary": "まとめ（120〜160文字）"
}}

【事実データ】
{json.dumps(facts, ensure_ascii=False, indent=1)}
"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.model_name)
            raw = model.generate_content(prompt, request_options={"timeout": 180}).text.strip()
            m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
            data = json.loads(m.group(1) if m else raw)
            for k, v in fallback.items():
                if not data.get(k):
                    data[k] = v
            if len(data["works"]) < n_works:
                data["works"] += fallback["works"][len(data["works"]):]
            return data
        except Exception as e:
            print(f"[Gemini生成エラー] {e} → テンプレート文章を使用")
            return fallback

    def _fallback_text(self, p):
        name = p["name"]
        info = (p["wiki"] or {}).get("infobox", {})
        genre = info.get("ジャンル") or "グラビア"
        latest = p["works"][0]
        intro = (p["wiki"] or {}).get("summary") or f"{name}さんは、写真集を中心に活躍する注目の美女です。"
        intro += f" 最新作は{latest['date'][:4]}年発売の『{latest['title']}』。DMMブックスでは{p['total_works']}作品の写真集が配信されています。"
        return {
            "catch": f"{genre}界で輝く{name}",
            "intro": intro,
            "charms": [
                {"title": "作品ごとに変わる表情", "body": f"{name}さんの写真集は、作品ごとにテーマや撮影地が異なり、さまざまな表情を楽しめるのが魅力です。"},
                {"title": "豊富なリリース", "body": f"これまでに{p['total_works']}作品がリリースされており、継続的に新作が届けられています。"},
                {"title": "幅広い出版社から刊行", "body": "複数の出版社から作品が刊行されていることも、高い支持を集めている証拠です。"},
            ],
            "career": (p["wiki"] or {}).get("extract", "")[:300] or f"{name}さんは写真集を中心に活動しています。",
            "works": [f"{w['publisher'] or '出版社'}から{w['date'][:7].replace('-', '年')}月に発売された作品です。" for w in p["works"]],
            "faq": [
                {"q": f"{name}さんの最新写真集は？", "a": f"最新作は『{latest['title']}』（{latest['date']}発売）です。"},
            ],
            "summary": f"{name}さんの最新情報や新作写真集は、本記事の作品リンクや公式SNSからチェックしてみてください。",
        }

    # ------------------------------------------------------------------ HTML
    STYLE = """
<style>
.bz-wrap{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans",sans-serif;color:#2d3748;max-width:820px;margin:0 auto;line-height:1.85}
.bz-hero{text-align:center;margin-bottom:28px}
.bz-hero img{max-width:100%;max-height:640px;border-radius:14px;box-shadow:0 8px 24px rgba(0,0,0,.15)}
.bz-catch{display:inline-block;background:linear-gradient(135deg,#ec4899,#f43f5e);color:#fff;font-weight:bold;padding:6px 18px;border-radius:20px;margin:16px 0 6px;font-size:15px}
.bz-intro{background:#fdf2f8;border-left:5px solid #ec4899;padding:18px 20px;border-radius:10px;margin:18px 0 30px}
.bz-h2{font-size:20px;border-bottom:3px solid #ec4899;padding-bottom:6px;margin:42px 0 18px;color:#1f2937}
.bz-table{width:100%;border-collapse:collapse;font-size:14px}
.bz-table th{background:#fce7f3;width:32%;text-align:left;padding:10px 12px;border:1px solid #fbcfe8;color:#831843}
.bz-table td{padding:10px 12px;border:1px solid #fbcfe8}
.bz-src{font-size:12px;color:#9ca3af;text-align:right;margin-top:6px}
.bz-charm{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px 18px;margin-bottom:14px;box-shadow:0 2px 10px rgba(0,0,0,.04)}
.bz-charm b{color:#be185d;font-size:16px}
.bz-works{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}
.bz-work{border:1px solid #e5e7eb;border-radius:12px;padding:14px;background:#fff;text-align:center}
.bz-work img{width:100%;max-height:330px;object-fit:contain;border-radius:8px}
.bz-work .t{font-weight:bold;font-size:14px;margin:10px 0 4px;text-align:left}
.bz-work .m{font-size:12px;color:#6b7280;text-align:left}
.bz-work .c{font-size:13px;text-align:left;margin:8px 0}
.bz-btn{display:block;background:linear-gradient(135deg,#ec4899,#f43f5e);color:#fff!important;text-decoration:none;font-weight:bold;font-size:14px;padding:10px;border-radius:22px;margin-top:8px}
.bz-sns a{display:inline-block;background:#1f2937;color:#fff!important;text-decoration:none;padding:8px 16px;border-radius:20px;margin:4px;font-size:14px}
.bz-news li{margin-bottom:8px;font-size:14px}
.bz-faq dt{font-weight:bold;color:#831843;margin-top:14px}
.bz-faq dt:before{content:"Q. "}
.bz-faq dd{margin:4px 0 0 0;padding-left:1.4em}
.bz-faq dd:before{content:"A. ";margin-left:-1.4em;font-weight:bold}
.bz-summary{background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px}
</style>
"""

    def build_html(self, p, text, hero_url):
        e = html.escape
        name = p["name"]
        out = [self.STYLE, '<div class="bz-wrap">']
        out.append(f'<div class="bz-hero"><a href="{e(p["works"][0]["url"])}" target="_blank" rel="nofollow noopener">'
                   f'<img src="{e(hero_url)}" alt="{e(name)}"></a><br>'
                   f'<span class="bz-catch">{e(text["catch"])}</span></div>')
        out.append(f'<div class="bz-intro">{e(text["intro"])}</div>')

        # プロフィール
        info = (p["wiki"] or {}).get("infobox", {})
        rows = [("名前", name)] + list(info.items())
        count_label = "X注目ポスト数" if p.get("kind") == "indie" else "DMM/FANZA配信作品数"
        rows.append((count_label, f"{p['total_works']}件"))
        out.append(f'<h2 class="bz-h2">{e(name)}のプロフィール</h2><table class="bz-table">')
        for k, v in rows:
            out.append(f"<tr><th>{e(k)}</th><td>{e(str(v))}</td></tr>")
        out.append("</table>")
        if p["wiki"]:
            out.append(f'<div class="bz-src">出典: <a href="{e(p["wiki"]["url"])}" target="_blank" rel="noopener">Wikipedia「{e(p["wiki"]["title"])}」</a></div>')

        # 魅力
        out.append(f'<h2 class="bz-h2">{e(name)}の魅力ポイント</h2>')
        for c in text["charms"][:3]:
            out.append(f'<div class="bz-charm"><b>✔ {e(c.get("title", ""))}</b><br>{e(c.get("body", ""))}</div>')

        # 経歴
        out.append(f'<h2 class="bz-h2">経歴・これまでの活動</h2><p>{e(text["career"])}</p>')

        # 作品
        work_label = "注目SNSポスト" if p.get("kind") == "indie" else ("出演作品" if p.get("kind") == "av" else "写真集")
        out.append(f'<h2 class="bz-h2">{e(name)}の最新・おすすめ{work_label}</h2><div class="bz-works">')
        for i, w in enumerate(p["works"]):
            meta = " ／ ".join(x for x in [w["date"], w["publisher"], w.get("photographer", "")] if x)
            if w.get("review_avg"):
                meta += f" ／ ★{w['review_avg']}（{w['review_count']}件）"
            comment = text["works"][i] if i < len(text["works"]) else ""
            out.append(
                f'<div class="bz-work"><a href="{e(w["url"])}" target="_blank" rel="nofollow noopener">'
                f'<img src="{e(w["img_hosted"])}" alt="{e(w["title"])}" loading="lazy"></a>'
                f'<div class="t">{e(w["title"])}</div><div class="m">{e(meta)}</div>'
                f'<div class="c">{e(comment)}</div>'
                f'<a class="bz-btn" href="{e(w["url"])}" target="_blank" rel="nofollow noopener">{"✨ X(Twitter)でポストを見る" if p.get("kind") == "indie" else "📖 試し読み・詳細を見る"}</a></div>')
        out.append("</div>")

        # SNS
        sns = (p["wiki"] or {}).get("sns", [])
        if sns:
            out.append(f'<h2 class="bz-h2">{e(name)}の公式SNS</h2><div class="bz-sns">')
            for s in sns:
                out.append(f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["service"])}（@{e(s["id"])}）</a>')
            out.append('</div><div class="bz-src">出典: Wikidata</div>')

        # ニュース
        if p["news"]:
            out.append(f'<h2 class="bz-h2">{e(name)}の最近の話題</h2><ul class="bz-news">')
            for n in p["news"]:
                out.append(f'<li>{e(n["date"])} <a href="{e(n["url"])}" target="_blank" rel="nofollow noopener">{e(n["title"])}</a></li>')
            out.append("</ul>")

        # FAQ
        out.append(f'<h2 class="bz-h2">{e(name)}に関するよくある質問</h2><dl class="bz-faq">')
        for f in text["faq"][:4]:
            out.append(f'<dt>{e(f.get("q", ""))}</dt><dd>{e(f.get("a", ""))}</dd>')
        out.append("</dl>")

        # 関連美女
        if p["related"]:
            out.append('<h2 class="bz-h2">共演した美女もチェック</h2><ul>')
            for r in p["related"]:
                out.append(f'<li><a href="{e(r["url"])}">{e(r["name"])}のプロフィール・写真集まとめ</a></li>')
            out.append("</ul>")

        out.append(f'<h2 class="bz-h2">まとめ</h2><div class="bz-summary">{e(text["summary"])}</div>')
        out.append(f'<p style="font-size:12px;color:#9ca3af;margin-top:24px">※作品情報は{datetime.date.today():%Y年%m月%d日}時点のDMMブックスの掲載内容に基づきます。価格・配信状況は各販売ページでご確認ください。</p>')
        out.append("</div>")
        return sanitize_text("\n".join(out))

    # ------------------------------------------------------------------ 投稿
    def post(self, title, content, tags):
        cats = "".join(f'<category term="{saxutils.escape(t)}" />\n' for t in [CATEGORY] + tags[:9])
        payload = f'''<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:app="http://www.w3.org/2007/app">
  <title>{saxutils.escape(title)}</title>
  <content type="text/html"><![CDATA[{content}]]></content>
  {cats}
  <app:control><app:draft>no</app:draft></app:control>
</entry>'''
        resp = requests.post(
            f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article",
            auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/atom+xml;type=entry"}, timeout=30,
        )
        if resp.status_code not in (200, 201):
            print(f"[投稿失敗] HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        try:
            root = ET.fromstring(resp.text)
            for l in root.findall("{http://www.w3.org/2005/Atom}link"):
                if l.attrib.get("rel") == "alternate":
                    return l.attrib.get("href")
        except Exception:
            pass
        return "https://bijozukan.doorblog.jp/"

    def run(self, name=None, dry_run=False, max_tries=8, source_type="all"):
        if name:
            found = self.find_actor(name, source_type=source_type)
            if not found:
                print(f"[エラー] DMM/FANZA で「{name}」の出演者IDが見つかりません")
                return False
            candidates = [found]
        else:
            candidates = self.discover_candidates(source_type=source_type)
        profile = None
        for c in candidates[:max_tries]:
            print(f"--- 候補: {c['name']}（{c['source']} / id={c['actor_id']}）")
            profile, reason = self.build_profile(c["name"], c["actor_id"], kind=c.get("kind", "gravure"), x_id=c.get("x_id"), categories=c.get("categories"))
            if profile:
                profile["pool"] = c.get("pool") or c.get("kind", "gravure")
                break
            print(f"    × 品質基準を満たさないためスキップ: {reason}")
            self.history.setdefault("skipped", {})[c["name"]] = reason
        return self._post_process_profile(profile, dry_run)
    def _legacy_block(self):
        if name:
            actor_id = self.find_actor_id(name)
            if not actor_id:
                print(f"[エラー] DMM.com で「{name}」の出演者IDが見つかりません")
                return False
            candidates = [{"name": name, "actor_id": actor_id, "source": "指定"}]
        else:
            candidates = self.discover_candidates()

        profile = None
        for c in candidates[:max_tries]:
            print(f"--- 候補: {c['name']}（{c['source']} / actor_id={c['actor_id']}）")
            profile, reason = self.build_profile(c["name"], c["actor_id"])
            if profile:
                break
            print(f"    × 品質基準を満たさないためスキップ: {reason}")
            self.history.setdefault("skipped", {})[c["name"]] = reason
    def _post_process_profile(self, profile, dry_run):
        if not profile:
            print("[エラー] 品質基準を満たす候補がいませんでした")
            if not dry_run:
                self.save_history()
            return False

        print(f"✔ 採用: {profile['name']}（作品{len(profile['works'])}件 / Wikipedia: {'あり' if profile['wiki'] else 'なし'} / ニュース{len(profile['news'])}件）")
        text = self.generate_text(profile)

        # 画像はライブドアに保存（dry-run時は元URLのまま）
        for w in profile["works"]:
            w["img_hosted"] = w["image"] if dry_run else (self.upload_image(w["image"]) or w["image"])
        hero_url = profile["works"][0]["img_hosted"]

        latest = re.sub(r"【[^】]*】", "", profile["works"][0]["title"]).strip()
        catch = text["catch"].replace(profile["name"], "").strip("、。！!｜ ")
        work_label = "SNS画像・魅力" if profile.get("kind") == "indie" else ("出演作品" if profile.get("kind") == "av" else "写真集")
        title = sanitize_text(f"{profile['name']}のプロフィールと最新{work_label}まとめ｜{catch}")[:100]
        content = self.build_html(profile, text, hero_url)
        info = (profile["wiki"] or {}).get("infobox", {})
        tags = [profile["name"], "写真集", "グラビア"]
        if info.get("所属事務所"):
            tags.append(re.sub(r"（.*", "", info["所属事務所"])[:20])
        tags += list({w["publisher"] for w in profile["works"] if w["publisher"]})[:3]

        if dry_run:
            os.makedirs(os.path.join(BASE_DIR, "scratch"), exist_ok=True)
            path = os.path.join(BASE_DIR, "scratch", f"bijozukan_preview_{profile['name']}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"<html><head><meta charset='utf-8'><title>{html.escape(title)}</title></head><body><h1>{html.escape(title)}</h1>{content}</body></html>")
            print(f"[DRY-RUN] タイトル: {title}\n[DRY-RUN] 文字数: {len(re.sub('<[^>]+>', '', content))}\n[DRY-RUN] プレビュー: {path}")
            return True

        url = self.post(title, content, tags)
        if not url:
            return False
        print(f"[SUCCESS] 投稿完了: {url}")
        self.history.setdefault("profiles", []).append({
            "name": profile["name"],
            "actor_id": profile["actor_id"],
            "kind": profile.get("kind", "gravure"),
            "pool": profile.get("pool", profile.get("kind", "gravure")),
            "url": url,
            "title": title,
            "catch": text["catch"],
            "comment": text["intro"][:120],
            "image_url": hero_url,
            "dmm_url": profile["works"][0]["url"],
            "latest_work": latest,
            "posted_at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        self.save_history()
        try:
            from notifier import ArticleNotifier
            ArticleNotifier().send_notification_email(
                title=title, article_url=url, category=CATEGORY, blog_title="美女図鑑",
                hashtags=["美女図鑑", profile["name"].replace(" ", ""), "グラビア", "写真集"], image_url=hero_url)
        except Exception as e:
            print(f"[通知エラー] {e}")
        return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="美女図鑑 個別プロフィール記事 自動投稿")
    ap.add_argument("--name", help="紹介する人を手動指定（DMM.comの出演者名と完全一致）")
    ap.add_argument("--dry-run", action="store_true", help="投稿せず scratch/ にプレビューHTMLを保存")
    ap.add_argument("--type", choices=["all", "gravure", "av", "bigirl", "indie"], default="all", help="対象ジャンル（all: 全て / indie: 非商業SNS美女 / bigirl: bi-girl RSS / gravure: 写真集 / av: AV女優）")
    ap.add_argument("--blog-id", default=DEFAULT_BLOG_ID)
    args = ap.parse_args()
    ok = BijozukanProfileEngine(blog_id=args.blog_id).run(name=args.name, dry_run=args.dry_run, source_type=args.type)
    sys.exit(0 if ok else 1)


"""Wikipedia / Wikidata からタレントのプロフィールと公式SNSを取得するクライアント"""
import re
import requests

WIKI_API = "https://ja.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
HEADERS = {"User-Agent": "BijozukanBot/1.0 (https://bijozukan.doorblog.jp/)"}

# 本人ページか判定するための職業キーワード
PERSON_HINTS = ["グラビア", "アイドル", "タレント", "女優", "AV女優", "セクシー女優", "モデル", "コスプレイヤー", "歌手", "アナウンサー", "インフルエンサー", "YouTuber", "レースクイーン"]

# インフォボックスのキー → 表示名
INFOBOX_KEYS = {
    "愛称": "愛称",
    "出身地": "出身地",
    "血液型": "血液型",
    "身長": "身長",
    "ジャンル": "ジャンル",
    "職業": "職業",
    "デビュー": "デビュー",
    "活動期間": "活動期間",
    "事務所": "所属事務所",
    "グループ名": "グループ",
    "他の活動": "その他の活動",
}

# Wikidata プロパティ → (SNS名, URLテンプレート)
SNS_PROPS = {
    "P2002": ("X", "https://x.com/{}"),
    "P2003": ("Instagram", "https://www.instagram.com/{}/"),
    "P7085": ("TikTok", "https://www.tiktok.com/@{}"),
    "P2397": ("YouTube", "https://www.youtube.com/channel/{}"),
}


def clean_wikitext(value):
    """ウィキ記法を取り除いてプレーンテキストにする"""
    if not value:
        return ""
    v = re.sub(r"<ref[^>]*/>", "", value)
    v = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"<br\s*/?>", "、", v)
    v = re.sub(r"<[^>]+>", "", v)
    # {{JPN}} {{R|..}} などのテンプレートは除去、{{lang|xx|text}} 等は最後の引数を残す
    for _ in range(3):
        v = re.sub(r"\{\{(?:JPN|R|Sfn|要出典|efn|refnest)[^{}]*\}\}", "", v, flags=re.I)
        v = re.sub(r"\{\{[^{}|]*\|([^{}]*)\}\}", lambda m: m.group(1).split("|")[-1], v)
        v = re.sub(r"\{\{[^{}]*\}\}", "", v)
    v = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", v)
    v = re.sub(r"'''?", "", v)
    v = re.sub(r"\s+", " ", v).strip(" ・、")
    return v


class WikiClient:
    def __init__(self, timeout=10):
        self.timeout = timeout

    def _get_page(self, title):
        params = {
            "action": "query",
            "prop": "revisions|extracts|pageprops",
            "rvprop": "content",
            "rvslots": "main",
            "exintro": 1,
            "explaintext": 1,
            "titles": title,
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }
        try:
            r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=self.timeout)
            pages = r.json().get("query", {}).get("pages", [])
            if pages and not pages[0].get("missing"):
                return pages[0]
        except Exception as e:
            print(f"[Wikipedia取得エラー] {title}: {e}")
        return None

    def _is_person_page(self, page, name):
        extract = page.get("extract", "") or ""
        if "曖昧さ回避" in extract or "may refer to" in extract:
            return False
        head = extract[:300]
        compact = name.replace(" ", "").replace("　", "")
        if compact not in head.replace(" ", "").replace("　", ""):
            return False
        return any(h in head for h in PERSON_HINTS)

    def _parse_infobox(self, wikitext):
        info = {}
        # 生年月日（生年/生月/生日 形式）
        y = re.search(r"\|\s*生年\s*=\s*(\d{4})", wikitext)
        m = re.search(r"\|\s*生月\s*=\s*(\d{1,2})", wikitext)
        d = re.search(r"\|\s*生日\s*=\s*(\d{1,2})", wikitext)
        if y and m and d:
            info["生年月日"] = f"{y.group(1)}年{int(m.group(1))}月{int(d.group(1))}日"
        for key, label in INFOBOX_KEYS.items():
            mm = re.search(rf"^\|[ \t]*{key}[ \t]*=[ \t]*(.+)$", wikitext, flags=re.M)
            if mm:
                val = clean_wikitext(mm.group(1))
                val = re.sub(r"[、,]{2,}", "、", val).replace("（、", "（")
                if val and len(val) < 80 and not val.startswith("|"):
                    if key == "身長" and re.fullmatch(r"\d{3}(\.\d)?", val):
                        val += " cm"
                    info[label] = val
        return info

    def _parse_wikitext_sns(self, wikitext):
        """日本語版Wikipediaの『外部リンク』セクション（{{Twitter|...}} 等）から最新の公式SNSを取得する"""
        sns = []
        patterns = [
            ("X", r"\{\{(?:Twitter|X)\s*\|\s*([A-Za-z0-9_]+)", "https://x.com/{}"),
            ("X", r"https?://(?:x|twitter)\.com/([A-Za-z0-9_]+)", "https://x.com/{}"),
            ("Instagram", r"\{\{Instagram\s*\|\s*([A-Za-z0-9_.]+)", "https://www.instagram.com/{}/"),
            ("Instagram", r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)", "https://www.instagram.com/{}/"),
            ("TikTok", r"\{\{TikTok\s*\|\s*@?([A-Za-z0-9_.]+)", "https://www.tiktok.com/@{}"),
            ("TikTok", r"https?://(?:www\.)?tiktok\.com/@([A-Za-z0-9_.]+)", "https://www.tiktok.com/@{}"),
        ]
        ext_sec = wikitext[wikitext.find("外部リンク"):] if "外部リンク" in wikitext else wikitext
        seen_services = set()
        for label, pat, tmpl in patterns:
            if label in seen_services:
                continue
            m = re.search(pat, ext_sec, flags=re.I)
            if m:
                uid = m.group(1).strip("/")
                if uid.lower() not in ("intent", "share", "hashtag", "search", "i", "p", "reel"):
                    sns.append({"service": label, "id": uid, "url": tmpl.format(uid)})
                    seen_services.add(label)
        return sns

    def _get_sns(self, qid, wikitext=""):
        # 1. 日本語版Wikipediaの外部リンクを最優先（改名後の最新アカウントが反映されているため）
        sns = self._parse_wikitext_sns(wikitext)
        seen_services = {s["service"] for s in sns}
        if not qid:
            return sns
        try:
            r = requests.get(WIKIDATA_API.format(qid=qid), headers=HEADERS, timeout=self.timeout)
            claims = r.json().get("entities", {}).get(qid, {}).get("claims", {})
            for prop, (label, tmpl) in SNS_PROPS.items():
                if label in seen_services:
                    continue
                # 複数ある場合は deprecated を除外し preferred または末尾（最新）を選ぶ
                valid_vals = []
                for c in claims.get(prop, []):
                    rank = c.get("rank", "normal")
                    if rank == "deprecated":
                        continue
                    val = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if isinstance(val, str) and val:
                        if rank == "preferred":
                            valid_vals = [val]
                            break
                        valid_vals.append(val)
                if valid_vals:
                    uid = valid_vals[-1]
                    sns.append({"service": label, "id": uid, "url": tmpl.format(uid)})
                    seen_services.add(label)
        except Exception as e:
            print(f"[Wikidata取得エラー] {qid}: {e}")
        return sns

    def get_profile(self, name):
        """名前から本人のWikipediaページを探してプロフィールを返す。見つからなければ None"""
        candidates = [name, f"{name} (タレント)", f"{name} (グラビアアイドル)", f"{name} (AV女優)", f"{name} (モデル)", f"{name} (女優)"]
        for title in candidates:
            page = self._get_page(title)
            if not page or not self._is_person_page(page, name):
                continue
            wikitext = page.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("content", "")
            extract = (page.get("extract") or "").strip()
            # 読みがな・生年月日の括弧書きを除去した要約
            summary = re.sub(r"（[^）]*）", "", extract.split("\n")[0])[:300]
            qid = page.get("pageprops", {}).get("wikibase_item")
            return {
                "title": page["title"],
                "url": f"https://ja.wikipedia.org/wiki/{page['title'].replace(' ', '_')}",
                "summary": summary,
                "extract": extract[:1200],
                "infobox": self._parse_infobox(wikitext),
                "sns": self._get_sns(qid, wikitext=wikitext),
            }
        return None


if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(WikiClient().get_profile(sys.argv[1] if len(sys.argv) > 1 else "菊地姫奈"), ensure_ascii=False, indent=2))

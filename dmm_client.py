import os
import requests
from dotenv import load_dotenv

load_dotenv()

class DMMClient:
    def __init__(self):
        self.api_id = os.getenv("DMM_API_ID")
        self.affiliate_id = os.getenv("DMM_AFFILIATE_ID")
        self.base_url = "https://api.dmm.com/affiliate/v3"

    def search_actress(self, name=None, actress_id=None):
        """女優を検索してプロフィール（BWH等）を取得する"""
        params = {
            "api_id": self.api_id,
            "affiliate_id": self.affiliate_id,
            "operation": "ActressSearch",
            "output": "json"
        }
        if name:
            params["keyword"] = name
        if actress_id:
            params["actress_id"] = actress_id
            
        try:
            response = requests.get(f"{self.base_url}/ActressSearch", params=params, timeout=10)
            if response.status_code != 200:
                print(f"DMM API Error (ActressSearch): {response.status_code}")
                return []
            data = response.json()
            if "result" in data and "actress" in data["result"]:
                return data["result"]["actress"]
        except Exception as e:
            print(f"DMM API Exception (ActressSearch): {e}")
        return []

    def get_actress_works(self, actress_id, hits=10, site="FANZA", service="digital", floor=None, keyword=None):
        """特定女優の作品（サンプル画像URL、アフィリンク）を取得する"""
        params = {
            "api_id": self.api_id,
            "affiliate_id": self.affiliate_id,
            "site": site,
            "service": service,
            "article": "actress",
            "article_id": actress_id,
            "hits": hits,
            "output": "json"
        }
        if floor:
            params["floor"] = floor
        if keyword:
            params["keyword"] = keyword
            
        try:
            response = requests.get(f"{self.base_url}/ItemList", params=params, timeout=10)
            if response.status_code != 200:
                print(f"DMM API Error (get_actress_works): {response.status_code}")
                return []
            data = response.json()
            if "result" in data and "items" in data["result"]:
                return data["result"]["items"]
        except Exception as e:
            print(f"DMM API Exception (get_actress_works): {e}")
        return []

    def get_anime_works(self, keyword, hits=10, service="digital", floor=None):
        """アニメ作品（2D）を検索して、サンプル画像やアフィリンクを取得する"""
        params = {
            "api_id": self.api_id,
            "affiliate_id": self.affiliate_id,
            "site": "DMM.com",
            "service": service,
            "keyword": keyword,
            "hits": hits,
            "output": "json"
        }
        if floor:
            params["floor"] = floor
            
        try:
            response = requests.get(f"{self.base_url}/ItemList", params=params, timeout=10)
            if response.status_code != 200:
                print(f"DMM API Error (get_anime_works): {response.status_code}")
                return []
            data = response.json()
            if "result" in data and "items" in data["result"]:
                return data["result"]["items"]
            
            # フォールバック: serviceを変えて再試行
            if service == "digital":
                return self.get_anime_works(keyword, hits, service="ebook")
        except Exception as e:
            print(f"DMM API Exception (get_anime_works): {e}")
        return []

    def get_top_fanza_works(self, service="digital", floor="videoa", hits=10, keyword=None):
        """FANZAの特定サービスにおける売れ筋(rank順)商品を取得する"""
        params = {
            "api_id": self.api_id,
            "affiliate_id": self.affiliate_id,
            "site": "FANZA",
            "service": service,
            "sort": "rank",
            "hits": hits,
            "output": "json"
        }
        if floor: params["floor"] = floor
        if keyword: params["keyword"] = keyword
            
        try:
            response = requests.get(f"{self.base_url}/ItemList", params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("result", {}).get("items", [])
        except Exception as e:
            print(f"DMM API Exception: {e}")
        return []

    def get_general_works(self, keyword=None, service="ebook", floor=None, hits=10):
        """一般作品（非アダルト）を検索する"""
        params = {
            "api_id": self.api_id,
            "affiliate_id": self.affiliate_id,
            "site": "DMM.com",
            "service": service,
            "hits": hits,
            "sort": "rank",
            "output": "json"
        }
        if floor: params["floor"] = floor
        if keyword: params["keyword"] = keyword
            
        try:
            response = requests.get(f"{self.base_url}/ItemList", params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("result", {}).get("items", [])
        except Exception as e:
            print(f"DMM API Exception: {e}")
        return []

    def get_birthday_from_wikipedia(self, name):
        """Wikipedia APIを使用して生年月日を取得する"""
        import re
        headers = {"User-Agent": "FortuneBot/1.0 (contact: your-email@example.com)"}
        try:
            # 1. ページを検索
            search_url = "https://ja.wikipedia.org/w/api.php"
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": name,
                "format": "json"
            }
            r = requests.get(search_url, params=search_params, headers=headers, timeout=5)
            search_results = r.json().get("query", {}).get("search", [])
            if not search_results: return None
            
            page_id = search_results[0]["pageid"]
            
            # 2. ページ内容を取得
            content_params = {
                "action": "query",
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "pageids": page_id,
                "format": "json"
            }
            r = requests.get(search_url, params=content_params, headers=headers, timeout=5)
            pages = r.json().get("query", {}).get("pages", {})
            extract = pages.get(str(page_id), {}).get("extract", "")
            
            # 3. 生年月日を抽出 (例: 1993年8月16日)
            # Unicodeを使って「年」「月」「日」に柔軟に対応
            match = re.search(r'(\d{4})[\u5e74\s/.-]+(\d{1,2})[\u6708\s/.-]+(\d{1,2})[\u65e5\s/.-]*', extract)
            if match:
                y, m, d = match.groups()
                return f"{y}-{int(m):02d}-{int(d):02d}"
        except Exception as e:
            print(f"Wikipedia Error for {name}: {e}")
        return None

if __name__ == "__main__":
    client = DMMClient()
    # テスト: 三上悠亜
    actresses = client.search_actress(name="三上悠亜")
    print(f"Found {len(actresses)} actresses.")
    for a in actresses:
        print(f"Name: {a.get('name')}, Height: {a.get('height')}, B:{a.get('bust')} W:{a.get('waist')} H:{a.get('hip')}")
        # 作品も取得
        works = client.get_actress_works(a.get('id'), hits=1)
        if works:
            print(f"Latest Work image: {works[0].get('imageURL', {}).get('large')}")

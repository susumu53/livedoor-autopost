import os
import requests
import re
import time
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

class MGSClient:
    def __init__(self):
        self.affiliate_id = os.getenv("MGS_AFFILIATE_ID")
        self.base_url = "https://www.mgstage.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        }
        self.cookies = {"adc": "1"}

    def search_works(self, keyword=None, hits=5):
        """
        MGSの作品を検索・取得する
        """
        params = {"sort": "n"}
        if keyword:
            params["search_word"] = keyword
            
        print(f"MGS fetching URL: {self.base_url}/search/cSearch.php with params: {params}")
        
        try:
            response = requests.get(
                f"{self.base_url}/search/cSearch.php", 
                params=params,
                headers=self.headers, 
                cookies=self.cookies, 
                timeout=10
            )
            if response.status_code != 200:
                return []
                
            soup = BeautifulSoup(response.text, 'html.parser')
            items = []
            
            # 検索結果のリストを取得 (MGSのサイト構造変更に対応)
            list_items = soup.select('div.rank_list > ul > li') or soup.select('.common_product_list li') or soup.select('li.tile') or soup.select('.search_list li')
            
            if not list_items:
                print("MGS list_items is empty. Trying fallback div selector...")
                list_items = soup.select('.common_product_list .tile') or soup.select('.product_list li')
            
            for li in list_items[:hits]:
                try:
                    # タイトルまたは画像リンクからProduct IDを取得
                    a_tag = li.select_one('a[href*="product_detail"]')
                    if not a_tag: continue
                    
                    link = a_tag.get('href', '')
                    match = re.search(r'product_detail/([^/?]+)/', link)
                    if not match: continue
                    
                    product_id = match.group(1)
                    detail = self.get_product_detail(product_id)
                    if detail:
                        items.append(detail)
                        time.sleep(0.2)
                except Exception as e:
                    print(f"Error parsing MGS item: {e}")
                    
            return items
        except Exception as e:
            print(f"MGS search error: {e}")
            return []

    def get_product_detail(self, product_id):
        """
        作品の詳細情報を取得する
        """
        url = f"{self.base_url}/product/product_detail/{product_id}/"
        try:
            affiliate_url = f"{self.base_url}/ppc/{self.affiliate_id}/product_detail/{product_id}/"
            
            response = requests.get(url, headers=self.headers, cookies=self.cookies, timeout=10)
            if response.status_code != 200:
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # タイトル (pycの文字列から h1.tag)
            title_tag = soup.select_one('h1.tag') or soup.select_one('h1.tag_name') or soup.select_one('h1')
            title = title_tag.get_text(strip=True) if title_tag else "タイトル不明"
            
            # メイン画像
            main_image_tag = soup.select_one('a#EnlargeImage')
            image_url = main_image_tag.get('href', '') if main_image_tag else ""
            if image_url and image_url.startswith('/'):
                image_url = self.base_url + image_url
            
            # サンプル画像
            sample_tags = soup.select('#sample-photo a.sample_image')
            samples = [s.get('href') for s in sample_tags if s.get('href')]
            
            # 価格 (複数の候補をチェック)
            price_selectors = ['#download_hd_price', '#download_price', '.price', 'div.price', 'p.price']
            price = 0
            for selector in price_selectors:
                price_tag = soup.select_one(selector)
                if price_tag:
                    price_text = price_tag.get_text(strip=True)
                    price_match = re.search(r'(\d{1,3}(,\d{3})*)', price_text)
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                        break
            
            # アイテム情報 (出演者, メーカー, レーベル, 配信開始)
            iteminfo = {"actress": [], "maker": [], "label": []}
            date = ""
            
            # 詳細データテーブルから抽出
            for tr in soup.select('table.detail_data tr') or soup.select('div.detail_data table tr'):
                th = tr.select_one('th')
                td = tr.select_one('td')
                if not th or not td: continue
                
                label_text = th.get_text(strip=True)
                
                if "出演" in label_text:
                    act_tags = td.select('a')
                    iteminfo["actress"] = [{"name": a.get_text(strip=True)} for a in act_tags]
                elif "メーカー" in label_text:
                    maker_tag = td.select_one('a')
                    if maker_tag:
                        iteminfo["maker"] = [{"name": maker_tag.get_text(strip=True)}]
                elif "レーベル" in label_text:
                    label_tag = td.select_one('a')
                    if label_tag:
                        iteminfo["label"] = [{"name": label_tag.get_text(strip=True)}]
                elif "配信開始" in label_text:
                    date = td.get_text(strip=True)

            return {
                "title": title,
                "imageURL": {"large": image_url},
                "sampleImageURL": {"sample_l": {"image": samples}},
                "affiliateURL": affiliate_url,
                "prices": {"price": price},
                "iteminfo": iteminfo,
                "date": date,
                "source": "MGS"
            }
        except Exception as e:
            print(f"MGS detail error ({product_id}): {e}")
            return None

if __name__ == "__main__":
    client = MGSClient()
    results = client.search_works(hits=1)
    if results:
        r = results[0]
        print(f"Title: {r['title']}")
        print(f"Price: {r['prices']['price']}")
        print(f"Date: {r['date']}")
        print(f"Actresses: {[a['name'] for a in r['iteminfo']['actress']]}")
        print(f"Link: {r['affiliateURL']}")
        print(f"Samples: {len(r['sampleImageURL']['sample_l']['image'])}")

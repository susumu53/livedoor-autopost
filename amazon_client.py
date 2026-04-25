import os
from amazon_paapi import AmazonApi

class AmazonPAClient:
    def __init__(self):
        self.access_key = os.getenv("AMAZON_ACCESS_KEY")
        self.secret_key = os.getenv("AMAZON_SECRET_KEY")
        self.associate_tag = os.getenv("AMAZON_ASSOCIATE_TAG", "blogseesaa090-22")
        
        self.is_configured = bool(self.access_key and self.secret_key)
        self.api = None
        
        if self.is_configured:
            try:
                self.api = AmazonApi(self.access_key, self.secret_key, self.associate_tag, "JP")
            except Exception as e:
                print(f"Amazon PA-API Init Error: {e}")
                self.api = None

    def search_works(self, keyword, search_index="Books", hits=10):
        if not self.api:
            return []
            
        print(f"Searching Amazon for: {keyword}")
        results = []
        try:
            search_result = self.api.search_items(keywords=keyword, search_index=search_index, item_count=hits)
            
            if not search_result or not search_result.items:
                return []
                
            for item in search_result.items:
                # DMM APIの戻り値の形に合わせて変換
                title = item.item_info.title.display_value if item.item_info and item.item_info.title else ""
                affiliate_url = item.detail_page_url or ""
                
                # 画像情報の抽出
                image_url = ""
                if item.images and item.images.primary and item.images.primary.large:
                    image_url = item.images.primary.large.url
                    
                if not image_url:
                    continue
                    
                # python-amazon-paapi の特殊オブジェクトを文字列化する等、完全な辞書形式にする
                dmm_style_item = {
                    "title": str(title),
                    "imageURL": {
                        "large": str(image_url)
                    },
                    "affiliateURL": str(affiliate_url),
                    "iteminfo": {
                        "actress": [{"name": keyword}] # フィルタリング突破用
                    },
                    "source": "amazon"
                }
                results.append(dmm_style_item)
                
        except Exception as e:
            # 認証エラーなどの場合は静かにスキップ
            print(f"Amazon Search API Error: {type(e).__name__} - {str(e)[:100]}...")
            
        return results

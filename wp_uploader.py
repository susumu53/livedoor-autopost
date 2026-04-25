import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

class WPUploader:
    def __init__(self):
        self.url = os.getenv("WP_URL").rstrip('/')
        self.username = os.getenv("WP_USERNAME")
        self.password = os.getenv("WP_APP_PASSWORD")
        
        # 認証ヘッダーの作成
        cred = f"{self.username}:{self.password}"
        token = base64.b64encode(cred.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}"
        }

    def upload_media(self, file_path, filename):
        """画像をWordPressのメディアライブラリにアップロードする"""
        with open(file_path, 'rb') as f:
            data = f.read()
        
        media_headers = {
            **self.headers,
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "image/png"  # レーダーチャート等はPNG
        }
        
        response = requests.post(f"{self.url}/wp-json/wp/v2/media", headers=media_headers, data=data)
        if response.status_code == 201:
            return response.json()
        else:
            print(f"Failed to upload media: {response.status_code} - {response.text}")
            return None

    def post_article(self, title, content, categories=None, tags=None, featured_media_id=None, slug=None):
        """記事を投稿する"""
        post_data = {
            "title": title,
            "content": content,
            "status": "publish", # 本番稼働時はpublish
            "categories": categories or [],
            "tags": tags or [999] # 特定のタグID(仮に999)を付加してプラグインで判別可能にする
        }
        if slug:
            post_data["slug"] = slug
        if featured_media_id:
            post_data["featured_media"] = featured_media_id

        response = requests.post(f"{self.url}/wp-json/wp/v2/posts", headers=self.headers, json=post_data)
        if response.status_code == 201:
            return response.json()
        else:
            print(f"Failed to post article: {response.status_code} - {response.text}")
            return None

    def get_post_by_slug(self, slug):
        """スラッグから該当する記事を検索する"""
        params = {"slug": slug, "status": "publish,draft"}
        response = requests.get(f"{self.url}/wp-json/wp/v2/posts", headers=self.headers, params=params)
        if response.status_code == 200:
            posts = response.json()
            if posts:
                return posts[0]
        return None

    def update_post(self, post_id, title, content):
        """既存の記事を更新する"""
        post_data = {
            "title": title,
            "content": content
        }
        response = requests.post(f"{self.url}/wp-json/wp/v2/posts/{post_id}", headers=self.headers, json=post_data)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to update article: {response.status_code} - {response.text}")
            return None

if __name__ == "__main__":
    # テスト
    uploader = WPUploader()
    # post = uploader.post_article("API Test", "This is a test post from Python.")
    # if post:
    #     print(f"Posted: {post.get('link')}")

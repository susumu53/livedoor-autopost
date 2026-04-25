import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

class LivedoorClient:
    def __init__(self):
        self.livedoor_id = os.getenv("LIVEDOOR_ID")
        self.blog_id = os.getenv("LIVEDOOR_BLOG_ID")
        self.api_key = os.getenv("LIVEDOOR_API_KEY")
        
        if not all([self.livedoor_id, self.blog_id, self.api_key]):
            raise ValueError("LIVEDOOR_ID, LIVEDOOR_BLOG_ID, LIVEDOOR_API_KEY環境変数が設定されていません。")
            
        self.endpoint = f"https://livedoor.blogcms.jp/atompub/{self.blog_id}/article"

    def post_article(self, title, content, categories=None, publish=True):
        """
        ライブドアブログに記事を投稿する
        
        :param title: 記事のタイトル
        :param content: HTML形式の記事本文
        :param categories: リスト形式のカテゴリ名の配列
        :param publish: Trueで公開、Falseで下書き
        :return: 投稿された記事のレスポンス（成功時）またはNone
        """
        draft_value = "no" if publish else "yes"
        
        # AtomPub XMLの構築
        category_tags = ""
        if categories:
            for cat in categories:
                category_tags += f'<category term="{cat}" />\n'
                
        xml_template = f'''<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{title}</title>
  <content type="text/html">
    <![CDATA[{content}]]>
  </content>
  {category_tags}
  <app:control>
    <app:draft>{draft_value}</app:draft>
  </app:control>
</entry>'''

        try:
            print(f"ライブドアブログへ投稿中... [{title}]")
            response = requests.post(
                self.endpoint,
                auth=HTTPBasicAuth(self.livedoor_id, self.api_key),
                data=xml_template.encode('utf-8'),
                headers={'Content-Type': 'application/atom+xml;type=entry'}
            )
            
            if response.status_code in [201, 200]:
                print(f"投稿成功！ ステータスコード: {response.status_code}")
                return response.text
            else:
                print(f"投稿失敗: ステータスコード {response.status_code}")
                print(f"レスポンス: {response.text}")
                return None
                
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            return None

if __name__ == "__main__":
    # テスト動作確認用
    try:
        client = LivedoorClient()
        print("初期化成功。")
        
        # 実際に投稿テストを行う場合は以下のコメントを外してください
        # res = client.post_article(
        #     "自動投稿テスト (Livedoor)", 
        #     "<p>これはPythonからのAtomPubテスト投稿です。</p>", 
        #     categories=["テスト"], 
        #     publish=False
        # )
        # if res:
        #     print("テスト投稿に成功しました。")
            
    except Exception as e:
        print(f"エラー: {e}")

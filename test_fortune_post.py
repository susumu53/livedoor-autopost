import datetime
import os
import json
import sqlite3
from dmm_client import DMMClient
from livedoor_client import LivedoorClient
from database import BeautyDatabase
from fortune_engine import FortuneEngine
from main import generate_fortune_article_html

def test_fortune_post():
    db_path_fanza = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beauty_index_fanza.db")
    db = BeautyDatabase(db_path=db_path_fanza)
    livedoor = LivedoorClient()
    dmm = DMMClient()
    fortune = FortuneEngine()
    
    print("--- Testing Fortune Analysis Post ---")
    
    # テスト対象
    actress_name = "雪平莉左" # 写真集が多く、Wikipediaデータもある
    
    print(f"Checking fortune for: {actress_name}")
    birthday = dmm.get_birthday_from_wikipedia(actress_name)
    
    if not birthday:
        print("Failed to get birthday from Wikipedia. Using fallback.")
        birthday = "1994-06-17" # 雪平莉左さんの誕生日

    print(f"Birthday: {birthday}")
    chart = fortune.get_chart(birthday)
    
    if chart:
        # 一般作品を取得
        works = dmm.get_general_works(keyword=actress_name, hits=5)
        if not works:
            works = dmm.get_top_fanza_works(keyword=actress_name, hits=5)
        
        article_html = generate_fortune_article_html(actress_name, chart, works)
        title = f"【テスト投稿】AI四柱推命鑑定：{actress_name}さんの運命と2024年のバイオリズム"
        
        print(f"Posting to Livedoor: {title}")
        post_id = livedoor.post_article(title, article_html, categories=["運勢分析"])
        if post_id:
            print(f"Successfully posted fortune analysis for {actress_name}")
        else:
            print("Failed to post to Livedoor.")
    else:
        print("Failed to generate fortune chart.")

if __name__ == "__main__":
    test_fortune_post()

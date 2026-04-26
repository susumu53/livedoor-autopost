import sqlite3
import os

db_path = r"c:\Users\garoa\Desktop\プログラム作成\プログラム練習\アプリ投稿サイト\livedoor_autopost\beauty_index_fanza.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT count(*) FROM scores")
count = cursor.fetchone()[0]
print(f"Total scores: {count}")

cursor.execute("SELECT name, total_score, category FROM scores ORDER BY total_score DESC LIMIT 10")
rows = cursor.fetchall()
for row in rows:
    print(row)
conn.close()

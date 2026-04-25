import sqlite3
from datetime import datetime
import os

class BeautyDatabase:
    def __init__(self, db_path=None):
        if db_path is None:
            # スクリプトの場所を基準にする
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, "beauty_index.db")
        else:
            self.db_path = db_path
        self._create_table()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    total_score REAL NOT NULL,
                    symmetry REAL,
                    neoteny REAL,
                    proportion REAL,
                    dimorphism REAL,
                    social_meme REAL,
                    affiliate_url TEXT,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save_score(self, data):
        """
        data: {name, category, total_score, symmetry, neoteny, proportion, dimorphism, social_meme, affiliate_url, image_url}
        同一人物が既にいる場合、得点の高い方を残す（同点の場合は最新版に更新）
        """
        name = data['name']
        category = data['category']
        new_score = data['total_score']

        with self._get_connection() as conn:
            # 既存のスコアをすべて確認
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(total_score) FROM scores WHERE name = ? AND category = ?", (name, category))
            max_existing_score = cursor.fetchone()[0]

            if max_existing_score is not None:
                if new_score >= max_existing_score:
                    # 新しい方が高いか同点なので、既存の古い（または同点の）データをすべて消す
                    conn.execute("DELETE FROM scores WHERE name = ? AND category = ?", (name, category))
                    print(f"Database: Updating record for {name} (Old Max: {max_existing_score} -> New: {new_score})")
                else:
                    # 古い最高スコアの方が高いので、何もしない
                    print(f"Database: Found higher existing score for {name} ({max_existing_score}). Skipping save.")
                    return

            # 新規保存または更新
            query = """
                INSERT INTO scores (
                    name, category, total_score, symmetry, neoteny, proportion, dimorphism, social_meme, affiliate_url, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            values = (
                name, category, new_score,
                data.get('symmetry'), data.get('neoteny'), data.get('proportion'),
                data.get('dimorphism'), data.get('social_meme'),
                data.get('affiliate_url'), data.get('image_url')
            )
            conn.execute(query, values)

    def get_rankings(self, category=None, limit=10):
        query = "SELECT name, total_score, category, affiliate_url, image_url, symmetry, neoteny, proportion, dimorphism, social_meme FROM scores"
        params = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY total_score DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_score_by_name(self, name, category="3D"):
        query = "SELECT name, total_score, category, affiliate_url, image_url, symmetry, neoteny, proportion, dimorphism, social_meme FROM scores WHERE name = ? AND category = ?"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (name, category))
            return cursor.fetchone()

if __name__ == "__main__":
    db = BeautyDatabase()
    print("Database and table initialized.")

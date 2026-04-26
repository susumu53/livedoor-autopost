import datetime
import argparse
import os
import math
import json
import traceback
import sys
from dmm_client import DMMClient
try:
    from mgs_client import MGSClient
except ImportError:
    class MGSClient:
        def __init__(self): pass
        def search_works(self, *args, **kwargs): return []
from livedoor_client import LivedoorClient
from database import BeautyDatabase
try:
    from generate_article import BeautyManager
except ImportError:
    BeautyManager = None

# 24時間分のローテーション設定 (サービス, フロア, キーワード, 表示用カテゴリ/タイトル)
# FC2の SCHEDULE_24H を継承
SCHEDULE_24H = [
    {"service": "digital", "floor": "videoa", "keyword": "競泳水着", "category": "競泳水着・スク水"},  # 0時 (同人から変更)
    {"service": "digital", "floor": "videoa", "keyword": "NTR", "category": "NTR"},  # 1時
    {"service": "digital", "floor": "videoa", "keyword": "タイツ", "category": "パンスト・タイツ"},  # 2時 (同人から変更)
    {"service": "digital", "floor": "videoa", "keyword": "痴漢", "category": "痴漢"},  # 3時
    {"service": "digital", "floor": "videoa", "keyword": "野外", "category": "野外・露出"},  # 4時 (同人から変更)
    {"service": "digital", "floor": "videoa", "keyword": "M字開脚", "category": "M字開脚"},  # 5時
    {"service": "digital", "floor": "videoa", "keyword": "巨乳", "category": "巨乳"},  # 6時
    {"service": "mono", "floor": "goods", "keyword": "オナホール", "category": "アダルトグッズ"},  # 7時
    {"service": "digital", "floor": "videoa", "keyword": "人妻", "category": "人妻・熟女"},  # 8時
    {"service": "digital", "floor": "videoa", "keyword": "マイクロビキニ", "category": "マイクロビキニ"},  # 9時
    {"service": "digital", "floor": "videoa", "keyword": "素人", "category": "素人ビデオ"},  # 10時
    {"service": "digital", "floor": "videoa", "keyword": "巨乳", "category": "巨乳女優"},  # 11時 (グッズから変更)
    {"service": "digital", "floor": "videoa", "keyword": "企画", "category": "企画ビデオ"},  # 12時
    {"service": "digital", "floor": "videoa", "keyword": "単体", "category": "単体女優"},  # 13時 (アニメから変更)
    {"service": "digital", "floor": "videoa", "keyword": "制服", "category": "制服・コスプレ"},  # 14時
    {"service": "digital", "floor": "videoa", "keyword": "美少女", "category": "美少女女優"},  # 15時 (PCゲームから変更)
    {"service": "digital", "floor": "videoa", "keyword": "お姉さん", "category": "お姉さん"},  # 16時
    {"service": "digital", "floor": "videoa", "keyword": "熟女", "category": "熟女・人妻"},  # 17時 (グッズから変更)
    {"service": "digital", "floor": "videoa", "keyword": "単体", "category": "単体女優人気"},  # 18時
    {"service": "digital", "floor": "videoa", "keyword": "OL", "category": "OL・制服"},  # 19時
    {"service": "digital", "floor": "videoa", "keyword": "ギャル", "category": "ギャル"},  # 20時
    {"service": "digital", "floor": "videoa", "keyword": "美脚", "category": "美脚・タイツ"},  # 21時
    {"service": "digital", "floor": "videoa", "keyword": "中出し", "category": "中出し"},  # 22時
    {"service": "digital", "floor": "videoa", "keyword": "VR", "category": "VRアダルト動画"},  # 23時
]

NG_WORDS = [
    "洗脳", "レイプ", "強姦", "盗撮", "リベンジポルノ", "乱暴", "鬼畜", "無理やり", "無理矢理", 
    "監禁", "奴隷", "調教", "強制", "辱め", "陵辱",
    "ロリ", "ペド", "幼女", "稚児", "児童", "JS", "JC", "JK", "女子校生", "女子高生", "女子中学生", "女子小学生",
    "女学生", "女子生徒", "教え子", "女子大生", "学生", "学園", "校内", "体育倉庫", "授乳",
    "援交", "援助交際", "パパ活", "売春", "買春", "近親相姦", "義母", "実母", "姉妹", "継母", "兄妹"
]

def sanitize_text(text):
    if not text:
        return ""
    for word in NG_WORDS:
        text = text.replace(word, "〇〇")
    return text

def calculate_cp_index(item):
    """
    コスパ指数(CP Index)を計算する
    ロジック: (評価 * 10) + (レビュー数ポイント) + (お得度ボーナス)
    """
    review = item.get("review", {})
    avg = float(review.get("average", 0))
    count = int(review.get("count", 0))
    
    prices = item.get("prices", {})
    deliveries = prices.get("deliveries", {}).get("delivery", [])
    
    # 標準的な販売価格 (hd or download or stream)
    price = 0
    list_price = 0
    target_types = ["hd", "download", "stream", "androiddl", "iosdl"]
    
    for d in deliveries:
        if d.get("type") in target_types:
            price = int(d.get("price", 0))
            list_price = int(d.get("list_price", price))
            break
            
    # 1. 評価ポイント (Max 50)
    score_pts = avg * 10
    
    # 2. 信頼度ポイント (件数) (Max 20)
    # 100件で 20pt (log10(100)*10 = 20)
    count_pts = min(20, math.log10(count + 1) * 10)
    
    # 3. お得度ポイント (割引率) (Max 30)
    discount_pts = 0
    if list_price > 0 and price > 0:
        discount_rate = (list_price - price) / list_price
        discount_pts = min(30, discount_rate * 60) # 50%引きで 30pt
        
    total = score_pts + count_pts + discount_pts
    return {
        "total": round(total, 1),
        "price": price,
        "discount_rate": round((1 - price/list_price)*100 if list_price > 0 else 0, 1) if list_price > 0 else 0
    }

def generate_html_article(items, category_name):
    """
    DMMのアイテムリストからライブドアブログ用HTMLを生成する
    """
    today_str = datetime.datetime.now().strftime("%Y年%m月%d日")
    
    # CSSスタイル定義（ライブドアブログの記事内に埋め込む）
    style = """
    <style>
    .ranking-container { font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif; color: #333; max-width: 800px; margin: 0 auto; line-height: 1.6; }
    .ranking-header { background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%); color: white; padding: 30px; text-align: center; border-radius: 15px; margin-bottom: 40px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
    .ranking-header h1 { margin: 0; font-size: 24px; font-weight: bold; }
    .ranking-item { background: #fff; border-radius: 15px; padding: 25px; margin-bottom: 50px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); border: 1px solid #f0f0f0; transition: transform 0.3s ease; }
    .ranking-item:hover { transform: translateY(-5px); }
    .rank-badge { display: inline-block; background: #e91e63; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 14px; margin-bottom: 15px; }
    .source-badge { display: inline-block; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 14px; margin-left: 10px; margin-bottom: 15px; }
    .fanza-badge { background: #000; color: #fff; }
    .mgs-badge { background: #00509d; color: #fff; }
    .cp-badge { display: inline-block; background: #ff9800; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 14px; margin-left: 10px; }
    .cp-god-badge { display: inline-block; background: #f44336; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 14px; margin-left: 10px; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
    .item-title { font-size: 20px; font-weight: bold; margin-bottom: 20px; color: #1a1a1a; border-left: 5px solid #2575fc; padding-left: 15px; }
    .main-image { text-align: center; margin-bottom: 25px; }
    .main-image img { max-width: 100%; height: auto; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); border: 3px solid #f8f9fa; }
    .cp-meter { background: #eee; height: 12px; border-radius: 6px; overflow: hidden; margin: 15px 0; }
    .cp-bar { background: linear-gradient(90deg, #ff9800, #f44336); height: 100%; border-radius: 6px; }
    .product-info-table { width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 14px; }
    .product-info-table th { background: #f8f9fa; text-align: left; padding: 10px; border-bottom: 1px solid #eee; width: 100px; color: #666; }
    .product-info-table td { padding: 10px; border-bottom: 1px solid #eee; color: #333; }
    .sample-images { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 10px; margin-top: 20px; }
    .sample-images img { width: 100%; height: auto; border-radius: 5px; cursor: pointer; transition: opacity 0.3s; border: 1px solid #eee; }
    .sample-images img:hover { opacity: 0.8; }
    .ranking-footer { text-align: center; margin-top: 50px; padding: 20px; border-top: 1px solid #eee; color: #888; font-size: 12px; }
    </style>
    """
    
    html = f'{style}\n<div class="ranking-container">\n'
    html += f'  <div class="ranking-header">\n'
    html += f'    <h1>【{today_str}更新】{category_name}ランキング TOP{len(items)}</h1>\n'
    html += f'  </div>\n'
    
    for rank, item in enumerate(items, 1):
        source = item.get("source", "FANZA")
        raw_title = item.get("title", "タイトル不明")
        title = sanitize_text(raw_title)
        affiliate_url = item.get("affiliateURL", "#")
        image_url = item.get("imageURL", {}).get("large", "")
        
        # アイテム情報の抽出
        item_info = item.get("iteminfo", {})
        actresses = ", ".join([a.get("name") for a in item_info.get("actress", []) if a.get("name")])
        maker = ", ".join([m.get("name") for m in item_info.get("maker", []) if m.get("name")])
        label = ", ".join([l.get("name") for l in item_info.get("label", []) if l.get("name")])
        date = item.get("date", "不明")
        
        # サンプル画像の抽出 (最大5枚)
        samples = item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
        sample_html = ""
        if samples:
            sample_html = '<div class="sample-images">\n'
            for s_img in samples[:5]:
                sample_html += f'    <a href="{affiliate_url}" target="_blank" rel="noopener"><img src="{s_img}" alt="サンプル"></a>\n'
            sample_html += '  </div>\n'
        
        # コスパ指数の計算
        if source == "FANZA":
            cp = calculate_cp_index(item)
            cp_badge_class = "cp-god-badge" if cp["total"] >= 80 else "cp-badge"
            cp_label = "🔥 神コスパ" if cp["total"] >= 80 else "⚖️ コスパ指数"
            cp_val = cp["total"]
            price_display = f'{cp["price"]}円 ({cp["discount_rate"]}% OFF)'
        else:
            # MGS用
            price = item.get("prices", {}).get("price", 0)
            cp_val = 75 
            cp_badge_class = "cp-badge"
            cp_label = "💎 MGS注目作"
            price_display = f"{price}円" if price > 0 else "詳細はサイトへ"
            # cp変数を定義してNameErrorを回避
            cp = {"total": cp_val, "price": price, "discount_rate": 0}
        
        source_class = "fanza-badge" if source == "FANZA" else "mgs-badge"
        
        # カードの組み立て
        html += f'  <div class="ranking-item">\n'
        html += f'    <div class="rank-badge">第{rank}位</div>\n'
        html += f'    <div class="source-badge {source_class}">{source}</div>\n'
        html += f'    <div class="{cp_badge_class}">{cp_label}: {cp_val}pt</div>\n'
        html += f'    <div class="item-title"><a href="{affiliate_url}" target="_blank" rel="noopener" style="text-decoration: none; color: inherit;">{title}</a></div>\n'
        
        if image_url:
            html += f'    <div class="main-image">\n'
            html += f'      <a href="{affiliate_url}" target="_blank" rel="noopener">\n'
            html += f'        <img src="{image_url}" alt="{title}">\n'
            html += f'      </a>\n'
            html += f'    </div>\n'
        
        html += f'    <div style="font-size: 12px; color: #666; margin-bottom: 5px;">コスパ充実度メーター</div>\n'
        html += f'    <div class="cp-meter"><div class="cp-bar" style="width: {cp["total"]}%;"></div></div>\n'
        
        html += f'    <table class="product-info-table">\n'
        if actresses: html += f'      <tr><th>出演者</th><td>{sanitize_text(actresses)}</td></tr>\n'
        if maker: html += f'      <tr><th>メーカー</th><td>{sanitize_text(maker)}</td></tr>\n'
        if label: html += f'      <tr><th>レーベル</th><td>{sanitize_text(label)}</td></tr>\n'
        html += f'      <tr><th>現在の価格</th><td style="color: #d32f2f; font-weight: bold;">{price_display}</td></tr>\n'
        if date: html += f'      <tr><th>配信開始</th><td>{date}</td></tr>\n'
        html += f'    </table>\n'
        
        if sample_html:
            html += f'    <div style="font-size: 13px; font-weight: bold; color: #666; margin-top: 20px;">▼ サンプル画像パネル</div>\n'
            html += f'    {sample_html}\n'
            
        html += f'  </div>\n'
        
    html += '  <div class="ranking-footer">\n'
    html += f'    <p>※ランキング情報は記事作成時点（{today_str}）のものです。最新の情報はリンク先（FANZA様/MGS様サイト）にてご確認ください。</p>\n'
    html += '  </div>\n'
    html += '</div>\n'
    return html

def generate_beauty_ranking_html(items):
    """
    美人度ランキング用HTMLを生成する
    """
    today_str = datetime.datetime.now().strftime("%Y年%m月%d日")
    
    style = """
    <style>
    .beauty-container { font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; max-width: 800px; margin: 0 auto; background: #fffaf0; padding: 20px; }
    .beauty-header { background: linear-gradient(135deg, #ff69b4 0%, #ff1493 100%); color: white; padding: 30px; text-align: center; border-radius: 15px; margin-bottom: 40px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
    .beauty-header h1 { margin: 0; font-size: 26px; }
    .beauty-item { background: #fff; border-radius: 15px; padding: 25px; margin-bottom: 40px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); border: 1px solid #ffe4e1; position: relative; overflow: hidden; }
    .rank-num { position: absolute; top: 10px; left: 10px; background: #ff1493; color: #fff; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 20px; z-index: 2; }
    .beauty-score-box { background: #fff0f5; border: 2px solid #ff69b4; border-radius: 10px; padding: 15px; text-align: center; margin-bottom: 20px; }
    .beauty-score-label { font-size: 14px; color: #d02090; font-weight: bold; }
    .beauty-score-value { font-size: 32px; font-weight: bold; color: #ff1493; }
    .actress-name { font-size: 24px; font-weight: bold; text-align: center; margin: 10px 0; color: #444; border-bottom: 2px solid #ffc0cb; display: inline-block; width: 100%; }
    .actress-image { text-align: center; margin: 20px 0; }
    .actress-image img { max-width: 100%; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); border: 4px solid #fff; }
    .metrics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 20px 0; }
    .metric-item { background: #fdf5f6; padding: 10px; border-radius: 8px; font-size: 13px; }
    .metric-label { font-weight: bold; color: #888; }
    .metric-val { float: right; color: #ff1493; font-weight: bold; }
    .btn-link { display: block; background: #ff1493; color: #fff !important; text-align: center; padding: 12px; border-radius: 25px; text-decoration: none; font-weight: bold; margin-top: 20px; transition: 0.3s; }
    .btn-link:hover { background: #d02090; transform: scale(1.02); }
    </style>
    """
    
    html = f'{style}\n<div class="beauty-container">\n'
    html += f'  <div class="beauty-header">\n'
    html += f'    <h1>【AI画像解析】AV女優 美人度ランキング TOP{len(items)}</h1>\n'
    html += f'    <p style="margin: 10px 0 0;">進化心理学と黄金比に基づき、AIが客観的にスコア化（{today_str}更新）</p>\n'
    html += f'  </div>\n'
    
    for rank, item in enumerate(items, 1):
        # name, total_score, category, affiliate_url, image_url, symmetry, neoteny, proportion, dimorphism, social_meme
        name, score, _, aff_url, img_url, sym, neo, prop, dim, soc = item
        
        # アフィリエイトURLの調整
        if aff_url and "amazon.co.jp" not in aff_url:
            aff_url = aff_url.replace("namasoku-990", "namasoku-001")
            
        html += f'  <div class="beauty-item">\n'
        html += f'    <div class="rank-num">{rank}</div>\n'
        html += f'    <div class="actress-name">{name}</div>\n'
        
        if img_url:
            html += f'    <div class="actress-image"><a href="{aff_url}" target="_blank"><img src="{img_url}" alt="{name}"></a></div>\n'
            
        html += f'    <div class="beauty-score-box">\n'
        html += f'      <div class="beauty-score-label">総合美人指数</div>\n'
        html += f'      <div class="beauty-score-value">{score} <span style="font-size: 16px;">pt</span></div>\n'
        html += f'    </div>\n'
        
        html += f'    <div class="metrics-grid">\n'
        html += f'      <div class="metric-item"><span class="metric-label">左右対称性</span><span class="metric-val">{sym}%</span></div>\n'
        html += f'      <div class="metric-item"><span class="metric-label">幼形適応(ネオテニー)</span><span class="metric-val">{neo}%</span></div>\n'
        html += f'      <div class="metric-item"><span class="metric-label">プロポーション</span><span class="metric-val">{prop}%</span></div>\n'
        html += f'      <div class="metric-item"><span class="metric-label">性的二型(コントラスト)</span><span class="metric-val">{dim}%</span></div>\n'
        html += f'    </div>\n'
        
        html += f'    <a href="{aff_url}" class="btn-link" target="_blank">{name} の出演作品をチェック</a>\n'
        html += f'  </div>\n'
        
    html += '  <div style="text-align: center; color: #888; font-size: 12px; margin-top: 30px;">\n'
    html += f'    <p>※本ランキングはAIによる独自の画像解析結果に基づいています。<br/>最新の作品情報はリンク先にてご確認ください。</p>\n'
    html += '  </div>\n'
    html += '</div>\n'
    return html

def main():
    parser = argparse.ArgumentParser(description="Livedoor Blog FANZAランキング自動投稿スクリプト")
    parser.add_argument("--keyword", type=str, default=None, help="手動検索キーワード")
    parser.add_argument("--service", type=str, default="digital", help="手動指定時のサービス")
    parser.add_argument("--floor", type=str, default="videoa", help="手動指定時のフロア")
    parser.add_argument("--category", type=str, default=None, help="手動時のカテゴリ名")
    parser.add_argument("--hits", type=int, default=10, help="取得件数")
    # --draft を削除（常に公開）
    args = parser.parse_args()

    try:
        # スケジュールの決定
        if not args.keyword and not args.category:
            # メイン処理 (Livedoor用は専用DBを使用)
            db_path_fanza = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beauty_index_fanza.db")
            db = BeautyDatabase(db_path=db_path_fanza)
            
            jst = datetime.timezone(datetime.timedelta(hours=9))
            now_jst = datetime.datetime.now(jst)
            current_hour = now_jst.hour
            
            # 2時間おきにローテーション
            # 偶数時: フェチランキング, 奇数時: 美人度ランキング
            is_beauty_time = (current_hour % 2 != 0)
            
            if is_beauty_time:
                print(f"JST {current_hour}時: 美人度ランキング配信タイム")
                
                # 前回の投稿から女優リストを読み込む
                names = []
                # 複数のパス候補をチェック
                json_paths = ["last_actresses.json"]
                target_json = None
                for jp in json_paths:
                    if os.path.exists(jp):
                        target_json = jp
                        break
                
                if target_json:
                    try:
                        print(f"Loading actress list from {target_json}")
                        with open(target_json, "r", encoding="utf-8") as f:
                            names = json.load(f)
                    except Exception as e:
                        print(f"Error loading {target_json}: {e}")
                
                if names:
                    print(f"前回のランキングから女優 {len(names)} 名を抽出しました。")
                    
                    # 既にDBにあるかチェックし、なければ分析を実行（多様性を確保）
                    if BeautyManager:
                        manager = BeautyManager(db_path=db_path_fanza)
                        analyzed_count = 0
                        for name in names:
                            # 分析上限を少し増やす (3 -> 6)
                            if analyzed_count >= 6: break 
                            
                            res = db.get_score_by_name(name, category="AV")
                            if not res:
                                print(f"新着女優 {name} をAI分析中...")
                                try:
                                    # 分析を実行
                                    # strict_fanza=False にして検索ヒット率を上げる
                                    manager.run_objective_analysis(name=name, category="AV", strict_fanza=False, update_wp=False)
                                    analyzed_count += 1
                                except Exception as e:
                                    print(f"分析エラー ({name}): {e}")
                        
                        if analyzed_count == 0:
                            print("  [WARNING] 新着女優の分析が1件も成功しませんでした。")
                    else:
                        print("BeautyManagerがロードされていないため、新規分析をスキップします。")
                    
                    beauty_items = []
                    for name in names:
                        res = db.get_score_by_name(name, category="AV")
                        if res:
                            if res[3] and "amazon.co.jp" not in res[3]:
                                beauty_items.append(res)
                            else:
                                print(f"Skipping {name}: No valid affiliate URL found in DB.")
                        else:
                            print(f"Skipping {name}: Not found in Beauty Database.")
                    
                    # 多様性を出すために、最近投稿された女優を避けるロジック（オプション）
                    # 今回はシンプルにスコア順で上位10名
                    beauty_items.sort(key=lambda x: x[1], reverse=True)
                    
                    # 10件に満たない場合は、DB全体のランキングから補填する
                    if len(beauty_items) < 10:
                        all_rankings = db.get_rankings(category="AV", limit=30)
                        for r in all_rankings:
                            if len(beauty_items) >= 10: break
                            # すでにリストにないかチェック (名前で比較: r[0])
                            if not any(r[0] == item[0] for item in beauty_items):
                                if r[3] and "amazon.co.jp" not in r[3]:
                                    beauty_items.append(r)
                    
                    beauty_items = beauty_items[:10]
                    
                    if beauty_items:
                        target_category = "美人解析"
                        article_html = generate_beauty_ranking_html(beauty_items)
                        title = f"【{now_jst.strftime('%Y/%m/%d')}】AIが選ぶ！最強女優美人度解析 TOP{len(beauty_items)}"
                    else:
                        print("解析データがDBにないため、一般ランキングに切り替えます。")
                        names = [] # フォールバックへ
                
                if not names:
                    # フォールバック: 従来通り全体から取得
                    all_beauty_items = db.get_rankings(category="AV", limit=50)
                    beauty_items = [item for item in all_beauty_items if item[3] and "amazon.co.jp" not in item[3]][:10]
                    
                    if not beauty_items:
                        print("美人度データがないため、通常のランキングに切り替えます。")
                        is_beauty_time = False
                    else:
                        target_category = "美人解析"
                        article_html = generate_beauty_ranking_html(beauty_items)
                        title = f"【{now_jst.strftime('%Y/%m/%d')}】AIが選ぶ！最強AV女優美人度ランキング TOP{len(beauty_items)}"
                        print(f"Success: {len(beauty_items)} items found for fallback beauty ranking.")

            if not is_beauty_time:
                conf = SCHEDULE_24H[current_hour % 24]
                current_keyword = conf["keyword"]
                current_service = conf["service"]
                current_floor = conf["floor"]
                target_category = conf["category"]
                print(f"JST {current_hour}時: スケジュール実行 - 「{target_category}」")
                
                # DMM/FANZAから売れ筋情報を取得 (複数のフロアを試行)
                dmm = DMMClient()
                fanza_items = []
                for floor in [current_floor, "videoa", "videoc"]:
                    print(f"Fetching FANZA Top Ranking ({floor})...")
                    fanza_items = dmm.get_top_fanza_works(service=current_service, floor=floor, hits=args.hits, keyword=current_keyword)
                    if fanza_items: break
                
                if not fanza_items and current_keyword:
                    print("FANZA結果0件のため、キーワードなしで再試行...")
                    fanza_items = dmm.get_top_fanza_works(service=current_service, floor="videoa", hits=args.hits, keyword=None)

                # MGSから情報を取得
                mgs = MGSClient()
                mgs_items = mgs.search_works(current_keyword, hits=args.hits // 2 if current_keyword else 5)
                
                # 結果の統合とインターリーブ
                combined_items = []
                max_len = max(len(fanza_items), len(mgs_items))
                for i in range(max_len):
                    if i < len(fanza_items):
                        fanza_items[i]["source"] = "FANZA"
                        combined_items.append(fanza_items[i])
                    if i < len(mgs_items):
                        mgs_items[i]["source"] = "MGS"
                        combined_items.append(mgs_items[i])
                
                top_items = combined_items[:args.hits]
                
                if not top_items:
                    print(f"警告: 「{target_category}」でアイテムが1件も見つかりませんでした。スキップします。")
                    return
                    
                print(f"合計 {len(top_items)}件のアイテム（FANZA:{len(fanza_items)}, MGS:{len(mgs_items)}）を取得しました。")
                article_html = generate_html_article(top_items, target_category)
                today_str = now_jst.strftime("%Y/%m/%d")
                title = f"【{today_str}】FANZA＆MGS混合！【{target_category}】ランキング TOP{args.hits}"
                
                # 次回の美人度解析用に女優リストを保存
                actress_names = []
                for item in top_items:
                    for act in item.get("iteminfo", {}).get("actress", []):
                        name = act.get("name")
                        if name and name not in actress_names:
                            actress_names.append(name)
                
                if actress_names:
                    print(f"次回の解析用に女優 {len(actress_names)} 名を保存しました。")
                    with open("last_actresses.json", "w", encoding="utf-8") as f:
                        json.dump(actress_names, f, ensure_ascii=False)

        else:
            current_keyword = args.keyword
            current_service = args.service
            current_floor = args.floor
            target_category = args.category if args.category else (current_keyword if current_keyword else "FANZAランキング")
            print(f"手動実行 - 「{target_category}」")
            
            # 手動実行時は通常のランキングロジックを使用
            dmm = DMMClient()
            fanza_items = dmm.get_top_fanza_works(service=current_service, floor=current_floor, hits=args.hits, keyword=current_keyword)
            
            # MGSからも取得 (手動実行でも混合ランキングにする)
            mgs = MGSClient()
            mgs_items = mgs.search_works(current_keyword, hits=args.hits // 2 if current_keyword else 5)
            
            # 結果の統合
            combined_items = []
            max_len = max(len(fanza_items), len(mgs_items))
            for i in range(max_len):
                if i < len(fanza_items):
                    fanza_items[i]["source"] = "FANZA"
                    combined_items.append(fanza_items[i])
                if i < len(mgs_items):
                    mgs_items[i]["source"] = "MGS"
                    combined_items.append(mgs_items[i])
            
            top_items = combined_items[:args.hits]
            if not top_items:
                print("アイテムを取得できませんでした。")
                return
                
            article_html = generate_html_article(top_items, target_category)
            title = f"【手動】{target_category}ランキング (FANZA＆MGS)"

            # 次回の美人度解析用に女優リストを保存
            actress_names = []
            for item in top_items:
                for act in item.get("iteminfo", {}).get("actress", []):
                    name = act.get("name")
                    if name and name not in actress_names:
                        actress_names.append(name)
            
            if actress_names:
                print(f"次回の解析用に女優 {len(actress_names)} 名を保存しました。")
                with open("last_actresses.json", "w", encoding="utf-8") as f:
                    json.dump(actress_names, f, ensure_ascii=False)
        
        try:
            livedoor = LivedoorClient()
            is_publish = True
            print(f"ライブドアブログへ投稿中... [{title}] [常に公開設定]")
            res = livedoor.post_article(title, article_html, categories=[target_category], publish=is_publish)
            if res:
                print(f"ブログ投稿成功！: {title}")
            else:
                print(f"ブログ投稿失敗。")
        except Exception as e:
            print(f"ブログ投稿中にエラーが発生しました: {e}")
            traceback.print_exc()
        
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

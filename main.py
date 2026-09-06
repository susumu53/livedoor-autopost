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
from fortune_engine import FortuneEngine

# 12種類のフェチカテゴリ・ローテーション設定
RANKING_ROTATION = [
    {"service": "digital", "floor": "videoa", "keyword": "巨乳", "category": "巨乳女優"},
    {"service": "digital", "floor": "videoa", "keyword": "人妻", "category": "人妻・熟女"},
    {"service": "digital", "floor": "videoa", "keyword": "美少女", "category": "美少女女優"},
    {"service": "digital", "floor": "videoa", "keyword": "素人", "category": "素人ビデオ"},
    {"service": "digital", "floor": "videoa", "keyword": "制服", "category": "制服・コスプレ"},
    {"service": "digital", "floor": "videoa", "keyword": "お姉さん", "category": "お姉さん"},
    {"service": "digital", "floor": "videoa", "keyword": "ギャル", "category": "ギャル"},
    {"service": "digital", "floor": "videoa", "keyword": "美脚", "category": "美脚・タイツ"},
    {"service": "digital", "floor": "videoa", "keyword": "中出し", "category": "中出し"},
    {"service": "digital", "floor": "videoa", "keyword": "VR", "category": "VRアダルト動画"},
    {"service": "digital", "floor": "videoa", "keyword": "競泳水着", "category": "競泳水着・スク水"},
    {"service": "digital", "floor": "videoa", "keyword": "熟女", "category": "熟女人気"},
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

def generate_single_beauty_article_html(res_data, works):
    """
    1人の美人分析詳細記事用HTMLを生成する (個人分析スタイル)
    res_data: (name, score, category, aff_url, img_url, sym, neo, prop, dim, soc)
    works: 関連作品リスト
    """
    name, score, _, aff_url, img_url, sym, neo, prop, dim, soc = res_data
    
    # アフィリエイトID調整
    if aff_url and "amazon.co.jp" not in aff_url:
        aff_url = aff_url.replace("namasoku-990", "namasoku-001")

    html = f"""
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; max-width: 800px; margin: 0 auto; background: #fffaf0; padding: 20px; border-radius: 15px; border: 1px solid #ffe4e1;">
        <h2 style="text-align: center; color: #d02090; border-bottom: 2px solid #ff69b4; padding-bottom: 10px;">【私個人の分析】{name} さんの圧倒的な美の理由を解説</h2>
        
        <p>こんにちは。今回は、私が個人的に注目している <b>{name}</b> さんについて、独自の解析ツールと進化心理学の視点からその魅力を徹底的に分析してみました。なぜ彼女がこれほどまでに惹きつけるのか、その「根拠」を数値とともに詳しくお伝えします。</p>

        <div style="background-color: #fff0f5; padding: 20px; border-radius: 10px; text-align: center; margin: 30px 0; border: 2px solid #ff69b4;">
            <h3 style="margin-top: 0; color: #d02090;">独自に算出した「美人指数」</h3>
            <span style="font-size: 3em; font-weight: bold; color: #ff1493;">{score}</span> <span style="font-size: 1.2em; color: #555;">pt</span>
            <p style="font-size: 0.9em; color: #666; margin-top: 10px;">※最高水準の美しさを誇る驚異的なスコアです</p>
        </div>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{aff_url}" target="_blank" rel="noopener">
                <img src="{img_url}" alt="{name}" style="max-width: 100%; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border: 2px solid #ffc0cb;" />
                <p style="font-size: 0.8em; color: #ff1493; margin-top: 5px;">（画像をクリックして詳細をチェック）</p>
            </a>
        </div>

        <h3 style="color: #ff1493; border-left: 5px solid #ff1493; padding-left: 10px;">分析の根拠1：左右対称性（シンメトリー） {sym}%</h3>
        <p>私の分析でまず注目したのは、彼女の顔の驚異的な「シンメトリー」です。進化心理学では、顔の対称性は遺伝的な健康さを示す指標とされており、人は本能的に美しさを感じます。{name}さんは左右のバランスが極めて整っており、これが清潔感と品格を生み出しています。</p>

        <h3 style="color: #ff1493; border-left: 5px solid #ff1493; padding-left: 10px;">分析の根拠2：若々しさの指標（ネオテニー） {neo}%</h3>
        <p>次に注目すべきは、目の配置や大きさに現れる「ネオテニー（幼形適応）」の要素です。守ってあげたくなるような愛くるしさが、この高い数値に現れています。大人の色気の中に共存する、この「少女のような無垢さ」こそが彼女の大きな武器と言えるでしょう。</p>

        <h3 style="color: #ff1493; border-left: 5px solid #ff1493; padding-left: 10px;">分析の根拠3：黄金比に基づくプロポーション {prop}%</h3>
        <p>顔の各パーツの配置を測定したところ、科学的に最も美しいとされる「黄金比」に非常に近いことがわかりました。無意識に「整っている」と感じさせる安定感は、この完璧な配置から来ています。</p>

        <h3 style="color: #ff1493; border-left: 5px solid #ff1493; padding-left: 10px;">分析の根拠4：女性的な魅力（性的二型） {dim}%</h3>
        <p>唇の厚みや顎のラインなど、女性特有のチャームポイントがどれだけ際立っているかを示す指標です。{name}さんはこのコントラストが非常に強く、一目見ただけで引き込まれるような強い女性的魅力を放っています。</p>

        <h3 style="color: #ff1493; border-left: 5px solid #ff1493; padding-left: 10px;">分析の根拠5：時代が求める美（トレンド度） {soc}%</h3>
        <p>最後に、現在のSNSや検索トレンドなどの社会的評価を加味しました。今、多くの人が求めている「旬の美しさ」を彼女は完璧に体現しており、その話題性がスコアを後押ししています。</p>

        <hr style="margin: 40px 0; border: 0; border-top: 1px dashed #ff69b4;" />

        <h3 style="text-align: center; color: #d02090;">【厳選】{name} さんの魅力を堪能できる作品</h3>
        <p style="text-align: center; font-size: 0.9em; color: #666;">今回分析の対象となった、彼女の魅力が詰まった作品をご紹介します。画像から詳細を確認できます。</p>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; margin-top: 20px;">
    """
    
    for item in works[:8]:
        t = item.get('title', '')
        i_url = item.get('imageURL', {}).get('large', '')
        a_url = item.get('affiliateURL', '').replace("namasoku-990", "namasoku-001")
        
        html += f"""
            <div style="background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); text-align: center;">
                <a href="{a_url}" target="_blank" rel="noopener">
                    <img src="{i_url}" style="width: 100%; border-radius: 5px; margin-bottom: 8px;" alt="{t}">
                </a>
                <div style="font-size: 12px; line-height: 1.4; height: 3em; overflow: hidden; margin-bottom: 8px;">
                    <a href="{a_url}" target="_blank" rel="noopener" style="text-decoration: none; color: #333;">{t}</a>
                </div>
                <a href="{a_url}" target="_blank" rel="noopener" style="display: inline-block; background: #ff1493; color: #fff; padding: 5px 10px; border-radius: 15px; text-decoration: none; font-size: 12px; font-weight: bold;">作品をチェック</a>
            </div>
        """
        
    html += """
        </div>
        <div style="margin-top: 30px; text-align: center; font-size: 0.8em; color: #888;">
            <p>※本分析はあくまで個人の視点と独自の解析システムによるものです。<br/>最新の作品情報はリンク先の公式サイトにてご確認ください。</p>
        </div>
    </div>
    """
    return html

def generate_fortune_article_html(actress_name, chart, works):
    """
    四柱推命・運勢鑑定記事用HTMLを生成する
    """
    theme_color = "#6b0f9c" # 占いらしい紫
    
    # 命式データの展開
    dm = chart["day_master"]
    trends = chart["luck_trends"]
    
    html = f"""
    <div style="font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', sans-serif; color: #333; max-width: 800px; margin: 0 auto; background: #fdfcff; padding: 25px; border: 2px solid {theme_color}; border-radius: 20px; box-shadow: 0 10px 30px rgba(107, 15, 156, 0.1);">
        <div style="text-align: center; margin-bottom: 30px; border-bottom: 3px double {theme_color}; padding-bottom: 20px;">
            <p style="color: {theme_color}; font-weight: bold; margin-bottom: 5px;">★ 運命の鑑定書 ★</p>
            <h1 style="margin: 0; color: #4b0082; font-size: 26px;">{actress_name} 様 の宿命と未来予測</h1>
        </div>

        <p style="line-height: 1.8;">
            最新の四柱推命ロジック「Fortune Engine」を用いて、<b>{actress_name}</b> さんの本質と運勢のバイオリズムを徹底鑑定しました。
            日主「{dm['stem']}」が導き出す、彼女の本当の姿とは？
        </p>

        <div style="background: {theme_color}; color: white; padding: 15px; border-radius: 10px; margin: 30px 0;">
            <h2 style="margin: 0; font-size: 18px; text-align: center;">☯ 魂の本質（日主：{dm['stem']} - {dm['element']}）</h2>
        </div>
        <p style="padding: 15px; background: #f5f0ff; border-left: 5px solid {theme_color}; border-radius: 0 10px 10px 0;">
            <b>【性格診断】</b><br/>{chart['personality']}
        </p>

        <div style="background: {theme_color}; color: white; padding: 15px; border-radius: 10px; margin: 30px 0;">
            <h2 style="margin: 0; font-size: 18px; text-align: center;">📈 運勢推移（過去・現在・未来）</h2>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px; text-align: center;">
            <tr style="background: #e6e0f8; color: {theme_color};">
                <th style="padding: 12px; border: 1px solid #ddd;">時期</th>
                <th style="padding: 12px; border: 1px solid #ddd;">総合</th>
                <th style="padding: 12px; border: 1px solid #ddd;">仕事</th>
                <th style="padding: 12px; border: 1px solid #ddd;">恋愛</th>
                <th style="padding: 12px; border: 1px solid #ddd;">金運</th>
                <th style="padding: 12px; border: 1px solid #ddd;">健康</th>
            </tr>
    """
    
    for tr in trends:
        bg = "#fff" if tr['label'] != "現在" else "#fff0f5"
        weight = "bold" if tr['label'] == "現在" else "normal"
        
        # 星による視覚化
        def get_stars(score):
            count = max(1, min(5, round(score / 20)))
            return "★" * count + "☆" * (5 - count)
            
        html += f"""
            <tr style="background: {bg}; font-weight: {weight};">
                <td style="padding: 12px; border: 1px solid #ddd;">{tr['year']}年 ({tr['label']})</td>
                <td style="padding: 12px; border: 1px solid #ddd; color: #d32f2f;"><span style="color: #ff9800;">{get_stars(tr['overall'])}</span><br/>{tr['overall']}</td>
                <td style="padding: 12px; border: 1px solid #ddd;">{tr['career']}</td>
                <td style="padding: 12px; border: 1px solid #ddd;">{tr['love']}</td>
                <td style="padding: 12px; border: 1px solid #ddd; color: #c09000;">{tr['wealth']}</td>
                <td style="padding: 12px; border: 1px solid #ddd;">{tr['health']}</td>
            </tr>
        """
        
    html += f"""
        </table>

        <div style="margin-top: 40px; padding-top: 20px; border-top: 2px dashed #ddd;">
            <h3 style="text-align: center; color: {theme_color};">✨ 関連作品ピックアップ</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px; margin-top: 20px;">
    """
    
    for item in works[:4]:
        t = item.get('title', '')
        i_url = item.get('imageURL', {}).get('large', '')
        a_url = item.get('affiliateURL', '').replace("namasoku-990", "namasoku-001")
        
        html += f"""
            <div style="background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); text-align: center;">
                <a href="{a_url}" target="_blank">
                    <img src="{i_url}" style="width: 100%; border-radius: 5px; margin-bottom: 8px;" alt="{t}">
                </a>
                <div style="font-size: 11px; line-height: 1.4; height: 3em; overflow: hidden; margin-bottom: 8px;">
                    <a href="{a_url}" target="_blank" style="text-decoration: none; color: #333;">{t}</a>
                </div>
            </div>
        """
        
    html += """
            </div>
        </div>
        
        <div style="margin-top: 30px; text-align: center; font-size: 0.8em; color: #888;">
            <p>※分析結果は四柱推命の伝統的な理論に基づく独自の鑑定です。<br/>運命は自らの行動で切り拓くものです。日々の彩りとしてお楽しみください。</p>
        </div>
    </div>
    """
    return html

from curation_engine import CurationEngine, THEMES
from sex_technique_engine import SexTechniqueEngine, CATEGORIES as SEX_TECH_CATEGORIES

def main():
    parser = argparse.ArgumentParser(description="Livedoor Blog 美女まとめ＆セックステクニック自動投稿スクリプト")
    parser.add_argument("--mode", type=str, default="curation", choices=["curation", "legacy", "sex_tech", "ranking"], help="投稿モード (curation: 週2回まとめ特集, legacy: 従来ランキング, sex_tech: セックステクニック解説, ranking: 毎日お昼の売れ筋ランキングTOP10)")
    parser.add_argument("--theme", type=str, default=None, help="まとめ特集テーマ (cosplay, bishojo, legs, mature, busty, ranking)")
    parser.add_argument("--count", type=int, default=20, help="まとめ記事に掲載する人数/件数 (デフォルト: 20)")
    parser.add_argument("--dry-run", action="store_true", help="ブログに投稿せず生成テストのみ行う")
    
    # レガシーおよびセックステクニック用オプション
    parser.add_argument("--keyword", type=str, default=None, help="手動検索キーワード")
    parser.add_argument("--service", type=str, default="digital", help="手動指定時のサービス")
    parser.add_argument("--floor", type=str, default="videoa", help="手動指定時のフロア")
    parser.add_argument("--category", type=str, default=None, help="手動時のカテゴリ名 (sex_tech時は foreplay, positions, zones, oral, mind, goods など)")
    parser.add_argument("--hits", type=int, default=10, help="取得件数")
    parser.add_argument("--blog-id", type=str, default="ranking000", help="対象ブログID (デフォルト: ranking000)")
    args = parser.parse_args()

    title = None
    article_html = None
    target_category = "美女まとめ"
    post_tags = []

    try:
        if args.mode == "ranking":
            # === 【毎日お昼12時用】12大フェチジャンル日替わり売れ筋ランキングTOP10 ===
            today = datetime.datetime.now()
            day_of_year = today.timetuple().tm_yday
            rot_item = RANKING_ROTATION[day_of_year % len(RANKING_ROTATION)]
            target_category = args.category or rot_item["category"]
            target_keyword = args.keyword or rot_item["keyword"]
            service = rot_item.get("service", "digital")
            floor = rot_item.get("floor", "videoa")

            print(f"【日替わりランキング自動実行】 ジャンル: {target_category} (キーワード: {target_keyword})")
            dmm = DMMClient()
            f_items = dmm.get_top_fanza_works(service=service, floor=floor, hits=args.hits, keyword=target_keyword)
            m_items = MGSClient().search_works(target_keyword, hits=args.hits // 2)
            combined = []
            for i in range(max(len(f_items), len(m_items))):
                if i < len(f_items): f_items[i]["source"]="FANZA"; combined.append(f_items[i])
                if i < len(m_items): m_items[i]["source"]="MGS"; combined.append(m_items[i])
            top_items = combined[:args.hits]
            if top_items:
                # 1位の作品画像をライブドアにアップロードしてOGP画像に自動設定
                if not args.dry_run and top_items[0].get("imageURL", {}).get("large"):
                    try:
                        livedoor = LivedoorClient(blog_id=args.blog_id)
                        uploaded_img = livedoor.upload_image(top_items[0]["imageURL"]["large"])
                        if uploaded_img:
                            top_items[0]["imageURL"]["large"] = uploaded_img
                    except Exception as img_err:
                        print(f"[ランキング画像アップロード例外] {img_err}")

                article_html = generate_html_article(top_items, target_category)
                date_str = today.strftime("%Y/%m/%d")
                title = f"【{date_str}】FANZA＆MGS混合！【{target_category}】売れ筋ランキング TOP{len(top_items)}"
                post_tags = [target_category, "ランキング", "FANZA", "MGS"]

        elif args.mode == "sex_tech":
            # === 【新機能】pan-pan.co風 セックステクニック自動生成モード ===
            engine = SexTechniqueEngine()
            selected_cat = args.category if args.category in SEX_TECH_CATEGORIES else None
            title, article_html, target_category, post_tags = engine.generate_article_content(
                cat_key=selected_cat or list(SEX_TECH_CATEGORIES.keys())[0],
                topic_info=SEX_TECH_CATEGORIES[selected_cat or list(SEX_TECH_CATEGORIES.keys())[0]]["topics"][0]
            )

        elif args.mode == "curation" and not args.keyword:
            # === 【新機能】週2回・20〜30人まとめ特集モード ===
            jst = datetime.timezone(datetime.timedelta(hours=9))
            now_jst = datetime.datetime.now(jst)
            weekday = now_jst.weekday()  # 0:月, 2:水, 6:日
            week_num = now_jst.isocalendar()[1]
            
            # テーマの決定（引数指定がなければ曜日別にローテーション）
            target_theme = args.theme
            if not target_theme:
                if weekday == 2:  # 水曜日: フェチ・特化ジャンル特集
                    special_rotation = ["cosplay", "legs", "mature", "busty"]
                    target_theme = special_rotation[week_num % len(special_rotation)]
                elif weekday == 6:  # 日曜日: 総合ランキング・王道美少女
                    sunday_rotation = ["ranking", "bishojo"]
                    target_theme = sunday_rotation[week_num % len(sunday_rotation)]
                else:
                    # その他の曜日（手動実行等）
                    all_keys = list(THEMES.keys())
                    target_theme = all_keys[now_jst.day % len(all_keys)]

            print(f"【週2回まとめ特集実行】 テーマ: {target_theme} | 掲載数: {args.count}件")
            engine = CurationEngine()
            title, article_html, target_category, tags = engine.generate_weekly_article_html(
                theme_key=target_theme, count=args.count
            )
            post_tags = [target_category] + [t for t in tags if t != target_category][:15]

        elif args.keyword or args.category or args.mode == "legacy":
            # === 従来の個別/手動ランキングモード（互換性維持） ===
            target_category = args.category or args.keyword or "FANZAランキング"
            print(f"従来手動実行 - 「{target_category}」")
            dmm = DMMClient()
            f_items = dmm.get_top_fanza_works(service=args.service, floor=args.floor, hits=args.hits, keyword=args.keyword)
            m_items = MGSClient().search_works(args.keyword, hits=args.hits // 2 if args.keyword else 5)
            combined = []
            for i in range(max(len(f_items), len(m_items))):
                if i < len(f_items): f_items[i]["source"]="FANZA"; combined.append(f_items[i])
                if i < len(m_items): m_items[i]["source"]="MGS"; combined.append(m_items[i])
            top_items = combined[:args.hits]
            if top_items:
                article_html = generate_html_article(top_items, target_category)
                title = f"【私個人の厳選】{target_category} 今チェックすべきランキング TOP{args.hits}"
                post_tags = [target_category]

        # 最終的な投稿処理
        if title and article_html:
            if args.dry_run:
                print(f"[DRY-RUN成功] タイトル: {title}")
                print(f"[DRY-RUN成功] カテゴリー: {target_category}")
                print(f"[DRY-RUN成功] タグ数: {len(post_tags)}")
                print(f"[DRY-RUN成功] HTML文字数: {len(article_html)}")
            else:
                livedoor = LivedoorClient(blog_id=args.blog_id)
                print(f"ライブドアブログへ投稿中... [{title}]")
                res = livedoor.post_article(title, article_html, categories=post_tags, publish=True)
                if res:
                    print(f"ブログ投稿成功！: {title}")
                    try:
                        import xml.etree.ElementTree as ET
                        from notifier import ArticleNotifier
                        root = ET.fromstring(res)
                        ns = {'atom': 'http://www.w3.org/2005/Atom'}
                        alt_links = [l.attrib.get('href') for l in root.findall('atom:link', ns) if l.attrib.get('rel') == 'alternate']
                        art_url = alt_links[0] if alt_links else f"https://ranking000.livedoor.blog/"
                        
                        notifier = ArticleNotifier()
                        notifier.send_notification_email(title=title, article_url=art_url, category=target_category)
                    except Exception as notify_err:
                        print(f"通知処理エラー: {notify_err}")
                else:
                    print(f"ブログ投稿失敗。")
        else:
            print("投稿対象のデータが生成されなかったため、スキップします。")
            
    except Exception as e:
        print(f"エラー発生: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()


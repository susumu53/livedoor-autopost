import html
import os
import urllib.parse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_AMAZON_TAG = "blogseesaa090-22"
DEFAULT_MGS_ID = "4KJKIW7EGE6YZLCITH4A5FMOLN"

A8_BANNERS_HTML = (
    '<div class="rk-a8-banners" style="display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:16px;margin-top:18px;padding-top:16px;border-top:1px dashed #f59e0b;">'
    '<div><a href="https://px.a8.net/svt/ejp?a8mat=4BGCFA+7N2H7E+3RN2+63WO1" rel="nofollow" target="_blank">'
    '<img border="0" width="300" height="250" alt="" src="https://www20.a8.net/svt/bgt?aid=261103078462&wid=010&eno=01&mid=s00000017579001026000&mc=1" style="max-width:100%;height:auto;border-radius:10px;box-shadow:0 4px 12px rgba(0,0,0,.08);"></a>'
    '<img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=4BGCFA+7N2H7E+3RN2+63WO1" alt=""></div>'
    '<div><a href="https://px.a8.net/svt/ejp?a8mat=4BGCFA+6S3XQY+9FQ+6CHB5" rel="nofollow" target="_blank">'
    '<img border="0" width="350" height="240" alt="" src="https://www22.a8.net/svt/bgt?aid=261103078410&wid=010&eno=01&mid=s00000001223001066000&mc=1" style="max-width:100%;height:auto;border-radius:10px;box-shadow:0 4px 12px rgba(0,0,0,.08);"></a>'
    '<img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=4BGCFA+6S3XQY+9FQ+6CHB5" alt=""></div>'
    '</div>'
)


def get_amazon_url(query, tag=None):
    amz_tag = tag or os.getenv("AMAZON_ASSOCIATE_TAG", DEFAULT_AMAZON_TAG)
    q = urllib.parse.quote(query)
    return f"https://www.amazon.co.jp/s?k={q}&tag={amz_tag}"


def get_kindle_unlimited_url(tag=None):
    amz_tag = tag or os.getenv("AMAZON_ASSOCIATE_TAG", DEFAULT_AMAZON_TAG)
    return f"https://www.amazon.co.jp/kindle-dbs/hz/signup?tag={amz_tag}"


def get_mgs_top_url(mgs_id=None):
    mid = mgs_id or os.getenv("MGS_AFFILIATE_ID", DEFAULT_MGS_ID)
    return f"https://www.mgstage.com/ppv/{mid}/"


def build_monetize_section(subject=None, mode="general"):
    """
    Amazonアソシエイト・Kindle Unlimited・MGS動画・A8.netバナー2種を組み合わせた
    共通収益化セクションHTMLを返す。
    mode: "technique" | "review" | "ranking" | "general"
    """
    e = html.escape
    amz_tag = os.getenv("AMAZON_ASSOCIATE_TAG", DEFAULT_AMAZON_TAG)
    mgs_url = get_mgs_top_url()
    kindle_url = get_kindle_unlimited_url(amz_tag)

    if mode == "technique":
        kw = subject or "ラブグッズ カップル 人気"
        amz_main = get_amazon_url(f"{kw} 人気 ランキング", amz_tag)
        amz_sub = get_amazon_url("ナイトケア アロマ マッサージオイル", amz_tag)
        main_label = "🛒 Amazonで人気の関連アイテム・ケアグッズを見る"
        sub_label = "🌿 Amazonで人気のアロマ・マッサージオイルを見る"
    elif subject:
        amz_main = get_amazon_url(f"{subject} 写真集 DVD", amz_tag)
        amz_sub = get_amazon_url(f"{subject} グッズ 雑誌", amz_tag)
        main_label = f"📦 Amazonで「{e(subject)}」の写真集・DVDを探す"
        sub_label = f"🎁 Amazonで「{e(subject)}」の関連アイテムを見る"
    else:
        amz_main = get_amazon_url("グラビア 写真集 人気ランキング", amz_tag)
        amz_sub = get_amazon_url("カップル 人気 ケアグッズ", amz_tag)
        main_label = "📦 Amazonで人気の写真集・DVDランキングを見る"
        sub_label = "🎁 Amazonで人気のナイトケア・関連グッズを見る"

    btn_style_base = (
        "display:block;padding:12px 14px;border-radius:25px;font-weight:bold;"
        "font-size:14px;text-decoration:none;color:#fff!important;text-align:center;"
        "box-shadow:0 3px 10px rgba(0,0,0,.1);"
    )

    btns_html = (
        f'<a href="{e(mgs_url)}" target="_blank" rel="nofollow noopener" '
        f'style="{btn_style_base}background:linear-gradient(135deg,#ec4899,#be185d);">'
        f'🎬 MGS動画で人気女優・独占配信作品をチェック</a>'
        f'<a href="{e(amz_main)}" target="_blank" rel="nofollow noopener" '
        f'style="{btn_style_base}background:linear-gradient(135deg,#f59e0b,#d97706);">'
        f'{main_label}</a>'
        f'<a href="{e(kindle_url)}" target="_blank" rel="nofollow noopener" '
        f'style="{btn_style_base}background:linear-gradient(135deg,#2563eb,#1d4ed8);">'
        f'📚 Kindle Unlimited（30日間無料）で写真集・実用書を読み放題</a>'
        f'<a href="{e(amz_sub)}" target="_blank" rel="nofollow noopener" '
        f'style="{btn_style_base}background:linear-gradient(135deg,#059669,#047857);">'
        f'{sub_label}</a>'
    )

    return (
        '<div class="rk-monetize-box" style="background:linear-gradient(135deg,#fffbeb,#fef3c7);'
        'border:2px solid #f59e0b;border-radius:14px;padding:20px;margin:32px 0;text-align:center;">'
        '<h3 style="margin:0 0 8px;color:#92400e;font-size:18px;">📚 公式配信＆関連アイテムをお得にチェック</h3>'
        '<p style="margin:0 0 12px;font-size:13px;color:#78350f;">'
        '動画配信・Amazon公式ストア・Kindle Unlimited読み放題・おすすめサービスはこちらからご覧いただけます。'
        '</p>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:12px;">'
        f'{btns_html}'
        '</div>'
        f'{A8_BANNERS_HTML}'
        '</div>'
    )


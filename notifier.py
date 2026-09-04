import os
import urllib.parse
import smtplib
import ssl
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

class ArticleNotifier:
    def __init__(self):
        self.to_email = "garoa53@yahoo.co.jp"
        # スマホプッシュ通知用トピック（登録不要・完全無料）
        self.push_topic = os.getenv("NTFY_TOPIC", "garoa-blog-post")
        
        # SMTP設定
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.mail.yahoo.co.jp")
        self.smtp_port = int(os.getenv("SMTP_PORT", "465"))
        self.smtp_user = os.getenv("YAHOO_USER", "garoa53@yahoo.co.jp")
        self.smtp_pass = os.getenv("YAHOO_PASSWORD") or os.getenv("SMTP_PASSWORD") or ""

    def _determine_blog_meta(self, article_url, blog_title=None, category=None, hashtags=None):
        """ブログの種類（美女図鑑 or 大人の性教育）と最適なタグ・文面を自動判定"""
        if blog_title:
            resolved_title = blog_title
        elif "bijozukan" in article_url:
            resolved_title = "美女図鑑"
        else:
            resolved_title = "大人の性教育"

        if not category:
            resolved_category = "美女総集編" if resolved_title == "美女図鑑" else "セックステクニック"
        else:
            resolved_category = category

        if hashtags:
            resolved_tags = list(hashtags)
        else:
            if resolved_title == "美女図鑑":
                resolved_tags = ["美女図鑑", "美女", "グラビア"]
                if resolved_category and resolved_category not in resolved_tags:
                    resolved_tags.append(resolved_category)
            else:
                resolved_tags = [resolved_category, "大人の性教育", "夜の営み"]

        tag_icons = ["sparkles", "camera"] if resolved_title == "美女図鑑" else ["sparkles", "memo"]
        return resolved_title, resolved_category, resolved_tags, tag_icons

    def generate_intent_url(self, title, article_url, hashtags=None, blog_title=None, cache_bust=True):
        """X (Twitter) 公式 Web Intent 投稿URLを生成"""
        resolved_title, _, resolved_tags, _ = self._determine_blog_meta(
            article_url, blog_title=blog_title, hashtags=hashtags
        )
            
        tags_str = " ".join([f"#{t.replace(' ', '_')}" for t in resolved_tags])
        tweet_text = f"{title} - {resolved_title}\n\n{tags_str}"
        
        # Xが過去のOGP（画像なし等）をキャッシュしているのを防ぐため、キャッシュクリア用パラメータを付与
        post_url = article_url
        if cache_bust and "archives" in article_url:
            sep = "&" if "?" in article_url else "?"
            post_url = f"{article_url}{sep}ogp=1"

        encoded_text = urllib.parse.quote(tweet_text)
        encoded_url = urllib.parse.quote(post_url)
        
        return f"https://x.com/intent/tweet?text={encoded_text}&url={encoded_url}", tweet_text

    def send_push_notification(self, title, article_url, intent_url, category=None, blog_title=None, image_url=None):
        """スマホ・ブラウザへ直接プッシュ通知を送信（ワンタップボタン付き・アイキャッチ画像プレビュー対応）"""
        try:
            resolved_title, resolved_category, _, tag_icons = self._determine_blog_meta(
                article_url, blog_title=blog_title, category=category
            )
            url = f"https://ntfy.sh"
            payload = {
                "topic": self.push_topic,
                "title": f"✨ 【{resolved_title}】新着記事公開！",
                "message": f"【{resolved_category}】\n{title}\n\n記事URL: {article_url}\n\n下のボタンを押すと𝕏の投稿画面が開き、アイキャッチ付きでポストできます！",
                "priority": 4,
                "tags": tag_icons,
                "actions": [
                    {
                        "action": "view",
                        "label": "𝕏 にポストする",
                        "url": intent_url
                    },
                    {
                        "action": "view",
                        "label": "記事を読む",
                        "url": article_url
                    }
                ]
            }
            if image_url:
                payload["attach"] = image_url
            
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                print(f"[プッシュ通知] 通知を送信しました！ ({resolved_title})")
                print(f"確認URL: https://ntfy.sh/{self.push_topic}")
                return True
            else:
                print(f"[通知送信レスポンス] {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[プッシュ通知エラー] {e}")
        return False

    def send_notification_email(self, title, article_url, category=None, blog_title=None, hashtags=None, image_url=None):
        """通知メールおよびスマホプッシュ通知を送信"""
        resolved_title, resolved_category, resolved_tags, _ = self._determine_blog_meta(
            article_url, blog_title=blog_title, category=category, hashtags=hashtags
        )
        intent_url, tweet_body = self.generate_intent_url(
            title, article_url, hashtags=resolved_tags, blog_title=resolved_title
        )

        # 1. スマホ・ブラウザへ即時プッシュ通知（パスワード不要・確実）
        self.send_push_notification(
            title, article_url, intent_url, category=resolved_category, blog_title=resolved_title, image_url=image_url
        )

        # 2. ローカルHTMLプレビュー保存
        preview_dir = os.path.join(os.path.dirname(__file__), "scratch")
        os.makedirs(preview_dir, exist_ok=True)
        preview_path = os.path.join(preview_dir, "latest_tweet_intent.html")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Xワンタップ投稿 - {resolved_title}</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f4f6f9; padding: 20px; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 14px; padding: 25px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;">
                <div style="border-bottom: 2px solid #ff4081; padding-bottom: 12px; margin-bottom: 20px;">
                    <h2 style="font-size: 18px; color: #1a1a2e; margin: 0;">✨ 新しいブログ記事が公開されました！【{resolved_title}】</h2>
                </div>
                <div style="background: #fdf2f8; border-left: 4px solid #ec4899; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <div style="font-size: 11px; font-weight: bold; color: #be185d;">カテゴリー: {resolved_category}</div>
                    <div style="font-size: 16px; font-weight: bold; color: #1e293b; margin: 8px 0 10px 0;">{title}</div>
                    <a href="{article_url}" target="_blank" style="font-size: 12px; color: #3b82f6;">{article_url}</a>
                </div>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{intent_url}" target="_blank" style="display: inline-block; background: #000000; color: #ffffff; font-size: 16px; font-weight: bold; text-decoration: none; padding: 15px 35px; border-radius: 30px; box-shadow: 0 6px 16px rgba(0,0,0,0.25);">
                        𝕏 にワンタップでポストする ＞
                    </a>
                </div>
                <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 14px; font-size: 13px; color: #475569;">
                    <div style="font-weight: bold; margin-bottom: 6px;">📝 ポストされる文面:</div>
                    <div style="white-space: pre-wrap;">{tweet_body}
{article_url}</div>
                </div>
            </div>
        </body>
        </html>
        """
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 3. SMTPメール送信（パスワードが設定されていて接続できる場合）
        if self.smtp_pass:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"【X投稿リンク/{resolved_title}】{title[:30]}..."
                msg["From"] = self.smtp_user
                msg["To"] = self.to_email
                msg.attach(MIMEText(html_content, "html", "utf-8"))

                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context, timeout=10) as server:
                    server.login(self.smtp_user, self.smtp_pass)
                    server.sendmail(self.smtp_user, self.to_email, msg.as_string())
                print(f"[メール送信] {self.to_email} へ正常に送信しました！")
            except Exception as e:
                print(f"[メール送信スキップ/エラー] {e}")

        return intent_url

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="X Web Intent通知送信ツール")
    parser.add_argument("--url", type=str, help="記事URL")
    parser.add_argument("--title", type=str, help="記事タイトル")
    parser.add_argument("--category", type=str, default=None, help="カテゴリー")
    parser.add_argument("--blog-title", type=str, default=None, help="ブログ名 (美女図鑑 / 大人の性教育)")
    parser.add_argument("--tags", type=str, nargs="*", default=None, help="ハッシュタグリスト")
    args = parser.parse_args()

    notifier = ArticleNotifier()
    if args.url and args.title:
        notifier.send_notification_email(
            title=args.title,
            article_url=args.url,
            category=args.category,
            blog_title=args.blog_title,
            hashtags=args.tags
        )
    else:
        # デフォルト動作テスト
        notifier.send_notification_email(
            title="手マンで必ず悦ばせる指使いの正解！回転・ストロークと愛液を促すテンポ",
            article_url="https://ranking000.livedoor.blog/archives/14758577.html",
            category="前戯・愛撫"
        )

import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from app.core.config import settings

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enable_notify = settings.ENABLE_TELEGRAM_NOTIFY
        
        # 添加除錯資訊
        print(f"Bot Token: {self.bot_token}")
        print(f"Chat ID: {self.chat_id}")
        print(f"Enable Notify: {self.enable_notify}")

    def send_message(self, message, parse_mode='Markdown'):
        """發送 Telegram 通知"""
        if not self.enable_notify:
            print("Telegram 通知已停用")
            return

        if not all([self.bot_token, self.chat_id]):
            print("Telegram 設定不完整")
            return

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=data)
            response.raise_for_status()
            print("Telegram 通知發送成功")
        except Exception as e:
            print(f"Telegram 通知發送失敗: {str(e)}")

    def format_success_message(self, duration, environment="本地開發", log_summary=None):
        """格式化成功訊息"""
        message = [
            "*FPG 自動化流程執行報告* 🤖\n",
            "📊 *執行資訊*",
            "-" * 30,
            f"*執行狀態*: ✅ 成功",
            f"*執行時間*: {duration} 秒",
            f"*執行環境*: {environment}",
            f"*執行時間*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "-" * 30
        ]
        
        if log_summary:
            message.extend([
                "\n📝 *執行日誌摘要*:",
                "```",
                log_summary,
                "```"
            ])
        
        return "\n".join(message)

    def format_error_message(self, error):
        """格式化錯誤訊息"""
        return "\n".join([
            "*FPG 自動化流程執行報告* 🤖\n",
            "❌ *執行失敗*",
            f"錯誤信息: {str(error)}"
        ])

# 測試用
if __name__ == "__main__":
    notifier = TelegramNotifier()
    # 測試成功訊息
    success_msg = notifier.format_success_message(
        duration=10,
        log_summary="16:21 • 開始搜尋\n16:22 • 搜尋完成"
    )
    notifier.send_message(success_msg) 
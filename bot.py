import os
import requests

# Securely grab credentials from GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_simple_test():
    print(f"Attempting to connect to Telegram...")
    print(f"Target Chat ID being used: {CHAT_ID}")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": "🚀 Connection Success! Goldin Baseball Bot can talk to your Telegram!"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram API Gateway Response Status: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"Network Connection Error: {e}")

if __name__ == "__main__":
    send_simple_test()

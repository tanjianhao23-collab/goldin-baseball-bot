import os
import re
import datetime
import json
import requests
from google import genai
from google.genai import types

# Secure environment extraction from GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Singapore All-In Costs Formula Multipliers
BUYERS_PREMIUM = 0.22
EST_SHIPPING_SGD = 25.00
USD_TO_SGD = 1.35

# Initialize Upgraded Gemini Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

def calculate_max_goldin_bid(market_value_usd):
    """
    Reverse-engineers your SG shipping formula to determine the exact 
    maximum hammer price you can bid on Goldin before losing money.
    """
    if not market_value_usd or market_value_usd <= 0:
        return 0.0
    market_value_sgd = market_value_usd * USD_TO_SGD
    max_allowable_usd_with_bp = (market_value_sgd - EST_SHIPPING_SGD) / USD_TO_SGD
    max_hammer_bid = max_allowable_usd_with_bp / (1 + BUYERS_PREMIUM)
    return round(max_hammer_bid, 2)

def load_watchlist():
    """Reads target links directly from your repository text file."""
    filename = "watchlist.txt"
    if not os.path.exists(filename):
        print(f"⚠️ '{filename}' not found. Please create it in your repo root.")
        return []
    with open(filename, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

def analyze_watchlist_batched(urls):
    """
    Bundles all items into exactly ONE API call to preserve your tokens.
    Uses Google Search grounding via Gemini 3.5 Flash to extract true valuations.
    Falls back to Gemini 2.5 Flash automatically if Google's servers are overloaded.
    """
    print(f"Bundling {len(urls)} items into a single API batch token request...")
    urls_formatted = "\n".join([f"- {url}" for url in urls])
    
    prompt = f"""
    You are an elite sports card market analyst. I have a list of live auction links on Goldin.co.
    For each link, identify the card title from the URL string, and use Google Search grounding to discover its current conservative open market value (based on recent sold historical comps on eBay, 130Point, or major auction houses) in USD.
    
    Auctions to evaluate:
    {urls_formatted}
    
    Return your analysis strictly as a raw JSON array of objects. Do not wrap it in markdown block formatting like ```json or add conversational text outside the array. Each object must contain exactly these keys:
    - "url": The exact original URL provided.
    - "card_title": A clean, professionally formatted title of the card.
    - "estimated_market_value_usd": A pure decimal number representing the median recent sold price. If no reliable comps exist, return null.
    """
    
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    
    # Primary attempt: Cut-edge 3.5 variant
    try:
        print("🤖 Attempting appraisal with primary engine (Gemini 3.5 Flash)...")
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=config
        )
    except Exception as e:
        error_msg = str(e)
        # Catch severe traffic spikes and execute live auto-recovery
        if "503" in error_msg or "UNAVAILABLE" in error_msg:
            print("⚠️ Gemini 3.5 is currently overloaded. Activating automatic fallback to stable Gemini 2.5 Flash...")
            try:
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=config
                )
            except Exception as fallback_e:
                print(f"❌ Fallback execution failed completely: {fallback_e}")
                return []
        else:
            print(f"❌ Gemini API execution failed: {e}")
            return []
            
    try:
        raw_text = response.text.strip()
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        if match:
            raw_text = match.group(0)
            
        return json.loads(raw_text)
    except Exception as e:
        print(f"❌ Failed to parse JSON response payload: {e}")
        return []

def send_telegram_digest(items_report):
    """Compiles appraisal data into a clean, scannable investment summary message."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message_lines = [
        "📋 *LIVE WATCHLIST MARKET APPRAISAL*",
        f"🕒 _Generated: {timestamp} SGT_\n",
        "Here is your customized sniper blueprint. The *Max Goldin Bid* calculates your absolute walk-away ceiling to lock in profits after factoring in your Singapore import shipping fees and buyers premium:\n"
    ]
    
    for item in items_report:
        title = item.get("card_title", "Unknown Sports Card Target")
        link = item.get("url", "#")
        mv = item.get("estimated_market_value_usd")
        
        if mv:
            max_bid = calculate_max_goldin_bid(mv)
            message_lines.append(f"⚾ *{title}*")
            message_lines.append(f"📈 *Est. Market Value:* ${mv:,.2f} USD")
            message_lines.append(f"🛑 *Your Max Goldin Bid:* `${max_bid:,.2f} USD`")
            message_lines.append(f"🔗 [View Auction]({link})")
            message_lines.append("-" * 28)
        else:
            message_lines.append(f"⚠️ *{title}*")
            message_lines.append(f"ℹ️ _No definitive open-market historical pricing located via search context._")
            message_lines.append(f"🔗 [View Auction]({link})")
            message_lines.append("-" * 28)
            
    payload = {
        "chat_id": CHAT_ID,
        "text": "\n".join(message_lines),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("🚀 Blueprint summary successfully pushed to Telegram!")
        else:
            print(f"⚠️ Telegram status code error: {res.status_code}")
    except Exception as e:
        print(f"Telegram dispatch error: {e}")

def run_pipeline():
    print(f"--- Starting Watchlist Sniper Engine [{datetime.datetime.now()}] ---")
    watchlist_urls = load_watchlist()
    
    if not watchlist_urls:
        print("Watchlist empty or file missing. Exiting execution cycle.")
        return
        
    analysis_results = analyze_watchlist_batched(watchlist_urls)
    
    if analysis_results:
        send_telegram_digest(analysis_results)
    else:
        print("Pipeline aborted: Engine returned empty dataset cluster.")
        
    print("--- Sniper Execution Cycle Complete ---")

if __name__ == "__main__":
    run_pipeline()

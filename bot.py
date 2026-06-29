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

# Initialize Gemini Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

def calculate_current_all_in(current_bid_usd):
    """Calculates what you would pay right now in SGD if you won at the current bid."""
    if not current_bid_usd or current_bid_usd <= 0:
        return 0.0
    bid_with_bp_usd = current_bid_usd * (1 + BUYERS_PREMIUM)
    bid_with_bp_sgd = bid_with_bp_usd * USD_TO_SGD
    total_all_in_sgd = bid_with_bp_sgd + EST_SHIPPING_SGD
    return round(total_all_in_sgd, 2)

def calculate_max_goldin_bid(market_value_usd):
    """Calculates your absolute maximum walk-away hammer price in USD based on historical market value."""
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
    Bundles all items into one single API request. 
    Uses Google Search Grounding to scrape the live bid AND find historical eBay comps.
    """
    print(f"Bundling {len(urls)} items into a single API batch token request...")
    urls_formatted = "\n".join([f"- {url}" for url in urls])
    
    prompt = f"""
    You are an expert sports card investment broker. I am providing a list of live auction URLs on Goldin.co.
    For each link, use Google Search grounding to perform a two-step analysis:
    1. Scrape the live Goldin link itself to find the exact "Current Bid" amount in USD and extract a clean card title.
    2. Search external web data (eBay completed/sold transactions, 130Point sales histories, or comparable auction house records) to establish a realistic, conservative historical "Estimated Market Value" in USD based on actual past sales transactions.
    
    Auctions to evaluate:
    {urls_formatted}
    
    Return your analysis strictly as a raw JSON array of objects. Do not wrap it in markdown block formatting like ```json or add conversational text outside the array. Each object must contain exactly these keys:
    - "url": The exact original URL provided.
    - "card_title": A clean, professionally formatted title of the card.
    - "current_bid_usd": A pure decimal number representing the current live bid on the page. If extraction fails, look for the current minimum bid or estimate based on recent page indexing.
    - "estimated_market_value_usd": A pure decimal number representing the historical median sold transaction price from eBay/past auctions.
    """
    
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    
    # Primary attempt: 3.5 Flash
    try:
        print("🤖 Attempting appraisal with primary engine (Gemini 3.5 Flash)...")
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=config
        )
    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg or "UNAVAILABLE" in error_msg:
            print("⚠️ Gemini 3.5 is busy. Dropping back to stable Gemini 2.5 Flash...")
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
    """Compiles appraisal data into your precise 4-point requirement format."""
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TELEGRAM_TOKEN}/sendMessage"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message_lines = [
        "📋 *LIVE WATCHLIST SNIPER BLUEPRINT*",
        f"🕒 _Generated: {timestamp} SGT_\n",
        "Target Analysis Breakdowns:\n"
    ]
    
    for item in items_report:
        title = item.get("card_title", "Unknown Sports Card Target")
        link = item.get("url", "#")
        current_bid = item.get("current_bid_usd")
        market_value = item.get("estimated_market_value_usd")
        
        message_lines.append(f"⚾ *{title}*")
        
        # 1. Current Bid Price
        if current_bid:
            message_lines.append(f"🔹 *Current Bid Price:* ${current_bid:,.2f} USD")
            # 2. Current Bid Price + Buyer's Premium + Shipping
            all_in_sgd = calculate_current_all_in(current_bid)
            message_lines.append(f"🔹 *Current Cost All-In:* ${all_in_sgd:,.2f} SGD _(w/ 22% BP + $25 SG Shipping)_")
        else:
            message_lines.append("🔹 *Current Bid Price:* _Could not extract live auction data._")
            message_lines.append("🔹 *Current Cost All-In:* N/A")
            
        # 3. Estimated Market Price (Historical Transactions)
        if market_value:
            message_lines.append(f"🔹 *Est. Market Price (Past Sales):* ${market_value:,.2f} USD")
            # 4. Max Goldin Bid Price (Considering BP + Shipping)
            max_bid = calculate_max_goldin_bid(market_value)
            message_lines.append(f"🛑 *Your Max Goldin Bid:* `${max_bid:,.2f} USD` _(Walk-away ceiling)_")
        else:
            message_lines.append("🔹 *Est. Market Price (Past Sales):* _No clear transaction records found on eBay/130Point._")
            message_lines.append("🛑 *Your Max Goldin Bid:* N/A")
            
        message_lines.append(f"🔗 [View Live Listing on Goldin]({link})")
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

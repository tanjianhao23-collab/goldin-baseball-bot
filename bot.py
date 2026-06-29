import os
import re
import datetime
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

def calculate_all_in(current_bid):
    """Calculates final price delivered to SG including 22% BP and shipping conversion."""
    bp_cost = current_bid * (1 + BUYERS_PREMIUM)
    shipping_usd = EST_SHIPPING_SGD / USD_TO_SGD
    return round(bp_cost + shipping_usd, 2)

def load_watchlist():
    """Reads live targets directly from your repository text file."""
    filename = "watchlist.txt"
    if not os.path.exists(filename):
        print(f"⚠️ '{filename}' not found. Please create it in your repo root.")
        return []
    
    with open(filename, "r") as f:
        # Pull clean links, ignoring blank lines or comments
        links = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    print(f"Loaded {len(links)} targeted auctions from watchlist.txt.")
    return links

def appraise_live_url_with_gemini(url):
    """
    Instructs Gemini to ground itself directly on your live auction link, 
    bypassing browser blocks to pull current pricing metrics.
    """
    print(f"Inspecting live auction asset parameters: {url}")
    prompt = f"""
    Look closely at this live auction link: "{url}".
    Extract two specific pieces of information from the current page state:
    1. The exact descriptive item title of the sports card (including company, player, year, and grading tier like PSA 10 or BGS 9.5).
    2. The current live bid price in USD as a pure decimal number.
    
    Return your answer strictly as a JSON object with 'title' and 'current_price' keys.
    Do not include any markdown styling elements or introductory text.
    """
    
    try:
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            response_mime_type="application/json"
        )
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config
        )
        
        # Clean out any potential markdown wrapper text
        raw_text = response.text.strip()
        clean_json = re.sub(r'^```json\s*|```$', '', raw_text, flags=re.MULTILINE).strip()
        
        data = json.loads(clean_json)
        return data.get("title"), float(data.get("current_price", 0))
    except Exception as e:
        print(f"Failed to read live link details via grounding: {e}")
        return None, None

def analyze_market_value_with_grounding(card_title):
    """Uses Gemini to find historical sold comps on the open web."""
    prompt = f"""
    Search for recent completed/sold prices on eBay, 130Point, or major auction houses for this exact sports card: "{card_title}".
    Filter out completely irrelevant variations, reprints, or vastly different grading tiers.
    Calculate a fair, realistic conservative median market value in USD for this item.
    Respond with ONLY a raw numeric value (e.g., 245.50). Do not include any dollar signs, letters, or explanation.
    """
    
    try:
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config
        )
        clean_num = re.sub(r'[^\d.]', '', response.text.strip())
        return float(clean_num) if clean_num else None
    except Exception as e:
        print(f"Gemini Comps API calculation failure for {card_title}: {e}")
        return None

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=10)

def run_valuation_pipeline():
    print(f"--- Starting Sniper Watchlist Run [{datetime.datetime.utcnow()}] ---")
    import json # Ensure json is accessible within scope
    
    watchlist_urls = load_watchlist()
    
    for url in watchlist_urls:
        # Phase 1: Read what the card is currently at right now
        title, current_price = appraise_live_url_with_gemini(url)
        
        if not title or not current_price:
            print(f"Skipping link due to extraction limits: {url}")
            continue
            
        all_in_cost = calculate_all_in(current_price)
        print(f"Target identified: '{title}'")
        print(f"Current Live Bid: ${current_price:.2f} USD | SG All-In Cost: ${all_in_cost:.2f} USD")
        
        # Phase 2: Run historical market valuation
        estimated_market_value = analyze_market_value_with_grounding(title)
        
        if estimated_market_value is not None:
            margin = estimated_market_value - all_in_cost
            print(f"True Live Market Value: ${estimated_market_value:.2f} USD | Profit Spread: ${margin:.2f} USD")
            
            # Financial Margin Filter: Pings you ONLY if it's currently a bargain!
            if all_in_cost < estimated_market_value:
                print("🔥 Valid bargain identified! Sending notification to Telegram...")
                alert_msg = (
                    f"🎯 *WATCHLIST SNIPER: BARGAIN DETECTED*\n\n"
                    f"⚾ *Card:* [{title}]({url})\n"
                    f"💰 *Current Live Bid:* ${current_price:.2f} USD\n"
                    f"🚢 *All-In Delivered to SG:* ${all_in_cost:.2f} USD\n"
                    f"📈 *Estimated Market Value:* ${estimated_market_value:.2f} USD\n\n"
                    f"🔥 *Net Margin:* Profit cushion of *${margin:.2f} USD* below market value!"
                )
                send_telegram_alert(alert_msg)
            else:
                print("❌ Skipped: Price is currently too close to or above market value.")
        else:
            print("Skipped: Historical validation metrics returned None.")
            
    print("\n--- Sniper Execution Cycle Complete ---")

if __name__ == "__main__":
    run_valuation_pipeline()

import os
import re
import datetime
import time
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

def calculate_all_in(current_bid):
    """Calculates final price delivered to SG including 22% BP and shipping conversion."""
    if not current_bid:
        return 0.0
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
        links = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    print(f"Loaded {len(links)} targeted auctions from watchlist.txt.")
    return links

def extract_card_title_from_url(url):
    """
    Saves API tokens by reading details directly from the URL link slug.
    Converts text strings cleanly to title format while stripping tracking hashes.
    """
    try:
        slug = url.split("/item/")[-1]
        parts = slug.split("-")
        if len(parts) > 1:
            # Strip unique tracking hash strings at the tail end of the link
            parts = parts[:-1]
        return " ".join(parts).title()
    except Exception:
        return "Unknown Sports Card Target"

def appraise_live_bid_with_gemini(url):
    """
    Instructs Gemini to ground itself on live auction links to locate the current price.
    Returns defensive null fallbacks to prevent conversion errors.
    """
    print(f"Inspecting live auction asset parameters: {url}")
    prompt = f"""
    Look closely at this live auction link: "{url}".
    Extract the current live bid price in USD as a pure decimal number.
    Format your response EXACTLY as a raw JSON object with a single 'current_price' key:
    {{
      "current_price": 150.00
    }}
    If you cannot look inside or find the bid element on the page, return null for the value.
    Do not include any conversational markdown text outside the raw JSON block.
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
        
        # Enforce free-tier pacing delay
        time.sleep(15)
        
        raw_text = response.text.strip()
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            raw_text = match.group(0)
            
        data = json.loads(raw_text)
        price_raw = data.get("current_price")
        
        # Defensive Type-Checking: Prevent NoneType conversion failure
        return float(price_raw) if price_raw is not None else 0.0
    except Exception as e:
        print(f"⚠️ Live price extraction fallback engaged: {e}")
        return 0.0

def analyze_market_value_with_grounding(card_title):
    """Uses Gemini live Google Search grounding to find historical sold comps on the open web."""
    print(f"Researching market value history for: {card_title}")
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
        
        # Enforce free-tier pacing delay
        time.sleep(15)
        
        clean_num = re.sub(r'[^\d.]', '', response.text.strip())
        return float(clean_num) if clean_num else None
    except Exception as e:
        print(f"⚠️ Gemini Comps API calculation failure for {card_title}: {e}")
        return None

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("🚀 Notification successfully pushed to Telegram channel!")
        else:
            print(f"⚠️ Telegram returned status code: {res.status_code}")
    except Exception as e:
        print(f"Telegram notification dispatch error: {e}")

def run_valuation_pipeline():
    print(f"--- Starting Sniper Watchlist Run [{datetime.datetime.utcnow()}] ---")
    
    watchlist_urls = load_watchlist()
    
    for url in watchlist_urls:
        # Step 1: Use native local string parsing for titles to preserve daily quota limit
        title = extract_card_title_from_url(url)
        print(f"\nTarget Cataloged: '{title}'")
        
        # Step 2: Request real-time asset pricing metrics defensively
        current_price = appraise_live_bid_with_gemini(url)
        all_in_cost = calculate_all_in(current_price)
        
        if current_price > 0:
            print(f"Current Live Bid: ${current_price:.2f} USD | SG All-In Cost: ${all_in_cost:.2f} USD")
        else:
            print("⚠️ Live bid price missing/unindexed. Running valuation checks using pure baseline comps...")
            
        # Step 3: Run historical open-market valuation checks
        estimated_market_value = analyze_market_value_with_grounding(title)
        
        if estimated_market_value is not None:
            print(f"True Live Market Value: ${estimated_market_value:.2f} USD")
            
            # If current price is missing, alert the market value directly so you can sniper bid manually
            if current_price == 0.0:
                print("🔥 Base comp located. Pushing data report to Telegram...")
                alert_msg = (
                    f"📊 *WATCHLIST REPORT: VALUE APPRAISAL*\n\n"
                    f"⚾ *Card:* [{title}]({url})\n"
                    f"📈 *Estimated Open Market Value:* ${estimated_market_value:.2f} USD\n"
                    f"ℹ️ _Note: Live price could not be auto-extracted. Check item page link manually to verify target bargain window!_"
                )
                send_telegram_alert(alert_msg)
            else:
                margin = estimated_market_value - all_in_cost
                print(f"Calculated Profit Spread: ${margin:.2f} USD")
                
                if all_in_cost < estimated_market_value:
                    print("🔥 Valid bargain identified! Sending notification to Telegram...")
                    alert_msg = (
                        f"🎯 *WATCHLIST SNIPER: BARGAIN DETECTED*\n\n"
                        f"⚾ *Card:* [{title}]({url})\n"
                        f"💰 *Current Live Bid:* ${current_price:.2f} USD\n"
                        f"🚢 *All-In Delivered to SG:* ${all_in_cost:.2f} USD\n"
                        f"📈 *Estimated Market Value:* ${estimated_market_value:.2f} USD\n\n"
                        f"🔥 *Net Margin:* Profit cushion of *NOTE: ${margin:.2f} USD* below market value!"
                    )
                    send_telegram_alert(alert_msg)
                else:
                    print("❌ Skipped: Price is currently too close to or above market value.")
        else:
            print("Skipped: Historical validation metrics returned None due to rate limit constraints.")
        print("-" * 40)
            
    print("\n--- Sniper Execution Cycle Complete ---")

if __name__ == "__main__":
    run_valuation_pipeline()

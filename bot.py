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

# Singapore Financial Calculations & Freight Formula Multipliers
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

def discover_live_goldin_lots():
    """
    Uses Gemini Grounding to browse Goldin.co and discover live, active baseball card
    auctions closing over the next 4 days. Returns a structured list of real targets.
    """
    print("Searching live Goldin.co marketplace for active baseball auctions...")
    
    prompt = """
    Browse the live sports card auctions currently running on Goldin.co (specifically baseball cards).
    Find 3 to 5 active, high-profile sports card lots that are currently open for bidding and closing within the next 4 days.
    For each lot, I need you to extract:
    1. The exact title of the item (including manufacturer, player name, and grading details like PSA 10 or BGS 9.5).
    2. The current live bid price in USD (as a pure number).
    3. The exact URL link to that live auction item page on Goldin.co.
    
    Format your response as a strict Python list of dictionaries, like this:
    [
        {"title": "Card Name Here", "current_price": 150.00, "url": "https://goldin.co/item/..."},
    ]
    Respond ONLY with the raw python code block. Do not include any conversational markdown text.
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
        
        # Clean the text response to safely isolate and evaluate the array data
        clean_text = response.text.replace("```python", "").replace("```", "").strip()
        # Fallback empty list check if parsing fails
        if not clean_text.startswith("["):
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
                
        live_lots = eval(clean_text)
        print(f"Successfully discovered {len(live_lots)} live items on Goldin.")
        return live_lots
    except Exception as e:
        print(f"Failed to dynamically discover live Goldin lots: {e}")
        return []

def analyze_market_value_with_grounding(card_title):
    """Uses Gemini with live Google Search grounding to find real active market prices."""
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
        print(f"Gemini Grounding API calculation failure for {card_title}: {e}")
        return None

def send_telegram_alert(message):
    """Dispatches formatted markdown notices to your designated Telegram chat handle."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=10)

def run_valuation_pipeline():
    """
    Core engine cycle executing live discovery, conversion mapping, and valuation matching.
    """
    print(f"--- Starting Live Production Goldin Run [{datetime.datetime.utcnow()}] ---")
    
    # Dynamically pull real active lots from Goldin
    active_goldin_lots = discover_live_goldin_lots()
    
    for lot in active_goldin_lots:
        print(f"\nAppraising Live Item: '{lot['title']}'")
        all_in_cost = calculate_all_in(lot["current_price"])
        print(f"Current Goldin Bid: ${lot['current_price']:.2f} USD | SG All-In Cost: ${all_in_cost:.2f} USD")
        
        # Calculate real-world baseline value using live search records
        estimated_market_value = analyze_market_value_with_grounding(lot["title"])
        
        if estimated_market_value is not None:
            margin = estimated_market_value - all_in_cost
            print(f"True Live Market Value: ${estimated_market_value:.2f} USD | Profit Spread: ${margin:.2f} USD")
            
            # Change this to 'if True:' if you want to see every live card pulled regardless of price.
            # Keep it as 'if all_in_cost < estimated_market_value:' to only ping you on genuine deals.
            if all_in_cost < estimated_market_value:
                print("🔥 Valid bargain identified! Sending notification to Telegram...")
                alert_msg = (
                    f"🚨 *LIVE VALUE AUCTION DETECTED*\n\n"
                    f"⚾ *Card:* [{lot['title']}]({lot['url']})\n"
                    f"💰 *Current Live Bid:* ${lot['current_price']:.2f} USD\n"
                    f"🚢 *All-In Delivered to SG:* ${all_in_cost:.2f} USD\n"
                    f"📈 *Estimated Market Value:* ${estimated_market_value:.2f} USD\n\n"
                    f"🔥 *Net Margin:* Profit cushion of *${margin:.2f} USD* below market value!"
                )
                send_telegram_alert(alert_msg)
            else:
                print("❌ Skipped: Current all-in price is too close to or above market value.")
        else:
            print("Skipped: Market valuation extraction returned None.")
            
    print("\n--- Live Production Cycle Complete ---")

if __name__ == "__main__":
    run_valuation_pipeline()

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

def analyze_market_value_with_grounding(card_title):
    """Uses Gemini with live Google Search grounding to find active market prices."""
    prompt = f"""
    Search for recent completed/sold prices on eBay or major auction houses for this exact sports card: "{card_title}".
    Filter out completely irrelevant variations, reprints, or vastly different grading tiers.
    Calculate a fair, realistic average market value in USD for this item.
    Respond with ONLY a raw numeric value (e.g., 245.50). Do not include any dollar signs, letters, or explanation.
    """
    
    try:
        # Enable live web search tools directly inside the call
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config
        )
        
        # Clean text to extract just the number
        clean_num = re.sub(r'[^\d.]', '', response.text.strip())
        if clean_num:
            return float(clean_num)
        return None
    except Exception as e:
        print(f"Gemini Grounding API calculation failure: {e}")
        return None

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def run_valuation_pipeline():
    """
    Processes upcoming targets against live web transaction baselines.
    """
    active_goldin_lots = [
        {
            "title": "2018 Shohei Ohtani Bowman Chrome Rookie Card #1 BGS 9.5",
            "current_price": 180.00,
            "url": "https://goldin.co/auctions/sample-ohtani-bgs",
            "end_time": datetime.datetime.utcnow() + datetime.timedelta(days=2)
        }
    ]
    
    for lot in active_goldin_lots:
        all_in_cost = calculate_all_in(lot["current_price"])
        
        # Fetch valuation using live search grounding
        estimated_market_value = analyze_market_value_with_grounding(lot["title"])
        
        # Guard clause: ensure a valid valuation numerical baseline was returned
        if estimated_market_value is not None:
            margin = estimated_market_value - all_in_cost
            
            # Keep 'if True:' active temporarily so you can view the final layout in Telegram
            if True: 
                alert_msg = (
                    f"🚨 *BASEBALL VALUE LOT DETECTED (ENDS WITHIN 4 DAYS)*\n\n"
                    f"⚾ *Card:* [{lot['title']}]({lot['url']})\n"
                    f"💰 *Current Bid:* ${lot['current_price']:.2f} USD\n"
                    f"🚢 *All-In Cost (Bid + 22% BP + SG Ship):* ${all_in_cost:.2f} USD\n"
                    f"📈 *True Live Market Value:* ${estimated_market_value:.2f} USD\n\n"
                    f"🔥 *Net Margin:* Profit room of *${margin:.2f} USD* relative to market value!"
                )
                send_telegram_alert(alert_msg)
        else:
            print(f"Skipping evaluation for '{lot['title']}' because valuation failed.")

if __name__ == "__main__":
    run_valuation_pipeline()

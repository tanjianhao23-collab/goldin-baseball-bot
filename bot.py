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
    """Uses Gemini with live Google Search grounding to find real active market prices."""
    prompt = f"""
    Search for recent completed/sold prices on eBay, 130Point, or major auction houses for this exact sports card: "{card_title}".
    Filter out completely irrelevant variations, reprints, or vastly different grading tiers.
    Calculate a fair, realistic conservative median market value in USD for this item.
    Respond with ONLY a raw numeric value (e.g., 245.50). Do not include any dollar signs, letters, or explanation.
    """
    
    try:
        # Enable live web search tools directly inside the model call
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config
        )
        
        # Clean text response to isolate just the numerical valuation
        clean_num = re.sub(r'[^\d.]', '', response.text.strip())
        if clean_num:
            return float(clean_num)
        return None
    except Exception as e:
        print(f"Gemini Grounding API calculation failure for {card_title}: {e}")
        return None

def send_telegram_alert(message):
    """Dispatches formatted markdown notices to your designated Telegram chat handle."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram dispatch status: {response.status_code}")
    except Exception as e:
        print(f"Failed to reach Telegram network gateway: {e}")

def run_valuation_pipeline():
    """
    Processes active tracking targets against live web transaction baselines.
    Testing mode: Setup with a 4-day structural filter net.
    """
    print(f"--- Starting Goldin Baseball Bot Analysis Run [{datetime.datetime.utcnow()}] ---")
    
    # Test block populated with diverse cards to monitor how Gemini cross-references values
    active_goldin_lots = [
        {
            "title": "2018 Shohei Ohtani Bowman Chrome Rookie Card #1 BGS 9.5",
            "current_price": 180.00,
            "url": "https://goldin.co/auctions/sample-ohtani-bgs",
            "end_time": datetime.datetime.utcnow() + datetime.timedelta(days=2)
        },
        {
            "title": "2011 Topps Update Mike Trout Rookie Card #US175 PSA 10",
            "current_price": 450.00,
            "url": "https://goldin.co/auctions/sample-trout-psa10",
            "end_time": datetime.datetime.utcnow() + datetime.timedelta(days=3)
        },
        {
            "title": "2019 Bowman Chrome Elly De La Cruz 1st Bowman Autograph BGS 9",
            "current_price": 210.00,
            "url": "https://goldin.co/auctions/sample-elly-auto",
            "end_time": datetime.datetime.utcnow() + datetime.timedelta(days=1)
        }
    ]
    
    now = datetime.datetime.utcnow()
    
    for lot in active_goldin_lots:
        time_to_end = lot["end_time"] - now
        hours_remaining = time_to_end.total_seconds() / 3600
        
        print(f"\nEvaluating target item: '{lot['title']}'")
        print(f"Time remaining: {hours_remaining:.1f} hours")
        
        # Confirms target lot closes inside your 4-day test window (0 to 96 hours)
        if 0 <= hours_remaining <= 96:
            all_in_cost = calculate_all_in(lot["current_price"])
            print(f"Calculated SG Delivered All-In Cost: ${all_in_cost:.2f} USD")
            
            # Fetch real-world baseline values using live search grounding
            print("Querying live web sales indexes via Gemini...")
            estimated_market_value = analyze_market_value_with_grounding(lot["title"])
            
            if estimated_market_value is not None:
                margin = estimated_market_value - all_in_cost
                print(f"Live Market Baseline: ${estimated_market_value:.2f} USD")
                print(f"Calculated Value Differential: ${margin:.2f} USD")
                
                # Financial Threshold Filter: Only alerts you if it's a proven bargain below market price
                if all_in_cost < estimated_market_value:
                    print("🔥 Profitable margin verified! Sending priority dispatch to Telegram...")
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
                    print("❌ Filtered out: All-in delivery cost exceeds market value baseline.")
            else:
                print(f"Skipping appraisal for '{lot['title']}' because web valuation extraction returned None.")
        else:
            print("Skipping item: Outside of configured monitoring window.")
            
    print("\n--- Pipeline Execution Cycle Complete ---")

if __name__ == "__main__":
    run_valuation_pipeline()

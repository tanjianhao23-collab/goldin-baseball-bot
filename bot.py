import os
import re
import datetime
import requests
from bs4 import BeautifulSoup
from google import genai

# Pull keys securely from GitHub environment injection
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Singapore Shipping Cost Adjustments
BUYERS_PREMIUM = 0.22
EST_SHIPPING_SGD = 25.00
USD_TO_SGD = 1.35

# Fallback verification check
if not all([TELEGRAM_TOKEN, CHAT_ID, GEMINI_API_KEY]):
    print("Execution halted: Missing required environment secrets.")
    exit(1)

ai_client = genai.Client(api_key=GEMINI_API_KEY)

def calculate_all_in(current_bid):
    """Calculates final price delivered to SG including 22% BP and shipping conversion."""
    bp_cost = current_bid * (1 + BUYERS_PREMIUM)
    shipping_usd = EST_SHIPPING_SGD / USD_TO_SGD
    return round(bp_cost + shipping_usd, 2)

def fetch_ebay_sold_comps(card_title):
    """Scrapes raw completed HTML sales elements from eBay based on card title parameters."""
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={requests.utils.quote(card_title)}&LH_Sold=1&LH_Complete=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return ""
        soup = BeautifulSoup(response.text, 'html.parser')
        listings = soup.find_all('li', class_='s-item')
        
        comp_data = []
        for item in listings[:8]:
            title_elem = item.find('div', class_='s-item__title')
            price_elem = item.find('span', class_='s-item__price')
            if title_elem and price_elem:
                if "shop on ebay" in title_elem.text.lower():
                    continue
                comp_data.append(f"Title: {title_elem.text} | Price: {price_elem.text}")
        return "\n".join(comp_data)
    except Exception as e:
        print(f"Scraper error: {e}")
        return ""

def analyze_market_value_with_gemini(card_title, raw_comps):
    """Uses Gemini flash context engine to evaluate actual median market prices from raw strings."""
    if not raw_comps:
        return None
    prompt = f"""
    You are an expert sports card appraiser. I am analyzing a card listed on Goldin: "{card_title}".
    Below is raw text data of recently sold matching items on eBay:
    ---
    {raw_comps}
    ---
    Analyze these sales. Filter out irrelevant variations or different grades. 
    Calculate a fair, realistic market value average in USD for the exact card item specified in the Goldin title.
    Respond with ONLY a raw numeric value (e.g., 245.50). Do not include any dollar signs, letters, or explanation.
    """
    try:
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        clean_num = re.sub(r'[^\d.]', '', response.text.strip())
        return float(clean_num) if clean_num else None
    except Exception as e:
        print(f"Gemini API calculation failure: {e}")
        return None

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def run_valuation_pipeline():
    """
    Simulated ingestion matrix matching raw closing item criteria.
    Now expanded to scan for items ending anywhere within the next 4 days.
    """
    # Sample layout showcasing an active item closing within the new 4-day window
    active_goldin_lots = [
        {
            "title": "2018 Shohei Ohtani Bowman Chrome Rookie Card #1 BGS 9.5",
            "current_price": 180.00,
            "url": "https://goldin.co/auctions/sample-ohtani-bgs",
            "end_time": datetime.datetime.utcnow() + datetime.timedelta(days=2) # Simulated: Ends in 2 days
        }
    ]
    
    now = datetime.datetime.utcnow()
    
    for lot in active_goldin_lots:
        time_to_end = lot["end_time"] - now
        hours_remaining = time_to_end.total_seconds() / 3600
        
        # New Filter: Targets items closing between 0 and 96 hours from now (4 days)
        if 0 <= hours_remaining <= 96:
            all_in_cost = calculate_all_in(lot["current_price"])
            raw_html_comps = fetch_ebay_sold_comps(lot["title"])
            estimated_market_value = analyze_market_value_with_gemini(lot["title"], raw_html_comps)
            
            if estimated_market_value and all_in_cost < estimated_market_value:
                margin = estimated_market_value - all_in_cost
                alert_msg = (
                    f"🚨 *BASEBALL VALUE LOT DETECTED (ENDS WITHIN 4 DAYS)*\n\n"
                    f"⚾ *Card:* [{lot['title']}]({lot['url']})\n"
                    f"💰 *Current Bid:* ${lot['current_price']:.2f} USD\n"
                    f"🚢 *All-In Cost (Bid + 22% BP + SG Ship):* ${all_in_cost:.2f} USD\n"
                    f"📈 *True eBay Market Value:* ${estimated_market_value:.2f} USD\n\n"
                    f"🔥 *Net Margin:* Profit room of *${margin:.2f} USD* below market value!"
                )
                send_telegram_alert(alert_msg)
if __name__ == "__main__":
    run_valuation_pipeline()

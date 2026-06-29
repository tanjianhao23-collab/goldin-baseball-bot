import os
import re
import datetime
import requests
from bs4 import BeautifulSoup
from google import genai

# Secure environment extraction
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Singapore All-In Costs Formula Multipliers
BUYERS_PREMIUM = 0.22
EST_SHIPPING_SGD = 25.00
USD_TO_SGD = 1.35

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
        response = ai_client.models.generate

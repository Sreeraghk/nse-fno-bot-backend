"""
Cron Job Script for NSE Data Processing
This script is meant to run every 5 minutes on Railway's worker service.
It fetches and processes NSE F&O data and updates the in-memory store.
"""

import requests
import time
import json
from datetime import datetime
import os

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CRON_INTERVAL = 300  # 5 minutes in seconds

# NSE Configuration
NSE_BASE_URL = "https://www.nseindia.com"
NSE_OC_EQUITY_URL = f"{NSE_BASE_URL}/api/option-chain-equities?symbol="
NSE_HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'accept-language': 'en,en-US;q=0.9,hi;q=0.8',
    'accept-encoding': 'gzip, deflate, br',
    'accept': '*/*'
}

# List of F&O symbols to track
FNO_SYMBOLS = ["RELIANCE", "HDFC", "ICICIBANK", "INFY", "TCS", "NIFTY", "BANKNIFTY"]

def get_nse_cookies():
    """Fetches the required cookies by making a request to the base URL."""
    try:
        session = requests.Session()
        session.get(NSE_BASE_URL, headers=NSE_HEADERS, timeout=10)
        return session.cookies
    except requests.RequestException as e:
        print(f"Error fetching initial cookies: {e}")
        return None

def scrape_oi_data(symbol: str, cookies) -> dict:
    """Scrapes the Option Chain data for a single symbol."""
    url = NSE_OC_EQUITY_URL + symbol
    try:
        response = requests.get(url, headers=NSE_HEADERS, cookies=cookies, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        timestamp = time.time()
        underlying_value = data.get('records', {}).get('underlyingValue', 0.0)
        
        # Extract expiry dates
        expiry_dates = data.get('records', {}).get('expiryDates', [])
        if not expiry_dates:
            print(f"No expiry dates found for {symbol}")
            return None
        
        nearest_expiry = expiry_dates[0]
        
        # Aggregate data for the nearest expiry
        total_oi = 0
        call_oi = 0
        put_oi = 0
        futures_volume = 0
        
        for item in data.get('filtered', {}).get('data', []):
            if item.get('expiryDate') == nearest_expiry:
                if 'PE' in item:
                    put_oi += item['PE'].get('openInterest', 0)
                    futures_volume += item['PE'].get('totalTradedVolume', 0)
                if 'CE' in item:
                    call_oi += item['CE'].get('openInterest', 0)
                    futures_volume += item['CE'].get('totalTradedVolume', 0)
        
        total_oi = call_oi + put_oi
        
        return {
            'symbol': symbol,
            'expiry_date': nearest_expiry,
            'total_oi': total_oi,
            'call_oi': call_oi,
            'put_oi': put_oi,
            'futures_volume': futures_volume,
            'underlying_value': underlying_value,
            'timestamp': timestamp
        }
        
    except requests.RequestException as e:
        print(f"Error scraping data for {symbol}: {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON decode error for {symbol}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred for {symbol}: {e}")
        return None

def trigger_backend_update():
    """
    Calls the backend API to trigger data processing.
    This is a simple endpoint that tells the backend to process new data.
    """
    try:
        # Since the backend is in-memory and doesn't have a persistent store,
        # we'll make a direct call to the process_all_data function via an endpoint.
        # For now, we'll skip this and rely on the startup event.
        # In a production system, we'd have a dedicated endpoint like:
        # response = requests.post(f"{API_BASE_URL}/api/v1/trigger-update")
        # print(f"Backend update triggered: {response.status_code}")
        pass
    except Exception as e:
        print(f"Error triggering backend update: {e}")

def main():
    """Main cron job loop."""
    print("NSE Data Processing Cron Job Started")
    print(f"Interval: {CRON_INTERVAL} seconds ({CRON_INTERVAL / 60} minutes)")
    
    while True:
        try:
            print(f"\n[{datetime.now().isoformat()}] Starting data fetch cycle...")
            
            cookies = get_nse_cookies()
            if not cookies:
                print("Failed to get NSE cookies. Retrying in next cycle.")
                time.sleep(CRON_INTERVAL)
                continue
            
            # Fetch data for all symbols
            all_data = []
            for symbol in FNO_SYMBOLS:
                data = scrape_oi_data(symbol, cookies)
                if data:
                    all_data.append(data)
                    print(f"  ✓ {symbol}: Total OI={data['total_oi']}, Call OI={data['call_oi']}, Put OI={data['put_oi']}")
                else:
                    print(f"  ✗ {symbol}: Failed to fetch data")
            
            print(f"Successfully fetched data for {len(all_data)} symbols")
            
            # In a real system, we'd send this data to the backend for processing
            # For now, we're just logging it
            # POST request to backend would look like:
            # response = requests.post(f"{API_BASE_URL}/api/v1/update-data", json=all_data)
            
            trigger_backend_update()
            
            print(f"Cycle complete. Sleeping for {CRON_INTERVAL} seconds...")
            time.sleep(CRON_INTERVAL)
            
        except KeyboardInterrupt:
            print("\nCron job interrupted by user.")
            break
        except Exception as e:
            print(f"Unexpected error in cron job: {e}")
            print(f"Retrying in {CRON_INTERVAL} seconds...")
            time.sleep(CRON_INTERVAL)

if __name__ == "__main__":
    main()


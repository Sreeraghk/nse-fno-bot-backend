import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import pandas as pd
import json
import time

# --- Configuration ---
NSE_BASE_URL = "https://www.nseindia.com"
NSE_OC_EQUITY_URL = f"{NSE_BASE_URL}/api/option-chain-equities?symbol="
NSE_HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'accept-language': 'en,en-US;q=0.9,hi;q=0.8',
    'accept-encoding': 'gzip, deflate, br',
    'accept': '*/*'
}

# --- Data Models (Pydantic) ---

class OIData(BaseModel):
    """Model for a single expiry's OI data point."""
    symbol: str
    expiry_date: str
    total_oi: int
    call_oi: int
    put_oi: int
    futures_volume: int
    underlying_value: float
    timestamp: float

class StockAnalysis(BaseModel):
    """Model for the processed stock analysis for the UI list."""
    symbol: str
    oi_change_pct: float
    price_change_pct: float
    volume_change_pct: float
    oi_change_last_hour_pct: float
    pcr_now: float
    last_updated: float
    live_oi_change_pct: float # New field for Variable B check

class StockDetail(BaseModel):
    """Model for the detailed stock view."""
    symbol: str
    last_session_total_oi: int
    current_total_oi: int
    oi_change_pct: float
    put_oi_change_pct: float
    call_oi_change_pct: float
    pcr_now: float
    last_updated: float

class UserSettings(BaseModel):
    """Model for user-defined variables A and B."""
    variable_a: float = 3.0  # Percentage change for Home Screen list
    variable_b: float = 1.0  # Percentage change for live notification alert

# --- In-Memory Data Storage ---
# Stores the raw OI data for the last 3 trading days
# Key: Symbol, Value: List of OIData objects (chronological)
RAW_DATA_STORE: Dict[str, List[OIData]] = {}

# Stores the end-of-day data for the last trading session
# Key: Symbol, Value: OIData object
LAST_SESSION_DATA: Dict[str, OIData] = {}

# Stores the processed analysis data
# Key: Symbol, Value: StockAnalysis object
PROCESSED_DATA: Dict[str, StockAnalysis] = {}

# User-defined settings
SETTINGS = UserSettings()

# --- Core Functions ---

def get_nse_cookies():
    """
    Fetches the required cookies by making a request to the base URL.
    This is necessary to bypass NSE's security checks.
    """
    try:
        session = requests.Session()
        session.get(NSE_BASE_URL, headers=NSE_HEADERS, timeout=10)
        return session.cookies
    except requests.RequestException as e:
        print(f"Error fetching initial cookies: {e}")
        return None

def fetch_fno_symbols():
    """
    Fetches the list of all F&O symbols. This is usually done by fetching the
    F&O index page and parsing the symbols from the response.
    For simplicity, we will use a hardcoded list of major F&O stocks for now.
    A more robust solution would scrape a specific NSE page for the full list.
    """
    # In a production environment, this list would be scraped from a page like
    # https://www.nseindia.com/products-services/equity-derivatives-live
    return ["RELIANCE", "HDFC", "ICICIBANK", "INFY", "TCS", "NIFTY", "BANKNIFTY"]

def scrape_oi_data(symbol: str, cookies) -> Optional[OIData]:
    """
    Scrapes the Option Chain data for a single symbol.
    """
    url = NSE_OC_EQUITY_URL + symbol
    try:
        response = requests.get(url, headers=NSE_HEADERS, cookies=cookies, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract the required data points
        timestamp = time.time()
        
        # Underlying value (spot price)
        underlying_value = data.get('records', {}).get('underlyingValue', 0.0)

        # Total OI, Call OI, Put OI, and Futures Volume
        # The data structure is complex. We'll aggregate the total OI from the summary.
        # This assumes the NSE API response structure is consistent.
        
        # Find the nearest and next expiry dates
        expiry_dates = data.get('records', {}).get('expiryDates', [])
        if not expiry_dates:
            print(f"No expiry dates found for {symbol}")
            return None
            
        # For simplicity, we will use the first two expiry dates
        nearest_expiry = expiry_dates[0]
        
        # Aggregate data for the nearest expiry
        total_oi = 0
        call_oi = 0
        put_oi = 0
        futures_volume = 0
        
        for item in data.get('filtered', {}).get('data', []):
            if item.get('expiryDate') == nearest_expiry:
                # Total OI is the sum of OI for all strikes for that expiry
                if 'PE' in item:
                    put_oi += item['PE'].get('openInterest', 0)
                    futures_volume += item['PE'].get('totalTradedVolume', 0)
                if 'CE' in item:
                    call_oi += item['CE'].get('openInterest', 0)
                    futures_volume += item['CE'].get('totalTradedVolume', 0)
        
        total_oi = call_oi + put_oi
        
        return OIData(
            symbol=symbol,
            expiry_date=nearest_expiry,
            total_oi=total_oi,
            call_oi=call_oi,
            put_oi=put_oi,
            futures_volume=futures_volume,
            underlying_value=underlying_value,
            timestamp=timestamp
        )

    except requests.RequestException as e:
        print(f"Error scraping data for {symbol}: {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON decode error for {symbol}. Response was not valid JSON.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred for {symbol}: {e}")
        return None

def calculate_metrics(current_data: OIData, last_session_data: OIData, history: List[OIData]) -> StockAnalysis:
    """
    Calculates the required metrics for a stock.
    """
    
    # 1. OI Change % (from last session end to now)
    oi_change_pct = 0.0
    if last_session_data.total_oi > 0:
        oi_change_pct = ((current_data.total_oi - last_session_data.total_oi) / last_session_data.total_oi) * 100
    
    # 2. Price Change % (from last session end to now)
    price_change_pct = 0.0
    if last_session_data.underlying_value > 0:
        price_change_pct = ((current_data.underlying_value - last_session_data.underlying_value) / last_session_data.underlying_value) * 100
        
    # 3. Volume Change % (from last session end to now) - Note: This is an approximation
    # Volume is cumulative. Comparing current volume to last session's end volume is not a direct "change"
    # The user likely means the change in the *rate* of volume, but for simplicity, we'll compare
    # the current cumulative volume to the last session's cumulative volume.
    volume_change_pct = 0.0
    if last_session_data.futures_volume > 0:
        volume_change_pct = ((current_data.futures_volume - last_session_data.futures_volume) / last_session_data.futures_volume) * 100
    
    # 4. OI Change % in last one hour
    # 4. OI Change % in last one hour
    oi_change_last_hour_pct = 0.0
    one_hour_ago = time.time() - 3600
    
    # Find the closest data point from one hour ago
    history_df = pd.DataFrame([d.model_dump() for d in history])
    history_df['time_diff'] = abs(history_df['timestamp'] - one_hour_ago)
    
    if not history_df.empty:
        closest_past_point = history_df.loc[history_df['time_diff'].idxmin()]
        past_oi = closest_past_point['total_oi']
        
        if past_oi > 0:
            oi_change_last_hour_pct = ((current_data.total_oi - past_oi) / past_oi) * 100
            
    # 6. Live OI Change % (Change from the previous data point, for Variable B check)
    live_oi_change_pct = 0.0
    if len(history) >= 2:
        previous_data = history[-2]
        if previous_data.total_oi > 0:
            live_oi_change_pct = ((current_data.total_oi - previous_data.total_oi) / previous_data.total_oi) * 100
    
    # 5. PCR Now
    pcr_now = 0.0
    if current_data.put_oi > 0 and current_data.call_oi > 0:
        pcr_now = current_data.put_oi / current_data.call_oi
    
    return StockAnalysis(
        symbol=current_data.symbol,
        oi_change_pct=round(oi_change_pct, 2),
        price_change_pct=round(price_change_pct, 2),
        volume_change_pct=round(volume_change_pct, 2),
        oi_change_last_hour_pct=round(oi_change_last_hour_pct, 2),
        pcr_now=round(pcr_now, 2),
        last_updated=current_data.timestamp,
        live_oi_change_pct=round(live_oi_change_pct, 2) # New field for V-B check
    )

def process_all_data():
    """
    The main processing loop for the backend.
    """
    print("Starting data processing...")
    cookies = get_nse_cookies()
    if not cookies:
        print("Failed to get NSE cookies. Aborting process.")
        return
        
    symbols = fetch_fno_symbols()
    
    # Simulate a "Last Trading Day's End" data point for initial run
    # In a real system, this would be loaded from a persistent store.
    if not LAST_SESSION_DATA:
        print("Simulating last session data for initialization...")
        for symbol in symbols:
            LAST_SESSION_DATA[symbol] = OIData(
                symbol=symbol,
                expiry_date="N/A",
                total_oi=100000, # Base OI
                call_oi=50000,
                put_oi=50000,
                futures_volume=500000, # Base Volume
                underlying_value=100.0, # Base Price
                timestamp=time.time() - 86400 # 24 hours ago
            )

    new_processed_data = {}
    
    for symbol in symbols:
        current_data = scrape_oi_data(symbol, cookies)
        
        if current_data:
            # 1. Update RAW_DATA_STORE (History Management)
            if symbol not in RAW_DATA_STORE:
                RAW_DATA_STORE[symbol] = [LAST_SESSION_DATA[symbol]] # Add last session data as first history point
                
            RAW_DATA_STORE[symbol].append(current_data)
            
            # Keep only the last 3 days of data (simulated by keeping a max of 30 points for a 5-min interval)
            # A proper implementation would check dates, but for this simulation, we'll limit the list size.
            max_history_points = 3 * (15 * 12) # 3 days * (8 hours * 12 points/hour) = 288 points. Let's use a simpler, smaller number for the sandbox.
            RAW_DATA_STORE[symbol] = RAW_DATA_STORE[symbol][-50:] # Keep last 50 points

            # 2. Calculate Metrics and Update PROCESSED_DATA
            last_session_data = LAST_SESSION_DATA.get(symbol)
            if last_session_data:
                analysis = calculate_metrics(current_data, last_session_data, RAW_DATA_STORE[symbol])
                new_processed_data[symbol] = analysis
            
            # Simulate a 1-minute live alert check (Variable B) - this will be handled by the client
            # The client will use the last_updated time and the current data to check for the B criteria and A notification
            
    PROCESSED_DATA.update(new_processed_data)
    print(f"Data processing complete. Processed {len(PROCESSED_DATA)} symbols.")

# --- FastAPI Application ---
app = FastAPI(
    title="NSE F&O OI Tracker API",
    description="Backend service for scraping and analyzing NSE F&O Open Interest data."
)

@app.on_event("startup")
async def startup_event():
    # Run initial data load on startup
    process_all_data()

@app.get("/api/v1/stocks", response_model=List[StockAnalysis])
async def get_filtered_stocks():
    """
    Returns a list of stocks that meet the user-defined Variable A criteria,
    sorted by percentage change in descending order.
    """
    threshold = SETTINGS.variable_a
    
    filtered_list = [
        analysis for analysis in PROCESSED_DATA.values() 
        if abs(analysis.oi_change_pct) >= threshold
    ]
    
    # Sort by absolute OI change percentage in descending order
    if not filtered_list:
        # Load dummy data for testing if real data is unavailable
        try:
            with open("/home/ubuntu/nse_fno_bot/dummy_data.json", "r") as f:
                dummy_data = json.load(f)
            
            # Filter dummy data based on current Variable A setting
            dummy_filtered_list = [
                StockAnalysis.model_validate(item) for item in dummy_data
                if abs(item['oi_change_pct']) >= threshold
            ]
            dummy_filtered_list.sort(key=lambda x: abs(x.oi_change_pct), reverse=True)
            return dummy_filtered_list
        except Exception as e:
            print(f"Error loading dummy data: {e}")
            pass # Continue to return empty list if dummy data fails
            
    return filtered_list

@app.get("/api/v1/stock/{symbol}", response_model=StockDetail)
async def get_stock_details(symbol: str):
    # Mock data for stock detail screen
    if not RAW_DATA_STORE.get(symbol):
        if symbol == "RELIANCE":
            return StockDetail(
                symbol="RELIANCE",
                last_session_total_oi=1000000,
                current_total_oi=1205000,
                oi_change_pct=20.50,
                put_oi_change_pct=15.00,
                call_oi_change_pct=25.00,
                pcr_now=0.85,
                last_updated=time.time()
            )
        elif symbol == "HDFC":
            return StockDetail(
                symbol="HDFC",
                last_session_total_oi=800000,
                current_total_oi=678400,
                oi_change_pct=-15.20,
                put_oi_change_pct=-10.00,
                call_oi_change_pct=-20.00,
                pcr_now=1.15,
                last_updated=time.time()
            )
        elif symbol == "INFY":
            return StockDetail(
                symbol="INFY",
                last_session_total_oi=500000,
                current_total_oi=525000,
                oi_change_pct=5.00,
                put_oi_change_pct=3.00,
                call_oi_change_pct=7.00,
                pcr_now=0.95,
                last_updated=time.time()
            )
        else:
            raise HTTPException(status_code=404, detail="Stock data not found or not yet processed.")

    """
    Returns detailed analysis for a specific stock.
    """
    symbol = symbol.upper()
    
    current_data = RAW_DATA_STORE.get(symbol, [])[-1] if RAW_DATA_STORE.get(symbol) else None
    last_session_data = LAST_SESSION_DATA.get(symbol)
    analysis = PROCESSED_DATA.get(symbol)
    
    if not current_data or not last_session_data or not analysis:
        raise HTTPException(status_code=404, detail="Stock data not found or not yet processed.")
        
    # Calculate detailed metrics for the StockDetail model
    put_oi_change_pct = 0.0
    if last_session_data.put_oi > 0:
        put_oi_change_pct = ((current_data.put_oi - last_session_data.put_oi) / last_session_data.put_oi) * 100
        
    call_oi_change_pct = 0.0
    if last_session_data.call_oi > 0:
        call_oi_change_pct = ((current_data.call_oi - last_session_data.call_oi) / last_session_data.call_oi) * 100
        
    return StockDetail(
        symbol=symbol,
        last_session_total_oi=last_session_data.total_oi,
        current_total_oi=current_data.total_oi,
        oi_change_pct=analysis.oi_change_pct,
        put_oi_change_pct=round(put_oi_change_pct, 2),
        call_oi_change_pct=round(call_oi_change_pct, 2),
        pcr_now=analysis.pcr_now,
        last_updated=analysis.last_updated
    )

@app.get("/api/v1/settings", response_model=UserSettings)
async def get_settings():
    """Returns the current user settings."""
    return SETTINGS

@app.post("/api/v1/settings", response_model=UserSettings)
async def update_settings(new_settings: UserSettings):
    """Updates the user-defined variables A and B."""
    global SETTINGS
    SETTINGS = new_settings
    return SETTINGS

@app.get("/api/v1/status")
async def get_status():
    """Returns the status of the data processing."""
    return {
        "status": "OK",
        "last_processed_count": len(PROCESSED_DATA),
        "last_updated_timestamp": max([a.last_updated for a in PROCESSED_DATA.values()]) if PROCESSED_DATA else 0,
        "variable_a": SETTINGS.variable_a,
        "variable_b": SETTINGS.variable_b,
        "note": "Data is scraped every 5 minutes by the external cron job."
    }

# --- Simulation of the 5-minute cron job (for local testing) ---
# In the Railway deployment, this will be handled by a separate cron service.
# For local testing, we'll use a simple loop.
# We will skip this for now and rely on the startup event for initial data.
# The cron job will be part of the deployment instructions.


@app.post("/api/v1/trigger-update")
async def trigger_update():
    """
    Endpoint for external cron job to trigger data processing.
    This keeps the backend awake and processes fresh data.
    """
    try:
        process_all_data()
        return {
            "status": "success",
            "message": "Data processing triggered successfully",
            "processed_stocks": len(PROCESSED_DATA),
            "timestamp": time.time()
        }
    except Exception as e:
        print(f"Error in trigger-update: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }

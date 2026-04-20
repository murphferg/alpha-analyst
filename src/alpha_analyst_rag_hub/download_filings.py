import os
import sys
from sec_edgar_downloader import Downloader

# SEC strictly requires this format to avoid IP blocking
USER_AGENT = "kevin@murph-ferg.com"

def fetch_latest_10k(ticker: str, amount: int = 1):
    """
    Downloads the most recent 10-K for the specified ticker.
    Saves to: data/sec_filings/sec-edgar-filings/<TICKER>/10-K/...
    """
    try:
        # Aligning with your ingest.py structure in the /data root
        download_path = os.path.join(os.getcwd(), "data", "sec_filings")
        
        if not os.path.exists(download_path):
            os.makedirs(download_path)
            print(f"📁 Created directory: {download_path}")

        dl = Downloader(USER_AGENT, download_path)

        print(f"⏳ Requesting the latest 10-K for {ticker.upper()}...")
        
        # Filtering for filings after 2025-01-01 to ensure the Auditor 
        # gets the 2026 data we've been targeting.
        dl.get("10-K", ticker.upper(), after="2025-01-01", limit=amount)
        
        print(f"✅ Download complete for {ticker.upper()}. Files are in the 'data' folder.")
        
    except Exception as e:
        # Catching everything from network timeouts to SEC rate-limiting
        print(f"❌ Error downloading filings for {ticker.upper()}: {e}")

if __name__ == "__main__":
    # 1. Parameter Check: Use first argument if provided, else default to TSLA
    # No other hardcoded references remain.
    target_ticker = sys.argv[1] if len(sys.argv) > 1 else "TSLA"
    
    fetch_latest_10k(target_ticker)
import os
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

def get_real_counts():
    search_client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name="alpha-analyst-sec-index",
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
    )

    print("--- 📊 ALPHA ANALYST: TRUE INDEX BALANCE ---")
    
    for t in ["TSLA", "MSFT"]:
        # include_total_count=True gives us the actual count in the index
        results = search_client.search(
            search_text="*", 
            filter=f"ticker eq '{t}'", 
            include_total_count=True
        )
        print(f"Ticker {t.upper()}: {results.get_count()} chunks")

if __name__ == "__main__":
    get_real_counts()
    
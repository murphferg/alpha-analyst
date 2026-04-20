import os
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

def run_diagnostic():
    index_name = "alpha-analyst-sec-index"
    endpoint = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
    key = os.getenv("AZURE_AI_SEARCH_KEY")
    
    admin_client = SearchIndexClient(endpoint, AzureKeyCredential(key))
    search_client = SearchClient(endpoint, index_name, AzureKeyCredential(key))

    print(f"--- 🛠️  DIAGNOSING: {index_name} ---")

    # 1. Check Schema
    index = admin_client.get_index(index_name)
    ticker_field = next(f for f in index.fields if f.name == "ticker")
    print(f"[SCHEMA] Ticker Field - Filterable: {ticker_field.filterable}, Facetable: {ticker_field.facetable}")
    
    # 2. Check Semantic Config
    has_semantic = len(index.semantic_search.configurations) > 0 if index.semantic_search else False
    print(f"[SCHEMA] Semantic Config Found: {has_semantic}")

    # 3. Check Document Count
    count = search_client.get_document_count()
    print(f"[DATA] Total Documents in Index: {count}")

    # 4. Test Filter (The most likely failure point)
    try:
        results = search_client.search(search_text="*", filter="ticker eq 'MSFT'", top=1)
        doc_count = sum(1 for _ in results)
        print(f"[SEARCH] Filter 'MSFT' returned: {doc_count} docs")
    except Exception as e:
        print(f"[SEARCH] ❌ FILTER FAILED: {str(e)}")

if __name__ == "__main__":
    run_diagnostic()

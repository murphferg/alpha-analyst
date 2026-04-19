import os
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType, SimpleField,
    SearchableField, VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile
)
from openai import AzureOpenAI

load_dotenv()

# Setup Clients
search_admin_client = SearchIndexClient(
    endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
    credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
)

# Strip '/openai/v1' if it's in your .env
base_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT").replace("/openai/v1", "").rstrip("/")

aoai_client = AzureOpenAI(
    azure_endpoint=base_endpoint,
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview"
)

INDEX_NAME = "alpha-analyst-sec-index"

def create_index():
    # Define the fields: ID, Content (text), and ContentVector (the embedding)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536, # Standard for text-embedding-3-small
            vector_search_profile_name="my-vector-config"
        ),
        SimpleField(name="ticker", type=SearchFieldDataType.String, filterable=True)
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="my-hnsw")],
        profiles=[VectorSearchProfile(name="my-vector-config", algorithm_configuration_name="my-hnsw")]
    )

    index = SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search)
    search_admin_client.create_or_update_index(index)
    print(f"Index {INDEX_NAME} created/updated.")

def upload_document(ticker, text):
    # 1. Chunking (Simple version for now)
    # 2. Embedding
    embedding = aoai_client.embeddings.create(
        input=text[:8000], # Keep it within limits
        model=os.getenv("AZURE_OPENAI_EMBEDDING_MODEL")
    ).data[0].embedding

    # 3. Upload to Search
    search_client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
    )

    # Force uppercase during upload
    search_client.upload_documents([{
        "id": f"{ticker.upper()}-latest",
        "content": text[:1000],
        "contentVector": embedding,
        "ticker": ticker.upper() # Standardize here
    }])
    print(f"Uploaded {ticker} data to Azure AI Search.")

if __name__ == "__main__":
    # 1. Ensure the shelf exists
    create_index()
    
    # 2. FORCE an upload for testing
    print("🚀 Starting manual test upload for TSLA...")
    
    test_text = "Successfully retrieved latest 10-K for TSLA: Revenue up 12%, R&D spend increased."
    
    # We must call the function here!
    upload_document("TSLA", test_text)
    
    print("✅ Ingest script finished. Check the portal count now.")
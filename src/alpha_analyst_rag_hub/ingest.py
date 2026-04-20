import os
import sys
import uuid
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType, SimpleField,
    SearchableField, VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile,
    SemanticConfiguration, SemanticPrioritizedFields, SemanticField, SemanticSearch
)
from openai import AzureOpenAI

load_dotenv()

# --- 1. CLIENT SETUP ---

# Search Admin for schema management
search_admin_client = SearchIndexClient(
    endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
    credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
)

# OpenAI Client for Embeddings
base_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT").replace("/openai/v1", "").rstrip("/")
aoai_client = AzureOpenAI(
    azure_endpoint=base_endpoint,
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview"
)

INDEX_NAME = "alpha-analyst-sec-index"

# --- 2. SCHEMA MANAGEMENT ---

def create_index():
    """Defines the index schema, including vector and semantic configurations."""
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
        # filterable=True and facetable=True are now set from the start
        SimpleField(name="ticker", type=SearchFieldDataType.String, filterable=True, facetable=True)
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="my-hnsw")],
        profiles=[VectorSearchProfile(name="my-vector-config", algorithm_configuration_name="my-hnsw")]
    )

    # 🏆 NEW: Semantic Configuration (Required for Hybrid Search in main.py)
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="alpha-analyst-config",
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="content")]
                )
            )
        ]
    )

    index = SearchIndex(
        name=INDEX_NAME, 
        fields=fields, 
        vector_search=vector_search,
        semantic_search=semantic_search
    )
    
    search_admin_client.create_or_update_index(index)
    print(f"✅ Index '{INDEX_NAME}' created/updated.")

# --- 3. DATA INGESTION PIPELINE ---

def chunk_text(text, chunk_size=1500, overlap=200):
    """Splits a long document into overlapping chunks to preserve financial context."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks

def upload_document(ticker, text):
    """Chunks, embeds, and uploads data. Replaces 'sticky note' with a full index."""
    
    # 1. Chunking
    text_chunks = chunk_text(text)
    print(f"📦 Splitting {ticker} into {len(text_chunks)} chunks...")

    search_client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
    )

    batch = []
    for i, chunk in enumerate(text_chunks):
        # 2. Embedding (one call per chunk)
        embedding = aoai_client.embeddings.create(
            input=chunk,
            model=os.getenv("AZURE_OPENAI_EMBEDDING_MODEL")
        ).data[0].embedding

        # 3. Create Unique ID
        # Using UUID suffix to prevent accidental overwrites during rapid updates
        batch.append({
            "id": f"{ticker.upper()}-chunk-{i}-{uuid.uuid4().hex[:6]}",
            "content": chunk,
            "contentVector": embedding,
            "ticker": ticker.upper()
        })

        # Upload in batches of 50 for stability
        if len(batch) >= 50:
            search_client.upload_documents(batch)
            batch = []

    if batch:
        search_client.upload_documents(batch)
        
    print(f"🚀 Successfully indexed {len(text_chunks)} chunks for {ticker.upper()}.")

# --- 4. EXECUTION ---

if __name__ == "__main__":
    # 1. Reset if you want a clean slate (removes the old test data)
    if "--reset" in sys.argv:
        # ... (reset logic)
        pass

    create_index()
    
    # 2. LOAD AND RENAME ACTUAL DATA (Directory-Level State)
    data_root = "data"
    
    if os.path.exists(data_root):
        print(f"🔍 Scanning '{data_root}' for new filings...")
        
        # Using topdown=False allows us to rename directories without breaking the walk
        for root, dirs, files in os.walk(data_root, topdown=False):
            
            # 🏆 SMART CHECK: Skip if this folder or any parent is already processed
            if "_processed" in root:
                continue

            # 1. Identify the 'Best' candidate in the current folder
            target_file = None
            html_files = [f for f in files if f == "primary-document.html"]
            other_html = [f for f in files if f.endswith(('.html', '.htm'))]
            txt_files = [f for f in files if f == "full-submission.txt"]

            if html_files:
                target_file = html_files[0]
            elif other_html:
                target_file = other_html[0]
            elif txt_files:
                target_file = txt_files[0]

            if not target_file:
                continue

            # 2. Process the identified target
            file_path = os.path.join(root, target_file)
            path_parts = file_path.split(os.sep)
            
            # --- Ticker Extraction ---
            if "sec-edgar-filings" in path_parts:
                ticker_idx = path_parts.index("sec-edgar-filings") + 1
                ticker = path_parts[ticker_idx].upper()
            else:
                ticker = os.path.basename(os.path.dirname(root)).upper()
            
            try:
                print(f"🚀 Found fresh filing for {ticker}. Indexing {target_file}...")
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                if len(content.strip()) > 1000: 
                    # Azure Upload logic
                    upload_document(ticker, content)
                    
                    # 🏆 THE UPGRADE: Rename the entire Accession Number directory
                    # This marks the whole filing as 'done'
                    new_root_path = root + "_processed"
                    
                    # Safety: If it already exists for some reason, remove it
                    if os.path.exists(new_root_path):
                        import shutil
                        shutil.rmtree(new_root_path)
                        
                    os.rename(root, new_root_path)
                    print(f"✅ Entire Filing Directory Marked Processed: {os.path.basename(new_root_path)}")
                
            except Exception as e:
                print(f"❌ Error processing {root}: {e}")
                    
        print("\n✨ Ingestion complete. Accession directories have been updated.")
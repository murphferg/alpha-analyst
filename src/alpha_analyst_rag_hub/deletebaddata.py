import os
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

# 🏆 This is the missing piece
load_dotenv() 

# Now this will return a string instead of None
search_key = os.getenv("AZURE_AI_SEARCH_KEY")
search_endpoint = os.getenv("AZURE_AI_SEARCH_ENDPOINT")

search_client = SearchClient(
    endpoint=search_endpoint,
    index_name="alpha-analyst-sec-index",
    credential=AzureKeyCredential(search_key)
)

# Delete the old placeholder by its ID
search_client.delete_documents(documents=[{"id": "TSLA-latest"}])
print("🗑️ Placeholder 'TSLA-latest' purged.")

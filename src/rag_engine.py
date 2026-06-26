import chromadb
from chromadb.utils import embedding_functions
from ddgs import DDGS
import os
import time

class MarketRAGEngine:
    def __init__(self, db_path="data/chroma_db"):
        """
        Initializes the local vector database for storing market news.
        """
        print(f"Initializing Local ChromaDB at {db_path}...")
        
        # Ensure directory exists
        os.makedirs(db_path, exist_ok=True)
        
        # Initialize the persistent local client
        self.client = chromadb.PersistentClient(path=db_path)
        
        # We use Chroma's default local embedding model (all-MiniLM-L6-v2)
        # This runs directly on your CPU and is completely free
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        # Get or create our news collection
        self.collection = self.client.get_or_create_collection(
            name="market_news",
            embedding_function=self.embedding_fn
        )
        print("Vector Database ready.")

    def fetch_and_store_news(self, ticker: str):
        """
        Pulls recent news from DuckDuckGo and embeds it into the vector database.
        """
        print(f"\nFetching latest news for {ticker} via DuckDuckGo...")
        
        # Add a 3-second delay to prevent DuckDuckGo from rate-limiting us!
        time.sleep(3)
        
        try:
            with DDGS() as ddgs:
                # Get the top 10 recent news articles about the ticker
                news_items = list(ddgs.news(ticker, max_results=10))
        except Exception as e:
            print(f"Failed to fetch news: {e}")
            return
            
        if not news_items:
            print(f"No recent news found for {ticker}.")
            return
            
        documents = []
        metadatas = []
        ids = []
        
        for idx, item in enumerate(news_items):
            # Extract relevant text
            title = item.get("title", "")
            publisher = item.get("source", "Unknown")
            summary = item.get("body", "") 
            date = item.get("date", "Unknown date")
            url = item.get("url", f"{ticker}_news_{idx}") # Use URL as a unique ID
            
            # Create a single cohesive text chunk for the embedding model
            full_text = f"Date: {date}. Title: {title}. Summary: {summary}"
            
            documents.append(full_text)
            metadatas.append({"ticker": ticker, "publisher": publisher})
            # Create a unique ID for the database so articles don't overwrite each other
            ids.append(url)
            
        # Add the data to our local ChromaDB
        # The embedding function automatically converts the text to vectors here
        print(f"Embedding and storing {len(documents)} articles...")
        self.collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print("Done storing news.")

    def query_sentiment(self, ticker: str, query_text: str = "Is the sentiment bullish or bearish?", n_results: int = 3):
        """
        Retrieves the most relevant news for a given query to feed to the LLM.
        """
        print(f"\nQuerying vector database for: '{query_text}'")
        
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where={"ticker": ticker} # Filter to only look at this specific stock
        )
        
        retrieved_docs = results['documents'][0]
        
        if not retrieved_docs:
            return "No relevant news found in the database."
            
        # Format the retrieved chunks into a single text block for the LLM
        formatted_context = "\n---\n".join(retrieved_docs)
        return formatted_context

# Quick local test
if __name__ == "__main__":
    test_ticker = "AAPL"
    
    # Initialize engine
    rag = MarketRAGEngine()
    
    # 1. Fetch and embed today's news
    rag.fetch_and_store_news(test_ticker)
    
    # 2. Test retrieving context for an LLM
    context = rag.query_sentiment(
        ticker=test_ticker,
        query_text="What are the recent product announcements or supply chain issues?"
    )
    
    print("\n=== RETRIEVED CONTEXT FOR LLM ===")
    print(context)
# rag/indexer.py
# Converts your resume into searchable vector embeddings.
# Run this once — creates a ChromaDB database in data/vectorstore/
# The retriever then searches this database to answer job questions.

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from config.settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

# ── Embedding model setup ──────────────────────────────────────────────
# Embeddings convert text into numbers that capture meaning.
# We use OpenAI's embedding model through OpenRouter.

def get_embeddings():
    return OpenAIEmbeddings(
        model           = "text-embedding-3-small",
        openai_api_key  = OPENROUTER_API_KEY,
        openai_api_base = OPENROUTER_BASE_URL,
    )

VECTORSTORE_PATH = "data/vectorstore"


# ── Core functions ─────────────────────────────────────────────────────

def build_index():
    """
    Reads resume.txt, splits it into chunks, converts each chunk
    into embeddings, and stores them in ChromaDB.
    Run this once before using the retriever.
    """

    print("Reading resume.txt...")
    with open("config/resume.txt", "r") as f:
        resume_text = f.read()

    # Also load Q&A answers as additional context
    import json
    with open("config/user_qa.json", "r") as f:
        qa_data = json.load(f)

    # Convert Q&A dict into readable text
    qa_text = "\n".join([
        f"Question: {k}\nAnswer: {v}"
        for k, v in qa_data.items()
    ])

    # Combine resume + Q&A into one knowledge base
    full_text = resume_text + "\n\n" + qa_text

    # Split into chunks
    # Why? Embeddings work best on small focused chunks, not huge documents.
    # Each chunk becomes one searchable unit.
    print("Splitting into chunks...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = 500,   # characters per chunk
        chunk_overlap = 50,    # overlap so context isn't lost at boundaries
    )
    chunks = splitter.create_documents([full_text])
    print(f"Created {len(chunks)} chunks from your resume")

    # Convert chunks to embeddings and store in ChromaDB
    print("Creating embeddings and building vector store...")
    os.makedirs(VECTORSTORE_PATH, exist_ok=True)

    vectorstore = Chroma.from_documents(
        documents        = chunks,
        embedding        = get_embeddings(),
        persist_directory = VECTORSTORE_PATH
    )

    print(f"Vector store saved to {VECTORSTORE_PATH}")
    print(f"Total chunks indexed: {len(chunks)}")
    return vectorstore


def load_index():
    """
    Loads an existing vector store from disk.
    Use this after build_index() has been run once.
    """
    if not os.path.exists(VECTORSTORE_PATH):
        print("No vector store found. Building now...")
        return build_index()

    return Chroma(
        persist_directory = VECTORSTORE_PATH,
        embedding_function = get_embeddings()
    )


# ── Test it ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Building resume index...\n")
    vectorstore = build_index()

    # Test: search for something in your resume
    print("\nTesting search...")
    results = vectorstore.similarity_search(
        "Python and API experience", k=3
    )

    print(f"\nTop {len(results)} chunks found for 'Python and API experience':\n")
    for i, doc in enumerate(results):
        print(f"── Chunk {i+1} ──────────────────────────────")
        print(doc.page_content)
        print()
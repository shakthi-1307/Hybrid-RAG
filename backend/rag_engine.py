"""
rag_logic.py
Simple Functional RAG Logic
No Classes, Just Functions
"""

import os
from pathlib import Path

# LangChain Imports
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama

# Local Config
from config import (
    DATA_DIR,
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    LLM_MODEL,
    OLLAMA_BASE_URL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K_RETRIEVAL
)

# ============================================================================
# 1. GLOBAL INITIALIZATION (Runs once when server starts)
# ============================================================================

print("🔧 Loading AI Models... (This may take a minute)")

# Load Embedding Model
embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

# Load Vector Store (ChromaDB)
vectorstore = Chroma(
    embedding_function=embeddings,
    persist_directory=str(CHROMA_PERSIST_DIR)
)

# Load LLM (Ollama)
llm = Ollama(
    model=LLM_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0.7
)

# Load Text Splitter
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP
)

print("✅ Models Loaded Successfully!\n")

# ============================================================================
# 2. FUNCTIONS
# ============================================================================

def ingest_file(file_path: str) -> dict:
    """
    Load a PDF, chunk it, and store embeddings.
    """
    try:
        print(f"📄 Processing: {file_path}")
        
        # 1. Load PDF
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        
        # 2. Split Text
        chunks = text_splitter.split_documents(documents)
        
        # 3. Store Embeddings
        vectorstore.add_documents(chunks)
        
        return {
            "success": True,
            "message": f"Ingested {len(documents)} pages ({len(chunks)} chunks)",
            "chunks": len(chunks)
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {
            "success": False,
            "message": str(e),
            "chunks": 0
        }

def get_answer(query: str) -> dict:
    """
    Retrieve context and generate an answer.
    """
    try:
        print(f"🔍 Searching for: {query}")
        
        # 1. Find Relevant Chunks
        relevant_docs = vectorstore.similarity_search(query, k=TOP_K_RETRIEVAL)
        
        if not relevant_docs:
            return {
                "success": False,
                "answer": "No relevant documents found. Please upload some PDFs first.",
                "sources": []
            }
        
        # 2. Build Context
        context_text = "\n\n".join([doc.page_content for doc in relevant_docs])
        
        # 3. Create Prompt
        prompt = f"""You are a helpful assistant. Answer the question using ONLY the context below.

CONTEXT:
{context_text}

QUESTION: {query}

ANSWER:"""
        
        # 4. Generate Answer
        answer = llm.invoke(prompt)
        
        # 5. Prepare Sources for Frontend
        sources = []
        for i, doc in enumerate(relevant_docs):
            sources.append({
                "id": i + 1,
                "text": doc.page_content[:150] + "..." # Preview text
            })
        
        return {
            "success": True,
            "answer": answer,
            "sources": sources
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {
            "success": False,
            "answer": f"Error generating answer: {str(e)}",
            "sources": []
        }

def get_stats() -> dict:
    """
    Get simple stats about the database.
    """
    try:
        count = vectorstore._collection.count()
        return {"documents": count}
    except:
        return {"documents": 0}
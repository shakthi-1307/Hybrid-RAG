"""
main.py
FastAPI Server for Offline RAG
Simple, Clean, No Complexity
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import shutil
import os

# Import RAG functions (simple, no classes)
from rag_engine import ingest_file, get_answer, get_stats
from config import DATA_DIR, HOST, PORT, CHROMA_PERSIST_DIR

# ============================================================================
# 1. SETUP FASTAPI
# ============================================================================

app = FastAPI(title="Offline RAG API")

# Enable CORS (allows frontend to talk to backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 2. REQUEST MODELS
# ============================================================================

class QueryRequest(BaseModel):
    query: str

# ============================================================================
# 3. API ENDPOINTS
# ============================================================================

@app.get("/")
def home():
    """Health check endpoint"""
    return {"message": "✅ RAG API is running", "status": "online"}

@app.get("/stats")
def stats():
    """Get database statistics"""
    return get_stats()

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a PDF file and ingest it into the vector store
    """
    try:
        # Save file temporarily
        file_path = os.path.join(DATA_DIR, file.filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Ingest into RAG system
        result = ingest_file(file_path)
        
        if result["success"]:
            return JSONResponse(status_code=200, content=result)
        else:
            return JSONResponse(status_code=500, content=result)
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

@app.post("/chat")
async def chat(request: QueryRequest):
    """
    Get answer to user's question using RAG
    """
    try:
        result = get_answer(request.query)
        
        if result["success"]:
            return JSONResponse(status_code=200, content=result)
        else:
            return JSONResponse(status_code=400, content=result)
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "answer": str(e), "sources": []}
        )

# ============================================================================
# 4. RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("🚀 STARTING RAG API SERVER")
    print("="*50)
    print(f"📍 URL: http://{HOST}:{PORT}")
    print(f"📁 Data Dir: {DATA_DIR}")
    print(f"💾 Vector DB: {CHROMA_PERSIST_DIR}")
    print("="*50 + "\n")
    
    uvicorn.run(app, host=HOST, port=PORT)
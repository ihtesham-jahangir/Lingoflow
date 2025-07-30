import logging
from asyncio.log import logger
import os
from dotenv import load_dotenv

# Load environment variables BEFORE any other imports
load_dotenv()
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from src.database import engine, Base
from src.auth import router as auth_router
from src.story import router as story_router  # New router for story endpoints
from src.api import router as api_router
app = FastAPI()
app.mount("/media", StaticFiles(directory="media"), name="media")
# Include auth routes
app.include_router(auth_router, prefix="/auth")
app.include_router(story_router, prefix="/story")  # Include story routes
app.include_router(api_router, prefix="/api")
@app.on_event("startup")
async def startup():
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create audio directory
    os.makedirs("src/audio", exist_ok=True)

@app.get("/")
async def health_check():
    return {"status": "healthy", "message": "JWT Auth with PostgreSQL & Storytelling Service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or use ["http://localhost:8000", "http://localhost:5000"] for specific ones
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

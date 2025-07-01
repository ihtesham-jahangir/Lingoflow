import os
from dotenv import load_dotenv

# Load environment variables BEFORE any other imports
load_dotenv()

from fastapi import FastAPI
from src.database import engine, Base
from src.auth import router as auth_router

app = FastAPI()

# Include auth routes
app.include_router(auth_router, prefix="/auth")

@app.on_event("startup")
async def startup():
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def health_check():
    return {"status": "healthy", "message": "JWT Auth with PostgreSQL"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.crud import update_user_interests, get_user_interests
from src.schemas import UserInterestsUpdate
from src.models import User

router = APIRouter(tags=["User Interests"])

# Endpoint to get user interests
@router.get("/users/{user_id}/interests", response_model=UserInterestsUpdate)
async def get_interests(user_id: int, db: AsyncSession = Depends(get_db)):
    interests = await get_user_interests(db, user_id)
    if not interests:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or no interests set.")
    return {"interests": interests}

# Endpoint to update user interests
@router.put("/users/{user_id}/interests", response_model=UserInterestsUpdate)
async def update_interests(user_id: int, interests_update: UserInterestsUpdate, db: AsyncSession = Depends(get_db)):
    updated_user = await update_user_interests(db, user_id, interests_update.interests)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return {"interests": updated_user.interests}

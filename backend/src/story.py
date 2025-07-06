# src/story.py
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src import crud, schemas, story_engine, database

router = APIRouter()        # no prefix here; it’s provided in main.py
logger = logging.getLogger(__name__)

@router.post("/start", response_model=schemas.StoryResponse)
async def start_story(
    story: schemas.StoryStart,
    db: AsyncSession = Depends(database.get_db),
):
    if len(story.interests) < 3:
        raise HTTPException(400, "Please provide at least 3 interests")

    db_session = await crud.create_story_session(db, story)
    story_text, choices = story_engine.generate_story_segment(story.interests)
    context_token = str(uuid.uuid4())

    audio_filename = f"audio/story_{db_session.id}.mp3"
    story_engine.generate_tts_audio(story_text, audio_filename)

    await crud.update_story_session(
        db,
        db_session.id,
        story_text,
        choices,
        audio_filename,
        context_token,
    )

    return schemas.StoryResponse(
        session_id=db_session.id,
        story_text=story_text,
        choices=choices,
        audio_url=f"/{audio_filename}",
        context_token=context_token,
    )

@router.post("/continue", response_model=schemas.StoryResponse)
async def continue_story(
    continuation: schemas.StoryContinue,
    db: AsyncSession = Depends(database.get_db),
):
    db_session = await crud.get_story_session(db, continuation.session_id)
    if not db_session:
        raise HTTPException(404, "Session not found")

    if continuation.context_token not in db_session.context_history:
        raise HTTPException(400, "Invalid context token")

    prev_choice = db_session.current_choices.get(continuation.choice, "")
    previous_context = (
        f"Previous story: {db_session.current_story}\n"
        f"User chose: {prev_choice}"
    )

    story_text, choices = story_engine.generate_story_segment(
        db_session.interests,
        previous_context,
    )
    context_token = str(uuid.uuid4())
    audio_filename = f"audio/story_{db_session.id}_{context_token[:8]}.mp3"
    story_engine.generate_tts_audio(story_text, audio_filename)

    await crud.update_story_session(
        db,
        db_session.id,
        story_text,
        choices,
        audio_filename,
        context_token,
    )

    return schemas.StoryResponse(
        session_id=db_session.id,
        story_text=story_text,
        choices=choices,
        audio_url=f"/{audio_filename}",
        context_token=context_token,
    )

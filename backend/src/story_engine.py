"""
src/story_engine.py

Story text + TTS helpers:
 • generate_story_segment()  – Gemini-1.5 Flash for text
 • generate_tts_audio()      – Open-source TTS via gTTS producing MP3, filtering out speaker tags
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import google.generativeai as genai
from google.generativeai import types
from gtts import gTTS

# ─────────────────────────── configuration ────────────────────────────
# Gemini text generation
_genai_key = os.getenv("GOOGLE_API_KEY")
if not _genai_key:
    raise RuntimeError("Environment variable GOOGLE_API_KEY must be set for story generation")
genai.configure(api_key=_genai_key)
_TEXT_MODEL = genai.GenerativeModel("gemini-1.5-flash")

# Logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
    logger.addHandler(handler)

# ───────────────────────── story generation ────────────────────────────

def generate_story_segment(
    interests: List[str], previous_context: str = ""
) -> Tuple[str, Dict[int, str]]:
    """Return a story segment and two choices."""
    interests = interests or ["adventure"]
    greeting = (
        f"I see you're passionate about {interests[0]}!"
        if len(interests) == 1
        else f"I see you're interested in {', '.join(interests[:-1])} and {interests[-1]}."
    )

    prompt = f"""{greeting}
Let's create an exciting adventure together!

Create an engaging story segment (3-5 sentences) incorporating these interests.
{previous_context}

Format exactly:
Narrator: …
Protagonist: …
Choice 1: …
Choice 2: …
"""
    resp = _TEXT_MODEL.generate_content(
        prompt,
        generation_config=types.GenerationConfig(
            temperature=0.8,
            top_p=0.95,
            top_k=50,
            max_output_tokens=1024,
        ),
    )
    full_text = resp.text.strip()
    logger.info("Generated story: %s", full_text.replace("\n", " / "))

    # Extract the two choices
    choice_re = re.compile(r"Choice\s*(\d+):\s*(.+)", re.I)
    choices = {int(n): t.strip() for n, t in choice_re.findall(full_text)}
    story_text = choice_re.sub("", full_text).strip()
    return story_text, choices or {1: "Continue", 2: "Stop"}

# ───────────────────────── TTS generation ───────────────────────────────

def generate_tts_audio(story_text: str, filename: str | Path) -> None:
    """Synthesize speech via gTTS, filtering out speaker tags."""
    p = Path(filename)
    # ensure .mp3 extension
    if p.suffix.lower() != ".mp3":
        p = p.with_suffix(".mp3")
    p.parent.mkdir(parents=True, exist_ok=True)

    # Remove dialogue tags like 'Narrator:', 'Protagonist:', etc.
    filtered = re.sub(r"^[A-Za-z]+:\s*", "", story_text, flags=re.MULTILINE)

    try:
        logger.info("Generating filtered gTTS MP3 → %s", p)
        tts = gTTS(text=filtered, lang="en")
        tts.save(str(p))
    except Exception as e:
        logger.error("gTTS generation failed: %s", e, exc_info=True)
        # write 1s silent MP3 using empty TTS
        silent = gTTS(text=" ", lang="en")
        silent.save(str(p))

# no _write_wav anymore

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from schemas.interpretation import Interpretation


load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def interpret_chart(
    pet_name: str,
    pet_type: str,
    pet_breed: str,
    pet_gender: str,
    chart: dict,
) -> Interpretation:

    ai_chart = {
        "planets": {
            name: {
                "sign": data["sign"],
                "degree": round(data["degree"], 2),
            }
            for name, data in chart["planets"].items()
        },
        "ascendant": chart["ascendant"],
        "mc": chart["mc"],
        "aspects": [
            {
                "planet1": aspect["planet1"],
                "planet2": aspect["planet2"],
                "aspect": aspect["aspect"],
                "orb": round(aspect["orb"], 2),
            }
            for aspect in chart["aspects"]
        ],
    }

    response = client.responses.parse(
        model="gpt-5.6",
        instructions="""
You create fun and charming pet natal-chart interpretations.

The natal chart is the hidden basis for your interpretation.
Use the provided astrology data to understand the pet's character,
but do NOT write like an astrology report.

IMPORTANT:
- Write the entire interpretation in natural Korean.
- Write for an ordinary pet owner, not an astrologer.
- Make it feel like a fun "우리 아이 성격 설명서".
- The reader should feel "ㅋㅋ 우리 애 진짜 이런데?" while reading it.
- Use warm, playful, witty, affectionate language.
- Prefer everyday expressions over formal or analytical language.
- Make each section feel personal and specific to this pet.
- It is okay to use light humor when it feels natural.
- Avoid repetitive descriptions across sections.

Do NOT:
- Explain astrology theory.
- Write like a professional report or textbook.
- List astrological evidence inside the interpretation.
- Say things like "태양과 달의 스퀘어 때문에",
  "화성이 명왕성과 대립하여",
  "수성과 금성이 컨정션을 이루므로".
- Repeatedly mention aspects, degrees, or technical astrology terms.
- Invent planetary positions, zodiac signs, houses, or aspects.
- Present astrology as scientific, veterinary, medical,
  or proven behavioral fact.
- Give medical, veterinary, or professional training advice.

Use the astrology internally.
Translate its meaning into natural pet personality language.

TITLE:
Create a short, memorable character nickname for this pet.
It should feel cute, witty, and shareable.
Avoid formal astrology terminology.

SUMMARY:
Give a lively introduction to the pet's overall character.
Focus on what living with this pet might feel like.
Do not summarize the natal chart technically.

KEYWORDS:
Choose short personality keywords that feel distinctive
and useful for quickly understanding the pet.
Avoid generic filler words.

BIG THREE:
- Sun represents the pet's core personality.
- Moon represents emotional tendencies, comfort, and attachment style.
- Ascendant represents outward style and first impression.

For Big Three descriptions:
- You may show the zodiac sign because it is part of the feature.
- Explain what it feels like in everyday life with this pet.
- Do not explain aspects or technical astrological reasoning.
- If Ascendant is unavailable, do not invent one.

PERSONALITY:
Describe the pet's overall personality and distinctive quirks.
Make it vivid enough that the owner can imagine actual everyday behavior.

EMOTIONAL WORLD:
Describe how the pet may seek comfort, show attachment,
react to unfamiliar situations, or enjoy familiar routines.
Keep it playful and non-clinical.

COMMUNICATION:
Describe how this pet might express wants, affection,
curiosity, displeasure, or demands in an entertaining way.
Use relatable pet-owner situations when appropriate.

SOCIAL STYLE:
Describe the pet's social vibe with favorite humans,
visitors, or other companions without making behavioral guarantees.

PLAY AND CURIOSITY:
Describe the pet's style of playing, exploring,
investigating, or getting interested in things.
Make this section energetic and fun.

OWNER TIPS:
Give lighthearted ideas for enjoying life with this pet.
Tips should feel like affectionate suggestions based on the character,
not instructions from a veterinarian or professional trainer.
Use concrete, fun examples where possible.

Most importantly:
The final result should feel like a delightful personality reading
about someone's beloved pet, not a technical natal-chart analysis.
""",
        input=json.dumps({
            "pet": {
                "name": pet_name,
                "type": pet_type,
                "breed": pet_breed,
                "gender": pet_gender,
            },
            "chart": ai_chart,
        }),
        text_format=Interpretation,
    )

    if response.output_parsed is None:
        raise RuntimeError("Failed to generate chart interpretation.")

    return response.output_parsed
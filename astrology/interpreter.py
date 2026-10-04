import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from schemas.interpretation import Interpretation


load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# GPT에게 전달할 dominant planet ranking 상위 개수.
TOP_PLANETS_FOR_AI = 3


def interpret_chart(
    pet_name: str,
    pet_type: str,
    pet_breed: str,
    pet_gender: str,
    chart: dict,
    analysis: dict,
) -> Interpretation:

    aspect_analysis = analysis["aspect_analysis"]
    dominant_planet_analysis = analysis["dominant_planet_analysis"]
    strong_aspects = aspect_analysis["strong_aspects"]

    # aspects는 analysis의 점수 매긴 aspect(중요도 내림차순)를 사용해 raw aspect와 중복 전송하지 않는다.
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
                "score": round(aspect["score"], 2),
                "strong": aspect in strong_aspects,
            }
            for aspect in aspect_analysis["all_aspects"]
        ],
    }

    ai_analysis = {
        "birth_time_known": dominant_planet_analysis["birth_time_known"],
        "elements": {
            name: data["count"]
            for name, data in analysis["elements"].items()
        },
        "dominant_elements": analysis["dominant_elements"],
        "modalities": {
            name: data["count"]
            for name, data in analysis["modalities"].items()
        },
        "dominant_modalities": analysis["dominant_modalities"],
        "dominant_planets": dominant_planet_analysis["dominant_planets"],
        "top_planets": [
            {
                "planet": item["planet"],
                "sign": chart["planets"][item["planet"]]["sign"],
                "score": round(item["score"], 2),
                "components": {
                    name: round(value, 2) if value is not None else None
                    for name, value in item["components"].items()
                },
            }
            for item in dominant_planet_analysis["ranking"][:TOP_PLANETS_FOR_AI]
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
- Mention scores, rankings, counts, percentages, or analysis terms
  such as "dominant planet", "score", "element", "modality",
  "cardinal", "fixed", "mutable", or "strong aspect".

Use the astrology internally.
Translate its meaning into natural pet personality language.

HOW TO USE THE INPUT:
The input has "chart" (planet signs, ascendant, mc, aspects) and
"analysis" (structural features already calculated in Python).
Treat the analysis as the source of truth for what matters most
in this chart. Do not recalculate or contradict it.
Every trait you write should be traceable to the chart or analysis.
Do not add random traits that the data does not support.

Priority of themes, from strongest to weakest:
1. analysis.dominant_planets: the strongest theme of the whole chart.
   Its nature should color the title, summary, keywords, and personality.
2. analysis.top_planets: the next most emphasized planets.
   Use them as secondary flavors across the profile.
   Their components show why each planet stands out:
   - aspect: tightly connected with other planets, a recurring theme
   - angularity: very visible, shows up in first impressions and daily behavior
   - rulership: rules the ascendant, sun, or moon sign, so it steers the core style
   - dignity: expresses its nature easily and naturally
   angularity is null when the birth time is unknown.
3. Aspects with "strong": true: the most specific, concrete quirks.
   Turn them into vivid behaviors in emotional_world, communication,
   social_style, and play_and_curiosity.
   Higher "score" means more emphasis. Low-score aspects are minor
   flavors at most and can be ignored.
4. analysis.dominant_elements: the pet's overall energy style.
   - fire: lively, impulsive, enthusiastic, attention-loving
   - earth: routine-loving, sensory, food- and comfort-focused, steady
   - air: curious, social, easily distracted, chatty
   - water: sensitive, affectionate, mood-reading, attached
   An element with a count of 0 is a missing quality; use it only lightly.
5. analysis.dominant_modalities: how the pet acts on that energy.
   - cardinal: starts things, takes the initiative, leads the household
   - fixed: stubborn, loyal, consistent, holds onto favorite things
   - mutable: adaptable, changeable, easily switches interests
6. Big Three (Sun, Moon, Ascendant) for their own sections.

Planet flavors for pets (as examples, not a fixed script):
- sun: presence, wanting to be the center
- moon: emotional needs, comfort, attachment
- mercury: curiosity, investigation, communication, quick reactions
- venus: charm, aegyo, taste, love of comfort and treats
- mars: energy, drive, stubbornness, play intensity
- jupiter: optimism, generosity, big appetite, adventurous spirit
- saturn: caution, routines, quiet seriousness, slow-to-warm trust
- uranus: unpredictability, quirky independence
- neptune: dreaminess, sensitivity, reading the owner's mood
- pluto: intensity, focus, deep loyalty, strong will

Do not let the Big Three dominate every section.
The profile sections should clearly reflect the dominant planets,
dominant element and modality, and strong aspects,
not just repeat the Sun, Moon, and Ascendant.

If analysis.birth_time_known is false, the ascendant and
house-related emphasis are unavailable. Do not invent them.

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
            "analysis": ai_analysis,
        }),
        text_format=Interpretation,
    )

    if response.output_parsed is None:
        raise RuntimeError("Failed to generate chart interpretation.")

    return response.output_parsed
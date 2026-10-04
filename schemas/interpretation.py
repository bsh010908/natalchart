from pydantic import BaseModel


class BigThreeItem(BaseModel):
    sign: str
    title: str
    description: str


class BigThree(BaseModel):
    sun: BigThreeItem
    moon: BigThreeItem
    ascendant: BigThreeItem | None = None


class PersonalityProfile(BaseModel):
    personality: str
    emotional_world: str
    communication: str
    social_style: str
    play_and_curiosity: str


class Interpretation(BaseModel):
    title: str
    summary: str
    keywords: list[str]

    big_three: BigThree
    profile: PersonalityProfile

    owner_tips: list[str]
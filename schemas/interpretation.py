
from pydantic import BaseModel, Field


# 공통: 태양, 달, 상승궁
class BigThreeItem(BaseModel):
    sign: str
    title: str
    description: str


class BigThree(BaseModel):
    sun: BigThreeItem
    moon: BigThreeItem
    ascendant: BigThreeItem | None = None


# 사람 전용 해석
class HumanProfile(BaseModel):
    personality: str
    emotional_world: str
    communication: str
    relationships: str
    love_style: str
    career_and_ambition: str
    strengths: str
    growth_areas: str


class HumanInterpretation(BaseModel):
    title: str
    summary: str
    keywords: list[str] = Field(min_length=3, max_length=5)

    big_three: BigThree
    profile: HumanProfile

    life_tips: list[str] = Field(min_length=3, max_length=5)


# 반려동물 전용 해석
class PetProfile(BaseModel):
    personality: str
    emotional_world: str
    communication: str
    social_style: str
    play_and_curiosity: str


class PetInterpretation(BaseModel):
    title: str
    summary: str
    keywords: list[str] = Field(min_length=3, max_length=5)

    big_three: BigThree
    profile: PetProfile

    owner_tips: list[str] = Field(min_length=3, max_length=5)


# 사람 + 반려동물 궁합 해석
class CompatibilityInterpretation(BaseModel):
    title: str
    summary: str
    keywords: list[str] = Field(min_length=3, max_length=5)

    bond_style: str
    emotional_connection: str
    communication: str
    daily_life: str

    strengths: list[str]
    challenges: list[str]
    bonding_tips: list[str] = Field(min_length=3, max_length=5)

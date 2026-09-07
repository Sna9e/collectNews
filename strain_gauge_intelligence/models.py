"""Data models for the strain gauge vertical technology module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ItemType = Literal["news", "patent", "paper"]
RelevanceLevel = Literal["high", "medium", "low"]


class StrainGaugeIntelligenceItem(BaseModel):
    item_id: str = Field(default="", description="Stable local item id.")
    item_type: ItemType = Field(description="news, patent, or paper.")
    title: str = Field(description="Original title.")
    date: str = Field(description="Published date, patent publication date, or paper year.")
    source_name: str = Field(default="", description="Source, publisher, patent office, company, journal, or conference.")
    source_url: str = Field(default="", description="Original URL.")
    summary: str = Field(default="", description="3-5 sentence Chinese factual summary.")
    relation_to_sensor: str = Field(default="", description="Relation to strain gauge or six-axis force/torque sensor.")
    fpc_implication: str = Field(default="", description="Implication for FPC process or integration.")
    relevance_level: RelevanceLevel = Field(default="medium", description="high, medium, or low.")
    relevance_reason: str = Field(default="", description="Rule-based relevance reason.")
    source_quality: str = Field(default="", description="official, professional, patent, paper, or review.")

    publication_number: str = Field(default="", description="Patent publication/application number.")
    applicant: str = Field(default="", description="Patent applicant.")
    country_or_region: str = Field(default="", description="Patent country or region.")
    core_solution: str = Field(default="", description="Patent core solution.")
    reference_point: str = Field(default="", description="Patent reference point.")

    authors_or_institutions: str = Field(default="", description="Paper authors or institutions.")
    venue: str = Field(default="", description="Journal or conference.")
    doi_or_link: str = Field(default="", description="DOI or URL.")
    research_object: str = Field(default="", description="Research object.")
    sensing_structure: str = Field(default="", description="Sensing structure.")
    key_methods_metrics: str = Field(default="", description="Method, experiment metrics, or validation result.")
    engineering_value: str = Field(default="", description="Engineering value assessment.")

    raw_query: str = Field(default="", description="Search query that found the item.")
    raw_snippet: str = Field(default="", description="Original search snippet/content excerpt.")

    @field_validator("title", "date")
    @classmethod
    def _required_text(cls, value):
        if not str(value or "").strip():
            raise ValueError("required text field cannot be empty")
        return str(value).strip()


class StrainGaugeModulePayload(BaseModel):
    module_name: str
    module_name_en: str
    generated_at: str
    news: list[StrainGaugeIntelligenceItem] = Field(default_factory=list)
    patents: list[StrainGaugeIntelligenceItem] = Field(default_factory=list)
    papers: list[StrainGaugeIntelligenceItem] = Field(default_factory=list)
    quantity_check: dict = Field(default_factory=dict)
    searched_windows: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


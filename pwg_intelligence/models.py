from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PWG_MATURITY_LEVELS = ("M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7")
PWG_SOURCE_LEVELS = ("A", "B", "C", "D")

MaturityLevel = Literal["M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7"]
SourceLevel = Literal["A", "B", "C", "D"]


class PWGIntelligenceCard(BaseModel):
    """Standard intelligence card for PWG technology tracking.

    The model mirrors the first-phase Excel `daily_intelligence` sheet. It is
    intentionally decoupled from existing news-only models such as NewsItem.
    """

    model_config = ConfigDict(extra="forbid")

    card_id: str = Field(description="唯一情报卡编号，建议格式为 PWG-YYYYMMDD-序号；演示数据以 DEMO 开头。")
    published_date: str = Field(default="", description="来源页面或文件公开发布日期，优先使用 YYYY-MM-DD。")
    event_date: str = Field(default="", description="事件实际发生日期；未知时可留空。")
    collected_at: str = Field(default="", description="系统采集时间，建议使用 ISO 时间。")
    source_type: str = Field(default="", description="来源类型，如 official、patent、paper、standard、media、market。")
    source_level: SourceLevel = Field(description="来源可信等级：A-D。A 为原始/权威信源，D 为低可信线索。")
    source_name: str = Field(default="", description="来源名称，如公司官网、Google Patents、IEEE、IEC。")
    title: str = Field(default="", description="情报标题。")
    source_url: str = Field(default="", description="原始来源 URL。")
    original_language: str = Field(default="", description="原文语言，如 zh、en、ja、de。")
    main_track: str = Field(default="", description="主赛道，如产品、应用、专利、论文、标准、厂商动态、机会。")
    application_scene: str = Field(default="", description="应用场景，如 AR 眼镜、数据中心光互连、车载光互连。")
    keywords: list[str] = Field(default_factory=list, description="关键词列表。")
    factual_summary: str = Field(default="", description="事实摘要，只记录来源明确披露的信息。")
    key_parameters: dict[str, str] = Field(default_factory=dict, description="关键参数键值对，如损耗、波长、材料、工艺。")
    maturity_level: MaturityLevel = Field(description="技术/产品成熟度等级：M0-M7。")
    evidence_strength: str = Field(default="", description="证据强度说明，如 high、medium、low 或中文说明。")
    fpc_relevance: str = Field(default="", description="与 FPC 厂商能力、工艺或产品机会的相关性。")
    recommended_action: str = Field(default="", description="建议动作，如跟踪、专利检索、样品拆解、客户访谈。")
    owner: str = Field(default="", description="内部负责人。")
    next_review_date: str = Field(default="", description="下一次复核日期，建议使用 YYYY-MM-DD。")
    demo_flag: str = Field(default="", description="演示数据标记；正式数据可留空。")
    pwg_category: str = Field(default="", description="第四阶段规则分类，如 automotive、connector、cpo_datacenter。")
    opportunity_score: int = Field(default=0, ge=0, le=100, description="PWG 机会评分，0-100。")
    scoring_reason: str = Field(default="", description="自动评分理由，必须保留各分项依据。")
    needs_manual_review: bool = Field(default=False, description="是否需要人工复核。")
    classification_reason: str = Field(default="", description="分类规则命中说明。")
    source_level_reason: str = Field(default="", description="来源等级规则命中说明。")
    maturity_reason: str = Field(default="", description="成熟度规则命中说明。")

    @field_validator("card_id")
    @classmethod
    def card_id_must_not_be_blank(cls, value):
        value = str(value or "").strip()
        if not value:
            raise ValueError("card_id must not be blank")
        return value

    @field_validator("keywords", mode="before")
    @classmethod
    def normalize_keywords(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.replace(",", "；").split("；") if item.strip()]
        return list(value)

    @field_validator("key_parameters", mode="before")
    @classmethod
    def normalize_key_parameters(cls, value):
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {str(key): str(val) for key, val in value.items()}
        raise ValueError("key_parameters must be a dict")

    def to_excel_row(self):
        parameters = "；".join(f"{key}={value}" for key, value in self.key_parameters.items())
        return {
            "card_id": self.card_id,
            "published_date": self.published_date,
            "event_date": self.event_date,
            "collected_at": self.collected_at,
            "source_type": self.source_type,
            "source_level": self.source_level,
            "source_name": self.source_name,
            "title": self.title,
            "source_url": self.source_url,
            "original_language": self.original_language,
            "main_track": self.main_track,
            "application_scene": self.application_scene,
            "keywords": "；".join(self.keywords),
            "factual_summary": self.factual_summary,
            "key_parameters": parameters,
            "maturity_level": self.maturity_level,
            "evidence_strength": self.evidence_strength,
            "fpc_relevance": self.fpc_relevance,
            "recommended_action": self.recommended_action,
            "owner": self.owner,
            "next_review_date": self.next_review_date,
            "demo_flag": self.demo_flag,
            "pwg_category": self.pwg_category,
            "opportunity_score": self.opportunity_score,
            "scoring_reason": self.scoring_reason,
            "needs_manual_review": str(self.needs_manual_review).lower(),
            "classification_reason": self.classification_reason,
            "source_level_reason": self.source_level_reason,
            "maturity_reason": self.maturity_reason,
        }

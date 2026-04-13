from pydantic import BaseModel, Field
from typing import List

class BattleDimension(BaseModel):
    dimension: str = Field(description="对比维度，如：核心技术、资金/商业化、舆论/安全性 等")
    company_a_status: str = Field(description="A公司的现状/动作概括（极简）")
    company_b_status: str = Field(description="B公司的现状/动作概括（极简）")
    winner: str = Field(description="本维度的赢家，必须在以下选一：A公司 / B公司 / 战平")

class BattleCardReport(BaseModel):
    summary: str = Field(description="100字以内的战局终极论断")
    dimensions: List[BattleDimension] = Field(description="必须包含 3 到 4 个核心对比维度")

def generate_battle_card(ai_driver, topic_a, data_a, topic_b, data_b, current_date):
    """
    触发红蓝对抗模式，生成竞品雷达简报
    """
    prompt = f"""
    【全局时间锚点】：今天是 {current_date}。
    你是顶级的商业战略分析师。你的任务是对【{topic_a}】和【{topic_b}】进行近期的红蓝对抗深度对比。
    
    {topic_a} 近期核心情报：
    {data_a}
    
    {topic_b} 近期核心情报：
    {data_b}
    
    要求：
    1. 根据双方的情报，提炼出 3-4 个最关键的交锋维度（例如：技术进展、市场份额、高管变动、监管压力等）。
    2. 对每个维度进行冷血、客观的裁决，判定当前阶段谁占上风。
    3. 输出一份对高管极具决策价值的战报。
    """
    report = ai_driver.analyze_structural(prompt, BattleCardReport)
    return report

def chat_with_report(ai_driver, question, report_context):
    prompt = f"""
    你现在是这份商业情报的【首席解读专家】。
    高管正在向你询问关于本次战报的细节。
    
    【本次战报的背景知识库】：
    {report_context}
    
    【高管的问题】：
    {question}
    
    规则：
    1. 必须基于【背景知识库】中的内容进行回答。
    2. 如果知识库中没有相关信息，请诚实回答“本次收集的情报中未提及此细节”，绝对不能依靠自身预训练数据编造！
    3. 回答要精炼、专业，直接切中要害，带有咨询顾问的专业口吻。
    """
    
    if not ai_driver.valid: 
        return "⚠️ AI 驱动器未连接。"
        
    try:
        res = ai_driver.client.chat.completions.create(
            model=ai_driver.model_id,
            messages=[
                {"role": "system", "content": "你是资深的商业分析师与战报解读专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3, # 保持较低温度，确保回答严谨不发散
            max_tokens=1024
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ 解答失败: {str(e)}"

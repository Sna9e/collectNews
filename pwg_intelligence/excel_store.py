from pathlib import Path

import xlsxwriter

from .models import PWGIntelligenceCard


DEFAULT_WORKBOOK_PATH = Path("data") / "pwg_intelligence" / "pwg_intelligence.xlsx"

DAILY_INTELLIGENCE_COLUMNS = [
    "card_id",
    "published_date",
    "event_date",
    "collected_at",
    "source_type",
    "source_level",
    "source_name",
    "title",
    "source_url",
    "original_language",
    "main_track",
    "application_scene",
    "keywords",
    "factual_summary",
    "key_parameters",
    "maturity_level",
    "evidence_strength",
    "fpc_relevance",
    "recommended_action",
    "owner",
    "next_review_date",
    "demo_flag",
    "pwg_category",
    "opportunity_score",
    "scoring_reason",
    "needs_manual_review",
    "classification_reason",
    "source_level_reason",
    "maturity_reason",
]

COMPANIES_COLUMNS = [
    "company_id",
    "company_name",
    "region",
    "role_in_pwg_ecosystem",
    "known_products_or_capabilities",
    "application_focus",
    "relationship_to_fpc",
    "source_level",
    "last_checked",
    "notes",
    "demo_flag",
]

OPPORTUNITIES_COLUMNS = [
    "opportunity_id",
    "opportunity_name",
    "application_scene",
    "target_customer_or_segment",
    "required_fpc_capability",
    "pwg_linkage",
    "maturity_level",
    "priority",
    "recommended_action",
    "owner",
    "next_review_date",
    "demo_flag",
]

STANDARDS_COLUMNS = [
    "standard_id",
    "organization",
    "standard_or_working_group",
    "scope",
    "status",
    "pwg_relevance",
    "source_url",
    "last_checked",
    "recommended_action",
    "demo_flag",
]

KEYWORD_LIBRARY_COLUMNS = [
    "keyword_id",
    "keyword",
    "language",
    "category",
    "related_terms",
    "search_intent",
    "priority",
    "notes",
    "demo_flag",
]

REQUIRED_WORKSHEETS = {
    "daily_intelligence": DAILY_INTELLIGENCE_COLUMNS,
    "companies": COMPANIES_COLUMNS,
    "opportunities": OPPORTUNITIES_COLUMNS,
    "standards": STANDARDS_COLUMNS,
    "keyword_library": KEYWORD_LIBRARY_COLUMNS,
}


def _demo_daily_cards():
    return [
        PWGIntelligenceCard(
            card_id="DEMO-PWG-20260609-001",
            published_date="2026-06-09",
            event_date="2026-06-08",
            collected_at="2026-06-09T09:00:00+08:00",
            source_type="official",
            source_level="A",
            source_name="DEMO - Waveguide Vendor Official Blog",
            title="[DEMO] 厂商展示低损耗聚合物光波导样件",
            source_url="https://example.com/demo/pwg-low-loss",
            original_language="en",
            main_track="产品",
            application_scene="AR 眼镜近眼显示",
            keywords=["DEMO", "polymer waveguide", "AR glasses", "low loss"],
            factual_summary="DEMO：示例厂商披露一款面向 AR 眼镜的聚合物光波导样件，材料体系、耦合结构和样件尺寸均为演示占位信息。",
            key_parameters={"loss": "DEMO 0.15 dB/cm", "wavelength": "DEMO 532 nm"},
            maturity_level="M3",
            evidence_strength="high",
            fpc_relevance="DEMO：可评估与柔性基板贴合、对位和模组组装工艺的耦合关系。",
            recommended_action="DEMO：建立材料与贴合工艺问题清单。",
            owner="DEMO-RD",
            next_review_date="2026-06-16",
            demo_flag="DEMO",
        ),
        PWGIntelligenceCard(
            card_id="DEMO-PWG-20260609-002",
            published_date="2026-06-07",
            event_date="2026-06-07",
            collected_at="2026-06-09T09:00:00+08:00",
            source_type="patent",
            source_level="A",
            source_name="DEMO - Patent Database",
            title="[DEMO] 公开专利涉及柔性聚合物光互连布线",
            source_url="https://example.com/demo/patent-flexible-optical-interconnect",
            original_language="en",
            main_track="专利",
            application_scene="数据中心板级光互连",
            keywords=["DEMO", "flexible optical circuit", "polymer waveguide", "interconnect"],
            factual_summary="DEMO：示例专利围绕柔性聚合物光互连结构展开，重点描述波导走线、耦合端口和封装接口的布局方法。",
            key_parameters={"form_factor": "DEMO flexible strip", "interface": "DEMO edge coupler"},
            maturity_level="M2",
            evidence_strength="medium",
            fpc_relevance="DEMO：与 FPC 的线路布局、压合窗口和端口保护结构存在潜在协同。",
            recommended_action="DEMO：检索同族专利并标注权利要求边界。",
            owner="DEMO-IP",
            next_review_date="2026-06-20",
            demo_flag="DEMO",
        ),
        PWGIntelligenceCard(
            card_id="DEMO-PWG-20260609-003",
            published_date="2026-06-05",
            event_date="2026-06-05",
            collected_at="2026-06-09T09:00:00+08:00",
            source_type="paper",
            source_level="B",
            source_name="DEMO - Academic Conference",
            title="[DEMO] 论文报告聚合物波导热可靠性测试",
            source_url="https://example.com/demo/pwg-thermal-reliability-paper",
            original_language="en",
            main_track="论文",
            application_scene="车载光互连",
            keywords=["DEMO", "thermal reliability", "polymer optical waveguide", "automotive"],
            factual_summary="DEMO：示例论文讨论聚合物光波导在温湿循环下的插损变化，并将可靠性观察点与车载环境需求关联。",
            key_parameters={"test": "DEMO thermal cycling", "metric": "DEMO insertion loss shift"},
            maturity_level="M1",
            evidence_strength="medium",
            fpc_relevance="DEMO：可作为 FPC 相关可靠性验证矩阵的参考输入。",
            recommended_action="DEMO：整理温湿循环、弯折和端口污染测试条件。",
            owner="DEMO-REL",
            next_review_date="2026-06-18",
            demo_flag="DEMO",
        ),
        PWGIntelligenceCard(
            card_id="DEMO-PWG-20260609-004",
            published_date="2026-06-03",
            event_date="2026-06-03",
            collected_at="2026-06-09T09:00:00+08:00",
            source_type="standard",
            source_level="B",
            source_name="DEMO - Standards Working Group",
            title="[DEMO] 标准工作组讨论板级光互连测试方法",
            source_url="https://example.com/demo/standard-board-optical-test",
            original_language="en",
            main_track="标准",
            application_scene="板级光互连测试",
            keywords=["DEMO", "board optical interconnect", "test method", "standard"],
            factual_summary="DEMO：示例标准工作组记录提到板级光互连测试方法，关注插损、耦合稳定性和环境应力后的复测流程。",
            key_parameters={"scope": "DEMO test method", "metric": "DEMO insertion loss"},
            maturity_level="M4",
            evidence_strength="medium",
            fpc_relevance="DEMO：测试方法可能影响 FPC 光互连模块的出货验证要求。",
            recommended_action="DEMO：跟踪工作组下一次会议纪要。",
            owner="DEMO-STD",
            next_review_date="2026-06-30",
            demo_flag="DEMO",
        ),
    ]


def _demo_companies():
    return [
        {
            "company_id": "DEMO-COMP-001",
            "company_name": "DEMO Waveguide Materials Co.",
            "region": "DEMO-US",
            "role_in_pwg_ecosystem": "聚合物材料/波导制程",
            "known_products_or_capabilities": "DEMO：低损耗聚合物材料、旋涂与图形化工艺",
            "application_focus": "AR 眼镜、板级光互连",
            "relationship_to_fpc": "可作为 FPC 光互连材料合作对象",
            "source_level": "B",
            "last_checked": "2026-06-09",
            "notes": "DEMO：仅为演示占位。",
            "demo_flag": "DEMO",
        },
        {
            "company_id": "DEMO-COMP-002",
            "company_name": "DEMO Optical Engine Inc.",
            "region": "DEMO-JP",
            "role_in_pwg_ecosystem": "光机/耦合模块",
            "known_products_or_capabilities": "DEMO：微型投影光机、波导耦合端口",
            "application_focus": "近眼显示",
            "relationship_to_fpc": "可能带动柔性连接与模组封装需求",
            "source_level": "B",
            "last_checked": "2026-06-09",
            "notes": "DEMO：需后续核查真实产品。",
            "demo_flag": "DEMO",
        },
        {
            "company_id": "DEMO-COMP-003",
            "company_name": "DEMO Flexible Circuit Supplier",
            "region": "DEMO-CN",
            "role_in_pwg_ecosystem": "FPC/模组制造",
            "known_products_or_capabilities": "DEMO：精密线路、贴合、补强和连接器组装",
            "application_focus": "消费电子与车载模组",
            "relationship_to_fpc": "内部对标对象",
            "source_level": "C",
            "last_checked": "2026-06-09",
            "notes": "DEMO：作为 FPC 能力映射样例。",
            "demo_flag": "DEMO",
        },
    ]


def _demo_opportunities():
    return [
        {
            "opportunity_id": "DEMO-OPP-001",
            "opportunity_name": "AR 眼镜波导柔性连接组件",
            "application_scene": "AR 眼镜",
            "target_customer_or_segment": "DEMO：近眼显示模组厂",
            "required_fpc_capability": "高精度贴合、薄型补强、端口保护",
            "pwg_linkage": "聚合物光波导与电连接/机械支撑集成",
            "maturity_level": "M3",
            "priority": "P1",
            "recommended_action": "DEMO：建立样件结构和公差分析。",
            "owner": "DEMO-RD",
            "next_review_date": "2026-06-16",
            "demo_flag": "DEMO",
        },
        {
            "opportunity_id": "DEMO-OPP-002",
            "opportunity_name": "板级光互连柔性跳线",
            "application_scene": "AI 服务器/数据中心",
            "target_customer_or_segment": "DEMO：光模块和交换机厂商",
            "required_fpc_capability": "柔性载体设计、端口固定、可靠性验证",
            "pwg_linkage": "柔性光路承载和板间互连",
            "maturity_level": "M2",
            "priority": "P2",
            "recommended_action": "DEMO：整理竞品结构和专利边界。",
            "owner": "DEMO-BD",
            "next_review_date": "2026-06-20",
            "demo_flag": "DEMO",
        },
        {
            "opportunity_id": "DEMO-OPP-003",
            "opportunity_name": "车载传感器光互连耐久验证服务",
            "application_scene": "车载光互连",
            "target_customer_or_segment": "DEMO：Tier1 光学/传感器模组",
            "required_fpc_capability": "温湿循环、弯折、端口污染控制",
            "pwg_linkage": "聚合物波导可靠性与车规验证相关",
            "maturity_level": "M1",
            "priority": "P3",
            "recommended_action": "DEMO：设计初版测试矩阵。",
            "owner": "DEMO-REL",
            "next_review_date": "2026-06-18",
            "demo_flag": "DEMO",
        },
    ]


def _demo_standards():
    return [
        {
            "standard_id": "DEMO-STD-001",
            "organization": "DEMO-IEC",
            "standard_or_working_group": "Board-level optical interconnect test method",
            "scope": "DEMO：板级光互连插损和环境应力测试",
            "status": "DEMO：working draft",
            "pwg_relevance": "可能定义 PWG 模块测试项目和验收口径",
            "source_url": "https://example.com/demo/iec-board-optical",
            "last_checked": "2026-06-09",
            "recommended_action": "DEMO：跟踪草案版本变化。",
            "demo_flag": "DEMO",
        },
        {
            "standard_id": "DEMO-STD-002",
            "organization": "DEMO-IEEE",
            "standard_or_working_group": "Optical interconnect working group",
            "scope": "DEMO：高速互连接口与链路预算",
            "status": "DEMO：discussion",
            "pwg_relevance": "可能影响数据中心 PWG 互连指标",
            "source_url": "https://example.com/demo/ieee-optical-interconnect",
            "last_checked": "2026-06-09",
            "recommended_action": "DEMO：识别成员公司和应用方向。",
            "demo_flag": "DEMO",
        },
        {
            "standard_id": "DEMO-STD-003",
            "organization": "DEMO-IPC",
            "standard_or_working_group": "Flexible optical circuit reliability",
            "scope": "DEMO：柔性光路结构可靠性与制造缺陷分类",
            "status": "DEMO：watchlist",
            "pwg_relevance": "与 FPC 光互连制造和检验直接相关",
            "source_url": "https://example.com/demo/ipc-flex-optical",
            "last_checked": "2026-06-09",
            "recommended_action": "DEMO：评估是否参与标准讨论。",
            "demo_flag": "DEMO",
        },
    ]


def _demo_keyword_library():
    return [
        {
            "keyword_id": "DEMO-KW-001",
            "keyword": "polymer optical waveguide",
            "language": "en",
            "category": "核心技术",
            "related_terms": "polymer waveguide；POW；optical interconnect",
            "search_intent": "检索聚合物光波导产品、论文和专利",
            "priority": "P1",
            "notes": "DEMO：频道四核心关键词。",
            "demo_flag": "DEMO",
        },
        {
            "keyword_id": "DEMO-KW-002",
            "keyword": "flexible optical circuit",
            "language": "en",
            "category": "FPC机会",
            "related_terms": "flexible waveguide；optical flex；光互连柔性电路",
            "search_intent": "检索 FPC 可切入的柔性光路方案",
            "priority": "P1",
            "notes": "DEMO：用于机会漏斗。",
            "demo_flag": "DEMO",
        },
        {
            "keyword_id": "DEMO-KW-003",
            "keyword": "AR waveguide polymer",
            "language": "en",
            "category": "应用场景",
            "related_terms": "near-eye display；AR glasses；光波导眼镜",
            "search_intent": "检索 AR 眼镜相关 PWG 产品和厂商动态",
            "priority": "P2",
            "notes": "DEMO：用于近眼显示专题。",
            "demo_flag": "DEMO",
        },
        {
            "keyword_id": "DEMO-KW-004",
            "keyword": "board-level optical interconnect",
            "language": "en",
            "category": "应用场景",
            "related_terms": "co-packaged optics；optical PCB；chip-to-chip optical link",
            "search_intent": "检索数据中心和板级光互连方向",
            "priority": "P2",
            "notes": "DEMO：用于 CPO/板级互连扩展。",
            "demo_flag": "DEMO",
        },
        {
            "keyword_id": "DEMO-KW-005",
            "keyword": "聚合物光波导",
            "language": "zh",
            "category": "核心技术",
            "related_terms": "光互连；柔性光波导；板级光互连",
            "search_intent": "检索中文公开材料、专利和产业报道",
            "priority": "P1",
            "notes": "DEMO：中文基础关键词。",
            "demo_flag": "DEMO",
        },
    ]


def build_demo_workbook_payload():
    return {
        "daily_intelligence": [card.to_excel_row() for card in _demo_daily_cards()],
        "companies": _demo_companies(),
        "opportunities": _demo_opportunities(),
        "standards": _demo_standards(),
        "keyword_library": _demo_keyword_library(),
    }


def _write_sheet(workbook, sheet_name, columns, rows, header_format, demo_format):
    worksheet = workbook.add_worksheet(sheet_name)
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(len(rows), 1), len(columns) - 1)
    for col_index, column_name in enumerate(columns):
        worksheet.write(0, col_index, column_name, header_format)
        worksheet.set_column(col_index, col_index, 18)
    for row_index, row in enumerate(rows, start=1):
        for col_index, column_name in enumerate(columns):
            value = row.get(column_name, "")
            cell_format = demo_format if row.get("demo_flag") == "DEMO" else None
            worksheet.write(row_index, col_index, value, cell_format)


def create_pwg_intelligence_workbook(output_path=DEFAULT_WORKBOOK_PATH, extra_daily_rows=None, extra_opportunity_rows=None):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_demo_workbook_payload()
    if extra_daily_rows:
        payload["daily_intelligence"].extend(dict(row or {}) for row in extra_daily_rows)
    if extra_opportunity_rows:
        payload["opportunities"].extend(dict(row or {}) for row in extra_opportunity_rows)

    workbook = xlsxwriter.Workbook(str(output))
    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E79",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )
    demo_format = workbook.add_format({"font_color": "#7F6000", "bg_color": "#FFF2CC"})

    for sheet_name, columns in REQUIRED_WORKSHEETS.items():
        _write_sheet(
            workbook,
            sheet_name,
            columns,
            payload.get(sheet_name, []),
            header_format,
            demo_format,
        )

    workbook.close()
    return output


def write_pwg_intelligence_rows(rows, output_path=DEFAULT_WORKBOOK_PATH, opportunity_rows=None):
    """Write classified PWG rows into the phase-1 workbook skeleton.

    The first version rewrites the workbook with DEMO sheets plus the supplied
    formal daily_intelligence rows. It does not attempt incremental xlsx reads.
    """

    return create_pwg_intelligence_workbook(
        output_path=output_path,
        extra_daily_rows=rows,
        extra_opportunity_rows=opportunity_rows,
    )


if __name__ == "__main__":
    print(create_pwg_intelligence_workbook())

import datetime
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.search_engine as search_engine  # noqa: E402
from tools.consumer_daily_validation import (  # noqa: E402
    build_topic_output,
    build_verified_news_package,
    build_verified_topic_events,
    expand_exa_queries_for_topic,
    normalize_time_window,
    verified_package_to_deepseek_material,
)
from tools.intelligence_packs import get_consumer_electronics_topics  # noqa: E402


TARGET_DATE = datetime.date(2026, 5, 12)


def _topic(topic_id):
    for item in get_consumer_electronics_topics():
        if item.get("id") == topic_id:
            return item
    raise AssertionError(f"missing topic: {topic_id}")


def _result(title, domain, content, source="", path="/news"):
    return {
        "title": title,
        "url": f"https://{domain}{path}",
        "content": content,
        "snippet": content,
        "source": source or domain,
        "published_at": "2026-05-12T10:00:00+08:00",
        "provider": "exa",
        "search_provider": "exa",
        "score": 0.5,
    }


def test_consumer_daily_exa_only_does_not_fallback_to_tavily():
    topic = _topic("consumer_phone")
    rows = search_engine.search_consumer_daily(
        topic,
        "",
        "d",
        tavily_key="fake-tavily",
        provider="exa",
        exa_key="",
    )
    assert rows == []


def test_wide_query_builder_generates_layered_exa_queries():
    topic = _topic("ar_vr_ai_glasses")
    queries = search_engine.build_exa_consumer_daily_queries(topic, TARGET_DATE, "72h", search_depth="wide")
    query_types = {item["query_type"] for item in queries}
    assert len(queries) >= 20
    assert {"core", "company_cn", "company_global", "technology", "supply_chain", "media_site", "official"} & query_types
    assert any("Rokid" in item["query"] or "雷鸟" in item["query"] for item in queries)
    assert any(item["language"] == "en" for item in queries)


def test_robotics_legacy_topic_generates_china_and_supply_chain_queries():
    topic = _topic("robotics_embodied_ai")
    queries = search_engine.build_exa_consumer_daily_queries(topic, TARGET_DATE, "72h", search_depth="wide")
    joined = "\n".join(item["query"] for item in queries)
    assert len(queries) >= 30
    assert "宇树" in joined or "智元" in joined or "优必选" in joined
    assert "具身智能" in joined
    assert "关节模组" in joined or "灵巧手" in joined or "减速器" in joined
    assert any(item["query_type"] in {"media_site", "official"} for item in queries)


def test_expand_exa_queries_for_topic_has_media_and_supply_chain_terms():
    topic = _topic("ar_vr_ai_glasses")
    queries = expand_exa_queries_for_topic(topic, 2, TARGET_DATE, limit=24)
    joined = "\n".join(queries)
    assert "site:ithome.com" in joined or "site:cls.cn" in joined
    assert "光波导" in joined or "Micro OLED" in joined or "显示模组" in joined


def test_discovery_keeps_candidate_without_required_terms_until_validation():
    topic = _topic("ar_vr_ai_glasses")
    original = search_engine._search_web_exa

    def fake_exa(query, sites_text, timelimit, max_results=20, exa_key="", exa_settings=None):
        return [
            _result(
                "消费电子公司发布新品但标题缺少专题关键词",
                "example.com",
                "今日 某公司 发布 新品 参数 更新，这条用于验证 discovery 阶段不要被 required_terms 过早硬过滤。",
                path=f"/{abs(hash(query))}.html",
            )
        ]

    try:
        search_engine._search_web_exa = fake_exa
        rows = search_engine.search_consumer_daily(
            topic,
            "",
            "d",
            provider="exa",
            exa_key="fake-exa",
            max_results_per_query=1,
            max_queries=4,
            search_depth="light",
            strict_required=False,
        )
        assert rows
        strict_rows = search_engine.rank_consumer_daily_results(rows, topic, strict_required=True)
        assert strict_rows == []
    finally:
        search_engine._search_web_exa = original


def test_exa_expansion_can_reach_three_main_events():
    topic = _topic("ar_vr_ai_glasses")
    base = [
        _result(
            "雷鸟 AI眼镜 今日 发布拍摄功能升级",
            "rayneo.com",
            "雷鸟创新 今日 发布 AI眼镜 拍摄、近眼显示和端侧AI功能升级。",
            source="雷鸟创新官网",
            path="/base",
        )
    ]

    def expansion_search(query, _topic_pack, _window=None):
        if "Rokid" not in query and "XREAL" not in query and "Meta" not in query:
            return []
        return [
            _result("Rokid 智能眼镜今日公布参数升级", "rokid.com", "Rokid 今日 发布 智能眼镜 参数升级，涉及光波导、显示模组和AI识别。", source="Rokid官网", path="/rokid"),
            _result("XREAL AR眼镜今日更新显示模组方案", "xreal.com", "XREAL 今日 发布 AR眼镜 显示模组更新，涉及Micro OLED和近眼显示体验。", source="XREAL官网", path="/xreal"),
            _result("Meta Quest VR头显今日公布系统更新", "meta.com", "Meta 今日 发布 Quest VR头显 系统更新，重点是空间计算、手势追踪和开发者功能。", source="Meta官网", path="/quest"),
        ]

    verified = build_verified_topic_events(topic, base, TARGET_DATE, "72h", verification_search_fn=expansion_search)
    output = build_topic_output(verified)
    assert verified.expansion_attempts
    assert len(output.main_events) >= 3


def test_old_news_from_exa_expansion_is_rejected_not_filled():
    topic = _topic("foldable_display_supply")

    def expansion_search(_query, _topic_pack, _window=None):
        return [
            _result(
                "三星折叠手机供应链旧闻汇总",
                "ithome.com",
                "这是一篇折叠屏 历史参数整理，正文回顾 2026年3月10日 的三星折叠手机铰链与OLED供应链消息。",
                source="IT之家",
                path="/old",
            )
        ]

    verified = build_verified_topic_events(topic, [], TARGET_DATE, "72h", verification_search_fn=expansion_search)
    assert not build_topic_output(verified).main_events
    assert any(item.confidence_level == "stale" for item in verified.rejected_summary)


def test_36kr_single_source_stays_watchlist_not_main():
    topic = _topic("ar_vr_ai_glasses")
    verified = build_verified_topic_events(
        topic,
        [
            _result(
                "雷鸟 AI 眼镜发布新功能",
                "36kr.com",
                "36氪获悉，雷鸟 AI眼镜 今日 发布 新功能，涉及显示模组和AI能力升级。",
                source="36氪",
                path="/36kr-only",
            )
        ],
        TARGET_DATE,
        "72h",
    )
    output = build_topic_output(verified)
    assert not output.main_events
    assert verified.watchlist_events


def test_ai_topic_defaults_to_week_window_and_deepseek_material_is_verified():
    topic = _topic("ai_weekly")
    assert normalize_time_window(topic, "72h") == "7d"
    verified = build_verified_topic_events(
        topic,
        [
            _result("DeepSeek 今日 发布 API 更新", "deepseek.com", "DeepSeek 今日 发布 AI 大模型 API 更新，涉及推理成本和上下文窗口。", source="DeepSeek官网", path="/api"),
        ],
        TARGET_DATE,
        "72h",
    )
    package = build_verified_news_package([verified], TARGET_DATE, "7d", search_provider="exa")
    material = verified_package_to_deepseek_material(package)
    assert '"search_provider": "exa"' in material
    assert "confirmed_events" in material
    assert "watchlist_events" in material


def run_all():
    tests = [
        test_consumer_daily_exa_only_does_not_fallback_to_tavily,
        test_wide_query_builder_generates_layered_exa_queries,
        test_robotics_legacy_topic_generates_china_and_supply_chain_queries,
        test_expand_exa_queries_for_topic_has_media_and_supply_chain_terms,
        test_discovery_keeps_candidate_without_required_terms_until_validation,
        test_exa_expansion_can_reach_three_main_events,
        test_old_news_from_exa_expansion_is_rejected_not_filled,
        test_36kr_single_source_stays_watchlist_not_main,
        test_ai_topic_defaults_to_week_window_and_deepseek_material_is_verified,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()

import datetime
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from agents.deep_analyst import map_reduce_analysis  # noqa: E402
except ModuleNotFoundError:
    map_reduce_analysis = None
from tools import consumer_topic_query_packs as topic_packs  # noqa: E402
from tools.consumer_daily_validation import (  # noqa: E402
    build_topic_output,
    build_verified_news_package,
    build_verified_topic_events,
    verified_package_to_deepseek_material,
)


TARGET_DATE = datetime.date(2026, 5, 12)
TARGET_DT = datetime.datetime(2026, 5, 12, 12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))


class FakeAI:
    valid = True
    label = "FakeAI"

    def analyze_structural(self, prompt, structure_class):
        return None


def _result(title, domain, content, path="/news", published="2026-05-12T10:00:00+08:00"):
    return {
        "title": title,
        "url": f"https://{domain}{path}",
        "content": content,
        "snippet": content,
        "published_at": published,
        "published": published,
        "published_date": published,
        "published_at_resolved": published,
        "source": domain,
        "provider": "exa",
        "search_provider": "exa",
        "score": 0.7,
    }


def _pack(topic_id):
    return topic_packs.get_consumer_topic_query_pack(topic_id)


def test_six_topic_packs_load():
    packs = topic_packs.get_all_consumer_topic_query_packs()
    ids = {pack.topic_id for pack in packs}
    assert len(packs) == 6
    assert ids == {
        "consumer_phone",
        "ar_vr_ai_glasses",
        "ai_weekly",
        "ev_smart_car",
        "foldable_display_supply_chain",
        "robotics_embodied_ai",
    }


def test_each_topic_pack_generates_at_least_ten_queries():
    for pack in topic_packs.get_all_consumer_topic_query_packs():
        queries = topic_packs.build_consumer_topic_queries_from_pack(pack)
        assert len(queries) >= 18, pack.topic_id


def test_robotics_topic_pack_has_china_weighted_breadth_queries():
    pack = _pack("robotics_embodied_ai")
    queries = topic_packs.build_consumer_topic_queries_from_pack(pack, max_queries=80)
    joined = "\n".join(queries)
    assert "宇树" in joined or "智元" in joined or "优必选" in joined
    assert "具身智能" in joined
    assert "关节模组" in joined or "灵巧手" in joined or "减速器" in joined
    assert any(query.startswith("site:") for query in queries)


def test_channel3_exa_only_requires_exa_key():
    try:
        topic_packs.collect_consumer_topic_search_results(_pack("consumer_phone"), "72h", exa_key="")
    except RuntimeError as exc:
        assert "EXA_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing EXA_API_KEY to fail explicitly")


def test_collect_consumer_topic_search_uses_exa_only(monkeypatch=None):
    calls = []
    original = topic_packs.search_web

    def fake_search_web(query, sites_text, timelimit, max_results=20, tavily_key="", provider="", exa_key="", exa_settings=None):
        calls.append({"provider": provider, "tavily_key": tavily_key, "exa_key": exa_key, "query": query})
        return [_result("华为新机发布 AI 功能升级", "ithome.com", "华为 手机 新品 参数 AI 功能 发布")]

    topic_packs.search_web = fake_search_web
    try:
        rows, stats = topic_packs.collect_consumer_topic_search_results(
            _pack("consumer_phone"),
            "72h",
            exa_key="fake-exa",
            search_depth="light",
        )
    finally:
        topic_packs.search_web = original

    assert rows
    assert stats["query_count"] >= 10
    assert calls
    assert all(call["provider"] == "exa" for call in calls)
    assert all(call["tavily_key"] == "" for call in calls)


def test_consumer_topic_freshness_filter_rejects_old_news():
    pack = _pack("ar_vr_ai_glasses")
    fresh = _result("雷鸟 AI 眼镜发布新功能", "ithome.com", "雷鸟 AI眼镜 智能眼镜 发布 参数")
    old = _result(
        "雷鸟 AI 眼镜旧款回顾",
        "ithome.com",
        "雷鸟 AI眼镜 旧款 回顾",
        path="/old",
        published="2026-01-01T10:00:00+08:00",
    )
    filtered, stats, warnings = topic_packs.filter_consumer_results_by_freshness([fresh, old], pack, "72h", TARGET_DT)
    assert len(filtered) == 1
    assert filtered[0]["title"] == fresh["title"]
    assert stats["dropped_stale_count"] == 1
    assert warnings


def test_event_master_can_be_generated_from_topic_results():
    if map_reduce_analysis is None:
        return "SKIP test_event_master_can_be_generated_from_topic_results: pydantic is not installed"
    pack = _pack("ev_smart_car")
    rows = [
        _result(
            "小鹏 OTA 推送高阶智驾更新",
            "autohome.com.cn",
            "小鹏在5月12日推送高阶智驾OTA更新，面向城市NOA和泊车场景升级。此次更新涉及感知算法、车道选择和复杂路口通行能力。报道提到新版本会分批覆盖主力车型，直接影响用户智能驾驶体验和后续软件订阅转化。",
        ),
        _result(
            "比亚迪发布电池新技术",
            "gasgoo.com",
            "比亚迪在5月12日发布电池新技术，重点围绕800V平台和快充效率展开。该技术涉及电芯、热管理和整车高压系统协同。报道提到新方案将服务后续车型平台，直接影响补能体验、供应链验证和同业快充竞争。",
        ),
    ]
    events = topic_packs.generate_consumer_topic_event_master(FakeAI(), pack, rows, "2026年05月12日", "72h")
    assert events
    assert all(getattr(event, "event_id", "") for event in events)


def test_map_reduce_fallback_outputs_structured_event_news():
    if map_reduce_analysis is None:
        return "SKIP test_map_reduce_fallback_outputs_structured_event_news: pydantic is not installed"
    event_blueprints = [
        {
            "event_id": "CONSUMER_PHONE-001",
            "date": "2026-05-12",
            "source": "IT之家",
            "event": "华为新机发布",
            "source_url": "https://ithome.com/news",
            "keywords": ["华为", "手机", "AI"],
        }
    ]
    rows = [
        _result(
            "华为新机发布 AI 功能升级",
            "ithome.com",
            "华为在5月12日发布新机并升级AI功能，重点面向影像、语音助手和端侧推理场景。新机参数涉及手机芯片、屏幕和电池配置。该更新会影响高端手机竞争、应用适配和上游零部件备货节奏。",
        )
    ]
    news, insight = map_reduce_analysis(
        FakeAI(),
        "消费电子 / 手机产业",
        "短材料",
        "2026年05月12日",
        "72h",
        "",
        event_blueprints=event_blueprints,
        source_mode="consumer_daily_full_pipeline",
        raw_search_results=rows,
        min_news_count=1,
        max_news_count=3,
    )
    assert news
    assert getattr(news[0], "event_id", "") == "CONSUMER_PHONE-001"


def test_weak_only_stays_watchlist_not_main_news():
    pack = _pack("ar_vr_ai_glasses").to_topic_dict()
    rows = [
        _result("36氪：某公司发布 AI 眼镜", "36kr.com", "36氪获悉 某公司 AI眼镜 发布 参数")
    ]
    verified = build_verified_topic_events(pack, rows, TARGET_DATE, time_window="72h", verification_search_fn=None)
    output = build_topic_output(verified)
    assert not output.main_events
    assert output.watchlist_events


def test_stale_event_is_not_formal_news():
    pack = _pack("foldable_display_supply_chain").to_topic_dict()
    rows = [
        _result(
            "三星折叠屏手机旧款盘点",
            "ithome.com",
            "三星 折叠屏 旧款盘点 历史回顾",
            published="2025-12-01T10:00:00+08:00",
        )
    ]
    verified = build_verified_topic_events(pack, rows, TARGET_DATE, time_window="72h", verification_search_fn=None)
    output = build_topic_output(verified)
    assert not output.main_events


def test_verified_package_is_deepseek_input_not_raw_cards():
    pack = _pack("ai_weekly").to_topic_dict()
    rows = [
        _result("OpenAI 发布模型更新", "openai.com", "OpenAI ChatGPT 模型 更新 API 发布"),
        _result("机器之心报道 OpenAI 模型更新", "jiqizhixin.com", "OpenAI ChatGPT 模型 更新 API 发布", path="/openai"),
    ]
    verified = build_verified_topic_events(pack, rows, TARGET_DATE, time_window="7d", verification_search_fn=None)
    package = build_verified_news_package([verified], TARGET_DATE, "7d", search_provider="exa")
    material = verified_package_to_deepseek_material(package)
    assert "confirmed_events" in material
    assert "likely_events" in material
    assert '"search_provider": "exa"' in material


def test_agent_app_channel3_pipeline_static_contract():
    text = (ROOT / "agent_app.py").read_text(encoding="utf-8")
    start = text.index("with tab3:")
    tail = text.index("else:", start)
    block = text[start:tail]
    assert "get_all_consumer_topic_query_packs()" in block
    assert "collect_consumer_topic_search_results(" in block
    assert "filter_consumer_results_by_freshness(" in block
    assert "build_event_blueprints(" in block
    assert "collect_source_material(" in block
    assert "consumer_daily_full_pipeline" in block
    assert "fetch_financial_data(" not in block


def run_all():
    tests = [
        test_six_topic_packs_load,
        test_each_topic_pack_generates_at_least_ten_queries,
        test_robotics_topic_pack_has_china_weighted_breadth_queries,
        test_channel3_exa_only_requires_exa_key,
        test_collect_consumer_topic_search_uses_exa_only,
        test_consumer_topic_freshness_filter_rejects_old_news,
        test_event_master_can_be_generated_from_topic_results,
        test_map_reduce_fallback_outputs_structured_event_news,
        test_weak_only_stays_watchlist_not_main_news,
        test_stale_event_is_not_formal_news,
        test_verified_package_is_deepseek_input_not_raw_cards,
        test_agent_app_channel3_pipeline_static_contract,
    ]
    for test in tests:
        result = test()
        if result:
            print(result)
        else:
            print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()

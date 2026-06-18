import datetime
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.deep_analyst import (  # noqa: E402
    NewsItem,
    _expand_short_summary,
    _finalize_news_output,
    _sanitize_generated_summary,
)
from tools.company_query_packs import get_company_query_pack, rank_results_by_company_pack  # noqa: E402
from tools.search_engine import verify_selected_news_by_title_search  # noqa: E402


NOW = datetime.datetime(2026, 5, 12, 12, 0, tzinfo=datetime.timezone.utc)


class StubNews:
    def __init__(self, title, url=""):
        self.title = title
        self.url = url


def _result(title, content="", published="2026-05-12T10:00:00+00:00", url_path="/news"):
    row = {
        "title": title,
        "url": f"https://example.com{url_path}",
        "content": content,
        "source": "example.com",
        "provider": "stub",
    }
    if published:
        row["published"] = published
        row["published_date"] = published
        row["published_at_resolved"] = published
    return row


def test_patch_lines_are_removed_and_section_titles_are_kept():
    summary = """
【事件核心】
苹果发布新芯片。
进一步看，第二条搜索摘要被拼接进来。
【深度细节/数据支撑】
材料显示新品涉及端侧 AI 和供应链变化。
更进一步，第三条搜索摘要继续被拼接。
【行业深远影响】
该事件可能影响高端手机和供应链排产。
补充判断：围绕“苹果、芯片”的后续信息仍在持续增加。
"""
    cleaned = _sanitize_generated_summary(summary)
    assert "【事件核心】" in cleaned
    assert "【深度细节/数据支撑】" in cleaned
    assert "【行业深远影响】" in cleaned
    assert "进一步看" not in cleaned
    assert "更进一步" not in cleaned
    assert "补充判断：围绕" not in cleaned


def test_expand_short_summary_does_not_append_supporting_results():
    summary = "【事件核心】\n苹果发布新芯片。\n【深度细节/数据支撑】\n材料只披露了标题。\n【行业深远影响】\n影响仍需观察。"
    supporting_results = [
        {"title": "第二条搜索摘要", "content": "这是不应被自动拼接的第二条搜索摘要。"},
        {"title": "第三条搜索摘要", "content": "这是不应被自动拼接的第三条搜索摘要。"},
    ]
    cleaned = _expand_short_summary(summary, "Apple", {"event": "苹果发布新芯片"}, supporting_results)
    assert "【事件核心】" in cleaned
    assert "【深度细节/数据支撑】" in cleaned
    assert "【行业深远影响】" in cleaned
    assert "第二条搜索摘要" not in cleaned
    assert "第三条搜索摘要" not in cleaned
    assert "进一步看" not in cleaned
    assert "补充判断：围绕" not in cleaned


def test_title_gate_keeps_matching_fresh_news():
    news = [StubNews("Apple 发布 M5 芯片")]

    def search_fn(*_args, **_kwargs):
        return [_result("Apple 发布 M5 芯片最新消息", "Apple 发布 M5 芯片，供应链进入验证阶段。")]

    kept, warnings = verify_selected_news_by_title_search(news, "Apple", "d", now=NOW, search_fn=search_fn)
    assert kept == news
    assert not warnings


def test_title_gate_keeps_same_url_when_translated_title_differs():
    news = [StubNews("苹果发布端侧AI功能更新", url="https://example.com/newsroom/apple-ai")]

    def search_fn(*_args, **_kwargs):
        return [
            _result(
                "Apple announces new on-device AI features",
                "Apple announces new on-device AI features for iPhone and Mac.",
                url_path="/newsroom/apple-ai",
            )
        ]

    kept, warnings = verify_selected_news_by_title_search(news, "Apple", "d", now=NOW, search_fn=search_fn)
    assert kept == news
    assert not warnings


def test_title_gate_drops_no_results_missing_time_stale_future_and_mismatch():
    cases = [
        ("搜索无结果", lambda *_args, **_kwargs: []),
        ("缺时间", lambda *_args, **_kwargs: [_result("Apple 发布 M5 芯片", published="")]),
        ("超窗", lambda *_args, **_kwargs: [_result("Apple 发布 M5 芯片", published="2026-05-01T10:00:00+00:00")]),
        ("未来", lambda *_args, **_kwargs: [_result("Apple 发布 M5 芯片", published="2026-05-14T10:00:00+00:00")]),
        ("标题不匹配", lambda *_args, **_kwargs: [_result("Google 发布 Gemini 模型更新", "Google Gemini 模型能力升级。")]),
    ]
    for label, search_fn in cases:
        kept, warnings = verify_selected_news_by_title_search(
            [StubNews("Apple 发布 M5 芯片")],
            "Apple",
            "d",
            now=NOW,
            search_fn=search_fn,
        )
        assert kept == [], label
        assert warnings, label
        assert "Apple 发布 M5 芯片" not in "\n".join(warnings), label


def test_channel1_static_order_does_not_refill_after_title_gate():
    text = (ROOT / "agent_app.py").read_text(encoding="utf-8")
    start = text.index("with tab1:")
    end = text.index("with tab2:", start)
    block = text[start:end]
    assert block.index("map_reduce_analysis(") < block.index("dedupe_news_items(")
    assert block.index("dedupe_news_items(") < block.index("verify_selected_news_by_title_search(")
    assert block.index("verify_selected_news_by_title_search(") < block.index("fetch_financial_data(")
    after_gate = block[block.index("verify_selected_news_by_title_search("): block.index("fetch_financial_data(")]
    assert "map_reduce_analysis(" not in after_gate


def test_source_quality_filters_low_quality_results():
    pack = get_company_query_pack("Apple")
    results = [
        {
            "title": "Apple announces iPhone AI feature update",
            "url": "https://www.apple.com/newsroom/iphone-ai-feature",
            "content": "Apple announces an iPhone AI feature update with on-device processing and developer APIs.",
            "published_date": "2026-06-09T08:00:00+00:00",
            "published_at_resolved": "2026-06-09T08:00:00+00:00",
            "source": "apple.com",
            "author": "Apple Newsroom",
        },
        {
            "title": "Apple AI update copied from other sites",
            "url": "https://random-low-blog.blogspot.com/apple-ai",
            "content": "转载 优惠券 阅读量 58 Apple AI update read more",
            "published_date": "2026-06-09T08:00:00+00:00",
            "published_at_resolved": "2026-06-09T08:00:00+00:00",
            "source": "blogspot",
        },
    ]
    ranked = rank_results_by_company_pack(results, pack, limit=5)
    assert len(ranked) == 1
    assert ranked[0]["url"] == "https://www.apple.com/newsroom/iphone-ai-feature"


def test_finalize_news_drops_disclaimer_and_invalid_items():
    valid_summary = (
        "【事件核心】\n"
        "苹果在6月发布端侧AI计划，面向iPhone和Mac提供本地模型能力。该计划涉及系统体验、开发者接口和设备端推理场景。"
        "报道提到芯片算力、隐私处理和应用适配是落地重点。\n"
        "【深度细节/数据支撑】\n"
        "苹果新闻稿列出了iPhone、Mac和开发者工具相关方向，说明本地模型能力会进入系统级体验。"
        "这些信息为供应链和开发者评估后续适配节奏提供了直接依据。\n"
        "【行业深远影响】\n"
        "该事件会影响终端AI功能竞争、芯片算力配置和应用生态适配节奏。"
    )
    disclaimer_summary = (
        "【事件核心】\n公开材料显示，苹果发布端侧AI计划。该线索由某网站披露。"
        "材料没有提供足够细节，时间线仅记录已披露动作。"
    )
    report = type(
        "Report",
        (),
        {
            "news": [
                NewsItem(
                    event_id="E01",
                    title="苹果发布端侧AI计划",
                    source="apple.com",
                    date_check="2026-06-09",
                    summary=valid_summary,
                    url="https://www.apple.com/newsroom/iphone-ai-feature",
                    importance=4,
                ),
                NewsItem(
                    event_id="E02",
                    title="苹果AI线索",
                    source="example.com",
                    date_check="2026-06-09",
                    summary=disclaimer_summary,
                    url="https://example.com/apple-ai",
                    importance=3,
                ),
            ],
            "overall_insight": "测试",
        },
    )()
    raw_results = [
        {
            "title": "苹果发布端侧AI计划",
            "url": "https://www.apple.com/newsroom/iphone-ai-feature",
            "content": "苹果在6月发布端侧AI计划，面向iPhone和Mac提供本地模型能力。该计划涉及系统体验、开发者接口和设备端推理场景。报道提到芯片算力、隐私处理和应用适配是落地重点。",
            "published_date": "2026-06-09T08:00:00+00:00",
            "published_at_resolved": "2026-06-09T08:00:00+00:00",
            "source": "apple.com",
            "author": "Apple Newsroom",
        }
    ]
    news, _ = _finalize_news_output(
        report,
        event_blueprints=[{"event_id": "E01", "event": "苹果发布端侧AI计划", "keywords": ["Apple", "iPhone", "AI"]}],
        valid_event_ids=["E01"],
        raw_search_results=raw_results,
        topic="Apple",
        min_count=2,
        max_count=3,
    )
    assert len(news) == 1
    assert news[0].title == "苹果发布端侧AI计划"
    assert "公开材料显示" not in news[0].summary


def run_all():
    tests = [
        test_patch_lines_are_removed_and_section_titles_are_kept,
        test_expand_short_summary_does_not_append_supporting_results,
        test_title_gate_keeps_matching_fresh_news,
        test_title_gate_keeps_same_url_when_translated_title_differs,
        test_title_gate_drops_no_results_missing_time_stale_future_and_mismatch,
        test_channel1_static_order_does_not_refill_after_title_gate,
        test_source_quality_filters_low_quality_results,
        test_finalize_news_drops_disclaimer_and_invalid_items,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()

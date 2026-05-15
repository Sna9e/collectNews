import datetime
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.consumer_daily_validation import (  # noqa: E402
    NewsEvent,
    TopicVerifiedEvents,
    build_verified_news_package,
    build_verified_topic_events,
    build_topic_output,
    candidate_from_raw,
    is_independent_source,
    raw_result_from_search_result,
    validate_consumer_daily_quality,
    verified_package_to_deepseek_material,
)
from tools.intelligence_packs import get_consumer_electronics_topics  # noqa: E402


TARGET_DATE = datetime.date(2026, 5, 12)


def _topic(topic_id):
    for item in get_consumer_electronics_topics():
        if item.get("id") == topic_id:
            return item
    raise AssertionError(f"missing topic: {topic_id}")


def _result(title, domain, content, date="2026-05-12", source="", url_path="/news/1", provider="unit"):
    return {
        "title": title,
        "url": f"https://{domain}{url_path}",
        "content": content,
        "source": source or domain,
        "published_at_resolved": date,
        "provider": provider,
    }


def _article(title, domain, content, topic_id="ar_vr_ai_glasses"):
    topic = _topic(topic_id)
    raw = raw_result_from_search_result(_result(title, domain, content, source=domain), topic)
    return candidate_from_raw(raw, topic, TARGET_DATE, "72h")


def _event(title, level="confirmed", topic_id="consumer_phone", source_count=3, score=0.9):
    return NewsEvent(
        event_id=f"{topic_id}-{title}",
        topic_id=topic_id,
        normalized_title=title,
        event_summary=f"{title} 摘要",
        companies=[],
        products=[],
        technologies=[],
        event_date=TARGET_DATE.isoformat(),
        first_seen_at=TARGET_DATE.isoformat(),
        latest_seen_at=TARGET_DATE.isoformat(),
        evidence_articles=[],
        independent_source_count=source_count,
        official_source_count=1 if level in {"confirmed", "likely"} else 0,
        domestic_source_count=source_count,
        overseas_source_count=0,
        source_domains=["ithome.com", "cls.cn", "rayneo.com"][:source_count],
        source_names=["IT之家", "财联社", "官方"][:source_count],
        confidence_level=level,
        confidence_score=score,
        rejection_reasons=[] if level in {"confirmed", "likely"} else ["evidence_not_enough"],
        time_window="72h",
    )


def _topic_verified(confirmed=None, likely=None, watchlist=None):
    return TopicVerifiedEvents(
        topic_id="consumer_phone",
        topic_name="消费电子与手机新品",
        time_window="72h",
        confirmed_events=list(confirmed or []),
        likely_events=list(likely or []),
        watchlist_events=list(watchlist or []),
        rejected_summary=[],
    )


def test_36kr_single_source_is_not_formal():
    topic = _topic("ar_vr_ai_glasses")
    verified = build_verified_topic_events(
        topic,
        [
            _result(
                "雷鸟 AI 眼镜发布新功能",
                "36kr.com",
                "36氪获悉，雷鸟 AI眼镜 今日 发布 新功能，涉及显示模组和AI能力升级。",
                source="36氪",
            )
        ],
        TARGET_DATE,
        "72h",
    )
    assert not verified.confirmed_events
    assert not verified.likely_events
    assert any(item.confidence_level in {"weak", "rejected"} for item in verified.rejected_summary)


def test_36kr_reprints_count_as_not_independent():
    article_a = _article("雷鸟 AI 眼镜发布新功能", "36kr.com", "36氪获悉，雷鸟 AI眼镜 今日 发布 新功能。")
    article_b = _article("雷鸟 AI 眼镜发布新功能", "qq.com", "据36氪报道，雷鸟 AI眼镜 今日 发布 新功能。")
    article_c = _article("雷鸟智能眼镜新功能", "sohu.com", "来源：36氪，雷鸟 AI眼镜 今日 发布 新功能。")
    assert not is_independent_source(article_a, article_b)
    assert not is_independent_source(article_a, article_c)


def test_official_vertical_and_mainstream_confirm_event():
    topic = _topic("ar_vr_ai_glasses")
    rows = [
        _result(
            "雷鸟创新发布 AI 眼镜显示与拍摄功能升级",
            "rayneo.com",
            "雷鸟创新 今日 发布 AI眼镜 新功能，升级近眼显示、摄像头和端侧AI能力，公布渠道发售节奏。",
            source="雷鸟创新官网",
            url_path="/news/rayneo-ai-glasses-update",
        ),
        _result(
            "雷鸟 AI 眼镜获得新一轮 OTA：显示和摄像头能力升级",
            "ithome.com",
            "IT之家消息，雷鸟 AI眼镜 今日 推出 OTA 更新，涉及近眼显示、摄像头、传感器和AI识别功能。",
            source="IT之家",
            url_path="/0/999/001.htm",
        ),
        _result(
            "雷鸟智能眼镜更新，供应链关注近眼显示模组",
            "cls.cn",
            "财联社报道，雷鸟 今日 更新 智能眼镜 产品功能，市场关注光波导、显示模组和渠道放量。",
            source="财联社",
            url_path="/detail/123",
        ),
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    assert verified.confirmed_events
    assert verified.confirmed_events[0].independent_source_count >= 3


def test_today_page_with_old_event_is_stale():
    topic = _topic("foldable_display_supply")
    verified = build_verified_topic_events(
        topic,
        [
            _result(
                "三星折叠手机供应链回顾",
                "ithome.com",
                "这是一篇折叠屏 历史参数整理，正文主要回顾 2026年3月10日 的三星折叠手机铰链与OLED供应链爆料，没有今天新进展。",
                date="2026-05-12",
                source="IT之家",
            )
        ],
        TARGET_DATE,
        "72h",
    )
    assert not verified.confirmed_events
    assert any(item.confidence_level == "stale" for item in verified.rejected_summary)


def test_ar_topic_rejects_foldable_iphone_noise():
    topic = _topic("ar_vr_ai_glasses")
    verified = build_verified_topic_events(
        topic,
        [
            _result(
                "苹果折叠 iPhone 供应链爆料",
                "ithome.com",
                "今日 苹果 折叠 iPhone 供应链 爆料，重点是折叠屏、铰链和OLED，不涉及AI眼镜或AR眼镜。",
                source="IT之家",
            )
        ],
        TARGET_DATE,
        "72h",
    )
    assert not verified.confirmed_events
    assert not verified.likely_events
    assert any("ar_vr_topic_polluted_by_foldable_phone" in ",".join(item.reasons) for item in verified.rejected_summary)


def test_same_event_clusters_once_and_enters_deepseek_package():
    topic = _topic("ar_vr_ai_glasses")
    rows = [
        _result(
            "雷鸟 AI 眼镜发布新功能",
            "rayneo.com",
            "雷鸟创新 今日 发布 AI眼镜 新功能，包含近眼显示、摄像头、传感器和AI识别升级。",
            source="雷鸟创新官网",
            url_path="/news/a",
        ),
        _result(
            "雷鸟智能眼镜升级近眼显示和 AI 识别",
            "ithome.com",
            "IT之家消息，雷鸟 今日 推出 智能眼镜 OTA 更新，近眼显示和AI识别能力升级。",
            source="IT之家",
            url_path="/news/b",
        ),
        _result(
            "RayNeo AI glasses get camera and display OTA update",
            "cls.cn",
            "财联社报道，雷鸟 AI眼镜 今日 更新 摄像头、显示模组和端侧AI功能，渠道放量受关注。",
            source="财联社",
            url_path="/news/c",
        ),
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    assert len(verified.confirmed_events) == 1
    package = build_verified_news_package([verified], TARGET_DATE, "72h")
    material = verified_package_to_deepseek_material(package)
    assert "雷鸟" in material
    assert "rejected_summary" in material
    assert "confirmed_events" in material


def test_topic_output_keeps_five_confirmed_without_watchlist():
    verified = _topic_verified(confirmed=[_event(f"confirmed-{idx}") for idx in range(5)])
    output = build_topic_output(verified)
    assert len(output.main_events) == 5
    assert not output.watchlist_events
    report = validate_consumer_daily_quality(build_verified_news_package([verified], TARGET_DATE, "72h"))
    assert report.topic_event_counts["消费电子与手机新品"] == 5


def test_topic_output_uses_likely_to_reach_main_news_count():
    verified = _topic_verified(
        confirmed=[_event("c1"), _event("c2")],
        likely=[_event("l1", level="likely", source_count=2), _event("l2", level="likely", source_count=2)],
    )
    output = build_topic_output(verified)
    assert len(output.main_events) == 4
    assert sum(1 for event in output.main_events if event.confidence_level == "likely") == 2


def test_topic_output_adds_watchlist_when_main_news_still_low():
    verified = _topic_verified(
        confirmed=[_event("c1")],
        likely=[_event("l1", level="likely", source_count=2)],
        watchlist=[_event("w1", level="weak", source_count=1)],
    )
    output = build_topic_output(verified)
    assert len(output.main_events) == 2
    assert len(output.watchlist_events) == 1
    assert output.insufficient_warning


def test_auto_expansion_adds_events_before_watchlist():
    topic = _topic("ar_vr_ai_glasses")
    base = [
        _result(
            "雷鸟 AI眼镜 今日 发布拍摄功能升级",
            "rayneo.com",
            "雷鸟创新 今日 发布 AI眼镜 拍摄、近眼显示和端侧AI功能升级。",
            source="雷鸟创新官网",
            url_path="/news/base",
        )
    ]

    def expansion_search(query, _topic_pack, _window=None):
        if "Rokid" not in query and "XREAL" not in query:
            return []
        return [
            _result(
                "Rokid 智能眼镜今日公布参数升级",
                "rokid.com",
                "Rokid 今日 发布 智能眼镜 参数升级，涉及光波导、显示模组和AI识别。",
                source="Rokid官网",
                url_path="/news/rokid",
            ),
            _result(
                "XREAL AR眼镜今日更新显示模组方案",
                "xreal.com",
                "XREAL 今日 发布 AR眼镜 显示模组更新，涉及Micro OLED和近眼显示体验。",
                source="XREAL官网",
                url_path="/news/xreal",
            ),
            _result(
                "Meta Quest VR头显今日公布系统与手势追踪更新",
                "meta.com",
                "Meta 今日 发布 Quest VR头显 系统更新，重点是手势追踪、空间计算和开发者功能。",
                source="Meta官网",
                url_path="/news/quest",
            ),
        ]

    verified = build_verified_topic_events(topic, base, TARGET_DATE, "72h", verification_search_fn=expansion_search)
    output = build_topic_output(verified)
    assert verified.expansion_attempts
    assert len(output.main_events) >= 3


def test_36kr_single_source_can_only_be_watchlist():
    topic = _topic("ar_vr_ai_glasses")
    verified = build_verified_topic_events(
        topic,
        [
            _result(
                "雷鸟 AI 眼镜发布新功能",
                "36kr.com",
                "36氪获悉，雷鸟 AI眼镜 今日 发布 新功能，涉及显示模组和AI能力升级。",
                source="36氪",
            )
        ],
        TARGET_DATE,
        "72h",
    )
    output = build_topic_output(verified)
    assert not output.main_events
    assert verified.watchlist_events


def test_expanded_old_news_is_not_used_to_fill_count():
    topic = _topic("foldable_display_supply")

    def expansion_search(_query, _topic_pack, _window=None):
        return [
            _result(
                "三星折叠手机供应链旧闻汇总",
                "ithome.com",
                "这是一篇折叠屏 历史参数整理，正文回顾 2026年3月10日 的三星折叠手机铰链与OLED供应链消息。",
                date="2026-05-12",
                source="IT之家",
                url_path="/old-foldable",
            )
        ]

    verified = build_verified_topic_events(topic, [], TARGET_DATE, "72h", verification_search_fn=expansion_search)
    output = build_topic_output(verified)
    assert not output.main_events
    assert any(item.confidence_level == "stale" for item in verified.rejected_summary)


def run_all():
    tests = [
        test_36kr_single_source_is_not_formal,
        test_36kr_reprints_count_as_not_independent,
        test_official_vertical_and_mainstream_confirm_event,
        test_today_page_with_old_event_is_stale,
        test_ar_topic_rejects_foldable_iphone_noise,
        test_same_event_clusters_once_and_enters_deepseek_package,
        test_topic_output_keeps_five_confirmed_without_watchlist,
        test_topic_output_uses_likely_to_reach_main_news_count,
        test_topic_output_adds_watchlist_when_main_news_still_low,
        test_auto_expansion_adds_events_before_watchlist,
        test_36kr_single_source_can_only_be_watchlist,
        test_expanded_old_news_is_not_used_to_fill_count,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()

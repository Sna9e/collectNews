import datetime
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.consumer_daily_validation import (  # noqa: E402
    NewsEvent,
    TopicVerifiedEvents,
    build_verified_digest_news_items,
    build_verified_news_package,
    build_verified_topic_events,
    build_topic_output,
    candidate_from_raw,
    classify_source,
    cluster_articles_into_events,
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


def _result(title, domain, content, date="2026-05-12", source="", url_path="/news/1", provider="unit", **extra):
    payload = {
        "title": title,
        "url": f"https://{domain}{url_path}",
        "content": content,
        "source": source or domain,
        "published_at_resolved": date,
        "provider": provider,
    }
    payload.update(extra)
    return payload


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
    topic = dict(_topic("ar_vr_ai_glasses"))
    topic["china_focus"] = True
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


def test_verified_digest_summary_is_factual_chinese_without_disclaimer():
    topic = _topic("ar_vr_ai_glasses")
    rows = [
        _result(
            "雷鸟创新发布 AI 眼镜拍摄与显示升级",
            "rayneo.com",
            "- 记者 张三 - 发布时间 2026-05-12 09:30:00 ... 雷鸟创新在5月12日发布AI眼镜功能升级，新增连续拍摄并改善近眼显示。官方说明本次更新同步优化端侧AI识别和语音交互，面向已售机型分批推送。",
            source="雷鸟创新官网",
            url_path="/news/summary-a",
        ),
        _result(
            "雷鸟 AI 眼镜获得新一轮 OTA",
            "ithome.com",
            "（图／翻摄官方YT）雷鸟AI眼镜在5月12日推送OTA，更新摄像头、显示模组和端侧AI功能。新版本采用分批升级方式，直接改善拍摄和识别体验。",
            source="IT之家",
            url_path="/news/summary-b",
        ),
        _result(
            "雷鸟智能眼镜更新拍摄和识别能力",
            "cls.cn",
            "雷鸟于5月12日更新智能眼镜产品，涉及连续拍摄、近眼显示和AI识别。更新将先覆盖在售设备，并影响后续渠道演示与用户体验。",
            source="财联社",
            url_path="/news/summary-c",
        ),
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    events = verified.confirmed_events or verified.likely_events
    assert events
    summary = events[0].event_summary
    assert re.search(r"[\u4e00-\u9fff]", summary)
    assert 45 <= len(summary) <= 220
    assert "记者" not in summary
    assert "发布时间" not in summary
    assert "..." not in summary
    assert "翻摄" not in summary
    for banned in (
        "公开材料显示",
        "该线索由",
        "材料没有提供足够细节",
        "暂不能确认更多参数",
        "时间线仅记录已披露动作",
    ):
        assert banned not in summary
    digest = build_verified_digest_news_items(events)
    assert digest
    assert digest[0]["summary"] == summary
    assert " / " not in digest[0]["title"]


def test_china_focused_topic_downgrades_global_only_event():
    topic = dict(_topic("consumer_phone"))
    topic["china_focus"] = True
    rows = [
        _result(
            "Samsung officially announces Galaxy phone update",
            "samsung.com",
            "三星官方宣布更新Galaxy手机系统，涉及影像功能和端侧AI能力，并将在海外市场分批推送。",
            source="Samsung",
            url_path="/global-official",
        ),
        _result(
            "Samsung announces Galaxy phone update",
            "engadget.com",
            "三星宣布更新Galaxy手机系统，涉及影像功能和端侧AI能力，并将在本周分批推送。",
            source="Engadget",
            url_path="/global-a",
        ),
        _result(
            "Galaxy phone receives camera and AI upgrade",
            "androidheadlines.com",
            "三星发布Galaxy手机功能升级，新增影像处理和AI识别能力，更新将在海外市场陆续上线。",
            source="Android Headlines",
            url_path="/global-b",
        ),
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    assert not verified.confirmed_events
    assert not verified.likely_events
    assert any(
        "china_focus_without_domestic_evidence" in item.reasons
        for item in verified.rejected_summary
    )


def test_domestic_media_translation_is_not_domestic_event_evidence():
    topic = dict(_topic("ai_weekly"))
    topic["china_focus"] = True
    rows = [
        _result(
            "海外AI公司发布本地智能体平台",
            "ithome.com",
            "Perplexity宣布与Nvidia合作推出本地智能体平台，产品面向海外用户发布，仅描述海外产品和服务安排。",
            source="IT之家",
            url_path="/global-ai-platform",
        )
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    assert not verified.confirmed_events
    assert not verified.likely_events
    assert any(
        "china_focus_without_domestic_evidence" in item.reasons
        for item in verified.rejected_summary
    )


def test_registered_vertical_media_is_trusted_and_unknown_mirrors_do_not_count():
    assert classify_source("phone.cnmo.com", "CNMO")[1] == 2
    assert classify_source("mirror-one.example", "Mirror")[1] == 4

    topic = dict(_topic("consumer_phone"))
    topic["china_focus"] = True
    rows = [
        _result(
            "小米发布新款手机并升级端侧AI",
            domain,
            "小米今日发布新款手机，升级端侧AI、影像系统和电池配置，并公布中国市场开售时间。",
            source=domain,
            url_path=f"/xiaomi-{index}",
        )
        for index, domain in enumerate(("mirror-one.example", "mirror-two.example"), start=1)
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    assert not verified.confirmed_events
    assert not verified.likely_events


def test_page_verified_registered_vertical_source_can_be_likely():
    topic = dict(_topic("consumer_phone"))
    topic["china_focus"] = True
    verified = build_verified_topic_events(
        topic,
        [
            _result(
                "小米发布玄戒O100原型机并展示端侧模型",
                "phone.cnmo.com",
                "小米今日发布玄戒O100原型机，展示Xiaomi MiMo端侧模型、芯片配置和本地AI能力，并公布中国市场演示安排。",
                source="CNMO",
                url_path="/news/xring-o100",
                publication_date_confidence="verified_page",
            )
        ],
        TARGET_DATE,
        "72h",
    )
    assert not verified.confirmed_events
    assert len(verified.likely_events) == 1


def test_generic_ai_glasses_terms_do_not_merge_different_company_events():
    topic = dict(_topic("ar_vr_ai_glasses"))
    rayneo = candidate_from_raw(
        raw_result_from_search_result(
            _result(
                "雷鸟发布 iO AI眼镜并在中国市场开售",
                "rayneo.com",
                "雷鸟创新今日发布iO AI眼镜，公布显示功能、产品价格和中国市场开售安排。",
                source="雷鸟官网",
                url_path="/rayneo-io",
            ),
            topic,
        ),
        topic,
        TARGET_DATE,
        "72h",
    )
    meta = candidate_from_raw(
        raw_result_from_search_result(
            _result(
                "Meta更新AI眼镜隐私提示功能",
                "meta.com",
                "Meta今日更新AI眼镜隐私提示功能，新增录制提示和应用控制选项，产品面向海外市场。",
                source="Meta",
                url_path="/meta-glasses-privacy",
            ),
            topic,
        ),
        topic,
        TARGET_DATE,
        "72h",
    )
    events = cluster_articles_into_events([rayneo, meta], topic, TARGET_DATE, "72h")
    assert len(events) == 2


def test_multi_source_rumor_and_forecast_roundup_never_become_formal_news():
    topic = dict(_topic("consumer_phone"))
    topic["china_focus"] = True
    rows = [
        _result(
            "9月手机新品大战一触即发：多款传闻机型预计集中亮相",
            domain,
            "消息称多家厂商预计在9月发布新机，传闻产品可能采用新芯片和折叠屏。报道未提供公司正式公告或已经发生的发布动作。",
            source=source,
            url_path=f"/forecast-{index}",
        )
        for index, (domain, source) in enumerate(
            (("cnmo.com", "CNMO"), ("gizbot.com", "Gizbot"), ("memeburn.com", "Memeburn")),
            start=1,
        )
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    assert not verified.confirmed_events
    assert not verified.likely_events
    assert any(
        "forecast_or_roundup_not_single_occurred_event" in item.reasons
        for item in verified.rejected_summary
    )


def test_event_uses_published_date_for_future_scheduled_launch_and_chinese_title():
    topic = dict(_topic("consumer_phone"))
    topic["china_focus"] = True
    rows = [
        _result(
            "Huawei announces a new consumer electronics event",
            "huawei.com",
            "华为宣布将在5月13日举行消费电子新品发布会，届时将公布手机端侧AI、影像和系统功能更新，并披露新品在中国市场的发售安排。公司同时宣布已于5月12日开放直播预约。",
            source="华为官网",
            url_path="/scheduled-a",
        )
    ]
    verified = build_verified_topic_events(topic, rows, TARGET_DATE, "72h")
    events = verified.confirmed_events or verified.likely_events
    assert events
    assert events[0].event_date == "2026-05-12"
    assert re.search(r"[\u4e00-\u9fff]", events[0].normalized_title)


def test_topic_output_keeps_three_confirmed_without_watchlist():
    verified = _topic_verified(confirmed=[_event(f"confirmed-{idx}") for idx in range(5)])
    output = build_topic_output(verified)
    assert len(output.main_events) == 3
    assert not output.watchlist_events
    report = validate_consumer_daily_quality(build_verified_news_package([verified], TARGET_DATE, "72h"))
    assert report.topic_event_counts["消费电子与手机新品"] == 3


def test_topic_output_uses_likely_to_reach_main_news_count():
    verified = _topic_verified(
        confirmed=[_event("c1"), _event("c2")],
        likely=[_event("l1", level="likely", source_count=2), _event("l2", level="likely", source_count=2)],
    )
    output = build_topic_output(verified)
    assert len(output.main_events) == 3
    assert sum(1 for event in output.main_events if event.confidence_level == "likely") == 1


def test_topic_output_adds_watchlist_when_main_news_still_low():
    verified = _topic_verified(
        confirmed=[_event("c1")],
        watchlist=[_event("w1", level="weak", source_count=1)],
    )
    output = build_topic_output(verified)
    assert len(output.main_events) == 1
    assert len(output.watchlist_events) == 1
    assert output.insufficient_warning


def test_auto_expansion_adds_events_before_watchlist():
    topic = _topic("ar_vr_ai_glasses")
    base = [
        _result(
            "雷鸟 AI眼镜 今日 发布拍摄功能升级",
            "rayneo.com",
            "雷鸟创新今日发布AI眼镜拍摄、近眼显示和端侧AI功能升级。新版本将面向在售设备分批推送，并改善连续拍摄和语音识别体验。",
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
                "Rokid今日发布智能眼镜参数升级，涉及光波导、显示模组和AI识别。公司同步说明新功能将通过系统更新覆盖在售设备。",
                source="Rokid官网",
                url_path="/news/rokid",
            ),
            _result(
                "XREAL AR眼镜今日更新显示模组方案",
                "xreal.com",
                "XREAL今日发布AR眼镜显示模组更新，涉及Micro OLED和近眼显示体验。新方案用于改善画面亮度与佩戴场景下的显示稳定性。",
                source="XREAL官网",
                url_path="/news/xreal",
            ),
            _result(
                "Meta Quest VR头显今日公布系统与手势追踪更新",
                "meta.com",
                "Meta今日发布Quest VR头显系统更新，重点是手势追踪、空间计算和开发者功能。更新将分批推送，并调整应用交互与开发接口。",
                source="Meta官网",
                url_path="/news/quest",
            ),
        ]

    verified = build_verified_topic_events(topic, base, TARGET_DATE, "72h", verification_search_fn=expansion_search)
    output = build_topic_output(verified)
    assert verified.expansion_attempts
    assert len(output.main_events) >= 3


def test_36kr_single_source_is_hard_blocked():
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
    assert not verified.watchlist_events
    assert any("blocked_source" in ",".join(item.reasons) for item in verified.rejected_summary)


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
        test_verified_digest_summary_is_factual_chinese_without_disclaimer,
        test_china_focused_topic_downgrades_global_only_event,
        test_domestic_media_translation_is_not_domestic_event_evidence,
        test_registered_vertical_media_is_trusted_and_unknown_mirrors_do_not_count,
        test_page_verified_registered_vertical_source_can_be_likely,
        test_generic_ai_glasses_terms_do_not_merge_different_company_events,
        test_multi_source_rumor_and_forecast_roundup_never_become_formal_news,
        test_event_uses_published_date_for_future_scheduled_launch_and_chinese_title,
        test_topic_output_keeps_three_confirmed_without_watchlist,
        test_topic_output_uses_likely_to_reach_main_news_count,
        test_topic_output_adds_watchlist_when_main_news_still_low,
        test_auto_expansion_adds_events_before_watchlist,
        test_36kr_single_source_is_hard_blocked,
        test_expanded_old_news_is_not_used_to_fill_count,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()

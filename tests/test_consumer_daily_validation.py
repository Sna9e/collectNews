import datetime
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.consumer_daily_validation import (  # noqa: E402
    build_verified_news_package,
    build_verified_topic_events,
    candidate_from_raw,
    is_independent_source,
    raw_result_from_search_result,
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


def run_all():
    tests = [
        test_36kr_single_source_is_not_formal,
        test_36kr_reprints_count_as_not_independent,
        test_official_vertical_and_mainstream_confirm_event,
        test_today_page_with_old_event_is_stale,
        test_ar_topic_rejects_foldable_iphone_noise,
        test_same_event_clusters_once_and_enters_deepseek_package,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()

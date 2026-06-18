import datetime as dt
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pwg_intelligence.classifier import classify_pwg_result  # noqa: E402
from pwg_intelligence.collector import PWGRawSearchResult, classify_and_score_pwg_records  # noqa: E402
from pwg_intelligence.excel_store import DAILY_INTELLIGENCE_COLUMNS, write_pwg_intelligence_rows  # noqa: E402
from pwg_intelligence.pwg_scoring import assess_pwg_maturity, score_pwg_opportunity  # noqa: E402
from pwg_intelligence.pwg_source_policy import assess_pwg_source  # noqa: E402


FETCHED_AT = dt.datetime(2026, 6, 9, 12, 0, 0, tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _record(title, url, snippet, query="polymer optical waveguide", source_name="source"):
    return PWGRawSearchResult(
        query=query,
        title=title,
        url=url,
        source_name=source_name,
        published_date="2026-06-08T08:00:00Z",
        snippet=snippet,
        fetched_at=FETCHED_AT,
        search_provider="exa",
    )


def test_classifier_covers_required_categories():
    samples = {
        "automotive": _record("Automotive optical ethernet ECU optical connector", "https://molex.com/a", "camera optical link for vehicle zonal controller"),
        "connector": _record("PMT connector with MPO and MT ferrule", "https://hakusan-mfg.co.jp/pmt", "fiber array board edge connector"),
        "cpo_datacenter": _record("CPO optical engine external laser source update", "https://broadcom.com/cpo", "PIC coupling optical RDL datacenter"),
        "material_process": _record("Siloxane waveguide photolithography reliability paper", "https://example.com/m", "bending loss roughness loss direct writing"),
        "standard": _record("IEEE 802.3cz standard working group update", "https://standards.ieee.org/x", "OPEN Alliance TC7 specification"),
        "patent": _record("Patent application for polymer optical waveguide", "https://patents.google.com/patent/US1", "claims describe optical wiring board"),
        "paper": _record("IEEE Xplore paper on polymer optical waveguide", "https://ieeexplore.ieee.org/document/1", "journal paper doi reliability"),
        "exhibition": _record("OFC exhibition booth showcases optical interconnect", "https://ofcconference.org/exhibit", "trade show presentation"),
        "company_update": _record("Company launches polymer optical waveguide product", "https://molex.com/product", "commercial product release"),
    }
    for expected, record in samples.items():
        assert classify_pwg_result(record).category == expected


def test_source_policy_assigns_a_to_d_levels():
    patent = _record("Polymer waveguide patent", "https://patents.google.com/patent/US1", "patent claims polymer optical waveguide")
    assert assess_pwg_source(patent, "patent").source_level == "A"

    interview = _record("Company interview about PMT connector", "https://ofcconference.org/session", "official presentation slides and interview")
    assert assess_pwg_source(interview, "exhibition").source_level == "B"

    media = _record("Optical interconnect market report", "https://lightwaveonline.com/news/1", "professional media report on CPO optical engine")
    assert assess_pwg_source(media, "cpo_datacenter").source_level == "C"

    low = _record("Copied polymer waveguide post", "https://example.blogspot.com/post", "转载 聚合 sponsored optical text")
    assessment = assess_pwg_source(low, "company_update")
    assert assessment.source_level == "D"
    assert assessment.needs_manual_review is True


def test_maturity_caps_paper_patent_and_concept_sources():
    paper = _record("Paper says commercial shipping polymer optical waveguide", "https://ieeexplore.ieee.org/document/1", "journal paper claims shipping volume production")
    paper_class = classify_pwg_result(paper)
    paper_source = assess_pwg_source(paper, paper_class.category)
    assert assess_pwg_maturity(paper, paper_class.category, paper_source).maturity_level == "M1"

    patent = _record("Patent says mass production optical wiring board", "https://patents.google.com/patent/US1", "patent claims mass production")
    patent_class = classify_pwg_result(patent)
    patent_source = assess_pwg_source(patent, patent_class.category)
    assert assess_pwg_maturity(patent, patent_class.category, patent_source).maturity_level == "M2"

    concept = _record("Concept image of CPO polymer waveguide", "https://broadcom.com/concept", "conceptual roadmap and concept image for future product")
    concept_class = classify_pwg_result(concept)
    concept_source = assess_pwg_source(concept, concept_class.category)
    assert assess_pwg_maturity(concept, concept_class.category, concept_source).maturity_level == "M0"


def test_opportunity_score_has_reason_and_components():
    record = _record(
        "Automotive camera optical link sample uses flexible optical circuit",
        "https://molex.com/product/camera-link",
        "datasheet sample product for automotive optical ethernet camera link, FPC flexible board edge connector reliability loss",
    )
    classification = classify_pwg_result(record)
    source = assess_pwg_source(record, classification.category)
    maturity = assess_pwg_maturity(record, classification.category, source)
    score = score_pwg_opportunity(record, classification, source, maturity)
    assert 0 <= score.opportunity_score <= 100
    assert set(score.components) == {
        "customer_pain",
        "fpc_capability_match",
        "public_product_evidence",
        "technical_feasibility",
        "competitive_entry",
    }
    assert "客户痛点" in score.scoring_reason


def test_classify_and_score_drops_d_by_default_and_keeps_low_trust_fallback():
    good = _record("Molex launches PMT connector sample", "https://molex.com/product/pmt", "datasheet sample PMT connector fiber array")
    low = _record("Copied PMT connector post", "https://copy.wordpress.com/post", "转载 polymer optical waveguide connector")
    rows, coverage, manual_review = classify_and_score_pwg_records([good, low], fetched_at=FETCHED_AT)
    assert len(rows) == 1
    assert rows[0]["source_level"] == "A"
    assert coverage["dropped_low_trust_count"] == 1
    assert "scoring_reason" in rows[0]
    assert "needs_manual_review" in rows[0]

    fallback_rows, fallback_coverage, fallback_review = classify_and_score_pwg_records([low], fetched_at=FETCHED_AT)
    assert len(fallback_rows) == 1
    assert fallback_rows[0]["source_level"] == "D"
    assert fallback_rows[0]["needs_manual_review"] == "true"
    assert fallback_coverage["low_trust_fallback_used"] is True
    assert fallback_review


def test_classified_rows_are_written_to_pwg_workbook():
    record = _record("Molex PMT connector sample", "https://molex.com/product/pmt", "datasheet sample PMT connector fiber array")
    rows, _, _ = classify_and_score_pwg_records([record], fetched_at=FETCHED_AT)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "pwg_intelligence.xlsx"
        write_pwg_intelligence_rows(rows, output_path=output)
        assert output.exists()
        with zipfile.ZipFile(output) as archive:
            shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        for column in (
            "pwg_category",
            "opportunity_score",
            "scoring_reason",
            "needs_manual_review",
            "classification_reason",
            "source_level_reason",
            "maturity_reason",
        ):
            assert column in DAILY_INTELLIGENCE_COLUMNS
            assert column in shared_strings
        assert "Molex PMT connector sample" in shared_strings


def run_all():
    tests = [
        test_classifier_covers_required_categories,
        test_source_policy_assigns_a_to_d_levels,
        test_maturity_caps_paper_patent_and_concept_sources,
        test_opportunity_score_has_reason_and_components,
        test_classify_and_score_drops_d_by_default_and_keeps_low_trust_fallback,
        test_classified_rows_are_written_to_pwg_workbook,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()

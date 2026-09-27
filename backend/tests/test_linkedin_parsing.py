"""LinkedIn alert parsing against several template variants."""

from __future__ import annotations

import pytest

from app.integrations.parsing.dedupe import (
    fingerprint_hash,
    linkedin_job_id,
    normalize_url,
    safe_public_url,
    title_from_slug,
)
from app.integrations.parsing.filters import message_matches, sanitize_filters
from app.integrations.parsing.linkedin import LinkedInAlertParser
from app.integrations.parsing.mime import html_to_text, parse_message_bytes
from tests.fixtures import emails

parser = LinkedInAlertParser()


def parse(html: str | None = None, text: str | None = None):
    return parser.parse(
        emails.raw_message(external_id="m", subject="LinkedIn iş ilanı", html=html, text=text)
    )


class TestParsing:
    def test_table_template_extracts_both_jobs(self):
        jobs = parse(html=emails.HTML_TABLE_V1)
        assert [job.title for job in jobs] == ["Senior AI Engineer", "LLM Engineer"]
        assert [job.company for job in jobs] == ["NovaTech AI", "VeriSfer"]
        assert jobs[0].location == "İstanbul, Türkiye (Hibrit)"
        assert jobs[0].external_id == "4012345678"
        assert jobs[0].description_status == "ok"
        assert len(jobs[0].description or "") > 120

    def test_div_template(self):
        jobs = parse(html=emails.HTML_DIV_V2)
        assert len(jobs) == 1
        assert jobs[0].title == "Machine Learning Engineer"
        assert jobs[0].company == "DeltaMind Analytics"
        assert jobs[0].location == "Ankara, Türkiye"
        # Only a one line snippet: flagged instead of inventing a description.
        assert jobs[0].description_status == "insufficient_description"

    def test_combined_company_and_location_line(self):
        jobs = parse(html=emails.HTML_COMBINED_V3)
        assert len(jobs) == 1
        assert jobs[0].title == "AI Backend Engineer"
        assert jobs[0].company == "Kobalt Yazılım"
        assert jobs[0].location == "İzmir, Türkiye (Hibrit)"

    def test_plain_text_only_alert(self):
        jobs = parse(text=emails.PLAIN_TEXT)
        assert [job.title for job in jobs] == ["Data Analyst", "Veri Analisti"]
        assert [job.company for job in jobs] == ["Anadolu Perakende", "Başka Şirket"]
        assert jobs[0].location == "Ankara, Türkiye"

    def test_digest_with_multiple_jobs(self):
        jobs = parse(html=emails.HTML_MULTI_JOB)
        assert len(jobs) == 3
        assert {job.external_id for job in jobs} == {
            "5011122233",
            "5011122244",
            "5011122255",
        }

    def test_broken_html_is_parsed_leniently(self):
        jobs = parse(html=emails.HTML_BROKEN)
        assert len(jobs) == 1
        assert jobs[0].title == "Bozuk & HTML Rolü"
        assert jobs[0].company == "Bozuk Şirket"

    def test_alert_without_jobs_is_zero_not_error(self):
        assert parse(html=emails.HTML_NO_JOBS) == []

    def test_duplicate_links_in_one_email_collapse(self):
        html = emails.HTML_TABLE_V1 + emails.HTML_TABLE_V1
        jobs = parse(html=html)
        assert len(jobs) == 2

    def test_parser_does_not_invent_company(self):
        html = """
        <div><a href="https://www.linkedin.com/jobs/view/6011122233">Gizemli Rol</a>
        <span>İstanbul, Türkiye</span></div>
        """
        jobs = parse(html=html)
        assert jobs[0].company == "Bilinmiyor"


class TestMime:
    def test_quoted_printable_turkish_charset(self):
        message = parse_message_bytes(
            emails.build_mime_message(html=emails.HTML_TABLE_V1),
            external_id="mime-1",
        )
        assert "Sonraki" in message.body_text or "iş" in message.body_text
        assert message.sender == "jobalerts-noreply@linkedin.com"
        assert message.subject
        assert parser.parse(message)[0].title == "Senior AI Engineer"

    def test_base64_encoding(self):
        message = parse_message_bytes(
            emails.build_mime_message(
                html=emails.HTML_DIV_V2, transfer_encoding="base64"
            ),
            external_id="mime-2",
        )
        assert parser.parse(message)[0].title == "Machine Learning Engineer"

    def test_iso_8859_9_charset(self):
        message = parse_message_bytes(
            emails.build_mime_message(
                text=emails.PLAIN_TEXT, charset="iso-8859-9", transfer_encoding="7bit"
            ),
            external_id="mime-3",
        )
        assert "Başka Şirket" in message.body_text

    def test_multipart_alternative_prefers_plain_but_keeps_html(self):
        raw = (
            b"From: a@linkedin.com\r\nSubject: test\r\n"
            b"Content-Type: multipart/alternative; boundary=BB\r\n\r\n"
            b"--BB\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
            b"Plain body with a job link https://www.linkedin.com/jobs/view/7011122233\r\n"
            b"--BB\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            b"<p>HTML body</p>\r\n--BB--\r\n"
        )
        message = parse_message_bytes(raw, external_id="mime-4")
        assert "Plain body" in message.body_text
        assert "HTML body" in (message.body_html or "")

    def test_html_to_text_unescapes_entities(self):
        assert "A & B" in html_to_text("<p>A &amp; B</p><p>C</p>")


class TestDedupe:
    @pytest.mark.parametrize(
        "url,expected",
        [
            (
                "https://www.linkedin.com/comm/jobs/view/role-4012345678?trk=email&trackingId=x",
                "https://linkedin.com/comm/jobs/view/role-4012345678",
            ),
            (
                "https://www.linkedin.com/jobs/view/4012345678/?refId=abc#frag",
                "https://linkedin.com/jobs/view/4012345678",
            ),
        ],
    )
    def test_normalize_strips_tracking(self, url, expected):
        assert normalize_url(url) == expected

    def test_normalize_rejects_non_http(self):
        assert normalize_url("javascript:alert(1)") is None
        assert normalize_url("not a url") is None

    def test_safe_public_url_requires_https(self):
        assert safe_public_url("https://linkedin.com/jobs/view/1")
        assert safe_public_url("http://linkedin.com/jobs/view/1") is None
        assert safe_public_url(None) is None

    def test_job_id_extraction(self):
        assert linkedin_job_id("https://linkedin.com/jobs/view/senior-ai-4012345678") == "4012345678"
        assert linkedin_job_id(None, "veri-analisti-at-x-4299887766") == "4299887766"
        assert linkedin_job_id("https://linkedin.com/jobs/search?currentJobId=5556667777") == "5556667777"
        assert linkedin_job_id("https://linkedin.com/jobs/view/short") is None

    def test_title_from_slug(self):
        assert title_from_slug("senior-ai-engineer-at-novatech-4012345678") == (
            "Senior Ai Engineer @ Novatech"
        )
        assert title_from_slug("4012345678") is None

    def test_fingerprint_is_stable_and_discriminative(self):
        first = fingerprint_hash(title="AI Engineer", company="Nova", location="İstanbul")
        second = fingerprint_hash(title="ai  engineer", company="nova", location="istanbul")
        other = fingerprint_hash(title="AI Engineer", company="Nova", location="Ankara")
        assert first == second
        assert first != other

    def test_fingerprint_prefers_job_id(self):
        with_id = fingerprint_hash(title="A", company="B", location=None, job_id="12345678")
        without = fingerprint_hash(title="A", company="B", location=None)
        assert with_id != without


class TestFilters:
    def test_defaults_accept_linkedin_alert(self):
        matches, reason = message_matches(
            sender="jobalerts-noreply@linkedin.com",
            subject="NovaTech AI için yeni iş ilanı",
            filters={},
        )
        assert matches is True and reason is None

    def test_sender_filter_rejects_other_senders(self):
        matches, reason = message_matches(
            sender="newsletter@medium.com", subject="iş ilanı", filters={}
        )
        assert matches is False
        assert reason == "sender_filtered"

    def test_subject_filter(self):
        matches, reason = message_matches(
            sender="jobalerts-noreply@linkedin.com",
            subject="Haftalık bülteniniz",
            filters={},
        )
        assert matches is False
        assert reason == "subject_filtered"

    def test_custom_filters_replace_defaults(self):
        filters = {"senders": ["kariyer@firma.com"], "subjects": ["pozisyon"]}
        assert message_matches(
            sender="kariyer@firma.com", subject="Yeni pozisyon", filters=filters
        )[0]
        assert not message_matches(
            sender="jobalerts-noreply@linkedin.com", subject="iş ilanı", filters=filters
        )[0]

    def test_empty_filter_list_means_no_constraint_on_that_axis(self):
        filters = {"senders": [], "subjects": ["iş ilanı"]}
        sanitized = sanitize_filters(filters)
        assert sanitized["senders"] == []
        assert message_matches(
            sender="herhangi@bir-adres.com", subject="iş ilanı", filters=filters
        )[0]

    def test_sanitize_limits_and_trims(self):
        sanitized = sanitize_filters(
            {"senders": ["  a  ", "a", "b", "", 5], "subjects": "x,y"}
        )
        assert sanitized["senders"] == ["a", "b", "5"]
        assert sanitized["subjects"] == ["x", "y"]

"""Sample job-alert e-mails (no real addresses or postings).

Three different HTML shapes plus a text-only variant and a few edge cases, so
the parser is exercised against template drift instead of one lucky template.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.base import RawMessage
from app.integrations.parsing.mime import parse_message_bytes

RECEIVED_AT = datetime(2026, 9, 20, 8, 15, tzinfo=timezone.utc)

# --- Variant 1: classic table layout, Turkish ---------------------------------
HTML_TABLE_V1 = """<!doctype html>
<html><body>
<table width="600"><tr><td>
  <h1>LinkedIn</h1>
  <p>NovaTech AI sizin için yeni bir iş ilanı yayınladı</p>
</td></tr>
<tr><td>
  <table><tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/senior-ai-engineer-at-novatech-ai-4012345678?trk=email&amp;trackingId=abc123">
      <strong>Senior AI Engineer</strong>
    </a>
    <p>NovaTech AI</p>
    <p>İstanbul, Türkiye (Hibrit)</p>
    <p>Python, PyTorch ve LLM tabanlı ürünler geliştirecek deneyimli bir mühendis arıyoruz.
       Bu rolde RAG mimarileri kuracak, model değerlendirme hatlarını sahibi olacak ve
       üretim ortamında servis yayınlayacaksınız.</p>
    <a href="https://www.linkedin.com/comm/jobs/view/senior-ai-engineer-at-novatech-ai-4012345678?trk=email">View job</a>
  </td></tr></table>
</td></tr>
<tr><td>
  <table><tr><td>
    <a href="https://www.linkedin.com/jobs/view/llm-engineer-at-verisfer-4098765432?trackingId=zzz">
      <strong>LLM Engineer</strong>
    </a>
    <p>VeriSfer</p>
    <p>Uzaktan</p>
    <p>Uzaktan çalışan bir LLM Engineer arıyoruz. Açık kaynak modellerin ince ayarı,
       değerlendirme altyapısı ve prompt kütüphanesi sorumluluklarınız arasında olacak.</p>
  </td></tr></table>
</td></tr>
<tr><td>
  <p><a href="https://www.linkedin.com/help/linkedin/answer/3">Yardım</a></p>
  <p>Bu e-posta LinkedIn tarafından gönderildi. Abonelikten çık</p>
</td></tr>
</table>
</body></html>
"""

# --- Variant 2: div based, English subject, single job, no company line --------
HTML_DIV_V2 = """<div>
  <p>New job alert</p>
  <div class="job">
    <a href="https://www.linkedin.com/comm/jobs/view/machine-learning-engineer-at-deltamind-analytics-4123456789?refId=eml">
      Machine Learning Engineer
    </a>
    <span>DeltaMind Analytics</span>
    <span>Ankara, Türkiye</span>
    <span>Özellik mühendisliği ve model eğitimi süreçlerinde görev alacaksınız.</span>
  </div>
  <div><a href="https://www.linkedin.com/comm/jobs/view/machine-learning-engineer-at-deltamind-analytics-4123456789">Apply</a></div>
</div>
"""

# --- Variant 3: company and location in one line, seed title in the anchor -----
HTML_COMBINED_V3 = """<html><body>
  <p>Sizin için 1 yeni iş ilanı</p>
  <table><tr>
    <td><a href="https://www.linkedin.com/comm/jobs/view/4188776655?trk=eml">AI Backend Engineer</a></td>
    <td>Kobalt Yazılım · İzmir, Türkiye (Hibrit)</td>
  </tr></table>
  <p>Tüm ilanları gör</p>
</body></html>
"""

# --- Plain text only ----------------------------------------------------------
PLAIN_TEXT = """LinkedIn
Sizin için yeni iş ilanları

Data Analyst
Anadolu Perakende
Ankara, Türkiye

https://www.linkedin.com/jobs/view/data-analyst-at-anadolu-perakende-4200112233?trk=eml

Veri Analisti
Başka Şirket
Uzaktan

https://www.linkedin.com/comm/jobs/view/veri-analisti-at-baska-sirket-4299887766
"""

# --- One e-mail carrying several jobs (digest) --------------------------------
HTML_MULTI_JOB = """<html><body>
<p>Günlük özet</p>
<table>
  <tr><td>
    <a href="https://www.linkedin.com/jobs/view/5011122233">AI Engineer</a>
    <p>Şirket A</p><p>İstanbul, Türkiye</p>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/jobs/view/5011122244">LLM Engineer</a>
    <p>Şirket B</p><p>Uzaktan</p>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/jobs/view/5011122255">Data Engineer</a>
    <p>Şirket C</p><p>İzmir, Türkiye</p>
  </td></tr>
</table>
</body></html>
"""

# --- Broken HTML (unclosed tags, entities, quoted-printable leftovers) ---------
HTML_BROKEN = """<div>
 <a href="https://www.linkedin.com/jobs/view/broken-role-at-bozuk-sirket-5099988877?trk=eml">
   Bozuk &amp; HTML Rolü
 <p>Bozuk Şirket
 <p>İstanbul, Türkiye
</div"""

# --- No job at all (valid 0-result e-mail) ------------------------------------
HTML_NO_JOBS = """<html><body>
<p>Bu hafta profilinizle eşleşen yeni bir ilan yok.</p>
<p>Tercihlerinizi güncelleyebilirsiniz.</p>
</body></html>
"""


def raw_message(
    *,
    external_id: str,
    subject: str,
    html: str | None = None,
    text: str | None = None,
    sender: str = "jobalerts-noreply@linkedin.com",
    received_at: datetime = RECEIVED_AT,
) -> RawMessage:
    return RawMessage(
        external_id=external_id,
        subject=subject,
        sender=sender,
        received_at=received_at,
        body_text=text or "",
        body_html=html,
    )


def build_mime_message(
    *,
    subject: str = "NovaTech AI için yeni iş ilanı",
    sender: str = "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
    html: str = HTML_TABLE_V1,
    text: str | None = None,
    charset: str = "utf-8",
    transfer_encoding: str = "quoted-printable",
) -> bytes:
    """Real MIME bytes so charset/encoding handling is covered too."""
    import quopri

    if transfer_encoding == "quoted-printable":
        payload = quopri.encodestring((text or html).encode(charset))
    elif transfer_encoding == "base64":
        import base64

        payload = base64.encodebytes((text or html).encode(charset))
    else:
        payload = (text or html).encode(charset)

    content_type = "text/plain" if text is not None else "text/html"
    header = (
        f"From: {sender}\r\n"
        f"To: someone@example.com\r\n"
        f"Subject: {subject}\r\n"
        f"Date: Mon, 20 Sep 2026 08:15:00 +0000\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: {content_type}; charset={charset}\r\n"
        f"Content-Transfer-Encoding: {transfer_encoding}\r\n"
        f"\r\n"
    )
    return header.encode("utf-8") + payload + b"\r\n"


def mime_raw_message(external_id: str = "mime-1", **kwargs) -> RawMessage:
    return parse_message_bytes(build_mime_message(**kwargs), external_id=external_id)

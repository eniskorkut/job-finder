"""Mock data fixtures.

Everything created here is marked as mock (``Job.is_mock`` / ``JobMatch.is_mock``
/ ``SyncHistory.is_mock``) so the UI can label it and so phase 2/3 code can
ignore it when real data starts flowing in. No external service is contacted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cv import CV
from app.models.enums import (
    ConnectionStatus,
    JobSource,
    MatchStatus,
    NotificationChannel,
    NotificationStatus,
    SyncStatus,
    UserRole,
    WorkMode,
)
from app.models.job import Job, JobMatch
from app.models.mail_account import MailAccount
from app.models.notification import NotificationHistory
from app.models.sync import SyncHistory
from app.models.telegram import TelegramIntegration
from app.models.user import User
from app.repositories.cvs import CVRepository
from app.repositories.jobs import JobRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.users import UserRepository
from app.services.user_service import UserService

DEFAULT_DEMO_PASSWORD = "DemoParola!2026"

USER1 = {
    "username": "ai_hunter",
    "email": "ai.hunter@example.com",
    "full_name": "AI Hunter (örnek hesap)",
    "role": UserRole.OWNER.value,
    "titles": ["AI Engineer", "LLM Engineer"],
    "locations": ["İstanbul", "Remote"],
    "work_modes": [WorkMode.HYBRID.value, WorkMode.REMOTE.value],
    "keywords_include": ["Python", "LLM", "RAG", "PyTorch"],
    "keywords_exclude": ["satış", "saha"],
    "min_match_score": 75,
}

USER2 = {
    "username": "data_hunter",
    "email": "data.hunter@example.com",
    "full_name": "Data Hunter (örnek hesap)",
    "role": UserRole.MEMBER.value,
    "titles": ["Data Analyst", "Backend Developer"],
    "locations": ["Ankara", "Remote"],
    "work_modes": [WorkMode.REMOTE.value, WorkMode.ONSITE.value],
    "keywords_include": ["SQL", "Python", "FastAPI", "BI"],
    "keywords_exclude": ["staj"],
    "min_match_score": 65,
}

USER1_JOBS = [
    {
        "title": "Senior AI Engineer",
        "company": "NovaTech AI",
        "location": "İstanbul, Türkiye",
        "work_mode": WorkMode.HYBRID.value,
        "seniority": "Senior",
        "salary_text": "180.000 - 240.000 TL / ay",
        "score": 92,
        "status": MatchStatus.NEW.value,
        "rationale": "İlan metni LLM ürün geliştirme, RAG mimarisi ve Python ekosistemi üzerine kurulu; CV'deki 6 yıllık AI deneyimi ve vektör veritabanı çalışmaları birebir örtüşüyor.",
        "matched": ["Python", "LLM", "RAG", "Vector DB", "FastAPI"],
        "missing": ["Kubernetes"],
        "days_ago": 1,
        "description": (
            "Ürün ekibimizde müşteriye dokunan LLM özellikleri geliştirecek bir Senior AI Engineer arıyoruz.\n\n"
            "Sorumluluklar:\n"
            "- Retrieval-augmented generation (RAG) hatlarını tasarlamak ve iyileştirmek\n"
            "- Model değerlendirme ve regresyon testleri kurmak\n"
            "- FastAPI ile model servislerini yayınlamak\n\n"
            "Aranan nitelikler: Python, PyTorch, vektör veritabanları, üretim ortamı deneyimi."
        ),
    },
    {
        "title": "LLM Engineer",
        "company": "VeriSfer",
        "location": "Remote (Türkiye)",
        "work_mode": WorkMode.REMOTE.value,
        "seniority": "Mid-Senior",
        "salary_text": "€4.000 - €5.500 / ay",
        "score": 88,
        "status": MatchStatus.SAVED.value,
        "rationale": "Pozisyon doğrudan LLM uygulama geliştirme odaklı. CV'deki prompt mühendisliği ve fine-tuning deneyimi güçlü bir eşleşme sağlıyor; eksik kalan kısım yalnızca MLOps araçları.",
        "matched": ["LLM", "Prompt Engineering", "Fine-tuning", "Python"],
        "missing": ["MLflow", "Terraform"],
        "days_ago": 2,
        "description": (
            "Remote çalışan bir LLM Engineer arıyoruz. Görev, açık kaynak modellerin ince ayarı ve "
            "değerlendirme altyapısının kurulmasıdır.\n\nBeklentiler: Python, Hugging Face ekosistemi, "
            "deney tasarımı, ölçümleme (eval) kültürü."
        ),
    },
    {
        "title": "Machine Learning Engineer",
        "company": "DeltaMind Analytics",
        "location": "Ankara, Türkiye",
        "work_mode": WorkMode.ONSITE.value,
        "seniority": "Mid",
        "salary_text": "140.000 - 170.000 TL / ay",
        "score": 84,
        "status": MatchStatus.NEW.value,
        "rationale": "Klasik ML hattı deneyimi ve özellik mühendisliği CV ile örtüşüyor. Ofis ağırlıklı çalışma tercih edilen çalışma modelleriyle kısmen uyuşuyor.",
        "matched": ["Python", "scikit-learn", "Feature Engineering"],
        "missing": ["Spark"],
        "days_ago": 4,
        "description": (
            "Müşteri davranış modelleri geliştiren ekibe ML Engineer arıyoruz. Veri hazırlama, model "
            "eğitimi ve üretim dağıtımı süreçlerinde görev alacaksınız."
        ),
    },
    {
        "title": "AI Backend Engineer",
        "company": "Kobalt Yazılım",
        "location": "İzmir, Türkiye",
        "work_mode": WorkMode.HYBRID.value,
        "seniority": "Mid-Senior",
        "salary_text": "150.000 - 185.000 TL / ay",
        "score": 78,
        "status": MatchStatus.NEW.value,
        "rationale": "Python backend ve API geliştirme deneyimi güçlü; ilanın AI kısmı ikincil olduğu için eşleşme yüksek ama en yüksek değil.",
        "matched": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "missing": ["Ray"],
        "days_ago": 6,
        "description": (
            "AI destekli ürünlerimizin backend servislerini geliştirecek bir mühendis arıyoruz. "
            "FastAPI, PostgreSQL ve kuyruk sistemleri günlük araçlarınız olacak."
        ),
    },
    {
        "title": "Computer Vision Engineer",
        "company": "GörüTek",
        "location": "İstanbul, Türkiye",
        "work_mode": WorkMode.ONSITE.value,
        "seniority": "Mid",
        "salary_text": "130.000 - 160.000 TL / ay",
        "score": 58,
        "status": MatchStatus.DISMISSED.value,
        "rationale": "CV'de görüntü işleme deneyimi sınırlı olduğu ve pozisyon ofis ağırlıklı olduğu için eşleşme düşük.",
        "matched": ["Python", "PyTorch"],
        "missing": ["OpenCV", "CUDA", "Kalibrasyon"],
        "days_ago": 9,
        "description": (
            "Üretim hattı için görüntü işleme modülleri geliştirecek Computer Vision Engineer arıyoruz."
        ),
    },
    {
        "title": "Data Engineer",
        "company": "Bulut Veri",
        "location": "Remote (Türkiye)",
        "work_mode": WorkMode.REMOTE.value,
        "seniority": "Mid",
        "salary_text": "160.000 - 200.000 TL / ay",
        "score": 66,
        "status": MatchStatus.NEW.value,
        "rationale": "Veri boru hattı bilgisi var ancak ilan ağırlıklı olarak dbt/Airflow istiyor; CV'de bu araçlar ikincil seviyede.",
        "matched": ["Python", "SQL", "Airflow"],
        "missing": ["dbt", "Snowflake"],
        "days_ago": 11,
        "description": (
            "Veri platformu ekibimize Data Engineer arıyoruz. ETL süreçleri, veri kalitesi kontrolleri "
            "ve analitik katmanın kurulması temel sorumluluklar olacak."
        ),
    },
    {
        "title": "Junior AI Engineer",
        "company": "StartupHub",
        "location": "Remote (Türkiye)",
        "work_mode": WorkMode.REMOTE.value,
        "seniority": "Junior",
        "salary_text": "70.000 - 95.000 TL / ay",
        "score": 61,
        "status": MatchStatus.NEW.value,
        "rationale": "Teknik içerik uyumlu fakat pozisyon kıdem olarak deneyimin altında kaldığı için skor sınırlı.",
        "matched": ["Python", "LLM", "Docker"],
        "missing": ["Üretim deneyimi"],
        "days_ago": 13,
        "description": (
            "Yeni mezun veya 1-2 yıl deneyimli AI Engineer arıyoruz. Model denemeleri ve prototip "
            "geliştirme süreçlerinde destek olacaksınız."
        ),
    },
]

USER2_JOBS = [
    {
        "title": "Data Analyst",
        "company": "Anadolu Perakende",
        "location": "Ankara, Türkiye",
        "work_mode": WorkMode.ONSITE.value,
        "seniority": "Mid",
        "salary_text": "110.000 - 140.000 TL / ay",
        "score": 90,
        "status": MatchStatus.NEW.value,
        "rationale": "SQL ve dashboard deneyimi ilanın tamamıyla örtüşüyor; perakende alan bilgisi ek puan sağladı.",
        "matched": ["SQL", "Power BI", "Excel", "Veri Görselleştirme"],
        "missing": ["Python"],
        "days_ago": 1,
        "description": (
            "Perakende operasyonları için raporlama ve analiz yapacak Data Analyst arıyoruz. "
            "SQL sorguları, Power BI panoları ve haftalık yönetim raporları temel işleriniz olacak."
        ),
    },
    {
        "title": "Backend Developer (Python)",
        "company": "E-Kurumsal Yazılım",
        "location": "Remote (Türkiye)",
        "work_mode": WorkMode.REMOTE.value,
        "seniority": "Mid",
        "salary_text": "150.000 - 190.000 TL / ay",
        "score": 86,
        "status": MatchStatus.SAVED.value,
        "rationale": "FastAPI ve PostgreSQL deneyimi birebir; ilanın test/kalite beklentileri CV'de karşılanıyor.",
        "matched": ["Python", "FastAPI", "PostgreSQL", "pytest"],
        "missing": ["Celery"],
        "days_ago": 3,
        "description": (
            "Kurumsal müşteriler için Python tabanlı servisler geliştirecek Backend Developer arıyoruz. "
            "FastAPI, PostgreSQL, pytest ve CI süreçleri günlük akışınız olacak."
        ),
    },
    {
        "title": "Business Intelligence Analyst",
        "company": "VeriDanışman",
        "location": "İstanbul, Türkiye",
        "work_mode": WorkMode.HYBRID.value,
        "seniority": "Mid",
        "salary_text": "120.000 - 155.000 TL / ay",
        "score": 74,
        "status": MatchStatus.NEW.value,
        "rationale": "Raporlama ve veri modelleme deneyimi uyumlu; ilan İngilizce sunum becerisini öne çıkarıyor.",
        "matched": ["SQL", "BI Araçları", "Veri Modelleme"],
        "missing": ["İngilizce sunum", "Tableau"],
        "days_ago": 5,
        "description": (
            "Müşterilere yönelik BI çözümleri geliştiren ekibe analyst arıyoruz. Veri modeli tasarımı ve "
            "yönetim panoları sorumluluğunuz olacak."
        ),
    },
    {
        "title": "DevOps Engineer",
        "company": "BulutAltyapı",
        "location": "Remote (Türkiye)",
        "work_mode": WorkMode.REMOTE.value,
        "seniority": "Senior",
        "salary_text": "190.000 - 230.000 TL / ay",
        "score": 54,
        "status": MatchStatus.DISMISSED.value,
        "rationale": "Kubernetes ve Terraform derinliği aranan pozisyon için deneyim yetersiz kaldı.",
        "matched": ["Docker", "Linux", "CI/CD"],
        "missing": ["Kubernetes", "Terraform", "AWS"],
        "days_ago": 8,
        "description": (
            "Kubernetes tabanlı platformumuz için DevOps Engineer arıyoruz. Gözlemlenebilirlik ve "
            "otomasyon ana odak alanlarıdır."
        ),
    },
    {
        "title": "Frontend Developer",
        "company": "Dijital Atölye",
        "location": "Ankara, Türkiye",
        "work_mode": WorkMode.HYBRID.value,
        "seniority": "Mid",
        "salary_text": "115.000 - 150.000 TL / ay",
        "score": 48,
        "status": MatchStatus.NEW.value,
        "rationale": "React deneyimi sınırlı olduğu için eşleşme düşük; pozisyon backend tercihleriyle örtüşmüyor.",
        "matched": ["JavaScript", "HTML/CSS"],
        "missing": ["React", "Next.js", "TypeScript"],
        "days_ago": 10,
        "description": (
            "Ürün arayüzlerimizi geliştirecek Frontend Developer arıyoruz. React ve TypeScript "
            "günlük araçlarınız olacak."
        ),
    },
    {
        "title": "Veri Analisti (Staj)",
        "company": "Başlangıç Teknoloji",
        "location": "Remote (Türkiye)",
        "work_mode": WorkMode.REMOTE.value,
        "seniority": "Stajyer",
        "salary_text": "Asgari ücret",
        "score": 35,
        "status": MatchStatus.NEW.value,
        "rationale": "Stajyer pozisyonu olduğu için deneyim seviyesi uyuşmuyor.",
        "matched": ["SQL"],
        "missing": ["Deneyim seviyesi"],
        "days_ago": 14,
        "description": "Veri analizi ekibimize stajyer alıyoruz. Temel SQL bilgisi yeterli.",
    },
]

USER1_CV = """
Enis Korkut - AI Engineer / LLM Engineer (ÖRNEK CV)
E-posta: ai.hunter@example.com

DENEYİM
- Kıdemli AI Engineer, 2019-2026
  - RAG mimarisi ile üretim ortamında LLM servisleri geliştirme
  - FastAPI tabanlı model servisleri, değerlendirme (eval) hatları
  - Vektör veritabanları: pgvector, Qdrant
  - Fine-tuning ve prompt optimizasyonu

YETKİNLİKLER
Python, PyTorch, FastAPI, PostgreSQL, Docker, LLM, RAG, Prompt Engineering, Vector DB

EĞİTİM
Bilgisayar Mühendisliği, lisans
""".strip()

USER2_CV = """
Data Hunter - Data Analyst / Backend Developer (ÖRNEK CV)
E-posta: data.hunter@example.com

DENEYİM
- Data Analyst, 2020-2026
  - SQL ile analitik sorgular, Power BI panoları, haftalık yönetim raporları
  - Veri modelleme ve kalite kontrolleri
- Backend Developer (Python)
  - FastAPI ve PostgreSQL ile servis geliştirme, pytest ile otomatik testler

YETKİNLİKLER
SQL, Python, FastAPI, PostgreSQL, pytest, Power BI, Docker, Linux, CI/CD

EĞİTİM
İstatistik, lisans
""".strip()


def seed_demo_data(
    db: Session,
    *,
    user1_password: str = DEFAULT_DEMO_PASSWORD,
    user2_password: str = DEFAULT_DEMO_PASSWORD,
) -> dict:
    users = UserRepository(db)
    preferences = PreferenceRepository(db)
    job_repo = JobRepository(db)
    cvs = CVRepository(db)

    user_service = UserService(db)
    created: list[str] = []

    user1 = users.get_by_username(USER1["username"])
    if user1 is None:
        user1 = user_service.create_user(
            username=USER1["username"],
            email=USER1["email"],
            password=user1_password,
            full_name=USER1["full_name"],
            make_owner=True,
        )
        created.append(user1.username)

    user2 = users.get_by_username(USER2["username"])
    if user2 is None:
        user2 = user_service.create_user(
            username=USER2["username"],
            email=USER2["email"],
            password=user2_password,
            full_name=USER2["full_name"],
            role=UserRole.MEMBER.value,
        )
        created.append(user2.username)

    for spec, user in ((USER1, user1), (USER2, user2)):
        preference = preferences.get_for_user(user.id) or preferences.get_or_create(user)
        preference.desired_titles = spec["titles"]
        preference.locations = spec["locations"]
        preference.work_modes = spec["work_modes"]
        preference.keywords_include = spec["keywords_include"]
        preference.keywords_exclude = spec["keywords_exclude"]
        preference.min_match_score = spec["min_match_score"]
        preference.notify_telegram = True
        db.flush()

    _seed_accounts(db, user1, "gmail", "ai.hunter.gmail@example.com")
    _seed_accounts(db, user2, "outlook", "data.hunter.outlook@example.com")
    _seed_telegram(db, user1)
    _seed_telegram(db, user2)

    cv1 = _seed_cv(db, cvs, user1, "ornek-cv-ai-engineer.txt", USER1_CV)
    cv2 = _seed_cv(db, cvs, user2, "ornek-cv-data-analyst.txt", USER2_CV)

    _seed_jobs(db, job_repo, user1, USER1_JOBS, cv1)
    _seed_jobs(db, job_repo, user2, USER2_JOBS, cv2)

    _seed_sync_history(db, user1, "gmail", findings=7)
    _seed_sync_history(db, user1, "outlook", findings=3)
    _seed_sync_history(db, user2, "outlook", findings=6)
    _seed_notifications(db, user1)
    _seed_notifications(db, user2)

    db.commit()
    return {
        "created_users": created,
        "users": [
            {"username": user1.username, "password": user1_password, "jobs": len(USER1_JOBS)},
            {"username": user2.username, "password": user2_password, "jobs": len(USER2_JOBS)},
        ],
        "note": "Tüm kayıtlar mock olarak işaretlendi (is_mock=True).",
    }


def _seed_cv(db: Session, cvs: CVRepository, user: User, filename: str, text: str) -> CV | None:
    existing = cvs.get_active_for_user(user.id)
    if existing is not None:
        return existing
    user_dir = settings.cv_storage_path / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    target = user_dir / filename
    target.write_text(text, encoding="utf-8")
    cv = CV(
        user_id=user.id,
        filename=filename,
        content_type="text/plain",
        size_bytes=len(text.encode("utf-8")),
        storage_path=str(target.relative_to(settings.data_path)),
        extracted_text=text,
        summary="Örnek CV (mock veri) - 2. aşamada gerçek CV yüklemesi kullanılacak.",
        is_active=True,
    )
    db.add(cv)
    db.flush()
    return cv


def _seed_accounts(db: Session, user: User, provider: str, address: str) -> None:
    existing = [
        account
        for account in db.query(MailAccount).filter(MailAccount.user_id == user.id).all()
        if account.provider == provider
    ]
    if existing:
        return
    db.add(
        MailAccount(
            user_id=user.id,
            provider=provider,
            email_address=address,
            display_name="Örnek hesap (mock)",
            status=ConnectionStatus.DISCONNECTED.value,
            scopes=[],
        )
    )
    db.flush()


def _seed_telegram(db: Session, user: User) -> None:
    existing = (
        db.query(TelegramIntegration)
        .filter(TelegramIntegration.user_id == user.id)
        .one_or_none()
    )
    if existing is not None:
        return
    db.add(
        TelegramIntegration(
            user_id=user.id,
            status=ConnectionStatus.DISCONNECTED.value,
            username=None,
        )
    )
    db.flush()


def _seed_jobs(
    db: Session,
    job_repo: JobRepository,
    user: User,
    specs: list[dict],
    cv: CV | None,
) -> None:
    existing = db.query(Job).filter(Job.user_id == user.id, Job.is_mock.is_(True)).count()
    if existing:
        return

    now = datetime.now(timezone.utc)
    for index, spec in enumerate(specs):
        discovered = now - timedelta(days=spec["days_ago"], hours=index)
        job = Job(
            user_id=user.id,
            source=JobSource.MOCK.value,
            external_id=f"mock-{user.username}-{index + 1}",
            title=spec["title"],
            company=spec["company"],
            location=spec["location"],
            work_mode=spec["work_mode"],
            employment_type="Tam zamanlı",
            seniority=spec.get("seniority"),
            salary_text=spec.get("salary_text"),
            description=spec["description"],
            url=f"https://example.com/jobs/{user.username}/{index + 1}",
            posted_at=discovered - timedelta(days=2),
            discovered_at=discovered,
            is_mock=True,
            raw_payload={"mock": True, "fixture": f"{user.username}-{index + 1}"},
        )
        db.add(job)
        db.flush()
        db.add(
            JobMatch(
                user_id=user.id,
                job_id=job.id,
                cv_id=cv.id if cv else None,
                score=spec["score"],
                rationale=spec["rationale"],
                matched_skills=spec["matched"],
                missing_skills=spec["missing"],
                model="mock-fixture",
                status=spec["status"],
                is_mock=True,
            )
        )
        db.flush()


def _seed_sync_history(db: Session, user: User, source: str, *, findings: int) -> None:
    existing = (
        db.query(SyncHistory)
        .filter(SyncHistory.user_id == user.id, SyncHistory.is_mock.is_(True))
        .count()
    )
    if existing:
        return
    now = datetime.now(timezone.utc)
    account = (
        db.query(MailAccount)
        .filter(MailAccount.user_id == user.id, MailAccount.provider == source)
        .one_or_none()
    )
    for days in (1, 4, 7):
        started = now - timedelta(days=days)
        db.add(
            SyncHistory(
                user_id=user.id,
                mail_account_id=account.id if account else None,
                source=source,
                status=SyncStatus.SUCCESS.value,
                started_at=started,
                finished_at=started + timedelta(minutes=3),
                jobs_found=findings,
                jobs_new=max(0, findings - days),
                matches_created=max(0, findings - days),
                is_mock=True,
                error_message=None,
            )
        )
    db.flush()


def _seed_notifications(db: Session, user: User) -> None:
    existing = (
        db.query(NotificationHistory)
        .filter(NotificationHistory.user_id == user.id, NotificationHistory.is_mock.is_(True))
        .count()
    )
    if existing:
        return
    matches = (
        db.query(JobMatch)
        .filter(JobMatch.user_id == user.id, JobMatch.score >= 80)
        .order_by(JobMatch.score.desc())
        .limit(2)
        .all()
    )
    now = datetime.now(timezone.utc)
    for index, match in enumerate(matches):
        job = db.get(Job, match.job_id)
        db.add(
            NotificationHistory(
                user_id=user.id,
                job_id=match.job_id,
                job_match_id=match.id,
                channel=NotificationChannel.TELEGRAM.value,
                status=NotificationStatus.SKIPPED.value,
                message=(
                    f"Örnek kayıt: {job.title} - {job.company} ({match.score} puan). "
                    "Telegram gönderimi 3. aşamada açılacak."
                ),
                sent_at=None,
                is_mock=True,
                created_at=now - timedelta(days=index + 1),
            )
        )
    db.flush()

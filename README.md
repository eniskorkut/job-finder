# Job Hunter

İki kullanıcının kendi e-posta hesaplarına gelen LinkedIn iş ilanlarını toplayıp CV'leriyle
eşleştirdiği ve uygun ilanları Telegram üzerinden aldığı web uygulaması.

**Durum: Aşama 1/3 tamamlandı** — temel mimari, kullanıcı yönetimi, veritabanı ve frontend.

| Aşama | Kapsam | Durum |
| --- | --- | --- |
| 1 | Mimari, kullanıcı yönetimi, oturum/CSRF, tercihler, mock ilanlar, dashboard | ✅ tamamlandı |
| 2 | Gmail + Hotmail/Outlook + CV metin çıkarımı | ⏳ |
| 3 | DeepSeek V4.1 Flash skorlama, Telegram bildirimi, otomatik tarama | ⏳ |

Ayrıntılı kurulum ve komutlar için aşağıdaki bölümlere bakın. (Tamamlanan iş listesi ve test
sonuçları için bu dosyanın sonundaki **Aşama 1 raporu** bölümüne göz atın.)

- Backend: FastAPI + SQLAlchemy 2 + Alembic + SQLite → http://localhost:8000
- Frontend: Next.js + TypeScript + Tailwind → http://localhost:3000

## Hızlı başlangıç

```bash
# 1) Backend
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env.local          # gerekirse anahtarları doldurun
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SESSION_SECRET
alembic upgrade head
python -m app.cli seed              # iki örnek kullanıcı + mock ilanlar
uvicorn app.main:app --reload --port 8000

# 2) Frontend (yeni terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev                          # http://localhost:3000
```

Seed sonrası giriş bilgileri:

| Kullanıcı | Parola | İçerik |
| --- | --- | --- |
| `ai_hunter` (owner) | `DemoParola!2026` | AI Engineer / LLM Engineer mock ilanları |
| `data_hunter` (member) | `DemoParola!2026` | Data Analyst / Backend mock ilanları |

> Mock kayıtların tamamı `is_mock=True` ile işaretlidir ve arayüzde "Örnek veri" etiketiyle
> gösterilir. Gerçek Gmail/Hotmail/Telegram bağlantısı 2. ve 3. aşamada eklenecek; bu uçlar
> şimdilik dürüstçe `501 Not Implemented` döner.

## Gerçek (iki kullanıcılı) kurulum

```bash
cd backend
source .venv/bin/activate

# İlk kullanıcı (owner) - parolayı güvenli şekilde sorar
python -m app.cli create-user --username enis --email enis@example.com --owner

# İkinci kullanıcı daveti (süreli + tek kullanımlık bağlantı üretir)
python -m app.cli invite --email esim@example.com --ttl-hours 48

# Davet bağlantısı http://localhost:3000/invite/<token> adresinde açılır.
python -m app.cli list-users
python -m app.cli list-invitations
python -m app.cli purge-invitations
```

## Testler

```bash
cd backend
source .venv/bin/activate
pytest                       # 63 test
pytest -q tests/test_security.py
```

```bash
cd frontend
npm test                     # vitest + testing-library
```

## Dokümantasyon

- API şeması: http://localhost:8000/docs
- Ortam değişkenleri: `backend/.env.example`

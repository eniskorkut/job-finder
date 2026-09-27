# Job Hunter

İki kullanıcının kendi e-posta hesaplarına gelen LinkedIn iş ilanlarını toplayıp CV'leriyle
eşleştirdiği ve uygun ilanları Telegram üzerinden aldığı web uygulaması.

**Durum: Aşama 1/3 tamamlandı** — temel mimari, kullanıcı yönetimi, veritabanı, API ve frontend.

| Aşama | Kapsam | Durum |
| --- | --- | --- |
| 1 | Mimari, kullanıcı yönetimi, oturum/CSRF, tercihler, CV yükleme, mock ilanlar, dashboard | ✅ tamamlandı |
| 2 | Gmail + Hotmail/Outlook OAuth, e-posta okuma, CV metin çıkarımı | ⏳ |
| 3 | DeepSeek V4.1 Flash skorlama, Telegram bildirimi, otomatik tarama | ⏳ |

- **Backend:** FastAPI + SQLAlchemy 2 + Alembic + SQLite → http://localhost:8000
- **Frontend:** Next.js 16 + TypeScript + Tailwind CSS 4 (Better UI ilkeleri) → http://localhost:3000

Bu proje [simonleybovich/linkedin-job-alerts](https://github.com/simonleybovich/linkedin-job-alerts)
akışını örnek alır (e-posta → ilan çıkarma → CV ile skorlama → bildirim) ancak bağımsız bir
uygulamadır: n8n, Notion, Gemini, LinkedIn scraping ve otomatik başvuru yoktur.

## Gereksinimler

- Python 3.12+
- Node.js 20+ (bu geliştirme Node 22 ile yapıldı)
- Docker gerekmez; her şey localhost üzerinde çalışır
- 3000 ve 8000 portları boş olmalı (Next.js backend'e kendi proxy'si üzerinden gider)

## Kurulum

### 1) Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env.local
# .env.local içine gerçek anahtarları yazın. En azından:
#   SESSION_SECRET        -> python -c "import secrets; print(secrets.token_urlsafe(48))"
#   APP_ENCRYPTION_KEY    -> python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   DEEPSEEK_API_KEY      -> 3. aşamada kullanılacak (şimdi boş kalabilir)
```

> `.env.local` ve `backend/*.db` git'e **dahil edilmez** (`.gitignore`). Kullanıcı verileri
> (`backend/data/`) de repoya girmez.

### 2) Migration'lar

```bash
cd backend
source .venv/bin/activate
alembic upgrade head          # şemayı oluşturur
alembic current               # aktif revizyon: 0001_initial_schema
alembic check                 # model ile şema farkı var mı (boş çıkmalı)
alembic downgrade base        # geri alma (gerekirse)
```

### 3) İlk kullanıcı (CLI)

```bash
python -m app.cli create-user --username enis --email enis@example.com --owner
#   --password verilmezse parolayı güvenli şekilde sorar (en az 10 karakter)
```

### 4) İkinci kullanıcıyı davet et

```bash
python -m app.cli invite --email esim@example.com --ttl-hours 48
# Çıktı: http://localhost:3000/invite/<token>
```

Bağlantı **sürelidir ve tek kullanımlıktır**. Kullanıcı bu adresten kendi parolasını belirler.
Aynı işlem arayüzde **Davetler** sayfasından da yapılabilir (yalnızca owner kullanıcı görür).

```bash
python -m app.cli list-users
python -m app.cli list-invitations
python -m app.cli purge-invitations      # süresi dolmuş davetleri temizle
python -m app.cli status
```

### 5) Mock veriler (isteğe bağlı ama önerilir)

```bash
python -m app.cli seed
```

| Kullanıcı | Parola | İçerik |
| --- | --- | --- |
| `ai_hunter` (owner) | `DemoParola!2026` | 7 örnek ilan: AI Engineer / LLM Engineer / ML Engineer |
| `data_hunter` (üye) | `DemoParola!2026` | 6 örnek ilan: Data Analyst / Backend / BI / DevOps / Frontend |

Tüm mock kayıtlar `is_mock=True` ile işaretlidir, arayüzde **"Örnek veri"** etiketiyle görünür ve
gerçek ilan olmadıkları her ekranda açıkça belirtilir.

### 6) Sunucuları başlat

```bash
# backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# frontend (yeni terminal)
cd frontend
npm install
cp .env.example .env.local     # BACKEND_URL=http://localhost:8000
npm run dev                    # http://localhost:3000
```

Frontend tarayıcıdan gelen `/api/v1/*` isteklerini `BACKEND_URL` adresine proxy'ler; böylece
oturum çerezi birinci taraf olur ve CORS gerekmez.

## Testler

```bash
cd backend && source .venv/bin/activate
pytest                    # 63 test
pytest -v tests/test_security.py
```

```bash
cd frontend
npm test                  # 25 test (vitest + testing-library)
npm run typecheck         # tsc --noEmit
npm run build             # üretim derlemesi
```

Ayrıntılı sonuçlar için aşağıdaki **Aşama 1 raporu** bölümüne bakın.

## API

Tüm uçlar `/api/v1` altındadır. Kimlik doğrulama **HTTP-only oturum çerezi** (`jh_session`) ile
yapılır; kullanıcı kimliği hiçbir zaman istek gövdesinden/başlığından alınmaz, sunucu tarafındaki
oturumdan belirlenir.

| Grup | Uçlar |
| --- | --- |
| `/auth` | `GET /csrf`, `POST /login`, `POST /logout`, `GET /session`, `POST /password`, `GET/POST /invitations`, `DELETE /invitations/{id}`, `GET /invitations/{token}/inspect`, `POST /invitations/accept`, `GET /users` (owner) |
| `/me` | `GET`, `PATCH`, `GET /overview` |
| `/preferences` | `GET`, `PUT` |
| `/cvs` | `GET`, `POST` (dosya), `GET/PATCH/DELETE /{id}`, `GET /{id}/download` |
| `/jobs` | `GET`, `GET /stats`, `GET /filters`, `GET /{id}`, `PATCH /{id}` (durum) |
| `/integrations` | `GET`, `POST /{provider}/connect`, `DELETE /{provider}/accounts/{id}`, `GET /telegram/status`, `POST /telegram/link`, `DELETE /telegram` |
| `/sync` | `GET /history`, `GET /status`, `POST /run` |
| `/notifications` | `GET`, `POST /test` |

Etkileşimli dokümantasyon: http://localhost:8000/docs

**Aşama 1'de gerçekten çalışanlar:** kullanıcı yönetimi, oturum, davet akışı, tercihler, CV
yükleme/indirme, mock ilan listeleme/filtreleme/durum güncelleme, tarama ve bildirim geçmişi
okuma, dashboard özeti.

**Aşama 2/3 uçları** (`connect`, `telegram/link`, `sync/run`, `notifications/test`) sahte başarı
döndürmez; `501 Not Implemented` ve hangi aşamada geleceğini söyleyen bir mesaj döner. Aynı şekilde
DeepSeek entegrasyonu "etkin değil" olarak raporlanır.

## Mimari

```
backend/
  app/
    api/v1/        auth, me, preferences, cvs, jobs, integrations, sync, notifications
    core/          config, security (Argon2id), crypto (Fernet), rate_limit, errors
    db/            SQLAlchemy 2 Base + engine/session
    models/        users, sessions, invitations, user_preferences, cvs, mail_accounts,
                   jobs, job_matches, telegram_integrations, sync_history,
                   notification_history, oauth_states
    repositories/  her sorgu user_id ile kapsanır
    services/      auth, invitation, user, preference, cv, job, integration, sync, notification
    integrations/  Gmail, Microsoft Graph, DeepSeek, Telegram arayüzleri (Aşama 2/3 sözleşmeleri)
    cli.py         create-user, invite, list-users, list-invitations, seed, status
  alembic/         0001_initial_schema
  tests/           63 test

frontend/
  src/app/         (app)/ dashboard, jobs, jobs/[id], preferences, integrations, history, team
                   login, invite/[token]
  src/components/  ui/* (Better UI bileşenleri), app/* (shell, liste, form, kartlar)
  src/lib/         api istemcisi (CSRF'li), tipler, biçimlendirme, hook'lar
  src/proxy.ts     oturum çerezi kapısı + yönlendirmeler
```

### Güvenlik ve kullanıcı izolasyonu

- **Parola:** Argon2id (`argon2-cffi`, time_cost=3, memory_cost=64 MiB, parallelism=4).
- **Oturum:** rastgele 32 baytlık token; veritabanında yalnızca SHA-256 özeti saklanır; HTTP-only,
  `SameSite=Lax` çerez; süre `SESSION_TTL_DAYS` (varsayılan 14 gün); çıkışta iptal edilir.
- **CSRF:** double-submit. Oturum satırında CSRF özeti tutulur, `X-CSRF-Token` başlığı çerezle
  karşılaştırılır. Çerez taşıyan tüm POST/PUT/PATCH/DELETE isteklerinde zorunludur.
- **Rate limiting:** giriş denemeleri için kayan pencere (varsayılan 5 deneme / 15 dk, IP + kimlik).
- **Sahiplik:** Bütün kullanıcıya özel tablolarda `user_id` bulunur; repository katmanı her sorguya
  `user_id` filtresi ekler. Başka bir kullanıcının UUID'si bilinse bile kayıt **404** döner
  (varlık sızdırılmaz). Testler bunu ayrıca doğrular.
- **Şifreleme:** OAuth token'ları ve bot token'ları için `APP_ENCRYPTION_KEY` ile Fernet altyapısı
  hazır (Aşama 2'de kullanılacak).
- **Kişiye özel vs ortak:** Gmail, Hotmail ve Telegram ayarları kullanıcıya özeldir; DeepSeek
  anahtarı dağıtım genelinde ortaktır (`.env.local`).

### Veritabanı

SQLite kullanılır ancak şema PostgreSQL'e geçişi destekler: yalnızca taşınabilir tipler
(`Uuid`, `String`, `Text`, `Integer`, `Boolean`, `JSON`, `DateTime(timezone=True)`), SQLite'a özel
sütun yok. `DATABASE_URL` değerini PostgreSQL'e çevirmek yeterlidir.

## Aşama 1 raporu

### Oluşturulan dosyalar

- **Backend (54 dosya):** `app/` altında api (8 router + deps), core (5), db (2), models (11),
  schemas (9), repositories (10), services (9), integrations (6), `main.py`, `cli.py`, `seed.py`;
  `alembic/` (env + `0001_initial_schema`); `tests/` (7 dosya, 63 test); `pyproject.toml`;
  `.env.example`.
- **Frontend (37 dosya):** 9 sayfa/route (dashboard, iş ilanları, ilan detayı, CV ve tercihler,
  entegrasyonlar, tarama geçmişi, davetler, giriş, davet kabul), `src/proxy.ts`, 10 UI bileşeni,
  11 uygulama bileşeni, api istemcisi/tipler/hook'lar, 6 test dosyası (25 test), yapılandırma
  dosyaları (`next.config.ts`, `tailwind` v4, `vitest.config.ts`, `tsconfig.json`).
- **Kök:** `README.md`, `.gitignore` (`.env.local`, `*.db`, `backend/data/`, `node_modules`,
  `.next` hariç tutulur).

### Doğrulama sonuçları

| Kontrol | Komut | Sonuç |
| --- | --- | --- |
| Backend testleri | `pytest` | **63 passed** |
| Migration (up/down/check) | `alembic upgrade head && alembic check && alembic downgrade base` | Başarılı, model-şema farkı yok |
| Frontend birim testleri | `npm test` | **25 passed** (6 dosya) |
| Tip kontrolü | `npm run typecheck` | Hatasız |
| Üretim derlemesi | `npm run build` | Başarılı (9 route + proxy) |
| Uçtan uca (localhost) | curl + backend 8010 / frontend 3010 | Aşağıdaki senaryolar |

Uçtan uca doğrulanan senaryolar:

1. `ai_hunter` giriş yapar → **7** ilan görür; `data_hunter` giriş yapar → **6** ilan görür.
2. `data_hunter`, `ai_hunter`'ın ilan UUID'sini bilse bile `GET /api/v1/jobs/{id}` → **404**.
3. Üye kullanıcı `GET /api/v1/auth/invitations` → **403** (owner-only).
4. Çerezsiz `GET /api/v1/me` → **401**; CSRF başlığı olmadan `POST /auth/logout` → **403**.
5. `POST /api/v1/sync/run` → **501** + "henüz geliştirilmedi" mesajı (sahte başarı yok).
6. Davet akışı: owner davet üretir → davet sayfası açılır → davetli kendi parolasıyla hesap
   oluşturur → boş bir çalışma alanı görür (**0** ilan) → aynı bağlantı ikinci kez kullanılamaz
   (**422**).
7. Frontend: çerezsiz `/` → `/login` yönlendirmesi; giriş sonrası `/`, `/jobs`, `/preferences`,
   `/integrations`, `/history`, `/team` → **200**; Next proxy'si üzerinden `/me/overview`
   dashboard verisini döner.

### Bu aşamada yapılmayanlar (bilinçli)

- Gerçek Gmail / Microsoft Graph / DeepSeek / Telegram çağrıları (Aşama 2-3) — arayüzler ve
  veritabanı alanları hazır, uçlar dürüstçe 501 döner.
- CV metin çıkarımı ve otomatik eşleştirme puanı — örnek puanlar `mock-fixture` model adıyla
  işaretlidir.
- LinkedIn scraping, n8n, Notion, Gemini, otomatik başvuru — kapsam dışı.
- "Şimdi Tara" düğmesi 501 mesajını gösterir (tarama gerçekten yok).

### Bilinen sınırlar

- Giriş rate limiti süreç içi (in-memory) tutulur; çok işçili dağıtımda Redis'e taşınmalıdır.
- Frontend `proxy.ts` yalnızca çerez varlığına bakar; yetkilendirme her istekte API'de yapılır
  (çerez değeri yalnızca bir ipucudur).
- SMTP yapılandırılmadığı için davet bağlantıları e-posta ile gönderilmez, arayüz/CLI üzerinden
  paylaşılır (Aşama 2'de e-posta gönderimi eklenebilir).

## Lisans

MIT

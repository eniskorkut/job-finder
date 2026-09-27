# Job Hunter

İki kullanıcının kendi e-posta hesaplarına gelen LinkedIn iş ilanlarını toplayıp CV'leriyle
eşleştirdiği ve uygun ilanları Telegram üzerinden aldığı web uygulaması.

**Durum: Aşama 2/3 tamamlandı** — panelden kişisel OAuth, e-posta taraması, ilan çıkarımı,
CV metin çıkarımı ve dayanıklı manuel tarama.

| Aşama | Kapsam | Durum |
| --- | --- | --- |
| 1 | Mimari, kullanıcı yönetimi, oturum/CSRF, tercihler, CV yükleme, mock ilanlar, dashboard | ✅ tamamlandı |
| 2 | Gmail + Hotmail/Outlook OAuth (kullanıcı bazlı istemci), e-posta okuma, ilan ayrıştırma, tekilleştirme, CV metin çıkarımı, kalıcı tarama kuyruğu | ✅ tamamlandı |
| 3 | DeepSeek V4.1 Flash skorlama, Telegram bildirimi, otomatik zamanlayıcı | ⏳ |

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

Tarama işlerini işleyen **ayrı bir worker süreci** gerekir (API yalnızca kuyruğa alır):

```bash
# 1) backend API
cd backend && source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 2) tarama worker'ı (ayrı terminal, sürekli çalışır)
cd backend && source .venv/bin/activate
python -m app.worker                 # kuyruğu sürekli dinler
python -m app.worker --once          # tek iş işleyip çıkar (geliştirme/test)
python -m app.worker --poll-seconds 1 --verbose

# 3) frontend (üçüncü terminal)
cd frontend
npm install
cp .env.example .env.local     # BACKEND_URL=http://localhost:8000
npm run dev                    # http://localhost:3000
```

Worker süreci çalışmıyorsa "Şimdi Tara" işi kuyrukta bekler; arayüz bunu açıkça söyler
("İş kuyrukta. İşçi süreci çalışmıyorsa: python -m app.worker").

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

## Gmail bağlantısı (kullanıcı kendi OAuth uygulamasını kurar)

Her kullanıcı **kendi** Google OAuth istemcisini panele girip kendi Gmail hesabını bağlar.
Paylaşılan bir Google uygulaması yoktur; client secret kullanıcı bazında `APP_ENCRYPTION_KEY`
ile şifrelenerek saklanır ve bir daha düz metin gösterilmez.

1. <https://console.cloud.google.com> üzerinde bir proje açın.
2. **APIs & Services → Library → Gmail API → Enable**.
3. **OAuth consent screen**: External; test aşamasında *Test users* listesine bağlayacağınız
   Gmail adresini ekleyin. Scope: `https://www.googleapis.com/auth/gmail.readonly`
   (+ `openid`, `email` hesap adını doğrulamak için).
4. **Credentials → Create credentials → OAuth client ID → Web application**.
5. **Authorized redirect URIs** alanına birebir şunu ekleyin:
   `http://localhost:8000/api/v1/integrations/gmail/callback`
6. Client ID ve Client Secret değerlerini **Entegrasyonlar** sayfasındaki forma kaydedin,
   ardından **Gmail ile bağlan** düğmesine basın.

Notlar:

- Uygulama *Testing* modundayken Google refresh token'ı **7 gün** sonra geçersiz olur;
  hesabı "Yeniden yetkilendir" ile tazeleyin (arayüz bunu `needs_reauth` olarak gösterir).
- Yalnızca okuma izni istenir; **e-posta parolası hiçbir zaman istenmez ve saklanmaz**.
- `localhost` ile `127.0.0.1` karıştırılmamalıdır: uygulamanın adresi
  `http://localhost:3000`, callback adresi `http://localhost:8000/...` olmalıdır. Çerez
  alan adı `localhost` için yazıldığından callback sırasında oturum taşınır.
- Aynı istemci bilgileriyle **birden fazla Gmail hesabı** eklenebilir (hesap başına ayrı kart,
  ayrı filtre ve ayrı tarama checkpoint'i).

## Hotmail / Outlook bağlantısı (Microsoft Entra)

1. <https://entra.microsoft.com> → **Entra ID → App registrations → New registration**.
2. **Supported account types**: kişisel Microsoft hesapları dahil olan seçenek
   (*Accounts in any organizational directory and personal Microsoft accounts*).
3. **Authentication → Add a platform → Web** ve redirect URI olarak birebir:
   `http://localhost:8000/api/v1/integrations/outlook/callback`
4. **Certificates & secrets → New client secret**; değeri forma girin
   (kiracı alanı kişisel hesaplar için `consumers`).
5. **API permissions → Microsoft Graph → Delegated**: `Mail.Read`, `User.Read`
   (`offline_access` otomatik eklenir).

Notlar:

- MSAL **confidential client** akışı kullanılır: gizli anahtar uygulamayı doğruladığı için
  PKCE gerekmez (MSAL bu istemci türünde desteklemez); state + oturum eşleşmesi ile CSRF
  korunur.
- Token yenileme MSAL'in şifrelenmiş token cache'i üzerinden `acquire_token_silent` ile yapılır;
  cache de `APP_ENCRYPTION_KEY` ile şifreli saklanır.
- Artımlı tarama `deltaLink` ile yapılır; geçersiz delta bağlantısında (410/404) iş
  kullanıcıya hata göstermek yerine sınırlı yeniden tarama yapar ve checkpoint'i yeniler.
- Client secret süresi dolduğunda aynı formdan yeni secret girip yeniden bağlanın.

## API

Tüm uçlar `/api/v1` altındadır. Kimlik doğrulama **HTTP-only oturum çerezi** (`jh_session`) ile
yapılır; kullanıcı kimliği hiçbir zaman istek gövdesinden/başlığından alınmaz, sunucu tarafındaki
oturumdan belirlenir.

| Grup | Uçlar |
| --- | --- |
| `/auth` | `GET /csrf`, `POST /login`, `POST /logout`, `GET /session`, `POST /password`, `GET/POST /invitations`, `DELETE /invitations/{id}`, `GET /invitations/{token}/inspect`, `POST /invitations/accept`, `GET /users` (owner) |
| `/me` | `GET`, `PATCH`, `GET /overview` |
| `/preferences` | `GET`, `PUT` |
| `/cvs` | `GET`, `POST` (dosya), `GET/PATCH/DELETE /{id}`, `GET /{id}/download`, `GET /{id}/preview` (çıkarılan metin), `POST /{id}/extract` |
| `/jobs` | `GET`, `GET /stats`, `GET /filters`, `GET /{id}`, `PATCH /{id}` (durum) |
| `/integrations` | `GET`, `PUT/DELETE /{provider}/client` (kendi OAuth uygulamanız), `POST /{provider}/connect`, `GET /{provider}/callback`, `GET /accounts`, `PATCH /accounts/{id}` (filtreler), `POST /accounts/{id}/test`, `POST /accounts/{id}/reconnect`, `DELETE /accounts/{id}` (bağlantıyı kes), `DELETE /accounts/{id}/purge`, `GET /telegram/status`, `POST /telegram/link`, `DELETE /telegram` |
| `/sync` | `POST /run` (**202 + job_id**), `GET /jobs`, `GET /jobs/{id}` (ilerleme), `POST /jobs/{id}/cancel`, `GET /history`, `GET /status` |
| `/notifications` | `GET`, `POST /test` |

Etkileşimli dokümantasyon: http://localhost:8000/docs

**Aşama 2'de gerçekten çalışanlar:** kullanıcı bazlı Gmail/Microsoft OAuth istemci kaydı ve
yetkilendirme akışı, hesap listesi/filtreleri/test/yeniden bağlama/bağlantı kesme, e-posta
taraması (ilk pencere + artımlı cursor), LinkedIn ilanı ayrıştırma ve tekilleştirme, CV metin
çıkarımı + önizleme, kalıcı tarama kuyruğu ve canlı ilerleme.

**Aşama 3 uçları** (`telegram/link`, `notifications/test`) sahte başarı döndürmez;
`501 Not Implemented` ve hangi aşamada geleceğini söyleyen bir mesaj döner. DeepSeek yalnızca
"yapılandırıldı/yapılandırılmadı" olarak raporlanır, anahtar değeri asla döndürülmez.

### Tarama davranışı

- `POST /sync/run` anında döner (**202**) ve kalıcı bir iş kaydı oluşturur; UI `GET /sync/jobs/{id}`
  ile ilerlemeyi yoklar. Aynı kullanıcı için ikinci tarama **409** ile reddedilir (çift tıklama koruması).
- İlk tarama sınırlıdır: `SYNC_INITIAL_WINDOW_DAYS` (varsayılan 7 gün) ve
  `SYNC_INITIAL_MAX_MESSAGES` (100). Geçmişin tamamı yalnızca açıkça istenirse taranır.
- Artımlı tarama Gmail'de `users.history.list` + `historyId`, Outlook'ta `deltaLink` ile yapılır;
  cursor yalnızca sayfa kalıcı olarak kaydedildikten sonra ilerler.
- Eşzamanlılık: toplam `SYNC_MAX_ACTIVE_MAILBOXES` (4) posta kutusu, posta kutusu başına
  `SYNC_MAILBOX_CONCURRENCY` (2) ağ isteği. 429/5xx için `Retry-After` öncelikli, jitter'lı
  üstel geri çekilme uygulanır.
- İdempotency: her mesaj `processed_messages` defterine yazılır; aynı mesaj ve aynı ilan ikinci
  kez çoğalmaz. Bir posta kutusu hata verirse diğerleri taranmaya devam eder (kısmi başarı).
- Worker çökerse kira (lease) süresi dolar; iş yeniden kuyruğa alınır ve `attempt` sınırına
  ulaşınca dürüstçe `failed` olur.

## Mimari

```
backend/
  app/
    api/v1/        auth, me, preferences, cvs, jobs, integrations, sync, notifications
    core/          config, security (Argon2id), crypto (Fernet), rate_limit, errors
    db/            SQLAlchemy 2 Base + engine/session
    models/        users, sessions, invitations, user_preferences, cvs, mail_accounts,
                   oauth_client_configs, oauth_states, jobs, job_matches, job_sources,
                   sync_jobs, sync_job_accounts, sync_checkpoints, processed_messages,
                   sync_history, notification_history, telegram_integrations
    repositories/  her sorgu user_id ile kapsanır
    services/      auth, invitation, user, preference, cv, job, job_ingest, mail_scan,
                   sync_job, oauth, integration, sync, notification
    integrations/  gmail.py (Gmail REST), outlook.py (MSAL + Graph), http.py (retry/host
                   allowlist), cv_extraction.py, parsing/ (MIME, LinkedIn, dedupe, filters)
    worker.py      kalıcı tarama kuyruğunu işleyen ayrı süreç (python -m app.worker)
    cli.py         create-user, invite, list-users, list-invitations, seed, status
  alembic/         0001_initial_schema + 0002_email_sync_oauth_clients
  tests/           180 test / 13 dosya

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
- **Şifreleme:** Kullanıcının OAuth istemci secret'ı, access/refresh token'ları ve MSAL token
  cache'i `APP_ENCRYPTION_KEY` ile Fernet kullanılarak şifrelenir; hiçbiri frontend'e dönmez.
- **OAuth güvenliği:** Tek kullanımlık state (10 dk TTL) + oturuma bağlama + Gmail'de PKCE (S256);
  callback farklı oturum/kullanıcı ile tamamlanamaz. Sağlayıcı continuation linkleri yalnızca
  izinli host listesine (`graph.microsoft.com` vb.) kabul edilir; token yabancı adrese gönderilmez.
- **Log hijyeni:** Secret, OAuth kodu, tam CV metni ve ham posta gövdesi loglanmaz.
- **Kişiye özel vs ortak:** Gmail, Hotmail ve Telegram ayarları kullanıcıya özeldir; DeepSeek
  anahtarı dağıtım genelinde ortaktır (`.env.local`).

### Veritabanı

SQLite kullanılır ancak şema PostgreSQL'e geçişi destekler: yalnızca taşınabilir tipler
(`Uuid`, `String`, `Text`, `Integer`, `Boolean`, `JSON`, `DateTime(timezone=True)`), SQLite'a özel
sütun yok. `DATABASE_URL` değerini PostgreSQL'e çevirmek yeterlidir.

## Aşama 2'de eklenen dosyalar

**Backend (yeni)**: `app/models/oauth_client.py`, `app/models/sync_job.py`,
`app/repositories/oauth_clients.py`, `app/repositories/sync_jobs.py`,
`app/services/oauth_service.py`, `app/services/mail_scan_service.py`,
`app/services/sync_job_service.py`, `app/services/job_ingest_service.py`,
`app/integrations/http.py`, `app/integrations/errors.py`, `app/integrations/cv_extraction.py`,
`app/integrations/parsing/{mime,linkedin,dedupe,filters}.py`, `app/worker.py`,
`alembic/versions/0002_email_sync_oauth_clients.py`.

**Backend (güncellenen)**: `app/integrations/{gmail,outlook,base}.py` (gerçek istemciler),
`app/api/v1/{integrations,sync,cvs}.py`, `app/services/{cv,integration,user,sync}_service.py`,
`app/models/{job,mail_account,oauth,cv}.py`, `app/core/config.py`, `app/db/session.py` (WAL).

**Testler (yeni)**: `tests/fakes.py`, `tests/fixtures/emails.py`, `tests/test_oauth_flow.py` (22),
`tests/test_scan_pipeline.py` (15), `tests/test_sync_jobs.py` (17), `tests/test_cv_extraction.py` (20),
`tests/test_linkedin_parsing.py` (28), `tests/test_http_retry.py` (13).

**Frontend**: `src/components/app/sync-panel.tsx` (+test), `integrations-view.tsx` (yeniden yazıldı,
+test), `cv-manager.tsx` (önizleme, +test), `dashboard-view.tsx`, `history-view.tsx` (tarama işleri
sekmesi), `src/lib/types.ts`.

## Doğrulama sonuçları

| Kontrol | Komut | Sonuç |
| --- | --- | --- |
| Backend testleri | `pytest` | **180 passed** (13 dosya; Aşama 1: 65, Aşama 2: 115) |
| Migration (up/check) | `alembic upgrade head && alembic check` | 0002 uygulanır, model-şema farkı yok |
| Frontend birim testleri | `npm test` | **48 passed** (10 dosya) |
| Tip kontrolü | `npm run typecheck` | Hatasız |
| Üretim derlemesi | `npm run build` | Başarılı (9 route + proxy) |
| Worker | `python -m app.worker --once` | Kuyruk boşken temiz çıkış; kuyrukta iş varken işi işler |

Uçtan uca doğrulanan senaryolar (localhost; API 8010, frontend 3010 — 8000/3000 başka servislerce
kullanıldığı için):

1. `ai_hunter` giriş yapar → **7** ilan görür; `data_hunter` giriş yapar → **6** ilan görür.
2. `data_hunter`, `ai_hunter`'ın ilan UUID'sini bilse bile `GET /api/v1/jobs/{id}` → **404**.
3. Üye kullanıcı `GET /api/v1/auth/invitations` → **403**; çerezsiz `GET /api/v1/me` → **401**;
   CSRF başlığı olmadan `POST /auth/logout` → **403**.
4. Davet akışı: davet üretilir → davetli kendi parolasıyla hesap açar → boş çalışma alanı görür →
   aynı bağlantı ikinci kez kullanılamaz (**422**).
5. **Panelden OAuth istemcisi:** sahte Client ID/Secret kaydedildi → API `configured: true`,
   secret maskeli (`*************alue`) döndü, hiçbir yanıtta düz metin secret yok.
6. **Yetkilendirme adresi:** `POST /integrations/gmail/connect` → gerçek
   `https://accounts.google.com/o/oauth2/v2/auth` adresi; `redirect_uri` birebir
   `http://localhost:8000/api/v1/integrations/gmail/callback`, `scope=gmail.readonly openid email`,
   `code_challenge_method=S256`, `access_type=offline`, `prompt=consent`, 43 karakterlik tek
   kullanımlık state.
7. **CV metin çıkarımı:** gerçek PDF yüklendi → `extraction_status=ok`, önizleme metni ve
   karakter/satır sayısı döndü (metin yalnızca sahibine görünür).
8. **Worker + tarama:** `POST /sync/run` → **202 + job_id**; `python -m app.worker --once` işi
   aldı, gerçek Gmail sorgusunu (`from:(linkedin.com) subject:(...) after:2026/09/20`) oluşturdu,
   sahte token ile **401** aldı ve dürüstçe `failed` + hesap `needs_reauth` durumuna geçti.
   Sahte başarı üretilmedi.
9. Frontend: çerezsiz `/` → `/login`; giriş sonrası `/`, `/jobs`, `/preferences`, `/integrations`,
   `/history`, `/team` → **200**; `/integrations` uçları doğru durumu döndürdü (gmail/outlook
   `available=true`, telegram 3. aşama, DeepSeek `configured=true` ama anahtar değeri yok).

### Aşama 2'de yapılmayanlar (bilinçli)

- **Gerçek OAuth bağlantısı test edilmedi:** gerçek Google/Microsoft anahtarları olmadığı için
  canlı yetkilendirme ve gerçek Gmail/Graph okuması çalıştırılmadı. Akışın kendisi (state, PKCE,
  redirect URI, token şifreleme, hata sınıfları, worker yürütmesi) sahte sağlayıcı istemcileri ve
  gerçek HTTPS çağrısıyla doğrulandı; kullanıcı kendi istemci bilgilerini girip bağlandığında
  canlı akış devreye girer.
- DeepSeek skorlaması ve Telegram gönderimi yok (Aşama 3); ilan eşleşme puanı bu aşamada
  hesaplanmaz, `job_matches.score` boş kalır.
- OCR yok: taranmış PDF'ler `ocr_required` olarak işaretlenir, boş CV üretilmez.
- Otomatik zamanlayıcı/cron yok: tarama yalnızca manuel tetiklenir.

### Bilinen sınırlar

- Giriş rate limiti süreç içi (in-memory) tutulur; çok işçili dağıtımda Redis'e taşınmalıdır.
- Worker kirası ve eşzamanlılık sınırları SQLite üzerinde tek süreç için tasarlandı; yatay
  ölçekleme için PostgreSQL'e geçilmelidir (şema hazır).
- LinkedIn e-posta şablonları sık değişir; ayrıştırıcı sezgiseldir ve testlerde üç farklı HTML
  şablonu + düz metin + bozuk HTML ile doğrulanır. Yeni bir şablon geldiğinde ilan bulunamazsa
  mesaj "0 ilan" olarak kaydedilir (hata değil), gönderen/konu filtreleri panelden güncellenir.
- Frontend `proxy.ts` yalnızca çerez varlığına bakar; yetkilendirme her istekte API'de yapılır.
- SMTP yok: davet bağlantıları arayüz/CLI üzerinden paylaşılır.

## Lisans

MIT

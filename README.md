# AI-Market — Türkçe Doğal Dil Alışveriş Asistanı

Kullanıcının serbest Türkçe yazdığı isteği (`"1500 TL altında erkek ayakkabı"`,
`"şarjım dışarıda bitiyor"`) anlayıp ürün kataloğunda anlamsal arama yapan ve
doğal Türkçe yanıt üreten bir alışveriş asistanı. Bitirme ödevi (capstone):
React vitrin arayüzü + FastAPI backend.

Pipeline: niyet sınıflandırma → (Ollama ile) sorgu normalizasyonu → kural-tabanlı
ayrıştırma → FAISS anlamsal arama + bonus/ceza yeniden sıralama → (Ollama ile)
doğal Türkçe yanıt yazımı. Ollama yalnızca **normalizer/yazar** rolündedir; ürün
üretmez veya sıralamayı değiştirmez. Ollama kapalıyken sistem kural-tabanlı çalışır.

Derin mimari referansı: [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md).

## Gereksinimler

- Python 3.12+, Node.js 20+
- Docker + Docker Compose (PostgreSQL için)
- [Ollama](https://ollama.com) (opsiyonel; doğal dil normalizasyon/yanıt için).
  Varsayılan model `gemma3:4b` — `ollama pull gemma3:4b`

## Hızlı Başlangıç

### 1. Veritabanı (PostgreSQL)

```bash
docker compose up -d
# Yeni volume backend/db/seed_products.sql ile otomatik seed olur.
# postgres -> host portu 5433, pgadmin -> 5050
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Ortam değişkenleri: örneği kopyala, .env otomatik yüklenir (python-dotenv).
cp .env.example .env

uvicorn main:app --reload          # http://127.0.0.1:8000
```

`DATABASE_URL` tek zorunlu değişkendir; eksikse uvicorn açılışta sesli hata verir.
Katalog ve embedding'ler boot anında yüklenir (ilk açılış birkaç saniye sürer).

### 3. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

## Ollama (opsiyonel)

```bash
ollama pull gemma3:4b
ollama serve                       # http://localhost:11434
```

Tamamen devre dışı bırakmak için `backend/.env` içine `OLLAMA_ENABLED=false`.
Tüm config `AI_MARKET_*` / `OLLAMA_*` env değişkenleriyle ayarlanır; varsayılanlar
`backend/config.py` ve `backend/.env.example` içinde.

> Not: Varsayılan `gemma3:4b` bilinçli bir tercihtir. Daha büyük modeller (12b)
> 10 GB VRAM'e backend'in embedding modeliyle birlikte sığmaz ve CPU'ya taşarak
> yavaşlar; 4b tamamen GPU'da kalır ve halüsinasyon açısından da fark yaratmaz.

## Testler

```bash
cd backend
./.venv/bin/python -m pytest tests/                # deterministik birim testleri (CI-güvenli)

# Arama kalitesi regresyon harness'i (modeli yükler, API sunucusu gerekmez)
./.venv/bin/python eval/run_eval.py --show-failures

# Canlı API'ye karşı manuel regresyon (Ollama açıkken, ayrı terminalde)
./.venv/bin/python -m manual.api_queries           # STRICT: regresyonda non-zero çıkar
```

## Dil Kuralları

- **Kod İngilizce** — tüm tanımlayıcılar, dosya adları, satır-içi yorumlar.
- **Katalog verisi Türkçe** — ürün/kolon/mock verisi çevrilmez.
- **Kullanıcıya görünen metin Türkçe** — her chatbot yanıtı ve mesaj.

## Proje Yapısı

```
backend/          FastAPI servisi (tek endpoint: POST /search)
  config.py         env-tabanlı konfigürasyon
  query_parser.py   kural + alias + taksonomi ayrıştırma
  search_engine.py  FAISS arama + bonus/ceza skorlama
  response_*.py     mod kararı + Ollama yanıt yazımı
  db/, scripts/     PostgreSQL şema + seed
  tests/            deterministik pytest paketi
  eval/             altın-set arama kalitesi harness'i
frontend/         React 19 + Vite vitrin arayüzü
docs/             mimari dokümantasyon
```

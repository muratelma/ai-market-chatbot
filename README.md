# AI-Market — Türkçe Doğal Dil Alışveriş Asistanı

Kullanıcının serbest Türkçe yazdığı isteği (`"1500 TL altında erkek ayakkabı"`,
`"şarjım dışarıda bitiyor"`) anlayıp ürün kataloğunda anlamsal arama yapan ve
doğal Türkçe yanıt üreten bir alışveriş asistanı. Bitirme ödevi (capstone):
React vitrin arayüzü + FastAPI backend.

Pipeline: niyet sınıflandırma → (Ollama ile) sorgu normalizasyonu → kural-tabanlı
ayrıştırma → FAISS anlamsal arama + bonus/ceza yeniden sıralama → (Ollama ile)
doğal Türkçe yanıt yazımı. Ollama yalnızca **normalizer/yazar** rolündedir; ürün
üretmez veya sıralamayı değiştirmez. Ollama kapalıyken sistem kural-tabanlı çalışır.
Sonuçlar Ranking V2 ile doğrudan niyete göre sıralanır ve gerektiğinde
**“En uygun ürünler” / “İlgili alternatifler”** şeklinde gruplanır.

## Dokümantasyon

- [`README.md`](README.md): kurulum, çalıştırma ve hızlı doğrulama.
- [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md): güncel mimari, veri modeli,
  örnek sorgular, yapılandırma ve tüm test/eval komutları için tek teknik kaynak.
- [`AGENTS.md`](AGENTS.md): Codex ve diğer uyumlu kodlama ajanları için ortak proje
  kuralları.
- [`CLAUDE.md`](CLAUDE.md): Claude Code'un `AGENTS.md` kurallarını otomatik yüklemesini
  sağlayan kısa uyumluluk dosyası.

Geçici eval JSON çıktıları kaynak doküman değildir; gerektiğinde
`backend/eval/results/` altında yeniden üretilir ve Git tarafından izlenmez.

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

### 2. Ollama (opsiyonel)

```bash
# Ollama sistem servisi/masaüstü uygulaması çalışmıyorsa ayrı terminalde:
ollama serve

# İlk kurulumda modeli bir kez indirin:
ollama pull gemma3:4b
```

Ollama `http://localhost:11434` adresinde çalışır. Tamamen devre dışı bırakmak
için `backend/.env` içine `OLLAMA_ENABLED=false` yazılabilir; arama sistemi
kural-tabanlı fallback ile çalışmaya devam eder.

### 3. Backend (FastAPI)

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
Windows'ta sanal ortam yorumlayıcısı `backend\.venv\Scripts\python.exe` yolundadır.

### 4. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

## Servis Adresleri

- Frontend: `http://localhost:5173`
- Backend sağlık kontrolü: `http://127.0.0.1:8000/`
- Backend arama endpoint'i: `POST http://127.0.0.1:8000/search`
- Ollama: `http://localhost:11434`
- PostgreSQL: `localhost:5433`
- pgAdmin: `http://localhost:5050`

Tüm backend ayarları `AI_MARKET_*`, `DATABASE_URL`, `PRODUCTS_TABLE` ve
`OLLAMA_*` ortam değişkenleriyle yönetilir. Açıklamalar `backend/.env.example`
ve [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) içinde yer alır.

> Not: Varsayılan `gemma3:4b` bilinçli bir tercihtir. Daha büyük modeller (12b)
> 10 GB VRAM'e backend'in embedding modeliyle birlikte sığmaz ve CPU'ya taşarak
> yavaşlar; 4b tamamen GPU'da kalır ve halüsinasyon açısından da fark yaratmaz.

## Testler

```bash
cd backend
./.venv/bin/python -m pytest tests/
```

Gold eval, stress eval, uzun sorgu eval'i ve canlı API regresyon komutları için
[`PROJECT_OVERVIEW.md` içindeki Test ve Doğrulama Altyapısı](PROJECT_OVERVIEW.md#9-test-ve-doğrulama-altyapısı)
bölümüne bakın.

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
PROJECT_OVERVIEW.md teknik referans ve test kılavuzu
AGENTS.md          ortak kodlama ajanı talimatları
CLAUDE.md          Claude Code → AGENTS.md uyumluluk katmanı
```

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
- [`documentation/DOCKER_MIGRATION_REPORT.md`](documentation/DOCKER_MIGRATION_REPORT.md):
  Docker geçişi, CPU/GPU kurulumu, operasyon mantığı ve doğrulama raporu.
- [`documentation/RELEASE_NOTES_v1.1.0.md`](documentation/RELEASE_NOTES_v1.1.0.md):
  Tam Docker stack geçişini içeren v1.1.0 sürüm notları.
- [`AGENTS.md`](AGENTS.md): Codex ve diğer uyumlu kodlama ajanları için ortak proje
  kuralları.
- [`CLAUDE.md`](CLAUDE.md): Claude Code'un `AGENTS.md` kurallarını otomatik yüklemesini
  sağlayan kısa uyumluluk dosyası.

Geçici eval JSON çıktıları kaynak doküman değildir; gerektiğinde
`backend/eval/results/` altında yeniden üretilir ve Git tarafından izlenmez.

## Gereksinimler

- Docker Engine 24+ ve Docker Compose v2
- İlk kurulumda Docker imajları, Sentence-Transformers modeli ve `gemma3:4b`
  modelini indirmek için internet bağlantısı
- GPU modu için NVIDIA ekran kartı, güncel sürücü ve NVIDIA Container Toolkit
  (CPU kurulumu için gerekmez)

## Hızlı Başlangıç

### Docker Engine ve otomatik başlangıç politikası

Uzun süre çalışan Compose servisleri `restart: "on-failure:3"` kullanır. Bir servis
Docker Engine çalışırken hatayla kapanırsa en fazla üç kez yeniden denenir; bilgisayar
veya Docker Engine yeniden başladığında proje kendiliğinden ayağa kalkmaz. Docker'ı
başlatmak yalnız Engine'i kullanılabilir yapar; çalıştırılacak Compose projesi ayrıca
`docker compose up` ile seçilir.

Linux'ta Docker Engine'in bilgisayar açılışında başlamasını kapatmak için bir kez:

```bash
sudo systemctl disable --now docker.service docker.socket
```

Bu komut o anda çalışan tüm Docker projelerini durdurur. Docker'ı gerektiğinde elle
başlatın, ardından aşağıdaki CPU veya GPU Compose komutlarından yalnız uygun olanı
çalıştırın:

```bash
sudo systemctl start docker.service
```

### Varsayılan CPU kurulumu

```bash
docker compose up --build -d
```

Bu tek komut PostgreSQL, pgAdmin, Ollama, `gemma3:4b` model kurulumu, FastAPI
backend ve Nginx frontend servislerini bağımlılık sırasıyla başlatır. İlk çalıştırma
model indirmeleri nedeniyle uzun sürebilir; sonraki açılışlarda Docker volume'leri
kullanılır.

```bash
docker compose ps
docker compose logs -f backend
docker compose exec ollama ollama list
```

Sistemi durdurmak için `docker compose down` kullanın. PostgreSQL kataloğunu ve
indirilen modelleri korumak için `down -v` kullanmayın. Başka Docker projeleri de
kapalıysa Engine ayrıca `sudo systemctl stop docker.service docker.socket` ile
durdurulabilir; bu komut çalışan tüm Docker projelerini etkiler.

### NVIDIA GPU kurulumu

GPU desteği ana kurulumdan ayrıdır. Ubuntu/Debian üzerinde NVIDIA'nın
[resmî Container Toolkit rehberindeki](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
depo ve paket kurulum adımları:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
```

Ardından Docker runtime'ını yapılandırıp GPU erişimini doğrulayın:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all ubuntu nvidia-smi
```

Doğrulamadan sonra GPU override dosyasıyla sistemi başlatın:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

Bu mod Ollama'ya ve backend embedding modeline GPU erişimi verir; backend imajını
CUDA 13.0 uyumlu PyTorch ile yeniden oluşturur.

### İsteğe bağlı ayarlar

Compose hızlı yerel demo için varsayılan kimlik bilgileriyle doğrudan çalışır.
Bu değerler production için güvenli değildir; frontend, backend, PostgreSQL ve
pgAdmin portları host ağ arayüzlerine açılır. Yalnız güvenilen makine/ağda
kullanın. Veritabanı, pgAdmin veya Ollama ayarlarını değiştirmek için:

```bash
cp .env.example .env
# .env dosyasını düzenleyin; gerçek .env Git tarafından izlenmez.
```

### Docker olmadan yerel geliştirme

Ana çalışma yöntemi Docker'dır. Backend veya frontend'i ayrı geliştirmek gerekirse
yerel araç zinciri hâlâ kullanılabilir:

```bash
# Backend (Python 3.12+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload

# Frontend (ayrı terminal, Node.js 20.19+ veya 22.12+)
cd frontend
npm install
npm run dev
```

Yerel backend `backend/.env.example` içindeki host adreslerini kullanır ve host
Ollama kurulumuna bağlanır. Docker çalışmasında bu değerler Compose tarafından
servis adlarıyla override edilir.

## Servis Adresleri

- Frontend: `http://localhost:5173`
- Frontend API proxy: `POST http://localhost:5173/api/search`
- Backend sağlık kontrolü: `http://localhost:8000/`
- Backend arama endpoint'i: `POST http://localhost:8000/search`
- PostgreSQL: `localhost:5433`
- pgAdmin: `http://localhost:5050`

Ollama host portuna açılmaz; Docker ağı içinde `http://ollama:11434` adresindedir.
Model ve sağlık kontrolü `docker compose exec ollama ollama list` ile yapılır.

Tüm backend ayarları `AI_MARKET_*`, `DATABASE_URL`, `PRODUCTS_TABLE` ve
`OLLAMA_*` ortam değişkenleriyle yönetilir. Açıklamalar `backend/.env.example`
(`Docker olmadan yerel geliştirme`) ve [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md)
içinde yer alır. Docker ayarları kökteki `.env.example` dosyasındadır.

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
  Dockerfile        CPU/GPU uyumlu backend imajı
  config.py         env-tabanlı konfigürasyon
  query_parser.py   kural + alias + taksonomi ayrıştırma
  search_engine.py  FAISS arama + bonus/ceza skorlama
  response_*.py     mod kararı + Ollama yanıt yazımı
  db/, scripts/     PostgreSQL şema + seed
  tests/            deterministik pytest paketi
  eval/             altın-set arama kalitesi harness'i
frontend/         React 19 + Vite vitrin arayüzü
  Dockerfile        Node build + Nginx runtime imajı
  nginx.conf        SPA sunumu + /api backend proxy'si
docker-compose.yml CPU varsayılan tam sistem
docker-compose.gpu.yml NVIDIA GPU override ayarları
documentation/DOCKER_MIGRATION_REPORT.md Docker geçişi, kurulum ve doğrulama raporu
PROJECT_OVERVIEW.md teknik referans ve test kılavuzu
AGENTS.md          ortak kodlama ajanı talimatları
CLAUDE.md          Claude Code → AGENTS.md uyumluluk katmanı
```

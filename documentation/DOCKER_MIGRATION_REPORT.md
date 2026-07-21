# Docker Geçiş ve Doğrulama Raporu

Bu rapor, son Git commit'i olan **58f0ad4** sonrasında yapılan Docker
değişikliklerini, sistemin kurulumunu, servislerin çalışma mantığını ve commit
öncesi doğrulama durumunu tek yerde toplar.

## 1. Kapsam ve Sonuç

Önceki durumda Docker Compose yalnız PostgreSQL ve pgAdmin çalıştırıyordu.
Backend, frontend ve Ollama host üzerinde ayrı süreçlerdi. Yeni yapıda uygulamanın
tamamı tek Compose projesine taşındı:

| Alan | Önce | Şimdi |
|---|---|---|
| PostgreSQL | Docker | Docker |
| pgAdmin | Docker | Docker |
| Ollama | Host süreci | Docker, kalıcı model volume'ü |
| Model hazırlama | Manuel | ollama-init servisi |
| FastAPI backend | Host Python | CPU/GPU Docker image |
| React frontend | Host Vite | Node build + Nginx runtime |
| Servis sırası | Kısmen manuel | Healthcheck ve depends_on koşulları |
| GPU | Host kurulumuna bağlı | NVIDIA Container Toolkit + GPU override |

Sonuç olarak CPU modu taşınabilir varsayılan, GPU modu ise aynı temel Compose
dosyasına eklenen küçük bir override olarak çalışır. PostgreSQL kataloğu ve model
dosyaları container silinse bile named volume'lerde korunur.

## 2. Mimari ve Çalışma Mantığı

~~~text
Tarayıcı
   |
   | http://localhost:5173
   v
Frontend / Nginx
   |  statik React SPA
   |  /api/* -> http://backend:8000/*
   v
FastAPI Backend
   |------------------------------|
   v                              v
PostgreSQL                     Ollama
postgres:5432                  ollama:11434
1008 ürün                      gemma3:4b
   ^                              ^
   |                              |
postgres volume             ollama volume
                                  ^
                                  |
                             ollama-init
                           modeli kontrol eder/
                           eksikse indirir ve çıkar
~~~

Compose başlangıç sırası:

1. PostgreSQL ve Ollama paralel başlar.
2. PostgreSQL pg_isready, Ollama ise ollama list ile hazır olana kadar beklenir.
3. ollama-init, gemma3:4b modelini Ollama servisine çeker. Başarılı bitişi
   **Exited (0)** durumudur; sürekli çalışan bir servis değildir.
4. Backend, PostgreSQL sağlıklı ve ollama-init başarılı olduktan sonra başlar.
5. Backend Sentence-Transformers modelini yükler, 1008 ürünü PostgreSQL'den okur,
   ürün ve taksonomi embeddinglerini üretir ve Ollama warm-up yapar.
6. Backend healthcheck başarılı olunca Nginx tabanlı frontend başlar.
7. pgAdmin yalnız PostgreSQL sağlıklı olduktan sonra başlar.

Tüm servisler Compose'un varsayılan özel ağında servis adlarıyla haberleşir.
Ollama host portuna açılmaz. Backend için Ollama adresi **http://ollama:11434**,
PostgreSQL adresi **postgres:5432** olur.

Sürekli çalışan servisler `restart: "on-failure:3"` kullanır. Docker Engine
çalışırken non-zero kodla kapanan bir servis en fazla üç kez yeniden denenir; Docker
daemon veya bilgisayar yeniden başladığında proje otomatik başlamaz. Tek seferlik
`ollama-init` servisi `restart: "no"` kullanır. Böylece Docker'ı başlatmak tüm Compose
projelerini kaldırmaz; istenen proje ayrıca `docker compose up` ile seçilir.

## 3. Servisler, Portlar ve Kalıcı Veriler

| Servis | Image | Host portu | Kalıcı veri | Sağlık/çıkış beklentisi |
|---|---|---:|---|---|
| postgres | postgres:16 | 5433 | aimarket_postgres_data | healthy |
| pgadmin | dpage/pgadmin4 | 5050 | aimarket_pgadmin_data | running |
| ollama | ollama/ollama:latest | Açılmaz | aimarket_ollama_data | healthy |
| ollama-init | ollama/ollama:latest | Yok | Ollama volume'üne erişir | Exited (0) |
| backend | aimarket-backend:cpu veya :gpu | 8000 | aimarket_huggingface_cache | healthy |
| frontend | aimarket-frontend:latest | 5173 | Yok; immutable statik çıktı | healthy |

Named volume'ler:

- **aimarket_postgres_data:** PostgreSQL katalog verisi.
- **aimarket_pgadmin_data:** pgAdmin kullanıcı ayarları.
- **aimarket_ollama_data:** Ollama manifest ve model katmanları.
- **aimarket_huggingface_cache:** Sentence-Transformers model cache'i.

Normal durdurma için docker compose down kullanılır. **docker compose down -v**
volume'leri de silerek katalog ve indirilen modelleri kaldıracağı için normal
operasyonda kullanılmamalıdır.

## 4. Image Oluşturma Mantığı

### Backend

[backend/Dockerfile](../backend/Dockerfile) tek Dockerfile ile iki mod destekler.
**PYTORCH_INDEX_URL** build argümanı varsayılan olarak CPU PyTorch deposudur.
GPU override aynı Dockerfile'ı CUDA 13.0 PyTorch deposuyla yeniden build eder ve
farklı bir image etiketi kullanır:

- CPU: aimarket-backend:cpu, PyTorch CPU wheel
- GPU: aimarket-backend:gpu, torch 2.12.0+cu130

Container root olmayan **appuser** kullanıcısıyla çalışır. Hugging Face cache
dizini bu kullanıcıya aittir. tini benzeri sinyal/alt süreç yönetimi Compose'taki
init: true ile sağlanır.

[backend/.dockerignore](../backend/.dockerignore) sanal ortamı, test/eval çıktısını,
manuel araçları, cache'leri ve yerel veri dosyalarını build context dışında tutar.

### Frontend

[frontend/Dockerfile](../frontend/Dockerfile) iki aşamalıdır:

1. node:22-alpine aşamasında npm ci ve npm run build çalışır.
2. nginx:alpine aşamasına yalnız dist çıktısı ve Nginx ayarı kopyalanır.

Bu nedenle production frontend container'ında Node.js, npm veya kaynak kod
bulunmaz. [frontend/nginx.conf](../frontend/nginx.conf) SPA fallback sağlar ve
/api/ isteklerini backend servisine yönlendirir. Frontend build argümanı
**VITE_API_URL=/api/search** olduğu için tarayıcı doğrudan backend portuna bağımlı
değildir.

## 5. CPU ve GPU Ayrımı

[docker-compose.yml](../docker-compose.yml) taşınabilir CPU varsayılanıdır.
[docker-compose.gpu.yml](../docker-compose.gpu.yml) yalnız şu farkları uygular:

- Ollama servisine gpus: all
- Backend servisine gpus: all
- Backend image etiketi aimarket-backend:gpu
- PyTorch index'i CUDA 13.0
- GPU için Ollama çağrı timeout varsayılanı 30 saniye

Bu yaklaşım ortak servis tanımlarını kopyalamaz; GPU dosyası temel Compose
yapılandırmasının üzerine birleşir.

Gerçekleştirilen host GPU kurulumu:

| Bileşen | Doğrulanan değer |
|---|---|
| İşletim sistemi | Linux Mint 22.3, Ubuntu noble tabanı |
| GPU | NVIDIA GeForce RTX 3080, 10 GB |
| NVIDIA sürücüsü | 595.71.05 |
| Sürücünün CUDA desteği | 13.2 |
| NVIDIA Container Toolkit | 1.19.1-1 |
| Docker Engine | 29.1.3 |
| Docker Compose | 2.40.3 |

NVIDIA Container Toolkit, Docker daemon'a nvidia runtime kaydı eklemiştir.
Host'taki /etc/docker/daemon.json dosyası nvidia-container-runtime yolunu içerir.

## 6. Kurulum ve Çalıştırma

### Linux'ta manuel Docker Engine başlangıcı

Docker Engine'in sistem açılışında otomatik başlamaması isteniyorsa host'ta bir kez:

~~~bash
sudo systemctl disable --now docker.service docker.socket
~~~

Bu işlem çalışan bütün Docker projelerini durdurur. Engine gerektiğinde elle
başlatılır; ardından yalnız seçilen CPU veya GPU stack'i kaldırılır:

~~~bash
sudo systemctl start docker.service
~~~

Tüm projeler `docker compose down` ile kapatıldıktan sonra Engine de
`sudo systemctl stop docker.service docker.socket` ile durdurulabilir. Bu systemd
ayarı host'a aittir; repository checkout'u tek başına bu ayarı değiştirmez.

### CPU kurulumu

Gereksinimler: Docker Engine 24+ ve Docker Compose v2. İlk kurulumda internet
erişimi gerekir.

~~~bash
git clone <repo-url>
cd bitirmeodevi

# İsteğe bağlı: varsayılanları değiştirmek için
cp .env.example .env

docker compose up --build -d
docker compose ps
docker compose exec ollama ollama list
~~~

İlk açılışta Docker image'ları, gemma3:4b ve Sentence-Transformers modeli
indirildiği için işlem uzun sürebilir. Sonraki açılışlarda named volume ve build
cache kullanılır.

### NVIDIA GPU kurulumu

Host sürücüsünün önce çalıştığı doğrulanır:

~~~bash
nvidia-smi
~~~

Ubuntu/Debian tabanlı sistemde resmi NVIDIA Container Toolkit deposu eklenir:

~~~bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
~~~

Docker GPU erişimi bağımsız olarak test edilir:

~~~bash
docker run --rm --gpus all ubuntu:24.04 nvidia-smi
~~~

Ardından GPU stack başlatılır:

~~~bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
~~~

GPU'dan CPU'ya dönerken volume'leri korumak için:

~~~bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml down
docker compose up --build -d
~~~

## 7. Yapılandırma ve Secret Sınırları

[.env.example](../.env.example) yerel demo varsayılanlarını belgeler. Gerçek
.env ve backend/.env dosyaları Git tarafından izlenmez.

| Değişken grubu | Kullanan | Sınır/risk |
|---|---|---|
| POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD | PostgreSQL ve backend | Server-side; production değeri repoya konmamalı |
| PGADMIN_DEFAULT_EMAIL, PGADMIN_DEFAULT_PASSWORD | pgAdmin | Server-side; demo parolası production için uygun değil |
| OLLAMA_MODEL, OLLAMA_* | Backend/Ollama | Model, warm-up, keep-alive ve timeout |
| PRODUCTS_TABLE | Backend | Okunacak katalog tablosu |
| AI_MARKET_RANKING_V2, AI_MARKET_GROUPED_RANKING | Backend | Davranış feature flag'leri |
| VITE_API_URL | Frontend build | Tarayıcıya gömülür; secret konmamalı |
| PYTORCH_INDEX_URL | Backend build | CPU/GPU wheel kaynağı; secret değildir |

Uygulamada kullanıcı kimlik doğrulaması veya rol bazlı yetkilendirme yoktur.
Tarayıcı POST /search çağrısını anonim yapar; backend PostgreSQL'den okur ve
Ollama'ya istek gönderir. pgAdmin kendi kullanıcı/parola ekranına sahiptir.
Bu yapı güvenilen yerel demo ortamı içindir; internet-facing production dağıtımı
olarak değerlendirilmemelidir.

Mevcut port eşlemeleri 0.0.0.0 üzerinde frontend, backend, PostgreSQL ve pgAdmin'i
host ağ arayüzlerine açar. Aynı ağdaki erişimi istemeyen kurulumlarda portların
127.0.0.1 adresine bağlanması gerekir.

## 8. Son Commit Sonrasında Değişen Dosyalar

| Dosya | İşlem | Amaç |
|---|---|---|
| docker-compose.yml | Genişletildi | İki servisten tam CPU stack'e geçiş |
| docker-compose.gpu.yml | Eklendi | Backend ve Ollama için GPU override |
| backend/Dockerfile | Eklendi | CPU/GPU uyumlu FastAPI image |
| backend/.dockerignore | Eklendi | Küçük ve temiz build context |
| frontend/Dockerfile | Eklendi | Node build + Nginx runtime |
| frontend/.dockerignore | Eklendi | node_modules/dist/env dışlama |
| frontend/nginx.conf | Eklendi | SPA ve /api reverse proxy |
| .env.example | Eklendi | Compose override sözleşmesi |
| README.md | Güncellendi | Kurulum, GPU ve operasyon rehberi |
| PROJECT_OVERVIEW.md | Güncellendi | Mimari, test ve dosya ağacı |
| documentation/DOCKER_MIGRATION_REPORT.md | Eklendi | Docker geçişi, kurulum, risk ve doğrulama kaydı |
| documentation/RELEASE_NOTES_v1.1.0.md | Eklendi | v1.1.0 kullanıcı odaklı sürüm notları |
| frontend/package-lock.json | Güncellendi | npm ci ile yeniden üretilebilir kurulum |
| frontend/src/components/Chatbot.jsx | Küçük düzenleme | Hook sırası/lint uyumu; davranış değişikliği hedeflenmedi |
| .gitignore | Güncellendi | Env, Docker çıktıları ve genel backup dosyaları |
| docker-compose.yml.bak | Silindi | Eski yalnız-DB Compose kopyası |
| frontend/vite.config.js.bak | Silindi | İzlenmeyen eski Vite yedeği |

Host üzerinde, Git'e girmeyen değişiklikler:

- NVIDIA Container Toolkit ve paket deposu kuruldu.
- Docker nvidia runtime yapılandırıldı.
- Hatalı pgAdmin APT dağıtım adı zena yerine noble yapıldı.
- Cursor APT kaynağı mevcut Anysphere GPG anahtarına signed-by ile bağlandı.

## 9. Doğrulama ve Test Haritası

### Mevcut ve geçen kontroller

| Kontrol | Sonuç | Kapsadığı kural |
|---|---|---|
| Backend pytest | 122 passed | Parser, ranking, DB loader, response ve eval yardımcıları |
| Frontend npm ci | Başarılı | Lockfile'dan temiz kurulum |
| Frontend npm audit | 0 açık | Build bağımlılığı güvenlik kontrolü |
| Frontend ESLint | Başarılı | React/hook ve statik kod kuralları |
| Frontend production build | Başarılı | Vite derleme ve asset üretimi |
| CPU Compose config | Başarılı | Temel Compose sözdizimi/birleşimi |
| CPU+GPU Compose config | Başarılı | GPU override birleşimi |
| Backend pip check | No broken requirements | Python bağımlılık tutarlılığı |
| Docker GPU smoke test | RTX 3080 görüldü | Host runtime ve device passthrough |
| Backend CUDA testi | torch 2.12.0+cu130, CUDA true | Embedding modelinin GPU erişimi |
| Ollama testi | gemma3:4b, 100% GPU | LLM'in GPU'da yerleşmesi |
| Container health | Gerekli servisler healthy | Başlangıç bağımlılık zinciri |
| PostgreSQL sayımı | 1008 ürün | Volume ve katalog bütünlüğü |
| Down/up kalıcılık testi | Başarılı | Volume'lerin container ömründen bağımsızlığı |
| Nginx üzerinden gerçek sorgu | HTTP 200 | Browser yolu → API → DB/Ollama |
| Gerçek sorgu sonucu | 5 ürün, ollama_used=true | Arama ve Ollama rewrite davranışı |
| Canlı API strict regresyonu | 46/46 geçti | Uçtan uca deterministik API sözleşmeleri |
| git diff --check | Başarılı | Whitespace/patch bütünlüğü |

### Henüz otomatik olmayan kontroller

- CI içinde docker compose up ile tam smoke test yok.
- Docker image CVE taraması yok.
- Python bağımlılıkları pip-audit benzeri bir CVE aracıyla taranmadı.
- Volume yedekleme/geri yükleme prosedürü otomatik test edilmiyor.
- Portların yalnız localhost'a bağlı olduğunu zorlayan bir test yok.

## 10. Commit Öncesi Bulgular

### Release kararları

1. **Frontend npm audit düzeltildi:** `npm audit fix` uyumlu patch güncellemelerini
   lockfile'a uyguladı. Ardından temiz `npm ci`, lint, production build ve Docker image
   build'i geçti; audit sonucu 0 açıktır.
2. **Ağ erişimi ve demo parolaları kabul edilen yerel-demo sınırıdır:** Portlar host
   ağ arayüzlerine açıktır ve Compose demo kimlik bilgileri sağlar. README ile bu rapor
   yalnız güvenilen makine/ağ kullanımını açıkça belirtir. Internet-facing deployment
   bu release'in kapsamında değildir ve ayrıca güvenli yapılandırılmalıdır.

### Commit'i engellemeyen fakat izlenmesi gerekenler

- ollama/ollama:latest, dpage/pgadmin4, nginx:alpine ve node:22-alpine gibi mutable
  image etiketleri tam bit-for-bit yeniden üretilebilirlik sağlamaz. Sürüm veya
  digest sabitleme release öncesinde değerlendirilmeli.
- GPU backend image'ı yaklaşık 8.81 GB, CPU image'ı yaklaşık 2.12 GB'dır. İlk GPU
  build'i büyük CUDA paketleri nedeniyle uzun sürer.
- Docker image ve build cache kullanımı yüksektir. Denetim sırasında image alanı
  37.14 GB, build cache 19.82 GB raporlandı. Otomatik prune yapılmadı; CPU fallback
  ve başka projelere ait image'lar yanlışlıkla silinmemelidir.
- Hugging Face token'ı zorunlu değildir; tokensız kullanım yalnız indirme rate
  limitlerini etkileyebilir.

## 11. Release Hazırlık Sonucu

Fonksiyonel Docker geçişi tamamlanmış, CPU/GPU Compose birleşimleri doğrulanmış ve
veritabanı/model kalıcılığı korunmuştur. Release öncesindeki son tekrar kontrollerinde:

1. Backend testlerinin tamamı geçti: 122/122.
2. Frontend temiz kurulum, audit (0 açık), lint ve production build kontrollerini geçti.
3. Güncel frontend ve GPU backend image'ları başarıyla build edildi.
4. PostgreSQL, Ollama, backend ve frontend healthcheck'leri healthy oldu; pgAdmin çalıştı.
5. Backend ve frontend HTTP 200 döndürdü; Nginx proxy üzerinden gerçek arama 5 ürün ve
   `ollama_used=true` ile tamamlandı.
6. Çalışan Docker backend'e karşı strict canlı API regresyonu 46/46 geçti.
7. Restart politikası tüm sürekli servislerde `on-failure:3` olarak container metadata'sında
   doğrulandı; CPU/GPU Compose config ve `git diff --check` geçti.

Bilinen yerel-demo güvenlik sınırları Bölüm 7 ve 10'da belgelenmiştir. Otomatik Docker
prune uygulanmadı. Bu durumla v1.1.0 release'i hazırlanabilir.

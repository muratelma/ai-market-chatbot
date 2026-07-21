# AI-Market — v1.1.0 (21 Temmuz 2026)

## Yeni Özellikler

- **Tek Compose projesi:** PostgreSQL, pgAdmin, Ollama, model hazırlama, FastAPI backend
  ve React frontend artık tek komutla, doğru bağımlılık sırasıyla çalışıyor.
- **CPU ve NVIDIA GPU seçenekleri:** Taşınabilir CPU kurulumu varsayılan olarak sunuluyor;
  NVIDIA kullanıcıları küçük bir Compose override ile hem embedding modelini hem Ollama'yı
  GPU üzerinde çalıştırabiliyor.
- **Otomatik model hazırlama:** Tek seferlik `ollama-init` servisi `gemma3:4b` modelini
  hazırlar; model sonraki çalıştırmalar için kalıcı volume'de tutulur.

## İyileştirmeler

- **Daha güvenilir başlangıç:** Healthcheck ve koşullu bağımlılıklar, backend ile frontend'i
  yalnız PostgreSQL ve Ollama hazır olduğunda başlatır.
- **Kalıcı yerel veriler:** Ürün kataloğu, pgAdmin ayarları, Ollama modeli ve Hugging Face
  cache'i container ömründen bağımsız named volume'lerde korunur.
- **Production frontend sunumu:** React uygulaması çok aşamalı image ile build edilir,
  Nginx üzerinden sunulur ve `/api` istekleri doğrudan Docker ağındaki backend'e iletilir.
- **Kontrollü çalışma akışı:** Servisler hata durumunda en fazla üç kez yeniden denenir;
  Docker Engine veya bilgisayar açıldığında proje kendiliğinden başlamaz.

## Düzeltmeler

- Frontend otomatik sorgu effect sırası lint kurallarıyla uyumlu hale getirildi; kullanıcı
  davranışı korunuyor.
- Frontend build bağımlılıkları güvenli patch sürümlerine güncellendi ve `npm audit`
  sonucu 0 açığa indirildi.

## Kurulum ve Geçiş Notları

- Ana çalışma yöntemi için Docker Engine 24+ ve Docker Compose v2 gerekir.
- CPU kurulumu `docker compose up --build -d` ile başlatılır.
- GPU kurulumu NVIDIA Container Toolkit gerektirir ve
  `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d`
  komutunu kullanır.
- Mevcut PostgreSQL ve model volume'leri korunur; normal kapatmada `down -v`
  kullanılmamalıdır.
- Bu sürüm güvenilen yerel demo ortamını hedefler. Varsayılan portlar ve demo kimlik
  bilgileri internet-facing production kurulumu için uygun değildir.

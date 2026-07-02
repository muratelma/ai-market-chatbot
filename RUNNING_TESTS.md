# Test Çalıştırma Kılavuzu

Tüm komutlar `backend` klasöründeyken çalıştırılır.

```cmd
cd C:\Users\Ahmet\DOCUME~1\BITIRM~1\AI-MAR~1\backend
```

---

## 1. Unit Testler (pytest)

Backend veya Docker gerekmez.

```cmd
.venv\Scripts\python.exe -m pytest tests\ -v
```

Beklenen: **122 passed**

---

## 2. Gold Eval (60 sorgu)

Backend veya Docker gerekmez.

```cmd
.venv\Scripts\python.exe -m eval.run_eval
```

Beklenen: tüm sorgular hatasız tamamlanır

---

## 3. Stress Eval (1000 sorgu)

Backend veya Docker gerekmez.

```cmd
.venv\Scripts\python.exe -m eval.run_stress_eval
```

Beklenen: 1000 sorgu çalışır, exception yok

---

## 4. Long Query Eval (uzun sorgular)

Backend veya Docker gerekmez.

```cmd
.venv\Scripts\python.exe -m eval.run_eval --gold-set eval\long_queries.json
```

Beklenen: tüm sorgular hatasız tamamlanır

---

## 5. Manual Strict Testler (API)

> **Gereksinim:** Docker (PostgreSQL) ve backend (`localhost:8000`) çalışıyor olmalı.

```cmd
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe -m manual.api_queries
```

Beklenen: **46/46 PASS**

---

## 6. Ollama Regression

> **Gereksinim:** Docker, backend ve Ollama çalışıyor olmalı.

```cmd
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe -m manual.ollama_regression
```

Beklenen: tüm sorgular tutarlı sonuç döndürür

---

## Başlatma Sırası (5 ve 6 için)

1. `baslat.bat` dosyasına çift tıkla (Docker + backend + frontend açılır)
2. Testleri çalıştır

---

## pgAdmin — Veritabanı Arayüzü

### Giriş

Tarayıcıda aç: `http://127.0.0.1:5050`

| Alan | Değer |
|------|-------|
| Email | `admin@example.com` |
| Şifre | `admin123` |

### Sunucu Ekleme (ilk kez)

Sol panelde **Servers** → sağ tık → **Register → Server**

**General** sekmesi:

| Alan | Değer |
|------|-------|
| Name | `AI Market DB` |

**Connection** sekmesi:

| Alan | Değer |
|------|-------|
| Host | `postgres` |
| Port | `5432` |
| Database | `aimarket` |
| Username | `aimarket_user` |
| Password | `aimarket_pass` |
| SSL mode | `Prefer` |

Kaydet → sol ağaçta `AI Market DB → Schemas → public → Tables → products`

SELECT * FROM products
order by id


### Backend DATABASE_URL

Backend `.env` dosyasında kullanılan bağlantı (host portu farklı):

```
postgresql://aimarket_user:aimarket_pass@localhost:5433/aimarket
```

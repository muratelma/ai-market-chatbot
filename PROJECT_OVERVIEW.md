# AI-Market — Proje Genel Bakışı

> Türkçe doğal dille çalışan, LLM destekli (Ollama) bir e-ticaret alışveriş asistanı.
> Bitirme ödevi kapsamında geliştirilmiş; React tabanlı vitrin + FastAPI tabanlı arama/öneri backend'i içerir.

---

## 1. Tek Cümlede Sistem

Kullanıcı sohbet kutusuna doğal Türkçe (`"şarjım dışarıda bitiyor"`, `"yağlı saç için şampuan"`, `"1500 TL altında erkek ayakkabı"`) yazar; backend bu cümleyi niyete sınıflandırır, gerekirse Ollama ile normalleştirir, kuralcı parser ile yapılandırılmış sorguya çevirir, semantik arama + filtreleme + bonus/penaltı skorlamasıyla ürün döndürür ve yine Ollama ile doğal bir Türkçe yanıt metni üretir.

---

## 2. Üst Düzey Mimari

```
┌──────────────────────────┐         ┌──────────────────────────────────────────────────┐
│   Frontend (React 19)    │         │            Backend (FastAPI + Python)            │
│   Vite dev server         POST     │                                                  │
│   src/components/Chatbot ───────►   POST /search                                        │
│   - Header arama         │  JSON   │                                                  │
│   - Categories tıklama   │         │   ┌──────────────────────────────────────────┐   │
│   - Chatbot penceresi    │         │   │ 1. chat_intent.classify_intent           │   │
│                          │         │   │    greeting / help / thanks / nonsense   │   │
│   "answer" + "products"  │         │   │    / product_search  (kural + Ollama)    │   │
│   alanlarını render eder │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 2. chat_memory.resolve_follow_up         │   │
│                          │         │   │    Önceki clarification varsa kısa cevap │   │
│                          │         │   │    sorguyla birleştirilir.               │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 3. chat_normalizer.normalize_query       │   │
│                          │         │   │    Ollama (gemma3:4b varsayılan) ile     │   │
│                          │         │   │    sorguyu temiz aramaya çevirir;        │   │
│                          │         │   │    düşük confidence → fallback orijinal  │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 4. query_parser.parse_query              │   │
│                          │         │   │    Regex + alias + taksonomi (FAISS) →   │   │
│                          │         │   │    main/sub/product_type, target_group,  │   │
│                          │         │   │    features, contexts, min/max_price     │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 5. response_planner.build_response_plan  │   │
│                          │         │   │    Mode: chat_reply / clarification_only │   │
│                          │         │   │          focused_search / broad_search   │   │
│                          │         │   │    + soft follow-up sorusu               │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 6. query_parser.get_clarification_resp.. │   │
│                          │         │   │    Çok genel sorgularda takip sorusu     │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 7. search_engine                         │   │
│                          │         │   │    - apply_filters (fiyat sert; diğerleri│   │
│                          │         │   │      yumuşak fallback'li)                │   │
│                          │         │   │    - semantic_search (FAISS/L2 + bonus / │   │
│                          │         │   │      penalty + nonsense threshold)       │   │
│                          │         │   │    - diversify_results (broad mode için) │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 8. response_rewriter.rewrite_response    │   │
│                          │         │   │    Ollama ile doğal Türkçe assistant_text│   │
│                          │         │   │    (ürünler/sıralama ASLA değişmez)      │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │                                                  │
│                          │◄────────│   JSON: answer, products[], parsed_query,        │
│                          │  JSON   │         needs_clarification, follow_up_question, │
│                          │         │         response_mode, response_source, debug    │
└──────────────────────────┘         └──────────────────────────────────────────────────┘
                                                 │
                                                 ▼
                                       ┌───────────────────────────┐
                                       │  Yan servis: Ollama        │
                                       │  http://localhost:11434    │
                                       │  /api/generate (httpx)     │
                                       │  Model: gemma3:4b (env)    │
                                       └───────────────────────────┘
```

---

## 3. Dizin Yapısı

```
bitirmeodevi/
├── backend/
│   ├── main.py                  # FastAPI app, /search endpoint, 12 adımlık pipeline
│   ├── config.py                # ENV tabanlı yapılandırma (CSV yolları, Ollama, top_k)
│   ├── data_loader.py           # products.csv & taxonomy.csv yükleme + şema kontrolü
│   ├── data_prepare.py          # Veri hazırlık betiği
│   ├── chat_intent.py           # Kural + Ollama hybrid intent sınıflandırıcı
│   ├── chat_memory.py           # In-memory session store, follow-up birleştirme
│   ├── chat_normalizer.py       # Ollama tabanlı sorgu normalleştirici (+fallback)
│   ├── query_parser.py          # Fiyat/kategori/feature/context çıkarımı; alias kuralları
│   ├── response_planner.py      # Deterministik mod kararı (focused/broad/clarification)
│   ├── response_rewriter.py     # Ollama ile doğal Türkçe yanıt; ürünleri değiştirmez
│   ├── search_engine.py         # FAISS semantik + bonus/penalty rerank + diversification
│   ├── ollama_client.py         # /api/generate çağrısı; JSON çıkarma & graceful fallback
│   ├── products.csv             # 1000 ürünlük katalog (Türkçe)
│   ├── taxonomy.csv             # main_category/sub_category/product_type sözlüğü (~72 satır)
│   ├── requirements.txt         # FastAPI, sentence-transformers, faiss-cpu, httpx, ...
│   ├── eval/
│   │   ├── gold_queries.json    # 40 sorgudan oluşan altın küme
│   │   ├── run_eval.py          # Yerel benchmark koşucusu
│   │   ├── run_stress_eval.py   # 1000 sorgu stress eval
│   │   ├── stress_queries_1000.json
│   │   ├── README.md            # Eval harness kullanımı
│   │   └── results/             # Karşılaştırma çıktıları (json)
│   ├── tests/
│   │   ├── test_query_parser.py
│   │   ├── test_response_planner.py
│   │   └── test_eval_harness.py
│   └── scratch/, test_ollama_manual.py, test_queries.py
│
└── frontend/                    # React 19 + Vite 8 vitrin
    ├── index.html
    ├── package.json             # react, react-dom; react-compiler ile derlenir
    ├── vite.config.js           # host 0.0.0.0, allowedHosts true
    └── src/
        ├── App.jsx              # Header, HeroBanner, Categories, FeaturedProducts, Footer, Chatbot
        ├── App.css / index.css
        └── components/
            ├── Header.jsx           # Üst bar + arama formu (onSearchSubmit)
            ├── HeroBanner.jsx       # Ana banner + CTA
            ├── Categories.jsx       # Kategori kartları (tıklayınca chatbot açar)
            ├── FeaturedProducts.jsx # Statik öne çıkan ürünler
            ├── Footer.jsx
            └── Chatbot.jsx          # Sohbet penceresi, /search çağırır, ürün kartlarını render eder
```

---

## 4. Teknoloji Yığını

**Backend**

- Python + FastAPI (`uvicorn` ile çalıştırılır)
- `sentence-transformers` modeli: `paraphrase-multilingual-MiniLM-L12-v2` (Türkçe için)
- `faiss-cpu` ile vektör araması (cosine similarity, L2 normalize)
- `pandas` / `numpy` ile CSV katalog işleme
- `httpx` ile Ollama'ya HTTP çağrısı
- Ollama yan servisi (varsayılan: `gemma3:4b`, `http://localhost:11434`)

**Frontend**

- React 19 + Vite 8
- React Compiler (babel preset) etkin
- Saf CSS (App.css / index.css), framework yok
- Backend'e `fetch("http://127.0.0.1:8000/search")` ile bağlanır

**Veri**

- `products.csv` — 1000 ürün, 10 sütun (product_name, description, main_category, sub_category, target_group, product_type, features, tags, attributes, price)
- `taxonomy.csv` — main_category / sub_category / product_type için Türkçe semantik açıklamalar (FAISS embedding'i bu metinler üzerinden hesaplanır)

---

## 5. /search API Sözleşmesi

**İstek (POST /search)**

```json
{
  "query": "yağlı saç için şampuan öner",
  "session_id": "optional-uuid"
}
```

**Yanıt (sadeleştirilmiş)**

```json
{
  "answer": "Yağlı saç sorununa yönelik şampuan seçeneklerini listeledim. ...",
  "products": [
    { "id": 123, "name": "...", "price": "₺199", "match": "87%",
      "tags": ["Kişisel Bakım", "Saç Bakımı", "Unisex", "Şampuan"],
      "image": "🛍️", "rating": 4.5, "description": "..." }
  ],
  "parsed_query": { "main_category": "...", "product_type": "...", "features": [...] },
  "needs_clarification": false,
  "follow_up_question": null,
  "original_query": "yağlı saç için şampuan öner",
  "normalized_query": "yağlı saç şampuanı",
  "normalization_used": true,
  "normalization_confidence": 0.85,
  "ollama_used": true,
  "ollama_fallback_reason": null,
  "session_id": "...",
  "intent": "product_search",
  "response_mode": "focused_search",
  "response_source": "ollama_rewrite"
}
```

Yanıt her zaman dolu döner — Ollama erişilemese bile `template_*` kaynaklı bir cevap üretilir. Frontend yalnız `answer` ve `products` alanlarını gösterir; geri kalanlar debug/observability içindir.

---

## 6. Tasarım Kararları

| Karar | Gerekçe |
| --- | --- |
| **Ollama "üretici" değil, "normalleştirici/yazıcı" rolünde** | Ürünleri/sıralamayı asla değiştirmez. Halüsinasyon riskini taşımaz. |
| **Düşük confidence → her zaman fallback** | `OLLAMA_CONFIDENCE_THRESHOLD` (varsayılan 0.6) altında orijinal sorguya/şablon yanıta düşülür. |
| **`ollama_client.call_ollama` her hata türünde `None` döner** | Timeout, bağlantı, geçersiz JSON, vb. — caller fallback'ten sorumlu; API asla 500 atmaz. |
| **`config.OLLAMA_ENABLED=false` ile tamamen kapatılabilir** | Ollama servisi olmadan da pipeline kuralcı yoldan çalışır. |
| **Niyet sınıflandırması önce deterministik** | Greeting/thanks gibi açık örüntüler Ollama'ya hiç gitmez (gecikmeyi düşürür). |
| **`response_planner` saf kuralcı** | LLM olmadan mod kararı verilir, latency düşer, test edilebilir. |
| **Fiyat = tek sert filtre, diğerleri yumuşak fallback'li** | Yanlış sınıflandırılmış kategori boş sonuç üretmesin diye `apply_filters` `base_pool`'a düşer. |
| **`diversify_results` round-robin** | Geniş aramalarda (ör. "kamp") tek ürün tipinin tüm slotları kapmasını engeller. |
| **In-memory session (dict + TTL)** | DB ihtiyacı yok; takip sorularını birleştirmek için yeterli (`SESSION_TTL_SECONDS=1800`). |
| **Nonsense threshold (`max_score < 0.40` ve sert filtre yoksa)** | "Uzay mekiği" gibi sorgular için alakasız sonuç yerine boş döner. |
| **Frontend tek endpoint kullanır** | Header arama, kategori tıklama ve chatbot direkt mesajı — hepsi `/search`'ü çağırır. |

---

## 7. Yapılandırma (ENV)

`backend/config.py` aşağıdaki değişkenleri okur; hiçbirini set etmemek geçerli bir varsayılana düşer.

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `AI_MARKET_MODEL_NAME` | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-Transformers modeli (yerel dizin varsa onu tercih eder) |
| `AI_MARKET_PRODUCTS_CSV` | `products.csv` | Katalog yolu (göreceli → `backend/` altında) |
| `AI_MARKET_TAXONOMY_CSV` | `taxonomy.csv` | Taksonomi metni |
| `AI_MARKET_TOP_K` | `5` | `/search` yanıtındaki ürün sayısı |
| `AI_MARKET_TAXONOMY_MATCH_THRESHOLD` | `0.65` | Taksonomi semantik eşleşme eşiği |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP adresi |
| `OLLAMA_MODEL` | `gemma3:4b` | Kullanılacak Ollama modeli |
| `OLLAMA_ENABLED` | `true` | Ollama'yı tamamen devre dışı bırakır (`false`) |
| `OLLAMA_TIMEOUT_SECONDS` | `15` | Tek çağrı timeout'u |
| `OLLAMA_CONFIDENCE_THRESHOLD` | `0.6` | Bunun altında Ollama çıktısı reddedilir |

---

## 8. Çalıştırma

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# (Opsiyonel) Ollama'yı başlat ve gemma3:4b modelini çek:
#   ollama serve
#   ollama pull gemma3:4b
uvicorn main:app --reload   # http://127.0.0.1:8000
```

İlk açılışta model yüklenmesi + 1000 ürünün embeddinglenmesi birkaç saniye sürer; konsolda "AI-Market API hazır." görülür.

**Frontend**

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

Chatbot ikonu sağ alttan açılır; Header arama kutusu ve Categories kartları da tıklanınca chatbot'u açıp ilgili sorguyu otomatik gönderir.

**Eval harness**

```bash
cd backend
./.venv/bin/python eval/run_eval.py --show-failures \
  --output-json eval/results/baseline.json
```

`eval/results/` altında değişiklik öncesi/sonrası JSON çıktıları karşılaştırma için saklanır (`baseline_before_response_modes.json`, `after_generalization_fix.json`, vb. örnek olarak mevcut).

**Birim testler**

```bash
cd backend
./.venv/bin/python -m pytest tests/
```

---

## 9. /search Pipeline'ı — Adım Adım (main.py)

1. **Session al/oluştur** — `req.session_id` boşsa UUID üretilir.
2. **Intent sınıflandır** — `chat_intent.classify_intent`. Greeting/help/thanks/goodbye/wellbeing ise hazır cevap döner, arama çalıştırılmaz. `nonsense` + confidence ≥ 0.7 ise nazik "katalogda yok" mesajı döner.
3. **Follow-up çöz** — Bekleyen clarification varsa kısa cevap önceki sorguyla birleştirilir.
4. **Sorguyu normalleştir** — Ollama (`chat_normalizer`) doğal cümleyi temiz aramaya çevirir; başarısız olursa orijinal kullanılır.
5. **Parse** — `query_parser.parse_query`: fiyat (range/üst/alt/civarı), kategori (explicit + alias + taksonomi semantic), target_group, features (sinonim haritası), contexts, taxonomy_match. Kategori tutarlılığı `normalize_category_consistency` ile zorlanır.
6. **Response plan kur** — `response_planner.build_response_plan`: mode + `should_ask_followup` + `top_product_types`.
7. **Clarification kontrolü** — Çok genel sorgu + `broad/focused_search` modu değilse takip sorusu döner.
8. **Filtre uygula** — `apply_filters`: fiyat zorunlu; kategori filtreleri sonuç ≥ 10 değilse `base_pool`'a düşer.
9. **Semantik arama** — `semantic_search`: FAISS cosine + bonus (product_type tam eşleşme, kategori, target_group, features, taxonomy, context) ve penalty (yanlış cinsiyet, yanlış product_type). Düşük skor + sert filtre yok → boş döner.
10. **Çeşitlendir** — Broad search ise `diversify_results` round-robin ile farklı product_type'ları dağıtır.
11. **Yanıt yaz** — `response_rewriter.rewrite_response` Ollama'ya yaslar; başarısız olursa `build_answer` şablonu döner. `should_ask_followup` ise takip sorusunun yanıt içinde kelimesi kelimesine bulunması garanti edilir.
12. **Session güncelle ve yanıt döndür** — `parsed_query`, mod, debug alanları cevaba eklenir.

---

## 10. Veri Modeli

`products.csv` — gerekli sütunlar:

| Sütun | Örnek |
| --- | --- |
| `product_name` | "Kamp Çadırı 2 Kişilik" |
| `description` | "Hafif ve su geçirmez yapısıyla..." |
| `main_category` | "Kamp" |
| `sub_category` | "Çadır" |
| `target_group` | "Unisex" / "Kadın" / "Erkek" / "Çocuk" |
| `product_type` | "Kamp Çadırı" |
| `features` | virgülle ayrılmış: "su geçirmez,hafif,taşınabilir" |
| `tags` | virgülle ayrılmış: "kamp,çadır,outdoor" |
| `attributes` | JSON string: `{"kullanim":[...], "ortam":[...], "ozellik":[...]}` |
| `price` | sayısal (TL) |

`taxonomy.csv` — üç sütun: `field`, `value`, `text`. `text` alanı kategoriyi tanımlayan Türkçe anahtar kelimeleri içerir (FAISS embed'ine girer). Sorgu, taksonomi metinleriyle karşılaştırılır; eşik üstü en yakın taksonomi kaydı `parsed_query` içine yerleştirilir.

`gold_queries.json` (eval) — her satırda `id`, `query` ve `expected`. `expected` içinde `main_category`, `target_group`, `product_types_any` (kabul edilen listeden en az biri eşleşmeli) veya `expects_clarification` / `expects_empty_result` etiketleri bulunur.

---

## 11. Bilinen Sınırlar / Notlar

- **Auth yok.** `/search` herkese açıktır; CORS `allow_origins=["*"]`. Vitrin amaçlı bir bitirme projesi olduğu için kullanıcı/oturum/güvenlik katmanı eklenmemiştir (yalnız in-memory `session_id` izleme).
- **Veri yazma yok.** Backend hiçbir veriyi diske yazmaz, dış servise göndermez; Ollama dışında yan etki yoktur.
- **Single-process.** Session store ve embeddingler tek uvicorn prosesinde tutulur — ölçekleme için Redis + paylaşımlı index gerekir.
- **Frontend statik resimler kullanır.** Ürün görselleri emoji + Unsplash fallback'tir; gerçek katalog görseli yoktur.
- **Ollama dışsal bağımlılık.** Servis yoksa pipeline çalışır ama Ollama "normalleştirme" ve "doğal yanıt yazma" devre dışı kalır; cevap kalitesi şablon seviyesine düşer.
- **`products_30_backup.csv`** — eski 30 ürünlük katalog yedeği (kullanılmıyor).

---

## 12. Hızlı Yönelim Rehberi

| Soru | Nereye bakılır |
| --- | --- |
| API uçları neler? | `backend/main.py` (yalnız `GET /` ve `POST /search`) |
| Bir sorgu nasıl parse ediliyor? | `backend/query_parser.py::parse_query` |
| Mod kararı nerede veriliyor? | `backend/response_planner.py::build_response_plan` |
| Skorlama formülü? | `backend/search_engine.py::semantic_search` (bonus/penalty bölümleri) |
| Ollama prompt'ları? | `chat_intent.py` (`_INTENT_CLASSIFIER_PROMPT`), `chat_normalizer.py` (`NORMALIZER_SYSTEM_PROMPT`), `response_rewriter.py` (`REWRITER_SYSTEM_PROMPT`) |
| Yeni ürün eklemek? | `backend/products.csv`'ye satır ekle; uvicorn'u yeniden başlat (embeddingler boot'ta yeniden hesaplanır) |
| Yeni kategori sinyali eklemek? | `backend/taxonomy.csv` + gerekirse `query_parser.QUERY_ALIASES` veya `FEATURE_SYNONYMS` |
| Sohbet UI'sini değiştirmek? | `frontend/src/components/Chatbot.jsx` ve `App.css` |
| Otomatik regresyon testi? | `backend/tests/` (pytest) ve `backend/eval/run_eval.py` (gold küme) |

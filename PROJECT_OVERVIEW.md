# AI-Market — Proje Genel Bakışı

> Türkçe doğal dille çalışan, LLM destekli (Ollama) bir e-ticaret alışveriş asistanı.
> Bitirme ödevi kapsamında geliştirilmiştir: React tabanlı vitrin + FastAPI tabanlı
> arama/öneri backend'i. Ürün kaynağı artık **yalnızca PostgreSQL**'dir (CSV dönemi
> kapanmıştır), nihai sıralama **Ranking V2** ile yapılır ve sonuçlar gerektiğinde
> **"En uygun ürünler" / "İlgili alternatifler"** olarak ayrılabilir.

---

## 1. Proje Özeti

Kullanıcı sohbet kutusuna doğal Türkçe (`"şarjım dışarıda bitiyor"`, `"yağlı saç için
şampuan"`, `"1500 TL altında erkek ayakkabı"`) yazar. Backend bu cümleyi:

1. bir **niyete** sınıflandırır (selamlama mı, ürün araması mı, anlamsız mı),
2. gerekirse **Ollama ile normalleştirir** (argo/yazım hatasını temizler),
3. **kuralcı parser** ile yapısal bir sorguya çevirir (kategori, fiyat, hedef kitle…),
4. **semantik arama + filtreleme + bonus/penaltı skorlaması** yapar,
5. **Ranking V2** ile sonuçları kullanıcının doğrudan niyetine göre yeniden sıralar,
6. yine **Ollama ile** doğal bir Türkçe yanıt metni üretir.

Tüm bu işlemler tek bir HTTP endpoint'i (`POST /search`) arkasında orkestre edilir.

---

## 2. Amaç ve Kapsam

### Çözülen problem

Klasik e-ticaret araması, kullanıcının kelime kelime doğru ürün terimini yazmasını bekler.
Oysa gerçek kullanıcı çoğu zaman **ürün adını değil ihtiyacını** anlatır:

| Kullanıcının yazdığı | Aslında aradığı |
| --- | --- |
| "şarjım dışarıda bitiyor" | powerbank |
| "ev kendi kendine süpürsün" | robot süpürge |
| "saçım hemen yağlanıyor" | yağlı saç bakım ürünü |

AI-Market'in amacı bu doğal dildeki ihtiyaç ifadesini anlamlı bir ürün önerisine
çevirmektir.

### Tasarımın temel ilkesi: halüsinasyondan kaçınmak

> **LLM (Ollama) bir "üretici" değil, "normalleştirici/yazıcı"dır.** Ürün, fiyat, stok
> veya sıralama **uydurmaz**. Ürünler her zaman katalogdan, deterministik kod tarafından
> seçilir; LLM yalnızca girdi metnini temizler ve çıktı metnini güzelleştirir.

Bu ilke iki ek güvenceyle pekiştirilir: (1) yanıt yazıcıya ürünün **gerçek alanları**
(`tags`, `description`) verilir ve modele "yalnızca veride geçen özellikten bahset, istenen
ama bulunmayan özelliği (ör. su geçirmez) iddia etme" denir; (2) kullanıcının istediği
kategori sonuçlarda yoksa (fiyat filtresi kategoriyi gevşettiyse) yanıt bunu **dürüstçe**
bildirir ("aradığınız çantayı bulamadım, en yakın alternatifleri listeledim") — model
uymazsa deterministik bir guard cümleyi kendisi ekler.

### Kapsam dışı

Kullanıcı hesabı, kimlik doğrulama, sepet/ödeme, sipariş kaydı ve veri yazma yoktur.
Proje bir **vitrin/demo**'dur: katalog salt-okunur sunulur.

---

## 3. Üst Düzey Mimari

İki dış bağımlılık vardır: ürün verisi için **PostgreSQL** (zorunlu) ve doğal dil işleme
için **Ollama** (opsiyonel — kapalıyken sistem tamamen kuralcı yoldan çalışır).

```
┌──────────────────────────┐         ┌──────────────────────────────────────────────────┐
│   Frontend (React 19)    │         │            Backend (FastAPI + Python)            │
│   Vite dev server        │  POST   │                                                  │
│   src/components/Chatbot ───────►   POST /search                                       │
│   - Header arama         │  JSON   │                                                  │
│   - Categories tıklama   │         │   ┌──────────────────────────────────────────┐   │
│   - Chatbot penceresi    │         │   │ 1. chat_intent.classify_intent           │   │
│                          │         │   │    greeting / help / thanks / nonsense   │   │
│   "answer" + "products"  │         │   │    / product_search   (kural + Ollama)   │   │
│   + grouped görünüm      │         │   └──────────────────────────────────────────┘   │
│   alanlarını render eder │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 2. chat_memory.resolve_follow_up         │   │
│                          │         │   │    Önceki clarification varsa kısa cevap │   │
│                          │         │   │    önceki sorguyla birleştirilir.        │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 3. chat_normalizer.normalize_query       │   │
│                          │         │   │    Ollama (gemma3:4b) sorguyu temiz      │   │
│                          │         │   │    aramaya çevirir; düşük conf→orijinal,  │   │
│                          │         │   │    + deterministik kategori/fiyat guard  │   │
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
│                          │         │   │    - semantic_search (FAISS + bonus /    │   │
│                          │         │   │      penalty + nonsense threshold)       │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 8. ranking_core.finalize_ranking_v2      │   │
│                          │         │   │    Ranking V2: directness tier (DIRECT > │   │
│                          │         │   │    RELATED > OTHER) ile yeniden sıralar; │   │
│                          │         │   │    grouped → primary / alternative ayrımı│   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 9. ranking_diagnostics (observe-only)    │   │
│                          │         │   │    Directness/regime sinyallerini debug  │   │
│                          │         │   │    alanında raporlar; sıralamayı/ürünü   │   │
│                          │         │   │    ASLA değiştirmez.                     │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │         │   ┌──────────────────────────────────────────┐   │
│                          │         │   │ 10. response_rewriter.rewrite_response   │   │
│                          │         │   │    Ollama ile doğal Türkçe assistant_text│   │
│                          │         │   │    (ürünler / sıralama ASLA değişmez)    │   │
│                          │         │   └──────────────────────────────────────────┘   │
│                          │◄────────│   JSON: answer, products[], parsed_query,        │
│                          │  JSON   │         needs_clarification, follow_up_question, │
│                          │         │         response_mode, response_source,          │
│                          │         │         ranking_diagnostics, result_grouping     │
└──────────────────────────┘         └──────────────────────────────────────────────────┘
                                                  │
                          ┌───────────────────────┴───────────────────────┐
                          ▼                                                ▼
              ┌───────────────────────────┐                  ┌───────────────────────────┐
              │  Veri kaynağı: PostgreSQL  │                  │  Yan servis: Ollama        │
              │  host port 5433            │                  │  http://localhost:11434    │
              │  products tablosu          │                  │  /api/generate (httpx)     │
              │  ORDER BY id (açılışta,    │                  │  Model: gemma3:4b (env)    │
              │  salt-okunur yükleme)      │                  │  Normalizer + Writer       │
              │  Kaynak: db/seed_products  │                  │  OLLAMA_ENABLED=false→kapalı│
              │  .sql  (DATABASE_URL)      │                  │  hata → her zaman fallback │
              └───────────────────────────┘                  └───────────────────────────┘
```

### Backend katmanları — her adım ne yapar, neden var

Aşağıdaki sıra `main.py::search_products` içinde yukarıdan aşağıya işler. Her katman
deterministiktir; Ollama yalnızca 3 noktada (niyet/normalize/yazım) ve her zaman bir
**fallback** ile devreye girer.

| # | Katman (fonksiyon) | Ne yapar / neden var |
| --- | --- | --- |
| 1 | **`chat_intent.classify_intent`** | Mesajı niyete ayırır (greeting/help/thanks/goodbye/wellbeing/product_search/nonsense). Selamlama gibi açık örüntüler **arama pipeline'ına hiç girmeden** hazır cevap alır; böylece gecikme düşer. Önce kural, yalnız çok kısa/belirsiz mesajda Ollama. |
| 2 | **`chat_memory.resolve_follow_up`** | Önceki turda bir clarification (netleştirme) sorusu sorulmuşsa, kullanıcının kısa cevabını ("kadın", "200 TL altı") önceki sorguyla **birleştirir**. Kullanıcı kendini tekrar etmek zorunda kalmaz. In-memory, TTL 30 dk. |
| 3 | **`chat_normalizer.normalize_query`** | Ollama ile argo/yazım hatalı/dolaylı cümleyi temiz aramaya çevirir ("papuç lazım" → "ayakkabı"). Düşük güven veya hata → **orijinal sorgu** kullanılır. Prompt, ürün/fiyat/marka **uydurmayı yasaklar**. |
| — | **Normalleştirme guard'ları** | Ollama kategoriyi düşürür/değiştirir veya fiyatı silerse, kullanıcının **gerçek kelimeleri** esas alınarak yeniden parse edilir ve fiyat geri yüklenir. LLM'in yanlışını deterministik olarak telafi eden güvenlik katmanı. |
| 4 | **`query_parser.parse_query`** | Sorguyu **yapısal alanlara** ayırır: `main/sub/product_type`, `target_group`, `features`, `contexts`, `min/max_price`, `taxonomy_match`. Regex + alias kuralları + `taxonomy.csv` üzerinden **FAISS semantik kategori eşleşmesi** kullanır. |
| 5 | **`response_planner.build_response_plan`** | **Saf kuralcı** mod kararı: `chat_reply` / `clarification_only` / `focused_search` / `broad_search`. Ayrıca "kullanıcı yeterli detay verdi mi?" sorusunu kullanıcının **orijinal** kelimelerine göre yanıtlar; gerekirse yumuşak bir follow-up sorusu hazırlar. LLM çağırmaz → düşük gecikme, test edilebilir. |
| 6 | **`query_parser.get_clarification_response`** | Sorgu katalogda hiçbir sinyale oturmuyorsa "katalog dışı" (boş sonuç) der; çok genel ise bir **netleştirme sorusu** üretir. broad/focused modunda kullanıcı yeterli bilgi verdiyse bu adım atlanır ve ürünler gösterilir. |
| 7 | **`search_engine.apply_filters`** | Aday havuzunu daraltır. **Fiyat tek sert filtredir**; kategori/hedef-kitle filtreleri sonuç fazla daralırsa boş dönmemek için `base_pool`'a **yumuşak fallback** yapar. Yanlış sınıflandırma yüzünden "sonuç yok" yaşanmasını engeller. |
| 8 | **`semantic_search` (FAISS)** | Sorgu vektörü ile ürün embeddingleri arasında cosine benzerliği hesaplar, üstüne **bonus/penalty rerank** uygular (doğru product_type/kategori/cinsiyet bonus; ters cinsiyet/yanlış tip penalty). Sert filtre yokken çok düşük skor → **boş** ("uzay mekiği" gibi anlamsız sorgular için). |
| 9 | **`ranking_core.finalize_ranking_v2`** | **Ranking V2**: zaten skorlanmış sonuçları, kullanıcının **doğrudan niyetine ne kadar cevap verdiklerine** (directness tier) göre yeniden sıralar. Yalnızca sonuç listesini sıralar/kırpar; kaynak veriyi ve embeddingleri değiştirmez. (Bölüm 7.) |
| 10 | **`ranking_diagnostics.build_ranking_diagnostics`** | **Gözlem amaçlı** (observe-only): her ürünün directness sinyallerini ve sorgunun diversification "regime"ini bir **debug alanında** raporlar. Sıralamayı/ürünleri **asla değiştirmez** — Ranking V2 kararlarını izlemek/doğrulamak içindir. |
| 11 | **`response_rewriter.rewrite_response`** | Ollama ile sonuçlara uygun, doğal ve samimi bir Türkçe `answer` metni yazar; yalnızca ürünün **gerçek alanlarından** (tags/description) bahseder, istenen ama bulunmayan özelliği uydurmaz ve kategori ikamesini dürüstçe bildirir (bkz. Bölüm 2). Hata olursa `build_answer` şablonu döner. **Ürünleri, fiyatları ve sıralamayı asla değiştirmez.** |

### JSON yanıt sözleşmesi

Yanıt **her zaman dolu döner**; Ollama erişilemese bile `template_*` kaynaklı bir cevap
üretilir ve `/search` Ollama hatasında **asla 500 atmaz**. Temel alanlar:

```json
{
  "answer": "Yağlı saç sorununa yönelik şampuan seçeneklerini listeledim. ...",
  "products": [
    { "id": 123, "name": "...", "price": "₺199", "match": "87%",
      "tags": ["Kişisel Bakım", "Saç Bakımı", "Unisex", "Şampuan"],
      "description": "...", "rating": 4.5, "image": "🛍️",
      "match_group": "primary" }        // grouped ranking açıkken
  ],
  "parsed_query":        { "...": "parser'ın çıkardığı yapısal alanlar" },
  "needs_clarification": false,
  "follow_up_question":  null,
  "response_mode":       "focused_search",   // response_planner modu
  "response_source":     "ollama_rewrite",   // yanıt nereden geldi (ollama / template)
  "ranking_diagnostics": { "regime": "...", "direct_tier_count": 2, "products": [ ... ] },
  // grouped ranking açıkken ek alanlar:
  "result_grouping":      "primary_alternative",
  "primary_products":     [ ... ],
  "alternative_products": [ ... ],
  // debug/observability:
  "original_query": "...", "normalized_query": "...",
  "normalization_used": true, "normalization_confidence": 0.85,
  "ollama_used": true, "session_id": "...", "intent": "product_search"
}
```

Frontend yalnızca `answer`, `products` ve (varsa) grouped alanları gösterir; geri kalanlar
debug/observability içindir.

---

## 4. Backend Akışı (Pipeline Ayrıntısı)

`/search` tek gerçek endpoint'tir (`GET /` yalnızca sağlık kontrolüdür). Header arama,
kategori kartları ve chatbot — hepsi bu endpoint'i çağırır.

**İstek:** `{ "query": "yağlı saç için şampuan öner", "session_id": "opsiyonel-uuid" }`

Akış (Bölüm 3'teki katmanların sıralı uygulanışı):

1. **Session al/oluştur** — `session_id` boşsa UUID üretilir.
2. **Intent** — non-search niyetler hazır cevapla kısa devre yapar; `nonsense`+conf≥0.7 →
   nazik "katalogda yok" mesajı.
3. **Vague (belirsiz) ön-kontrol** — "ürün öner" gibi yalnız dolgu kelimeli sorgular,
   normalleştirme/arama yapılmadan **clarification**'a düşürülür (Ollama'nın belirsiz
   isteği sahte kategoriye genişletmesini engeller).
4. **Follow-up çöz** → 5. **Normalleştir** → 6. **Parse** → (guard'lar) → 7. **Plan**.
8. **Clarification kontrolü** — gerekiyorsa takip sorusu döner.
9. **Filtre + semantik arama** → 10. **Ranking V2 / legacy diversify** → 11. **Diagnostics**.
12. **Yanıt yaz** (Ollama → şablon fallback) → 13. **Session güncelle + JSON döndür**.

---

## 5. Frontend Akışı

`frontend/src/components/Chatbot.jsx` tek backend endpoint'ini çağırır
(`VITE_API_URL`, varsayılan `http://127.0.0.1:8000/search`).

- **Tek giriş noktası:** Header arama kutusu ve Categories kartları da tıklanınca chatbot'u
  açıp ilgili sorguyu otomatik gönderir.
- **Yükleme durumu:** sorgunun ürün araması mı sohbet mi olduğunu yüzeysel tahmin edip
  "Ürünler aranıyor..." / "Yanıt hazırlanıyor..." metnini gösterir (yalnız görsel; backend
  intent sistemini taklit etmez).
- **Mesaj varyantları:** `needs_clarification`, `no_result`, `error` durumlarına göre
  baloncuk stili ve küçük etiket (❓ Soru, 🔍 Sonuç bulunamadı, ⚠️ Bağlantı sorunu) değişir.
- **Hata kurtarma:** bağlantı hatasında "↻ Tekrar dene" butonu aynı sorguyu yeniden çalıştırır.

### Ürün kartları ve grup görünümü

- Her kartta ad, kategori etiketi, açıklama, fiyat, puan ve **eşleşme yüzdesi** (`match`)
  bulunur. Kart başlığında kategoriye göre emoji (👟, 🧴, 🔌…) frontend tarafında türetilir;
  veri sözleşmesini değiştirmez.
- Backend `result_grouping === "primary_alternative"` döndürür ve her iki grup da doluysa,
  liste **"✅ En uygun ürünler"** ve **"🔗 İlgili alternatifler"** olarak ikiye ayrılır.
  Aksi halde düz liste gösterilir — eski/flag-kapalı backend ile birebir uyumludur.

---

## 6. Veri Kaynağı ve PostgreSQL Yapısı

> **Önemli güncelleme:** Eski `products.csv` tabanlı yükleme **kaldırılmıştır.** Çalışma
> zamanı ürün kaynağı **yalnızca PostgreSQL**'dir; CSV fallback yoktur.

- **`DATABASE_URL` zorunludur**, varsayılanı yoktur. Eksikse `data_loader.load_products`
  `RuntimeError` fırlatır ve uygulama **açılmadan durur** (eksik katalogla servis vermemek
  için bilinçli karar).
- Katalog tek sefer, açılışta belleğe yüklenir; istek başına SQL yapılmaz.
- Yükleme `SELECT ... FROM products ORDER BY id` ile yapılır.

### Embedding / Sıra Sözleşmesi (kritik)

`product_embeddings[i]`, DataFrame'in `i`. satırına karşılık gelir. Katalog `ORDER BY id`
ile yüklenir, `reset_index` ile `0..N-1` sabit indeks alır ve embeddingler tam bu sıradan
üretilir. **Yüklemeden sonra DataFrame asla yeniden sıralanmaz/filtrelenmez**, aksi halde
arama sessizce yanlış ürün döndürür. `ORDER BY id` bu yüzden kozmetik değil zorunludur.

### `seed_products.sql`'in rolü

`backend/db/seed_products.sql`, kataloğun **tek doğru kaynağıdır** (`pg_dump` çıktısı):

- `products` tablosunun şemasını (`id` PK + 10 katalog sütunu) ve **1000 ürünlük** `INSERT`
  ifadelerini içerir. Satırlar `id = 1..N` ile sabittir → `ORDER BY id` yüklemesi embedding
  sırasını korur.

İki şekilde uygulanır:

1. **Otomatik (taze hacim):** `docker compose up` ilk kez çalıştığında dosya
   `/docker-entrypoint-initdb.d` üzerinden otomatik uygulanır; mevcut hacme dokunulmaz.
2. **Manuel yeniden seed (DESTRUCTIVE):** `backend/scripts/seed_products_postgres.py` →
   `DROP TABLE IF EXISTS products` sonrası tabloyu yeniden oluşturur (kataloğu commit'li
   anlık görüntüye sıfırlar).

> Yeni ürün eklemek için: `seed_products.sql` güncelle → DB'yi yeniden seed et → uvicorn'u
> yeniden başlat (embeddingler boot'ta yeniden hesaplanır).

### Ürün tablosu şeması

| Sütun | Tip | Açıklama |
| --- | --- | --- |
| `id` | integer (PK) | Sıra sözleşmesini sabitleyen birincil anahtar |
| `product_name` | text | Ürün adı (boş olamaz) |
| `description` | text | Açıklama |
| `main_category` | text | Ana kategori (ör. "Kişisel Bakım") |
| `sub_category` | text | Alt kategori (ör. "Saç Bakımı") |
| `target_group` | text | Hedef kitle (Kadın/Erkek/Çocuk/Unisex) |
| `product_type` | text | Ürün tipi (ör. "Kuru Şampuan") |
| `features` | text | Virgülle ayrılmış özellikler |
| `tags` | text | Virgülle ayrılmış etiketler |
| `attributes` | text | JSON string (kullanım/ortam/özellik) |
| `price` | numeric | Fiyat (TL) |

`taxonomy.csv` ise ayrı tutulur (`field`, `value`, `text`): ana/alt kategori ve ürün tipi
için Türkçe açıklama metinleridir; FAISS embedding'i bu metinlerden hesaplanır ve sorgunun
kategori eşleşmesinde kullanılır.

---

## 7. Ranking V2 ve Grouped Ranking

### Ranking V2 nedir?

> **Ranking V2:** Ürünleri yalnızca semantic similarity skoruna göre değil, kullanıcının
> **açık niyetine ne kadar doğrudan cevap verdiğine** göre de sıralayan yeni puanlama
> katmanıdır. Artık **ana sıralama sistemi**dir (`AI_MARKET_RANKING_V2=true`, varsayılan).

Çalışma mantığı (`ranking_core.finalize_ranking_v2`):

- Her sonuç ürünü bir **directness tier** (doğrudanlık katmanı) alır:
  - `DIRECT` (2): kullanıcının açık niyetine doğrudan cevap verir,
  - `RELATED` (1): aynı tip/kategori ama tam ihtiyaç değil,
  - `OTHER` (0): ilgisiz.
- Sıralama önce **tier'a** (DIRECT > RELATED > OTHER), eşitlikte mevcut **blended score**'a
  göre yapılır → doğrudan eşleşmeler en üste çıkar.
- **Rejim (regime) farkındalığı:** "browse_broad" (saf kategori gezintisi, örn. "ayakkabı
  öner") rejiminde tiering bypass edilip ürün tipi çeşitliliği korunur; "problem_broad"
  rejiminde DIRECT blok başa alınır, çeşitlilik yalnız DIRECT olmayan kuyruğa uygulanır.

> Ranking V2 yalnızca **arama sonucu listesini** yeniden sıralar/kırpar; kaynak DataFrame'i
> veya embeddingleri **asla** dokunmaz. `RANKING_V2=false` → legacy `diversify_results`
> (round-robin çeşitlendirme) davranışına dönülür.

### "En uygun ürünler" / "İlgili alternatifler" gruplaması

Sonuçlar, kullanıcı **açık bir niyet ekseni** verdiğinde (bir problem, bir ürün tipi ya da
mevsim/malzeme gibi bir modifier) iki gruba ayrılabilir:

- **primary** ("En uygun ürünler"): DIRECT tier ürünler,
- **alternative** ("İlgili alternatifler"): geri kalanlar.

Saf kategori gezintisinde (örn. "ayakkabı öner") ayıracak eksen olmadığından sonuç **flat**
kalır. `AI_MARKET_GROUPED_RANKING` flag'i ile kontrol edilir (canlı doğrulama sonrası
varsayılan **açık**):

- **Açıkken (varsayılan):** her ürün `match_group` etiketi alır; yanıta `result_grouping`,
  `primary_products`, `alternative_products` eklenir. `products` listesi yine primary-önce ve
  geriye dönük uyumlu kaldığından eski istemciler etkilenmez.
- **Kapalıyken:** bu ek alanlar üretilmez; yanıt ungrouped (düz liste) döner.

`ranking_diagnostics` tüm bu sinyalleri (tier, regime, directness skoru) yalnız **gözlem
amaçlı** bir debug alanında raporlar; sıralamayı/ürünleri değiştirmez.

---

## 8. Proje Dizin Yapısı

```
bitirmeodevi/
├── README.md                   # Kurulum + çalıştırma rehberi (clone → çalıştır)
├── docker-compose.yml          # PostgreSQL (5433) + pgAdmin (5050) servisleri
├── docs/                       # Proje dokümantasyonu (bu dosya) + arşiv
│   ├── PROJECT_OVERVIEW.md      # Güncel genel bakış (tek otoriter doküman)
│   └── archive/                # Legacy/geçmiş dokümanlar (CSV dönemi, migrasyon planı...)
│
├── backend/                    # FastAPI tabanlı arama/öneri servisi
│   ├── main.py                 # FastAPI giriş noktası; /search akışı + açılışta Ollama warm-up
│   ├── config.py               # ENV yapılandırma (DATABASE_URL zorunlu; .env otomatik yüklenir; Ollama, flag'ler)
│   ├── .env.example            # Örnek ortam dosyası (backend/.env'e kopyalanır, gitignored)
│   ├── database.py             # PostgreSQL bağlantısı + katalog SELECT (ORDER BY id, salt-okunur)
│   ├── data_loader.py          # Katalog finalize (price coerce, dropna, reset_index) + taxonomy yükleme
│   │
│   │   # --- Sorgu anlama katmanı ---
│   ├── chat_intent.py          # Kural + Ollama hybrid niyet sınıflandırıcı
│   ├── chat_memory.py          # In-memory session store + kısa follow-up birleştirme (TTL 30 dk)
│   ├── chat_normalizer.py      # Ollama tabanlı sorgu normalleştirici (+düşük güven fallback)
│   ├── query_parser.py         # Normalize sorguyu yapısal alanlara ayırır; alias + taksonomi (FAISS)
│   ├── response_planner.py     # Deterministik mod kararı (focused/broad/clarification)
│   │
│   │   # --- Arama ve sıralama katmanı ---
│   ├── search_engine.py        # Filtreleme + embedding tabanlı semantik arama + bonus/penalty rerank
│   ├── ranking_core.py         # Ranking V2 sıralama mantığı + primary/alternative gruplama
│   ├── ranking_diagnostics.py  # Ranking davranışını gözlemlemek için debug verisi (sıralamayı değiştirmez)
│   │
│   │   # --- Yanıt ve dış servis katmanı ---
│   ├── response_rewriter.py    # Ollama ile doğal Türkçe yanıt; grounding + ikame dürüstlüğü; sıralama değiştirmez
│   ├── ollama_client.py        # /api/generate çağrısı (format=json, keep_alive); warm_up_model; graceful fallback
│   │
│   ├── taxonomy.csv            # main/sub/product_type için Türkçe semantik açıklamalar (FAISS girdisi)
│   ├── requirements.txt        # FastAPI, sentence-transformers, faiss-cpu, psycopg2, httpx, python-dotenv...
│   │
│   ├── db/
│   │   └── seed_products.sql    # 1000 ürünlük katalog seed'i (pg_dump çıktısı; tek doğru kaynak)
│   ├── scripts/
│   │   └── seed_products_postgres.py  # Mevcut DB'yi seed dosyasından yeniden doldurur (DESTRUCTIVE)
│   │
│   ├── eval/                   # Arama kalitesi regresyon harness'i (model gerektirir, API değil)
│   │   ├── gold_queries.json    # 46 sorguluk altın küme (beklenen intent/kategori/boş sonuç etiketleri)
│   │   ├── run_eval.py          # Gold-set benchmark koşucusu (--show-failures, --output-json)
│   │   ├── stress_queries_*.json# Geniş stress sorgu kümesi (şu an 100 sorgu)
│   │   ├── run_stress_eval.py   # Stress benchmark koşucusu
│   │   └── results/             # Karşılaştırma çıktıları (JSON)
│   │
│   ├── manual/                 # Canlı API'ye karşı manuel regresyon harness'i (Ollama non-deterministik)
│   │   ├── scenarios.py         # Tek doğru kaynak: senaryo matrisi + check sözlüğü
│   │   ├── api_queries.py       # STRICT: deterministik pass/fail, regresyonda non-zero exit
│   │   └── ollama_regression.py # WARNING-only: Ollama'ya duyarlı kontroller, her zaman 0 exit
│   │
│   └── tests/                  # Deterministik pytest testleri (CI'de güvenli; pytest.ini yalnız tests/)
│       ├── test_query_parser.py        # Fiyat/kategori/feature/context çıkarımı
│       ├── test_response_planner.py     # Mod kararı
│       ├── test_search_engine.py        # Filtre + bonus/penalty skorlama
│       ├── test_ranking_core.py         # Directness tier / regime / gruplama
│       ├── test_ranking_v2_regression.py# Ranking V2 sıralama regresyon kilidi
│       ├── test_ranking_diagnostics.py  # Gözlem amaçlı sinyaller
│       ├── test_ranking_grouping.py     # primary/alternative gruplama
│       ├── test_grouped_examples.py     # Gruplama örnek senaryoları
│       ├── test_chat_intent.py          # Niyet sınıflandırma kuralları
│       ├── test_data_loader_db.py       # DB yükleme + finalize
│       ├── test_seed_sql.py             # seed_products.sql bütünlüğü
│       ├── test_eval_harness.py         # Eval yardımcıları
│       └── fixtures/                    # Test sabitleri (örn. örnek ürün CSV'si)
│
└── frontend/                   # React 19 + Vite 8 vitrin (React Compiler etkin)
    ├── index.html              # SPA giriş HTML'i
    ├── package.json            # Bağımlılıklar ve scriptler (dev/build/lint)
    ├── vite.config.js          # Vite yapılandırması
    ├── public/                 # Statik dosyalar (favicon.svg, icons.svg)
    └── src/
        ├── main.jsx            # React kök render
        ├── App.jsx             # Sayfa kompozisyonu: Header, HeroBanner, Categories, FeaturedProducts, Footer, Chatbot
        ├── App.css / index.css # Saf CSS (framework yok)
        ├── assets/             # Görseller: hero.png, products/*.jpg, react.svg, vite.svg
        └── components/
            ├── Header.jsx          # Üst bar + arama formu (chatbot'a sorgu gönderir)
            ├── HeroBanner.jsx      # Ana banner + CTA
            ├── Categories.jsx      # Kategori kartları (tıklayınca chatbot açıp sorgu gönderir)
            ├── FeaturedProducts.jsx# Statik öne çıkan ürünler
            ├── Footer.jsx          # Alt bilgi
            └── Chatbot.jsx         # Sohbet arayüzü + ürün kartı render akışı; /search çağırır
```

---

## 9. Test ve Doğrulama Altyapısı

Üç katmanlı bir doğrulama yapısı vardır: deterministik birim testler, canlı manuel
regresyon ve arama kalitesi eval'i.

### Birim/Entegrasyon Testleri (pytest — deterministik, CI'de güvenli)

`backend/tests/` altındaki testler Ollama'ya bağımlı değildir (bkz. Bölüm 8'deki dosya
açıklamaları).

```bash
cd backend
./.venv/bin/python -m pytest tests/        # pytest.ini yalnız tests/ klasörünü toplar
```

### Manuel Regresyon (canlı API'ye karşı, pytest dışında)

Ollama non-deterministik olduğu için **canlı çalışan bir API'ye** karşı koşulur. Senaryolar
tek kaynaktan (`manual/scenarios.py`) gelir:

```bash
./.venv/bin/python -m manual.api_queries        # STRICT: regresyonda non-zero exit
./.venv/bin/python -m manual.ollama_regression  # WARNING-only: her zaman 0 exit
```

### Eval / Stress Eval (arama kalitesi regresyonu)

Model gerektirir (API sunucusu değil). Parser/ranking değişikliği sonrası aynı komut tekrar
koşulup JSON çıktıları karşılaştırılır.

```bash
./.venv/bin/python eval/run_eval.py --show-failures --output-json eval/results/baseline.json
./.venv/bin/python eval/run_stress_eval.py
```

- **Gold set** (`gold_queries.json`, **46 sorgu**): beklenen intent/kategori/ürün tipi veya
  `expects_clarification` / `expects_empty_result` etiketleriyle relevance ölçümü.
- **Stress set** (şu an **100 sorgu**): geniş sorgu yelpazesiyle dayanıklılık ölçümü.

---

## 10. Çalıştırma Adımları

### 1) Veritabanı (PostgreSQL + pgAdmin)

```bash
docker compose up -d           # postgres → host 5433, pgadmin → 5050
# Taze hacim seed_products.sql ile otomatik dolar.
# Mevcut DB'yi yeniden seed etmek (DESTRUCTIVE):
cd backend && ./.venv/bin/python scripts/seed_products_postgres.py
```

### 2) Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # DATABASE_URL'i içerir; açılışta otomatik yüklenir (python-dotenv)
# (Opsiyonel) Ollama: ollama serve && ollama pull gemma3:4b
uvicorn main:app --reload      # http://127.0.0.1:8000
```

İlk açılışta sentence-transformers modeli yüklenir + 1000 ürün embed'lenir (birkaç saniye);
Ollama açıksa LLM modeli de arka planda **warm-up** edilir (ilk sorgu hızlı gelsin diye).
Konsolda "AI-Market API hazır." görünür.

### 3) Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

---

## 11. Ortam Değişkenleri

`backend/config.py` tüm değişkenleri ENV'den okur. **`DATABASE_URL` dışındaki** hepsinin
güvenli bir varsayılanı vardır. Açılışta `backend/.env` (varsa) `python-dotenv` ile otomatik
yüklenir; gerçek shell/CI/docker ENV değerleri yine önceliklidir.

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `DATABASE_URL` | **(zorunlu, varsayılan yok)** | PostgreSQL libpq URI. Eksikse açılış durur (CSV fallback yok). |
| `PRODUCTS_TABLE` | `products` | Ürün tablosu adı (operatör kontrolünde). |
| `AI_MARKET_MODEL_NAME` | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-Transformers modeli. |
| `AI_MARKET_TAXONOMY_CSV` | `taxonomy.csv` | Taksonomi metni yolu. |
| `AI_MARKET_TOP_K` | `5` | `/search` yanıtındaki ürün sayısı. |
| `AI_MARKET_TAXONOMY_MATCH_THRESHOLD` | `0.65` | Taksonomi semantic eşleşme eşiği. |
| `AI_MARKET_RANKING_V2` | `true` | Ranking V2 (directness tier sıralaması). `false` → legacy. |
| `AI_MARKET_GROUPED_RANKING` | `true` | primary/alternative gruplamasını API/UI'a açar (varsayılan açık). `false` → ungrouped yanıt. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP adresi. |
| `OLLAMA_MODEL` | `gemma3:4b` | Kullanılacak Ollama model. 10 GB GPU'ya backend embedding modeliyle birlikte sığar; 12b CPU'ya taşar (bkz. Bölüm 12). |
| `OLLAMA_ENABLED` | `true` | `false` → pipeline tamamen kuralcı çalışır. |
| `OLLAMA_TIMEOUT_SECONDS` | `15` | Tek çağrı timeout'u. |
| `OLLAMA_CONFIDENCE_THRESHOLD` | `0.6` | Altında Ollama çıktısı reddedilir. |
| `OLLAMA_WARMUP` | `true` | Açılışta modeli arka planda VRAM'e yükler (ilk sorgu hızlı). |
| `OLLAMA_KEEP_ALIVE` | `10m` | Modelin istek sonrası bellekte kalma süresi (`"1h"`, `"-1"` = süresiz). |
| `VITE_API_URL` (frontend) | `http://127.0.0.1:8000/search` | Build-time, public. Sır KOYULMAZ. |

> `docker-compose.yml` içindeki Postgres (`aimarket_user`/`aimarket_pass`) ve pgAdmin
> (`admin@example.com`/`admin123`) kimlik bilgileri yalnız yerel demo içindir; paylaşımlı/
> barındırılan bir ortamda değiştirilmelidir.

---

## 12. Bilinen Sınırlamalar

- **Auth yok.** `/search` herkese açıktır; CORS `allow_origins=["*"]`. Vitrin amaçlı bir
  bitirme projesi olduğu için kullanıcı/oturum/güvenlik katmanı eklenmemiştir.
- **Rate limit yok / sorgu uzunluğu sınırı yok.** Tek istek 3 Ollama çağrısına kadar
  fan-out yapabilir; bu bir hesaplama yükü yüzeyidir.
- **`session_id` doğrulanmaz.** İstemcinin verdiği string olduğu gibi güvenilir kabul
  edilir; içerikte PII tutulmaz, etki düşüktür.
- **Single-process.** Session store ve embeddingler tek uvicorn prosesinde tutulur;
  ölçekleme için paylaşımlı index/önbellek gerekir.
- **Ollama dışsal bağımlılık.** Servis yoksa pipeline çalışır ama normalleştirme ve doğal
  yanıt yazma devre dışı kalır; cevap kalitesi şablon seviyesine düşer.
- **Ollama modeli bilinçli olarak `gemma3:4b`.** 4b ve 12b karşılaştırıldı; 12b 10 GB GPU'ya
  backend embedding modeliyle birlikte sığmayıp CPU'ya taştığından çok yavaşladı ve halüsinasyon
  açısından bir avantaj sağlamadı, bu yüzden 4b tercih edildi.
- **İkame dürüstlüğü model-bağımsız ama yumuşak.** Kategori bulunamadığında deterministik guard
  cümleyi garanti eder; ancak küçük modelin (4b) koşullu kurallara her zaman tam uymaması
  nedeniyle bu guard'a dayanılır.
- **Stress eval dosyası şu an 100 sorgu** içerir (dosya adı `_1000` olsa da).
- **Ürün görselleri gerçek katalog görseli değildir.** Kartlarda kategoriye göre emoji
  kullanılır (FeaturedProducts gibi statik bölümlerde örnek jpg'ler vardır).

---

## 13. Sonraki Geliştirme Fikirleri

1. **Grouped ranking UI cilası:** Gruplama artık varsayılan açık; sıradaki adım "En uygun /
   İlgili alternatifler" başlıklarını ve boş-grup durumlarını arayüzde daha da iyileştirmek.
2. **Türkçe-özel model A/B'si:** Gerekirse Türkçe fine-tuned bir modeli (ör. Turkish-Gemma-9B
   Q4) yalnızca üslup kalitesi için A/B'ye sokmak. Grounding prompt'u model-bağımsız olduğundan
   halüsinasyon riski düşük; 4b varsayılan hız/VRAM için korunur.
3. **Rate limiting + sorgu uzunluğu sınırı:** `/search` önüne basit bir hız sınırı koymak.
4. **CORS daraltma:** `allow_origins=["*"]` yerine bilinen frontend origin'lerini whitelist'lemek.
5. **Stress eval'i gerçekten 1000 sorguya çıkarmak** ve CI'de düzenli koşmak.
6. **Gerçek ürün görselleri** ve fiyat/stok güncelliği için yönetim arayüzü.
7. **Kalıcı oturum/öneri geçmişi:** in-memory session yerine (gerekirse) hafif bir kalıcı katman.

---

## Ek: Hızlı Yönelim Rehberi

| Soru | Nereye bakılır |
| --- | --- |
| API uçları neler? | `backend/main.py` (yalnız `GET /` ve `POST /search`) |
| Ürün verisi nereden geliyor? | `backend/database.py` + `backend/db/seed_products.sql` (PostgreSQL) |
| Bir sorgu nasıl parse ediliyor? | `backend/query_parser.py::parse_query` |
| Mod kararı nerede? | `backend/response_planner.py::build_response_plan` |
| Semantik skorlama formülü? | `backend/search_engine.py::semantic_search` |
| Ranking V2 / gruplama? | `backend/ranking_core.py` (`finalize_ranking_v2`, `compute_grouping`) |
| Ollama prompt'ları? | `chat_intent.py`, `chat_normalizer.py`, `response_rewriter.py` |
| Yeni ürün eklemek? | `seed_products.sql` güncelle → DB'yi yeniden seed et → uvicorn restart |
| Sohbet UI'si / grup görünümü? | `frontend/src/components/Chatbot.jsx` |
| Otomatik testler? | `backend/tests/` (pytest), `backend/eval/` (gold/stress), `backend/manual/` (canlı) |
```

# 🎓 Sunum Teknik Savunma Rehberi — AI-Market Chatbot

> Bu doküman, bitirme sunumunda hocaların sorabileceği teknik soruları rahatça
> cevaplaman için hazırlandı. Her sınıfın ne işe yaradığını, FAISS/embedding
> mantığını, bir sorgunun baştan sona yol haritasını ve sık sorulan soruların
> hazır cevaplarını içerir.
>
> **Tek cümlelik özet:** Kullanıcı doğal Türkçe yazar → sistem niyeti anlar →
> (gerekirse LLM ile temizler) → kuralcı parser yapısal sorguya çevirir →
> embedding tabanlı semantik arama + filtre + skorlama yapar → sonuçları
> doğrudanlık (directness) sırasına dizer → LLM ile doğal bir cevap metni yazar.
> **Ürünleri her zaman kod seçer; LLM asla ürün/fiyat uydurmaz.**

---

## 0. 30 saniyede sistem (sahne arkası)

| Katman | Teknoloji | Görevi |
|---|---|---|
| Frontend | React 19 + Vite | Sohbet arayüzü, ürün kartları |
| Backend | FastAPI (Python) | `POST /search` tek endpoint, tüm orkestrasyon |
| Veritabanı | PostgreSQL | 1000 ürünlük katalog (salt-okunur, açılışta belleğe) |
| Anlamsal arama | sentence-transformers + FAISS + NumPy | 384 boyutlu embedding, cosine benzerlik |
| LLM | Ollama + `gemma3:4b` | Sadece **normalleştirici** ve **yazıcı** (üretici değil) |

---

## 1. Temel kavramlar (en çok sorulanlar)

### 1.1. Embedding (vektör gömme) nedir?
Bir metni, anlamını temsil eden bir **sayı dizisine (vektör)** çevirmektir. Bu projede
her ürün ve her sorgu **384 boyutlu** bir vektöre dönüştürülür. Anlamca yakın metinler
vektör uzayında birbirine yakın olur. Örneğin "powerbank" ile "taşınabilir şarj"
vektörleri birbirine yakındır; bu yüzden kelimeler birebir aynı olmasa da eşleşirler.

- **Model:** `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers).
- **Neden bu model?** Çok dilli (Türkçe dahil), hafif ve hızlı. Çıktısı 384 boyut.

### 1.2. Semantik arama nedir, klasik aramadan farkı?
Klasik arama **kelime eşleşmesi** yapar ("şampuan" yazmazsan şampuanı bulamaz).
Semantik arama **anlam eşleşmesi** yapar. Kullanıcı "saçım dökülüyor" der, ürün
adında "dökülme" geçmese bile "Saç Güçlendirici Serum" anlamca yakın olduğu için bulunur.

### 1.3. Cosine benzerliği ve `normalize_L2` neden var?
İki vektörün benzerliği **cosine similarity** (kosinüs benzerliği) ile ölçülür:
aralarındaki açının kosinüsü. 1'e yakınsa çok benzer, 0'a yakınsa alakasız.

- **Püf nokta:** Bir vektörü **L2-normalize** edersek (boyunu 1 yaparsak), iki normalize
  vektörün **nokta çarpımı (dot product) = cosine benzerliği** olur. Yani normalize
  ettikten sonra benzerlik tek bir çarpma işlemiyle hesaplanır — çok hızlı.
- Kodda bunu `faiss.normalize_L2(...)` yapar; benzerlik ise `np.dot(...)` ile hesaplanır.

### 1.4. FAISS ne için kullanılıyor? (DİKKAT — dürüst cevap)
FAISS, Facebook'un milyonlarca vektörde hızlı benzerlik araması için yazdığı bir
kütüphanedir. **Bu projede FAISS'i iki amaçla kullanıyoruz:**
1. **Vektör normalizasyonu** (`faiss.normalize_L2`) — vektörleri birim uzunluğa getirir.
2. Benzerlik hesabını ise katalog **1000 ürün** olduğu için **NumPy nokta çarpımı ile
   tam (brute-force/exact) cosine** olarak yapıyoruz — yani yaklaşık (ANN) index değil.

> **Hoca "hangi FAISS index'ini kullandın?" derse:** "1000 ürünlük katalogda tam
> (exact) cosine araması milisaniyeler sürdüğü için FAISS'in yaklaşık index'lerine
> (IndexIVFFlat gibi) gerek kalmadı; FAISS'ten vektör normalizasyonunu kullanıp
> benzerliği L2-normalize edilmiş vektörlerin nokta çarpımıyla hesaplıyorum. Katalog
> on binlere çıksaydı `IndexFlatIP` ya da `IndexIVFFlat`'e geçiş tek satırlık bir
> değişiklik olurdu." Bu hem doğru hem de ölçeklenebilirlik bilincini gösterir.

### 1.5. `taxonomy.csv` ne işe yarar?
Katalogdaki ürün satırlarından ayrı, küçük bir **kategori sözlüğüdür**. Üç sütunu var:
`field, value, text`.

```
field,value,text
main_category,Kamp,kamp outdoor doğa çadır kamp ekipmanı kamp malzemeleri açık hava
main_category,Elektronik,elektronik bilgisayar kulaklık mouse klavye akıllı saat powerbank şarj
sub_category,Saç Bakımı,saç bakımı şampuan saç kremi serum saç dökülmesi kepek kuru saç yağlı saç
```

- `field`: bu satır bir ana kategori mi, alt kategori mi, ürün tipi mi?
- `value`: katalogdaki gerçek kategori adı (ör. "Kamp").
- `text`: o kategoriyi **anlatan zengin Türkçe açıklama** (eş anlamlılar, kullanım alanları).

**Amacı:** Sorguyu doğru kategoriye **anlamsal olarak** oturtmak. Kullanıcı "açık havada
uyuyacağım" dediğinde hiçbir kelime "Kamp" değildir; ama bu cümlenin embedding'i
`taxonomy.csv`'deki Kamp açıklamasının embedding'ine yakın olduğu için kategori "Kamp"
olarak bulunur. Yani taxonomy.csv, **doğal dil ↔ katalog kategorisi köprüsüdür.**

> Ürünlerin kendisi PostgreSQL'de; taxonomy.csv yalnızca kategori eşleştirme metinleridir.

### 1.6. Neden LLM (Ollama) + neden "halüsinasyon yok"?
LLM bu projede **iki dar görevde** kullanılır ve **asla ürün üretmez:**
1. **Normalleştirici:** Argo/yazım hatalı/dolaylı cümleyi temiz aramaya çevirir
   ("papuç lazım" → "ayakkabı"). Prompt'ta ürün/fiyat/marka uydurmak **yasak**.
2. **Yazıcı (rewriter):** Bulunan ürünlerden doğal bir Türkçe cevap cümlesi yazar.

Ürün listesini, fiyatları ve sıralamayı **her zaman deterministik kod seçer.** LLM erişilemese
bile sistem kuralcı yoldan çalışır (`template` cevap döner), `/search` asla 500 hatası vermez.
Bu, "LLM uydurursa?" sorusuna karşı tasarımın temel güvencesidir.

---

## 2. Sınıf / Modül Sözlüğü (soldaki dosyaların hepsi)

Her madde: **ne işe yarar → anahtar fonksiyon/içerik → hoca sorarsa vurgu.**

### `main.py` — Orkestra şefi (FastAPI giriş noktası)
- **Ne yapar:** Tek endpoint `POST /search`. Tüm katmanları sırayla çağırır ve JSON döndürür.
  Açılışta: embedding modelini yükler, 1000 ürünü PostgreSQL'den çeker, embedding'leri üretir,
  taxonomy embedding'lerini hazırlar, Ollama modelini arka planda "warm-up" eder.
- **Anahtar:** `search_products()` — 13 aşamalı akış (Bölüm 4). `lifespan` — açılış warm-up.
- **Hoca sorarsa:** "Embedding'ler istek başına değil, **bir kez açılışta** hesaplanır;
  her arama hazır vektörler üzerinde çalışır, bu yüzden hızlıdır."

### `config.py` — Ayar merkezi
- **Ne yapar:** Tüm ayarları ortam değişkenlerinden (`.env`) okur. `DATABASE_URL` zorunlu,
  gerisinin güvenli varsayılanı var (model adı, TOP_K=5, Ollama ayarları, flag'ler).
- **Hoca sorarsa:** "Kod değiştirmeden davranışı `.env` ile değiştirebiliyorum; örn.
  `OLLAMA_ENABLED=false` ile sistem tamamen kuralcı çalışır."

### `database.py` — PostgreSQL erişimi
- **Ne yapar:** `SELECT ... FROM products ORDER BY id` ile tüm kataloğu çeker (psycopg2).
- **Kritik nokta:** `ORDER BY id` **kozmetik değil zorunludur** — embedding sırası buna bağlı
  (aşağıdaki "sıra sözleşmesi").
- **Hoca sorarsa:** "İstek başına SQL atmıyorum; katalog açılışta bir kez belleğe (pandas
  DataFrame) yükleniyor."

### `data_loader.py` — Katalog + taxonomy yükleme
- **Ne yapar:** DB'den gelen veriyi sonlandırır: fiyatı sayıya çevirir, eksik satırları atar,
  `reset_index(drop=True)` ile **0..N-1 sabit konumsal indeks** verir. Ayrıca `taxonomy.csv`'yi okur.
- **Kritik nokta (Sıra Sözleşmesi):** `product_embeddings[i]`, DataFrame'in `i`. satırına
  karşılık gelir. Yükleme sonrası DataFrame **asla yeniden sıralanmaz**, yoksa arama yanlış
  ürün döndürür. `ORDER BY id` → `reset_index` → embedding'ler bu sıradan üretilir.

### `chat_intent.py` — Niyet sınıflandırıcı
- **Ne yapar:** Mesajı türe ayırır: `greeting / help / thanks / goodbye / wellbeing /
  product_search / nonsense`. Önce **deterministik kural** (kelime/regex), ürün sinyali
  varsa direkt aramaya gider; yalnız çok kısa/belirsiz mesajda Ollama'ya danışır.
- **Neden var:** "Merhaba" gibi mesajlar **arama pipeline'ına hiç girmeden** anında cevaplanır
  → düşük gecikme.
- **Hoca sorarsa:** "Niyet tespiti hibrit: hız için kural, belirsizlikte LLM."

### `chat_memory.py` — Oturum hafızası
- **Ne yapar:** Bellekte (dict) basit oturum tutar (TTL 30 dk). Bir netleştirme sorusu
  sorulduysa, kullanıcının **kısa cevabını** ("kadın", "200 TL altı") önceki sorguyla
  **birleştirir** → kullanıcı kendini tekrar etmez.
- **Hoca sorarsa:** "Redis/DB yok; tek-proses demo için bellekte yeterli. Kısa mesaj +
  bekleyen netleştirme = takip cevabı; uzun/yeni mesaj birleştirilmez."

### `chat_normalizer.py` — LLM tabanlı sorgu normalleştirici
- **Ne yapar:** Ollama ile dağınık cümleyi temiz aramaya çevirir. Düşük güven (`confidence <
  0.6`) veya hata → **orijinal sorguya döner**. Prompt: ürün/fiyat/marka uydurmak yasak;
  hayali ürünleri (zaman makinesi vb.) gerçek kategoriye bağlamak yasak.
- **Hoca sorarsa:** "LLM çıktısına körü körüne güvenmiyorum; bir güven eşiği ve `main.py`'de
  ek guard'lar var (kategori düşürürse/değiştirirse kullanıcının kelimelerine dönerim)."

### `query_parser.py` — Kuralcı yapısal ayrıştırıcı (sistemin beyni)
- **Ne yapar:** Sorguyu yapısal alanlara böler: `main_category, sub_category, product_type,
  target_group, features, contexts, min/max_price, taxonomy_match, excluded_terms,
  explicit_intent`. Üç teknikle:
  1. **Fiyat regex'i** (`extract_price_range`): "1500 altında", "1000-2000 arası", "civarı" (±%30).
  2. **Alias kuralları** (`QUERY_ALIASES`): deterministik eşlemeler ("dokunmatik kalem" →
     Elektronik › Tablet Kalemi; "robot süpürge" → Ev & Yaşam).
  3. **Semantik taxonomy eşleşmesi** (`semantic_taxonomy_match`): taxonomy.csv embedding'leri
     ile cosine; eşik üstündeyse kategori atanır.
- **Fast-path detektörler (Ollama'sız bile çalışır):** "şarjım bitiyor" → Powerbank;
  "saçım dökülüyor" → Saç Bakımı; "kampta yemek" → Kamp › Pişirme; "yoga matı"; çocuk alışverişi.
- **Negatif kısıt** (`extract_excluded_terms`): "mont veya kaban değil" → bu kategorileri eler.
- **Çekim-duyarlı eşleşme** (`contains_term`): "elbisesi/elbiseleri" gibi Türkçe ekleri tanır.
- **Hoca sorarsa:** "LLM kapalı olsa bile kritik niyetler bu kuralcı katmanda garanti; LLM
  sadece dili temizliyor, kararı parser veriyor."

### `response_planner.py` — Mod kararı (saf kural, LLM yok)
- **Ne yapar:** `parsed_query`'ye bakıp **modu** seçer:
  `clarification_only` (bilgi yetersiz) / `focused_search` (net ürün tipi) /
  `broad_search` (kategori geneli, çeşitlendir + takip sorusu) / `chat_reply` / `no_result`.
  Ayrıca "kullanıcı yeterli detay verdi mi?" kararını **orijinal** kelimelere göre verir.
- **Hoca sorarsa:** "Mod kararı deterministik ve test edilebilir; LLM çağırmaz → gecikme yok."

### `search_engine.py` — Filtreleme + semantik arama + skorlama
- **Ne yapar (3 parça):**
  1. `apply_filters`: aday havuzunu daraltır. **Fiyat tek sert filtre**; kategori/cinsiyet
     filtreleri sonucu fazla daraltırsa "boş dönmemek" için yumuşak fallback yapar.
  2. `semantic_search`: cosine benzerlik + **bonus/penalty rerank** (doğru tip/kategori/cinsiyet
     bonus; ters cinsiyet/yanlış tip penalty). Anlamsız sorgu için **eşik** (skor < 0.40 → boş).
  3. `build_answer` / `diversify_results`: şablon cevap ve (legacy) çeşitlendirme.
- **Skor formülü:** `final = cosine + bonus − penalty`, `match% = clamp(final×80, 35, 99)`.
- **Hoca sorarsa:** Bkz. Bölüm 3 (skorlama detayı).

### `ranking_core.py` — Ranking V2 (doğrudanlık sıralaması) + gruplama
- **Ne yapar:** Skorlanmış sonuçları, kullanıcının **açık niyetine ne kadar doğrudan cevap
  verdiklerine** göre yeniden dizer. Her ürün bir **tier** alır:
  `DIRECT(2) > RELATED(1) > OTHER(0)`. Sıralama önce tier'a, eşitlikte skora göre.
- **Rejim farkındalığı:** `browse_broad` (saf "ayakkabı öner") → çeşitlilik korunur;
  `problem_broad` (ör. "saç dökülmesi için ürün") → DIRECT blok başa.
- **Gruplama:** `primary` ("En uygun ürünler") = DIRECT; `alternative` ("İlgili alternatifler")
  = geri kalan. Ayıracak eksen yoksa liste `flat` kalır.
- **Kritik:** Yalnızca **sonuç listesini** sıralar/kırpar; kaynak DataFrame'i/embedding'leri
  asla değiştirmez.

### `ranking_diagnostics.py` — Gözlem katmanı (observe-only)
- **Ne yapar:** Ranking V2'nin kararlarını (tier, regime, directness skoru) bir **debug
  alanında** raporlar. **Sıralamayı/ürünleri asla değiştirmez** — doğrulama/izleme içindir.

### `response_rewriter.py` — LLM ile doğal cevap yazımı
- **Ne yapar:** Bulunan ürünlerden samimi Türkçe `answer` metni yazar. Yalnızca ürünün
  **gerçek alanlarından** (tags/description) bahseder. Hata olursa `build_answer` şablonu döner.
- **İki güvence:** (1) Olmayan özelliği (ör. "su geçirmez") iddia etmek yasak; (2) kategori
  ikamesi olduğunda (`detect_unavailable_category`) dürüstçe söyler — model söylemezse
  deterministik guard cümleyi kendi ekler. Hayali ürün/sonuç-yok cevabı LLM'e **verilmez**
  (uydurmasın diye sabit metin).

### `ollama_client.py` — LLM HTTP istemcisi
- **Ne yapar:** Ollama `/api/generate`'e istek atar (`format=json`, `keep_alive`). **Her
  hatada `None` döner** → çağıran katman fallback yapar. `warm_up_model()` açılışta modeli
  VRAM'e yükler (ilk sorgu hızlı gelsin diye).

### `taxonomy.csv` ve `db/seed_products.sql`
- `taxonomy.csv`: kategori eşleştirme metinleri (Bölüm 1.5).
- `seed_products.sql`: 1000 ürünlük kataloğun **tek doğru kaynağı** (pg_dump). `id = 1..N`
  sabit → `ORDER BY id` embedding sırasını korur. Docker ilk açılışta otomatik uygular.

---

## 3. Semantik arama + skorlama (formül detayı)

`search_engine.semantic_search` adım adım:

1. **Sorgu vektörü:** `query_vector = model.encode([query])` → `faiss.normalize_L2`.
2. **Aday embedding'leri:** `product_embeddings[candidate_df.index]` (konumsal indeksleme —
   sıra sözleşmesi sayesinde doğru).
3. **Cosine skor:** `scores = np.dot(candidate_embeddings, query_vector)` (normalize edilmiş
   vektörlerde nokta çarpımı = cosine).
4. **Bonus / Penalty rerank** (her aday için):

| Sinyal | Bonus | Penalty |
|---|---|---|
| Ürün tipi tam/explicit eşleşme | +0.05 … +0.22 | yanlış tip −0.15 |
| Ana kategori eşleşme | +0.04 | uyumsuz −0.10 |
| Alt kategori eşleşme | +0.05 | — |
| Hedef kitle eşleşme | +0.08 | **ters cinsiyet −0.30** |
| Taxonomy eşleşme | +0.06 | — |
| Her feature eşleşmesi | +0.10 | — |
| Her context eşleşmesi | +0.03 | — |

5. **Nihai skor:** `final = cosine + bonus − penalty`. Eşleşme yüzdesi `clamp(round(final×80), 35, 99)`.
6. **Anlamsızlık eşiği:** Hiç sert filtre yoksa (kategori/tip/taxonomy) ve en yüksek skor
   **< 0.40** ise → **boş döner** ("uzay mekiği" gibi sorgular ürün uydurmasın diye).
7. **Kırpma:** `head(top_k)`. (Ranking V2/çeşitlendirme açıkken havuz daha geniş çekilir:
   `max(TOP_K×4, 20)`, böylece yeniden sıralayıcıya yeterli malzeme kalır.)

> **Neden sadece cosine yetmiyor?** Embedding cinsiyeti/tam ürün tipini bazen karıştırır
> (kadın vs erkek ayakkabı çok benzer vektör). Bonus/penalty bu **yapısal** sinyalleri
> ekleyerek "anlamca yakın ama yanlış" sonuçları aşağı iter.

---

## 4. BİR SORGUNUN YOL HARİTASI (uçtan uca)

Somut örnek: **`yağlı saç için şampuan öner`**

```
KULLANICI: "yağlı saç için şampuan öner"
        │
        ▼
[main.py /search]  ── session al/oluştur (chat_memory)
        │
        ▼
1) chat_intent.classify_intent
   "şampuan/öner" ürün sinyali var → intent = product_search
        │
        ▼
2) _is_vague_query?  (sadece "ürün öner" gibi mi?)  → HAYIR (şampuan somut)
        │
        ▼
3) chat_memory.resolve_follow_up  → bekleyen netleştirme yok, sorgu aynen kalır
        │
        ▼
4) chat_normalizer.normalize_query (Ollama)
   "yağlı saç için şampuan öner" → "yağlı saç için şampuan" (conf 0.9, used=true)
   [Ollama kapalıysa: orijinal sorgu kullanılır — guard'lar devrede]
        │
        ▼
5) query_parser.parse_query
   - fiyat: yok
   - fast-path is_hair_care_request? → "şampuan" geçtiği için product_type="Şampuan",
     main="Kişisel Bakım", sub="Saç Bakımı"
   - features: extract_features("yağlı saç") → ["yağlı saç","yağ dengeleyici"]
   → parsed_query = {main: Kişisel Bakım, sub: Saç Bakımı, product_type: Şampuan,
                     features: [...], excluded_terms: []}
        │
        ▼
   (4b guard) Normalize kategoriyi düşürmedi/değiştirmedi → olduğu gibi devam
        │
        ▼
6) response_planner.build_response_plan
   product_type var → mode = FOCUSED_SEARCH (çeşitlendirme yok, takip sorusu opsiyonel)
        │
        ▼
7) clarification kontrolü → mode focused olduğu için atlanır, ürünlere geç
        │
        ▼
8) search_engine.apply_filters
   Saç Bakımı + Şampuan havuzu süzülür (fiyat yok). Negatif kısıt yok.
        │
        ▼
9) search_engine.semantic_search   ◄── FAISS/embedding burada
   - "yağlı saç için şampuan" → 384-boyut vektör → normalize_L2
   - aday şampuanların embedding'leri ile np.dot → cosine skorları
   - bonus: product_type "Şampuan" eşleşme +; feature "yağ dengeleyici" +0.10 ...
   - yağlı saç şampuanları en üste; top_k (geniş havuz) seçilir
        │
        ▼
10) ranking_core.finalize_ranking_v2
    regime = focused. "yağlı" şampuanlar DIRECT(2), genel şampuanlar RELATED(1)
    → DIRECT önce. Gruplama: primary = yağlı şampuanlar, alternative = diğerleri
        │
        ▼
11) ranking_diagnostics  → tier/regime debug alanına yazılır (sıralamaya dokunmaz)
        │
        ▼
12) response_rewriter.rewrite_response (Ollama)
    Ürünlerin gerçek tags/description'ından doğal cevap:
    "Yağlı saç sorununa yönelik şampuan seçeneklerini listeledim..."
    [Ollama kapalı/hata → build_answer şablonu]
        │
        ▼
13) chat_memory.update_session + JSON döndür
    { answer, products[5], result_grouping, parsed_query, response_mode, ... }
        │
        ▼
FRONTEND (Chatbot.jsx): answer + ürün kartları (primary/alternative) render
```

### İkinci örnek — dolaylı anlatım: `telefonum hemen bitiyor`
- 1) intent = product_search.
- 4) Normalizer: "telefon için powerbank" (veya kapalıysa fast-path devrede).
- 5) **`is_power_depletion_complaint` fast-path** taxonomy'den önce devreye girer →
  `main=Elektronik, product_type=Powerbank`. (Aksi halde "şarj" kelimesi "Araç Şarj
  Cihazı"na kayardı — bu kural onu engeller.)
- 9) Powerbank havuzunda semantik arama → 5 powerbank.
- 12) "Telefonunuzun şarj sorununa powerbank önerdim..." → ✅ doğru ürün, ürün adı söylenmeden.

### Üçüncü örnek — hayali ürün: `görünmezlik pelerini almak istiyorum`
- 4) Normalizer prompt'u hayali ürünü gerçek kategoriye bağlamayı **yasaklar**, düşük conf.
- 5) Parser hiçbir kategori sinyali bulamaz; 9) semantik skor eşiğin (0.40) altında → **boş**.
- 12) Sonuç-yok için **sabit metin** ("Bu ürün katalogda bulunmuyor") — LLM'e
  verilmez → **uydurma yok.** ✅

---

## 5. Sık sorulan hoca soruları + hazır cevaplar

**S: Yapay zeka ürün uydurabilir mi?**
C: Hayır. LLM sadece girdiyi temizler ve çıktı cümlesini yazar. Ürün listesini her zaman
katalogdan deterministik kod seçer. LLM kapalıyken bile sistem çalışır.

**S: Türkçe'yi nasıl anlıyor?**
C: Çok dilli embedding modeli (`MiniLM-L12-v2`) Türkçe metni vektöre çeviriyor; ayrıca
Türkçe çekim eklerini tanıyan kurallar ve ASCII-katlama (ç→c, ş→s...) var.

**S: Embedding'i her aramada mı hesaplıyorsun?**
C: Hayır. 1000 ürünün embedding'i **açılışta bir kez** hesaplanıp bellekte tutulur; her
aramada sadece sorgunun vektörü hesaplanıp hazır matrisle çarpılır.

**S: FAISS index'i ne? Neden ANN kullanmadın?**
C: 1000 üründe tam cosine araması zaten milisaniyeler sürüyor; FAISS'ten normalizasyonu
kullanıp benzerliği nokta çarpımıyla hesaplıyorum. Ölçek büyürse `IndexFlatIP`/`IVF`'e
geçiş tek satır.

**S: Cosine skoru tek başına yetmiyor mu, bonus/penalty neden?**
C: Embedding "kadın/erkek ayakkabı" gibi yapısal ayrımları karıştırabiliyor; bonus/penalty
katmanı doğru kategori/tip/cinsiyeti ödüllendirip yanlışı cezalandırarak isabeti artırıyor.

**S: "ürün öner" gibi belirsiz sorguda ne olur?**
C: Ürün uydurmaz; netleştirme sorusu sorar ("Kategori/amaç/bütçe yazar mısın?").

**S: Fiyat filtresi garanti mi?**
C: Evet, fiyat **tek sert filtredir**; her dönen ürün sınıra uyar. (Demoda gösterilebilir.)

**S: taxonomy.csv olmasa ne olurdu?**
C: Doğal dildeki ihtiyacı katalog kategorisine bağlamak çok zorlaşırdı; "açık havada
uyuyacağım" → "Kamp" eşleşmesi taxonomy köprüsü sayesinde oluyor.

**S: Ranking V2 ne kazandırdı?**
C: Sadece anlam benzerliği değil, kullanıcının açık niyetine **doğrudan** cevap veren ürünleri
öne alıyor; sonuçları "En uygun" / "İlgili alternatifler" diye ayırabiliyor.

**S: Veritabanı bağlantısı kopsa?**
C: Katalog açılışta yükleniyor; `DATABASE_URL` yoksa uygulama **bilerek açılmıyor** (eksik
katalogla yanlış sonuç vermektense durmak daha güvenli).

**S: Ölçeklenebilir mi / sınırlar?**
C: Tek-proses demo; oturum ve embedding bellekte. Büyütmek için: gerçek FAISS index,
paylaşımlı oturum (Redis), rate-limit. (PROJECT_OVERVIEW Bölüm 12'de dürüstçe listeli.)

---

## 6. Test altyapısı (sorulursa)

- **pytest** (`backend/tests/`): deterministik birim testler (parser, planner, skorlama,
  ranking). Ollama'sız çalışır.
- **Gold eval** (`eval/gold_queries.json`, **46 sorgu**): beklenen intent/kategori isabeti.
- **Long query eval** (`eval/long_queries.json`, **18 sorgu**): tek cümlede çok bağlamlı
  doğal-dil sorguları; Top-1/Top-3 = %100.
- **Stress eval** (**100 sorgu**): dayanıklılık (exception yok).
- **Manuel regresyon** (`manual/`): canlı API'ye karşı senaryo matrisi.

Komutlar `RUNNING_TESTS.md`'de.

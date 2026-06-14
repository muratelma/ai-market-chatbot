# Local Manual Test Results After Pre-DB Semantic Fix
Bu dosya, local API üzerinden çalıştırılan manuel sorgu testlerinin Markdown formatına çevrilmiş halidir. Amaç, Claude raporu ile gerçek local API çıktıları arasındaki farkları görünür hale getirmek ve DB geçişi öncesi kalan problemleri işaretlemektir.
## Kısa Özet
Otomatik testler geçse de local manuel testlerde bazı davranış farklılıkları görülüyor. En önemli açık problem `cilt için serum öner` sorgusunun saç serumu ürünlerine gitmesi. `kışlık elbise öner` artık mont/kaban önermiyor ama kışlık/triko elbise en üst sırada değil.
## Kritik Bulgular
- ❌ **Cilt için serum problemi:** `cilt için serum öner` sorgusu cilt serumları yerine saç serumları döndürüyor.
- ⚠️ **Normalizer gizli riski:** `cilt serumu öner` sorgusunda sonuç doğru olsa bile `normalized_query` hâlâ `saç serumu`; fallback kurtarıyor.
- ⚠️ **Kışlık elbise sıralama problemi:** `kışlık elbise öner` elbise kategorisinde kalıyor ama kışlık/triko elbise 3. sırada.
- ⚠️ **Yazıcı / zihin okuma cevap tonu:** Ürün dönmemesi doğru olabilir; fakat cevap tipi/ifadeler daha net no-result olmalı.

## Genel Sonuç Tablosu
| # | Sorgu | Normalized Query | Mode | Main | Sub | Product Type | Ürün Sayısı | Durum | Not |
|---:|---|---|---|---|---|---|---:|---|---|
| 1 | serum öner | saç serumu | focused_search | Kişisel Bakım | Saç Bakımı | Saç Serumu | 5 | ⚠️ İncelenmeli | Genel 'serum' sorgusu yalnızca saç serumu tarafına normalize oluyor; cilt serumlarını da kapsaması veya soft clarification sorması daha iyi olabilir. |
| 2 | saç serumu öner | saç serumu | focused_search | Kişisel Bakım | Saç Bakımı | Saç Serumu | 5 | ✅ Kabul edilebilir | Saç serumları üstte; ek yakın saç bakım ürünleri düşük skorlu olarak geliyor. |
| 3 | cilt serumu öner | saç serumu | focused_search | Kişisel Bakım | Cilt Bakımı | Cilt Serumu | 5 | ⚠️ Gizli risk | Sonuçlar doğru Cilt Serumu; fakat normalized_query hâlâ 'saç serumu'. Fallback doğru çalışmış ama normalizer hatası kayıt altına alınmalı. |
| 4 | cilt için serum öner | saç serumu | focused_search | Kişisel Bakım | Saç Bakımı | Saç Serumu | 5 | ❌ Problem | Kullanıcı cilt için serum istiyor ama sistem Saç Serumu/Saç Bakımı ürünleri döndürüyor. |
| 5 | kışlık mont öner | kışlık mont | focused_search | Giyim | Mont | None | 5 | ⚠️ İncelenmeli | Doğru kategoriye gidiyor; ancak eşleşme oranları düşük ve cevapta fiyat ifadesi hatalı görünüyor. |
| 6 | kışlık bot öner | kışlık su geçirmez bot | focused_search | Ayakkabı | Bot | Bot | 5 | ✅ İyi | Bot ürünleri geliyor; su geçirmez/kışlık bağlamı korunmuş. |
| 7 | kışlık elbise öner | kışlık kadın elbiseleri | focused_search | Giyim | Elbise | None | 5 | ⚠️ Kısmi problem | Mont/kaban sorunu çözülmüş; elbise kategorisinde kalıyor. Ancak 'Kadın Kışlık Triko Elbise' 3. sırada, kışlık ürün en üstte olmalı. |
| 8 | yazlık elbise öner | yazlık elbise | focused_search | Giyim | Elbise | Yazlık | 2 | ✅ İyi | Yazlık elbise ürünleri geliyor. |
| 9 | yazıcı öner | ofset yazıcı | clarification_only | None | None | None | 0 | ⚠️ İncelenmeli | Ürün yoksa no-result mantıklı; ama response_mode clarification_only / needs_clarification False tutarsız görünüyor. |
| 10 | elbise öner | kadın elbise | focused_search | Giyim | Elbise | None | 5 | ✅ İyi | Elbise ürünleri ve soft follow-up geliyor. |
| 11 | özel gün için kadın elbise öner | kadın elbiseleri | focused_search | Giyim | Elbise | Abiye | 5 | ✅ İyi | Abiye ilk sırada; clarification yok. |
| 12 | özel gün için kadın elbisesi öner | kadın elbiseleri | focused_search | Giyim | Elbise | Abiye | 5 | ✅ İyi | Abiye ilk sırada; clarification yok. |
| 13 | saç dökülmesi için ürün öner | saç dökülmesi için saç bakım ürünü | broad_search | Kişisel Bakım | Saç Bakımı | None | 5 | ✅ İyi | Broad search ve karışık saç bakım ürünleri geliyor. |
| 14 | saç dökülmesi için şampuan öner | saç dökülmesi için şampuan | focused_search | Kişisel Bakım | Saç Bakımı | Şampuan | 5 | ✅ İyi | Şampuan-focused sonuçlar geliyor. |
| 15 | şampuan öner | şampuan | focused_search | Kişisel Bakım | Saç Bakımı | Şampuan | 5 | ✅ İyi | Şampuanlar ve soft follow-up geliyor. |
| 16 | ürün öner | ürün öner | clarification_only | None | None | None | 0 | ✅ İyi | Clarification ve 0 ürün. |
| 17 | spor için ürün öner | spor ekipmanları | broad_search | Spor | None | None | 5 | ✅ İyi | Broad spor ürünleri ve follow-up geliyor. |
| 18 | kamp için ürün arıyorum | kamp için ürün | broad_search | Kamp | None | None | 5 | ✅ İyi | Broad kamp ürünleri ve follow-up geliyor. |
| 19 | uzay mekiği | uzay mekiği | None | None | None | None | 0 | ✅ İyi | No-result ve 0 ürün. |
| 20 | zihin okuma cihazı | beyin aktivite ölçüm cihazı | clarification_only | None | None | None | 0 | ⚠️ İncelenmeli | Ürün dönmüyor; iyi. Ancak cevap 'beyin aktivite ölçüm cihazlarımız' gibi katalogda olmayan ürün varmış hissi verebilir. |

## Detaylı Sorgu Çıktıları

### serum öner

**Durum:** ⚠️ İncelenmeli

**Not:** Genel 'serum' sorgusu yalnızca saç serumu tarafına normalize oluyor; cilt serumlarını da kapsaması veya soft clarification sorması daha iyi olabilir.

| Alan | Değer |
|---|---|
| normalized_query | saç serumu |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kişisel Bakım |
| sub_category | Saç Bakımı |
| product_type | Saç Serumu |
| features | [] |

**Cevap:** Saç serumu aramanıza göre size beş farklı seçenek sundum. En uygun olanı, saçlarınıza yoğun bakım yapacak ve nemlendirme sağlayarak parlaklık verecek ‘Saç Serumu Güçlendirici’ oldu. Bu serum, içerdiği özel vitaminler sayesinde saç köklerini güçlendiriyor.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Saç Serumu Güçlendirici | Kişisel Bakım › Saç Bakımı | Saç Serumu | 80% | ₺349 |
| 2 | Saç Dökülmesine Karşı Serum | Kişisel Bakım › Saç Bakımı | Saç Serumu | 79% | ₺449 |
| 3 | Hassas Saç Derisi Yatıştırıcı Tonik | Kişisel Bakım › Saç Bakımı | Saç Toniği | 53% | ₺379 |
| 4 | Kuru Saçlar İçin Avokadolu Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 51% | ₺269 |
| 5 | Saç Dökülmesi Losyonu | Kişisel Bakım › Saç Bakımı | Saç Losyonu | 51% | ₺449 |

### saç serumu öner

**Durum:** ✅ Kabul edilebilir

**Not:** Saç serumları üstte; ek yakın saç bakım ürünleri düşük skorlu olarak geliyor.

| Alan | Değer |
|---|---|
| normalized_query | saç serumu |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kişisel Bakım |
| sub_category | Saç Bakımı |
| product_type | Saç Serumu |
| features | [] |

**Cevap:** **Saç Serumu** kategorisinde size en uygun 5 ürün listelendi. 🛍️  Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Saç Serumu Güçlendirici | Kişisel Bakım › Saç Bakımı | Saç Serumu | 80% | ₺349 |
| 2 | Saç Dökülmesine Karşı Serum | Kişisel Bakım › Saç Bakımı | Saç Serumu | 79% | ₺449 |
| 3 | Hassas Saç Derisi Yatıştırıcı Tonik | Kişisel Bakım › Saç Bakımı | Saç Toniği | 53% | ₺379 |
| 4 | Kuru Saçlar İçin Avokadolu Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 51% | ₺269 |
| 5 | Saç Dökülmesi Losyonu | Kişisel Bakım › Saç Bakımı | Saç Losyonu | 51% | ₺449 |

### cilt serumu öner

**Durum:** ⚠️ Gizli risk

**Not:** Sonuçlar doğru Cilt Serumu; fakat normalized_query hâlâ 'saç serumu'. Fallback doğru çalışmış ama normalizer hatası kayıt altına alınmalı.

| Alan | Değer |
|---|---|
| normalized_query | saç serumu |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kişisel Bakım |
| sub_category | Cilt Bakımı |
| product_type | Cilt Serumu |
| features | [] |

**Cevap:** **Cilt Serumu** kategorisinde size en uygun 5 ürün listelendi. 🛍️  Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Cilt Tonu Eşitleyici Serum | Kişisel Bakım › Cilt Bakımı | Cilt Serumu | 62% | ₺699 |
| 2 | Retinol Gece Serumu | Kişisel Bakım › Cilt Bakımı | Cilt Serumu | 62% | ₺799 |
| 3 | Leke Karşıtı Cilt Serumu | Kişisel Bakım › Cilt Bakımı | Cilt Serumu | 58% | ₺699 |
| 4 | Hyaluronik Asit Serum | Kişisel Bakım › Cilt Bakımı | Cilt Serumu | 57% | ₺549 |
| 5 | C Vitamini Aydınlatıcı Serum | Kişisel Bakım › Cilt Bakımı | Cilt Serumu | 55% | ₺699 |

### cilt için serum öner

**Durum:** ❌ Problem

**Not:** Kullanıcı cilt için serum istiyor ama sistem Saç Serumu/Saç Bakımı ürünleri döndürüyor.

| Alan | Değer |
|---|---|
| normalized_query | saç serumu |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kişisel Bakım |
| sub_category | Saç Bakımı |
| product_type | Saç Serumu |
| features | [] |

**Cevap:** Saçlarınız için farklı serum seçenekleri buldum! En uygun olanı, özellikle 'Saç Serumu Güçlendirici' oldu. İçeriğindeki özel vitaminler ve amino asitler sayesinde saçlarınızı derinlemesine besleyip güçlendirecek.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Saç Serumu Güçlendirici | Kişisel Bakım › Saç Bakımı | Saç Serumu | 80% | ₺349 |
| 2 | Saç Dökülmesine Karşı Serum | Kişisel Bakım › Saç Bakımı | Saç Serumu | 79% | ₺449 |
| 3 | Hassas Saç Derisi Yatıştırıcı Tonik | Kişisel Bakım › Saç Bakımı | Saç Toniği | 53% | ₺379 |
| 4 | Kuru Saçlar İçin Avokadolu Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 51% | ₺269 |
| 5 | Saç Dökülmesi Losyonu | Kişisel Bakım › Saç Bakımı | Saç Losyonu | 51% | ₺449 |

### kışlık mont öner

**Durum:** ⚠️ İncelenmeli

**Not:** Doğru kategoriye gidiyor; ancak eşleşme oranları düşük ve cevapta fiyat ifadesi hatalı görünüyor.

| Alan | Değer |
|---|---|
| normalized_query | kışlık mont |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Giyim |
| sub_category | Mont |
| product_type | None |
| features | [] |

**Cevap:** Kışlık mont aramanız için size beş farklı seçenek buldum. En uygun olanı, özellikle erkekler için tasarlanmış ve su geçirmez özelliğiyle -2399 TL fiyatlı Erkek Su Geçirmez Mont, soğuk havalarda sizi korumak için ideal bir seçim olacaktır.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Polar Mont | Giyim › Mont | Polar Mont | 47% | ₺1199 |
| 2 | Polar Mont Unisex | Giyim › Mont | Polar Mont | 45% | ₺1199 |
| 3 | Erkek Su Geçirmez Mont | Giyim › Mont | Yağmurluk Mont | 35% | ₺1499 |
| 4 | Erkek Kapüşonlu Kışlık Kaban Dolgulu | Giyim › Mont | Kaban | 35% | ₺1699 |
| 5 | Erkek Şişme Mont | Giyim › Mont | Şişme Mont | 35% | ₺2399 |

### kışlık bot öner

**Durum:** ✅ İyi

**Not:** Bot ürünleri geliyor; su geçirmez/kışlık bağlamı korunmuş.

| Alan | Değer |
|---|---|
| normalized_query | kışlık su geçirmez bot |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Ayakkabı |
| sub_category | Bot |
| product_type | Bot |
| features | ['su geçirmez', 'suya dayanıklı'] |

**Cevap:** Kış için su geçirmez bot arayışınızda size birkaç farklı seçenek sundum. En uygun seçeneğin 'Kadın Su Geçirmez Yağmur Botu' olduğu düşünülüyor, çünkü hem kadınlara özel tasarımı hem de ₺2399 fiyatıyla oldukça cazip bir alternatif sunuyor. Ayrıca, su geçirmez özelliğiyle de kış aylarında ayaklarınızı sıcak ve kuru tutacaktır.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kadın Su Geçirmez Yağmur Botu | Ayakkabı › Bot | Bot | 66% | ₺2399 |
| 2 | Kadın Bot Su Geçirmez | Ayakkabı › Bot | Bot | 65% | ₺2499 |
| 3 | Kadın Su Geçirmez Bot | Ayakkabı › Bot | Bot | 64% | ₺2499 |
| 4 | Erkek Su Geçirmez Deri Bot | Ayakkabı › Bot | Bot | 63% | ₺2999 |
| 5 | Erkek Bot Outdoor | Ayakkabı › Bot | Bot | 56% | ₺2699 |

### kışlık elbise öner

**Durum:** ⚠️ Kısmi problem

**Not:** Mont/kaban sorunu çözülmüş; elbise kategorisinde kalıyor. Ancak 'Kadın Kışlık Triko Elbise' 3. sırada, kışlık ürün en üstte olmalı.

| Alan | Değer |
|---|---|
| normalized_query | kışlık kadın elbiseleri |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Giyim |
| sub_category | Elbise |
| product_type | None |
| features | [] |

**Cevap:** Kış için harika elbise seçeneklerinden oluşan bir liste hazırladım. Özellikle 'Kadın Kışlık Triko Elbise' modeli, sıcak tutma özelliği ve rahat tasarımı sayesinde kış aylarında sizi en iyi şekilde koruyacak ve şık bir görünüm sunacak. Diğer modeller de farklı tarzlara hitap ediyor.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kadın Günlük Midi Elbise | Giyim › Elbise | Midi Elbise | 44% | ₺1599 |
| 2 | Kadın Çiçekli Elbise | Giyim › Elbise | Yazlık Elbise | 44% | ₺1499 |
| 3 | Kadın Kışlık Triko Elbise | Giyim › Elbise | Triko Elbise | 43% | ₺1599 |
| 4 | Kadın Yazlık Mini Elbise Çiçek Desenli | Giyim › Elbise | Mini Elbise | 42% | ₺699 |
| 5 | Kadın Mini Elbise | Giyim › Elbise | Mini Elbise | 42% | ₺1899 |

### yazlık elbise öner

**Durum:** ✅ İyi

**Not:** Yazlık elbise ürünleri geliyor.

| Alan | Değer |
|---|---|
| normalized_query | yazlık elbise |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 2 |
| main_category | Giyim |
| sub_category | Elbise |
| product_type | Yazlık |
| features | ['nefes alabilir', 'hafif', 'yazlık'] |

**Cevap:** Yazlık elbiseler için harika seçenekler buldum! Öncelikle 'Kadın Çiçekli Elbise' modeli ₺1499’dan ve ‘Kadın Yazlık Elbise’ modeli ise ₺1299’dan mevcut. Daha iyi bir öneri için elbiseyi günlük kullanım mı yoksa özel bir gün için mi arıyorsunuz? Renk veya fiyat aralığı tercihinizi belirtebilirsiniz.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kadın Çiçekli Elbise | Giyim › Elbise | Yazlık Elbise | 84% | ₺1499 |
| 2 | Kadın Yazlık Elbise | Giyim › Elbise | Yazlık | 83% | ₺1299 |

### yazıcı öner

**Durum:** ⚠️ İncelenmeli

**Not:** Ürün yoksa no-result mantıklı; ama response_mode clarification_only / needs_clarification False tutarsız görünüyor.

| Alan | Değer |
|---|---|
| normalized_query | ofset yazıcı |
| intent | product_search |
| response_mode | clarification_only |
| needs_clarification | False |
| product_count | 0 |
| main_category | None |
| sub_category | None |
| product_type | None |
| features | [] |

**Cevap:** Maalesef ofset yazıcı kategorimizde şu anda istediğiniz ürün bulunamadı. Farklı bir marka veya özellik arayışında deneyebilirsiniz, belki size daha uygun seçenekler bulabiliriz. 😊

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| - | Ürün dönmedi | - | - | - | - |

### elbise öner

**Durum:** ✅ İyi

**Not:** Elbise ürünleri ve soft follow-up geliyor.

| Alan | Değer |
|---|---|
| normalized_query | kadın elbise |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Giyim |
| sub_category | Elbise |
| product_type | None |
| features | [] |

**Cevap:** Kadın elbiseleri arasında günlük kullanım için 'Kadın Günlük Midi Elbise' (₺1599), özel günler için 'Kadın Çiçekli Elbise' (₺1499) ve yazlık mini elbise seçenekleri mevcut. Ayrıca, kışlık triko elbise (₺1599) ve yazlık elbisemizi de inceleyebilirsiniz. Daha iyi bir öneri için elbiseyi günlük kullanım mı yoksa özel bir gün için mi arıyorsunuz? Renk

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kadın Günlük Midi Elbise | Giyim › Elbise | Midi Elbise | 66% | ₺1599 |
| 2 | Kadın Çiçekli Elbise | Giyim › Elbise | Yazlık Elbise | 65% | ₺1499 |
| 3 | Kadın Yazlık Mini Elbise Çiçek Desenli | Giyim › Elbise | Mini Elbise | 64% | ₺699 |
| 4 | Kadın Kışlık Triko Elbise | Giyim › Elbise | Triko Elbise | 63% | ₺1599 |
| 5 | Kadın Yazlık Elbise | Giyim › Elbise | Yazlık | 63% | ₺1299 |

### özel gün için kadın elbise öner

**Durum:** ✅ İyi

**Not:** Abiye ilk sırada; clarification yok.

| Alan | Değer |
|---|---|
| normalized_query | kadın elbiseleri |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Giyim |
| sub_category | Elbise |
| product_type | Abiye |
| features | [] |

**Cevap:** Özel gününüz için harika seçenekler buldum! İşte size "Kadın Abiye Elbise" modeli, ₺3299 fiyatıyla en uygun seçim. Şık tasarımı ve abiye kalitesiyle özel günlerinizde göz alıcı olmanızı sağlayacak.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kadın Abiye Elbise | Giyim › Elbise | Abiye | 79% | ₺3299 |
| 2 | Kadın Günlük Midi Elbise | Giyim › Elbise | Midi Elbise | 48% | ₺1599 |
| 3 | Kadın Çiçekli Elbise | Giyim › Elbise | Yazlık Elbise | 46% | ₺1499 |
| 4 | Kadın Yazlık Mini Elbise Çiçek Desenli | Giyim › Elbise | Mini Elbise | 46% | ₺699 |
| 5 | Kadın Mini Elbise | Giyim › Elbise | Mini Elbise | 45% | ₺1899 |

### özel gün için kadın elbisesi öner

**Durum:** ✅ İyi

**Not:** Abiye ilk sırada; clarification yok.

| Alan | Değer |
|---|---|
| normalized_query | kadın elbiseleri |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Giyim |
| sub_category | Elbise |
| product_type | Abiye |
| features | [] |

**Cevap:** Özel gününüz için harika seçenekler buldum! İşte size "Kadın Abiye Elbise" modeli, ₺3299'a düşen bu elbise, zarif tasarımı ve yüksek kalitesiyle diğerlerine göre daha uygun bir seçim oldu. Ayrıca "Kadın Günlük Midi Elbise" ve "Kadın Çiçekli Elbise" gibi farklı stillerde de seçeneklerimiz mevcut.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kadın Abiye Elbise | Giyim › Elbise | Abiye | 80% | ₺3299 |
| 2 | Kadın Günlük Midi Elbise | Giyim › Elbise | Midi Elbise | 49% | ₺1599 |
| 3 | Kadın Çiçekli Elbise | Giyim › Elbise | Yazlık Elbise | 47% | ₺1499 |
| 4 | Kadın Yazlık Mini Elbise Çiçek Desenli | Giyim › Elbise | Mini Elbise | 46% | ₺699 |
| 5 | Kadın Mini Elbise | Giyim › Elbise | Mini Elbise | 46% | ₺1899 |

### saç dökülmesi için ürün öner

**Durum:** ✅ İyi

**Not:** Broad search ve karışık saç bakım ürünleri geliyor.

| Alan | Değer |
|---|---|
| normalized_query | saç dökülmesi için saç bakım ürünü |
| intent | product_search |
| response_mode | broad_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kişisel Bakım |
| sub_category | Saç Bakımı |
| product_type | None |
| features | ['güçlendirici', 'saç dökülmesi', 'dökülme karşıtı'] |

**Cevap:** Saç dökülmesi sorununuza yönelik çeşitli ürünler buldum. Özellikle Dökülme Karşıtı Şampuan, saç köklerini besleyerek ve saç derisini temizleyerek bu soruna karşı etkili bir başlangıç noktası olabilir. Ayrıca Saç Dökülmesine Karşı Serum da yoğunlaşmış bakım sunuyor.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Dökülme Karşıtı Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 92% | ₺249 |
| 2 | Saç Dökülmesine Karşı Serum | Kişisel Bakım › Saç Bakımı | Saç Serumu | 89% | ₺449 |
| 3 | Saç Dökülmesi Losyonu | Kişisel Bakım › Saç Bakımı | Saç Losyonu | 81% | ₺449 |
| 4 | Biotin Saç Bakım Kürü | Kişisel Bakım › Saç Bakımı | Saç Bakım Kürü | 75% | ₺549 |
| 5 | Hassas Saç Derisi Yatıştırıcı Tonik | Kişisel Bakım › Saç Bakımı | Saç Toniği | 64% | ₺379 |

### saç dökülmesi için şampuan öner

**Durum:** ✅ İyi

**Not:** Şampuan-focused sonuçlar geliyor.

| Alan | Değer |
|---|---|
| normalized_query | saç dökülmesi için şampuan |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kişisel Bakım |
| sub_category | Saç Bakımı |
| product_type | Şampuan |
| features | ['güçlendirici', 'saç dökülmesi', 'dökülme karşıtı'] |

**Cevap:** Saç dökülmenize yardımcı olabilecek birkaç şampuan seçeneği buldum. Özellikle ‘Dökülme Karşıtı Şampuan’ ve ‘Dökülme Karşıtı Biotin Şampuan’, saç köklerini güçlendiren biotin içeriği sayesinde bu konuda en etkili seçenekler arasında yer alıyor. Bu iki ürün, saç dökülmenizi azaltmaya yönelik formülasyonları ile öne çıkıyor.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Dökülme Karşıtı Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 99% | ₺249 |
| 2 | Dökülme Karşıtı Biotin Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 99% | ₺299 |
| 3 | Biotin Destekli Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 95% | ₺279 |
| 4 | Keratin Onarıcı Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 86% | ₺319 |
| 5 | Kuru Saçlar İçin Avokadolu Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 79% | ₺269 |

### şampuan öner

**Durum:** ✅ İyi

**Not:** Şampuanlar ve soft follow-up geliyor.

| Alan | Değer |
|---|---|
| normalized_query | şampuan |
| intent | product_search |
| response_mode | focused_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kişisel Bakım |
| sub_category | Saç Bakımı |
| product_type | Şampuan |
| features | [] |

**Cevap:** **Şampuan** kategorisinde size en uygun 5 ürün listelendi. 🛍️  Daha iyi bir şampuan önerisi için saç tipinizi ve saç problemi (kuru, yağlı, kepek veya dökülme gibi) gibi ihtiyaçlarınızı belirtebilirsiniz.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kuru Saçlar İçin Avokadolu Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 45% | ₺269 |
| 2 | Dökülme Karşıtı Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 43% | ₺249 |
| 3 | Hassas Saç Derisi Şampuanı Aloe Vera | Kişisel Bakım › Saç Bakımı | Şampuan | 43% | ₺289 |
| 4 | Argan Yağlı Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 42% | ₺259 |
| 5 | Keratin Onarıcı Şampuan | Kişisel Bakım › Saç Bakımı | Şampuan | 41% | ₺319 |

### ürün öner

**Durum:** ✅ İyi

**Not:** Clarification ve 0 ürün.

| Alan | Değer |
|---|---|
| normalized_query | ürün öner |
| intent | product_search |
| response_mode | clarification_only |
| needs_clarification | True |
| product_count | 0 |
| main_category | None |
| sub_category | None |
| product_type | None |
| features | None |

**Cevap:** Merhaba! Tam olarak ne tür bir ürün aradığınızı anlamak için biraz daha detay verir misiniz? Örneğin, hangi kategoriye ihtiyacınız var veya belirli bir kullanım amacı (örneğin, yağlı saçlar için şampuan mı yoksa 1500 TL altında erkek ayakkabı mı)?

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| - | Ürün dönmedi | - | - | - | - |

### spor için ürün öner

**Durum:** ✅ İyi

**Not:** Broad spor ürünleri ve follow-up geliyor.

| Alan | Değer |
|---|---|
| normalized_query | spor ekipmanları |
| intent | product_search |
| response_mode | broad_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Spor |
| sub_category | None |
| product_type | None |
| features | ['spor', 'rahat'] |

**Cevap:** Spor için farklı ihtiyaçlarınızı karşılayacak çeşitli ürünler listeledim. Spor Eldiveni, Diz Koruyucu, Diz Bandajı, Dambıl Seti ve Koşu Kemeri gibi seçeneklerimiz mevcut. Spor kategorisinden çeşitli ürünleri listeledim. Fitness, koşu, yoga veya outdoor gibi hangi alana odaklanmamı istersin?

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Spor Eldiveni | Spor › Fitness | Spor Eldiveni | 69% | ₺299 |
| 2 | Diz Koruyucu Kompresyon Çift Kol | Spor › Koşu | Diz Koruyucu | 68% | ₺299 |
| 3 | Spor Diz Bandajı | Spor › Aksesuar | Diz Bandajı | 67% | ₺249 |
| 4 | Dambıl Seti 5-20 kg | Spor › Fitness | Dambıl Seti | 67% | ₺2499 |
| 5 | Koşu Kemeri | Spor › Koşu | Koşu Kemeri | 67% | ₺299 |

### kamp için ürün arıyorum

**Durum:** ✅ İyi

**Not:** Broad kamp ürünleri ve follow-up geliyor.

| Alan | Değer |
|---|---|
| normalized_query | kamp için ürün |
| intent | product_search |
| response_mode | broad_search |
| needs_clarification | False |
| product_count | 5 |
| main_category | Kamp |
| sub_category | None |
| product_type | None |
| features | [] |

**Cevap:** Kamp için ihtiyacınıza göre birçok farklı ürün seçeneği buldum! Kamp Çadırı, Kamp Matı, Kamp Bardağı, Kamp Taburesi ve Şişme Kamp Matı gibi seçeneklerimiz mevcut. Kamp kategorisinden farklı ürün tiplerini listeledim. Uyku, barınma, aydınlatma veya yemek hazırlama gibi hangi ihtiyacına odaklanmamı istersin?

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| 1 | Kamp Çadırı 2 Kişilik | Kamp › Çadır | Kamp Çadırı | 69% | ₺1899 |
| 2 | Kamp Matı | Kamp › Uyku | Kamp Matı | 69% | ₺299 |
| 3 | Katlanır Kamp Bardağı | Kamp › Pişirme | Kamp Bardağı | 68% | ₺199 |
| 4 | Katlanır Kamp Taburesi | Kamp › Mobilya | Kamp Taburesi | 68% | ₺299 |
| 5 | Şişme Kamp Matı | Kamp › Uyku | Şişme Kamp Matı | 67% | ₺799 |

### uzay mekiği

**Durum:** ✅ İyi

**Not:** No-result ve 0 ürün.

| Alan | Değer |
|---|---|
| normalized_query | uzay mekiği |
| intent | nonsense |
| response_mode | None |
| needs_clarification | False |
| product_count | 0 |
| main_category | None |
| sub_category | None |
| product_type | None |
| features | None |

**Cevap:** Maalesef bu tür bir ürün katalogumuzda bulunmuyor. 😅 Farklı bir ürün aramak ister misin? Örneğin "kamp ocağı", "spor ayakkabı" veya "kablosuz kulaklık" gibi.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| - | Ürün dönmedi | - | - | - | - |

### zihin okuma cihazı

**Durum:** ⚠️ İncelenmeli

**Not:** Ürün dönmüyor; iyi. Ancak cevap 'beyin aktivite ölçüm cihazlarımız' gibi katalogda olmayan ürün varmış hissi verebilir.

| Alan | Değer |
|---|---|
| normalized_query | beyin aktivite ölçüm cihazı |
| intent | product_search |
| response_mode | clarification_only |
| needs_clarification | False |
| product_count | 0 |
| main_category | None |
| sub_category | None |
| product_type | None |
| features | [] |

**Cevap:** Maalesef şu anda zihin okuma cihazı gibi bir ürünümüz bulunmuyor. Ancak, beyin aktivite ölçüm cihazlarımızla ilgilenmenizi öneririm. Farklı modelleri ve özelliklerini incelemek isterseniz, lütfen tekrar farklı bir arama yapın.

| Sıra | Ürün | Kategori | Tip | Match | Fiyat |
|---:|---|---|---|---|---|
| - | Ürün dönmedi | - | - | - | - |

## DB Öncesi Önerilen Kalan Aksiyonlar
1. `cilt için serum öner` sorgusu için cilt bağlamı korunmalı; `Cilt Serumu` ürünlerine yönlenmeli.
2. `cilt serumu öner` sorgusunda final sonuç doğru olsa bile normalizer'ın `saç serumu` üretmesi risk olarak not edilmeli veya fallback testine eklenmeli.
3. `kışlık elbise öner` sorgusunda `Kadın Kışlık Triko Elbise` gibi kışlık/triko ürünlerin daha üst sıraya çıkması değerlendirilmeli.
4. `yazıcı öner` ve `zihin okuma cihazı` için cevap tipi ve no-result tonu tutarlı hale getirilmeli.
5. Bu manuel test seti eval/test senaryolarına eklenmeli veya en azından DB migration öncesi/sonrası smoke test olarak korunmalı.

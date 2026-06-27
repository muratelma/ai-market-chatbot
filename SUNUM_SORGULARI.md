# 🎤 Sunum Sorguları — AI-Market Chatbot

Bu dosyadaki sorguların **hepsi canlı sistemde test edildi** (arka arkaya 3 kez,
sonuçlar her seferinde aynı). Sunum sırasında hocalar soru sorduğunda buradan
kopyalayıp arama kutusuna yapıştırabilirsin.

> **Notlar**
> - Cevap süresi normalde **~8-10 saniye** (yapay zeka modeli cevabı yazıyor). İlk sorgu biraz daha uzun olabilir.
> - Her sorgu **tek başına** çalışır; önceki sorguya bağlı değildir.
> - Sistem **uydurma ürün üretmez**: olmayan bir şey istenirse dürüstçe "katalogda yok" der.

---

## ⭐ En garantili 6 sorgu (panik anı için)

Bunlar her zaman dolu, güzel sonuç verir:

- `kamp için uyku tulumu öner`
- `bilgisayar için kablosuz mouse öner`
- `yağlı saç için şampuan öner`
- `telefonum hemen bitiyor`
- `1500 TL altında erkek ayakkabı`
- `Kışlık kadın elbisesi önerir misin? Mont veya kaban değil, elbise arıyorum.`

---

## 1) 💬 Sohbet (anında cevap, ürün aramaz)

Sistemin sadece arama motoru değil, sohbet de anladığını gösterir. **Anında** (0 sn) cevaplar.

- `merhaba` → Karşılama + nasıl kullanılacağına dair örnek
- `ne yapabilirsin` → Yeteneklerini ve örnek aramaları listeler
- `teşekkürler` → Nazik teşekkür cevabı
- `nasılsın` → Hal hatır cevabı + "ne arıyorsun?"
- `görüşürüz` → Vedalaşma

---

## 2) 📂 Kategori geneli arama (broad)

Genel bir kategori istenir; sistem **çeşitli ürünler** gösterir ve "hangi ihtiyaca odaklanayım?" diye sorar.

- `kamp için ürün öner` → Kamp: çadır, mat, katlanır bardak, tabure…
- `elektronik ürün öner` → Telefon kılıfı, tripod, araç tutucu…
- `spor için ürün öner` → Spor eldiveni, diz koruyucu, bandaj…
- `ev için ürün öner` → Oda kokusu, paspas, kırlent seti…
- `mutfak için ürün öner` → Tava, bıçak seti, yapışmaz tava…
- `bebek için ürün öner` → Bebek şampuanı, kanguru, vücut yağı…
- `ayakkabı öner` → Sneaker, sandalet, çocuk ayakkabısı…

---

## 3) 🎯 Net ürün araması (focused) — 12 kategoriden örnek

Belirli bir ürün tipi istenir; sistem doğrudan o ürünleri getirir.

| Kategori | Sorgu |
|---|---|
| Kamp | `kamp için uyku tulumu öner` |
| Ayakkabı | `yağmurlu havalar için kadın bot öner` |
| Giyim | `özel gün için kadın abiye öner` |
| Elektronik | `bilgisayar için kablosuz mouse öner` |
| Spor | `yoga için mat öner` |
| Kişisel Bakım | `saç dökülmesi için şampuan öner` |
| Ev & Yaşam | `ev için dekoratif lamba öner` |
| Mutfak | `mutfak için kahve makinesi öner` |
| Anne & Bebek | `bebek için pişik kremi öner` |
| Aksesuar | `okul için sırt çantası öner` |
| Otomotiv | `araç için telefon şarj cihazı öner` |
| Kırtasiye | `tablet için dokunmatik kalem öner` |

---

## 4) 🧠 Doğal dil / dolaylı anlatım (en etkileyici kısım)

Kullanıcı ürün adını **söylemez**, problemi/ihtiyacı anlatır; sistem doğru ürünü çıkarır.

- `telefonum hemen bitiyor` → **Powerbank** önerir
- `kamp için yemek yapacak bir şey lazım` → **Kamp mutfak/ocak seti** önerir
- `koşmak için bir spor ayakkabı lazım` → **Koşu/spor ayakkabısı** önerir
- `yağlı cilt için temizleyici öner` → **Yağ dengeleyici yüz jeli / temizleyici** önerir

---

## 5) 💰 Fiyat filtresi (sınıra harfiyen uyar)

Sistem fiyat sınırını her üründe uygular.

- `1500 TL altında erkek ayakkabı` → Hepsi **1500 TL altı** sneaker/ayakkabı
- `1500 TL üstünde ayakkabı` → Hepsi **1500 TL üstü**
- `1000 ile 2000 TL arası elektronik ürün` → Hepsi **bu aralıkta**
- `2000 TL altında kahve makinesi` → 2000 TL altı kahve makineleri

---

## 6) 🚫 Negatif kısıt (istenmeyeni eler)

- `Kışlık kadın elbisesi önerir misin? Mont veya kaban değil, elbise arıyorum.`
  → Sadece **elbise** getirir; sonuçlarda **mont/kaban olmaz**.

---

## 7) ❓ Belirsiz istek → netleştirme sorusu

Yeterli bilgi yoksa sistem ürün uydurmaz, **soru sorar**.

- `ürün öner` → "Tam olarak ne arıyorsun? Kategori/amaç/bütçe yaz…"
- `bir şey lazım` → Netleştirme ister
- `1500 TL altında erkek` → "Hangi kategori?" diye sorar (sadece bütçe + kişi var, ürün yok)

---

## 8) 🛡️ Olmayan / hayali ürün → dürüst "yok" cevabı (uydurma yapmaz)

Katalogda olmayan bir şey istenirse sistem **asla uydurmaz**.

- `uzay mekiği` → "Bu tür bir ürün katalogumuzda bulunmuyor 😅"
- `zaman makinesi almak istiyorum` → "Bu ürün şu anda katalogda bulunmuyor."
- `görünmezlik pelerini almak istiyorum` → "Bu ürün şu anda katalogda bulunmuyor."

---

### 📌 Hoca tipik şunu sorabilir, hazır ol:

- **"Ürün adını söylemezsem anlar mı?"** → `telefonum hemen bitiyor` (powerbank çıkar)
- **"Olmayan bir şey istesem uydurur mu?"** → `görünmezlik pelerini almak istiyorum` (uydurmaz)
- **"Fiyat sınırına uyuyor mu?"** → `1500 TL altında erkek ayakkabı` (hepsi 1500 altı)
- **"İstemediğimi eleyebilir mi?"** → `... Mont veya kaban değil, elbise arıyorum.`

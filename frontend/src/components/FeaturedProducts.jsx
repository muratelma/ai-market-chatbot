import React from "react";
// Self-hosted product photos — bundled locally so the featured cards are
// accurate and immune to external (Unsplash) link rot.
import kampCadiriImg from "../assets/products/kampcadiri2kisilik.jpg";
import kablosuzKulaklikImg from "../assets/products/kablosuzkulaklik.jpg";
import kosuAyakkabisiImg from "../assets/products/sporayakkabi.jpg";
import robotSupurgeImg from "../assets/products/robotsupur.jpg";
import bebekSampuaniImg from "../assets/products/organik-bebek-sampuani.jpg";
import yogaMatiImg from "../assets/products/yogamat.jpg";
import yuzBakimKremiImg from "../assets/products/yuzbakımkrem.jpg";

const FALLBACK_IMAGE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400' viewBox='0 0 400 400'%3E%3Crect width='400' height='400' fill='%23F5F6F8'/%3E%3Crect x='140' y='120' width='120' height='120' rx='16' fill='%23E5E7EB'/%3E%3Crect x='155' y='175' width='90' height='8' rx='4' fill='%23D1D5DB'/%3E%3Crect x='170' y='195' width='60' height='6' rx='3' fill='%23D1D5DB'/%3E%3Ccircle cx='200' cy='150' r='18' fill='%23D1D5DB'/%3E%3Cpath d='M193 150l4 4 8-8' stroke='%23F5F6F8' stroke-width='2.5' fill='none' stroke-linecap='round'/%3E%3Ctext x='200' y='270' font-family='Inter,Arial,sans-serif' font-size='12' fill='%239CA3AF' text-anchor='middle'%3EGörsel yüklenemedi%3C/text%3E%3C/svg%3E";

const featuredProducts = [
  {
    name: "Kamp Çadırı 2 Kişilik",
    category: "Kamp",
    subCategory: "Çadır",
    type: "Kamp Çadırı",
    price: "₺1.899",
    image: kampCadiriImg,
    tags: ["Su Geçirmez", "Hafif"],
  },
  {
    name: "Kablosuz Bluetooth Kulaklık",
    category: "Elektronik",
    subCategory: "Kulaklık",
    type: "Bluetooth Kulaklık",
    price: "₺899",
    image: kablosuzKulaklikImg,
    tags: ["Kablosuz", "Gürültü Önleme"],
  },
  {
    name: "Koşu Ayakkabısı Pro",
    category: "Ayakkabı",
    subCategory: "Spor Ayakkabı",
    type: "Koşu Ayakkabısı",
    price: "₺1.299",
    image: kosuAyakkabisiImg,
    tags: ["Hafif", "Esnek"],
  },
  {
    name: "Robot Süpürge Akıllı",
    category: "Ev & Yaşam",
    subCategory: "Temizlik",
    type: "Robot Süpürge",
    price: "₺4.999",
    image: robotSupurgeImg,
    tags: ["Akıllı", "Otomatik"],
  },
  {
    name: "Organik Bebek Şampuanı",
    category: "Anne & Bebek",
    subCategory: "Bakım",
    type: "Bebek Şampuanı",
    price: "₺189",
    image: bebekSampuaniImg,
    tags: ["Organik", "Doğal"],
  },
  {
    name: "Yoga Matı Premium",
    category: "Spor",
    subCategory: "Fitness",
    type: "Yoga Matı",
    price: "₺349",
    image: yogaMatiImg,
    tags: ["Kaymaz", "Kalın"],
  },
  {
    name: "Akıllı Saat Fitnes",
    category: "Elektronik",
    subCategory: "Giyilebilir",
    type: "Akıllı Saat",
    price: "₺2.499",
    image: "https://images.unsplash.com/photo-1579586337278-3befd40fd17a?w=480&h=480&fit=crop&auto=format&q=80",
    tags: ["GPS", "Nabız Ölçer"],
  },
  {
    name: "Yüz Bakım Kremi",
    category: "Kişisel Bakım",
    subCategory: "Cilt Bakım",
    type: "Krem",
    price: "₺259",
    image: yuzBakimKremiImg,
    tags: ["Nemlendirici", "Doğal"],
  },
];

function handleImageError(e) {
  e.target.onerror = null;
  e.target.src = FALLBACK_IMAGE;
  e.target.style.objectFit = "contain";
  e.target.style.padding = "20px";
}

function FeaturedProducts() {
  return (
    <section className="featured-section" id="one-cikan-urunler">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Öne Çıkan Ürünler</h2>
          <p className="section-subtitle">Size özel seçilmiş popüler ürünler</p>
        </div>

        <div className="featured-grid">
          {featuredProducts.map((product, index) => (
            <div className="product-card" key={index} id={`featured-product-${index}`}>
              <div className="product-card-image">
                <img
                  src={product.image}
                  alt={product.name}
                  className="product-card-photo"
                  loading="lazy"
                  onError={handleImageError}
                />
                <div className="product-card-category-badge">{product.category}</div>
                <button className="product-card-wishlist" title="Favorilere Ekle" aria-label="Favorilere ekle">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                  </svg>
                </button>
              </div>

              <div className="product-card-body">
                <div className="product-card-type">{product.type}</div>
                <h3 className="product-card-name">{product.name}</h3>

                <div className="product-card-tags">
                  {product.tags.map((tag, i) => (
                    <span key={i} className="product-card-tag">{tag}</span>
                  ))}
                </div>

                <div className="product-card-footer">
                  <span className="product-card-price">{product.price}</span>
                  <button className="product-card-cart-btn" title="Sepete Ekle">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" />
                      <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default FeaturedProducts;

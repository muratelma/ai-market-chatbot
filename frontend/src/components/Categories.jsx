import React from "react";

const FALLBACK_IMAGE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300' viewBox='0 0 400 300'%3E%3Crect width='400' height='300' fill='%23F1F3F5'/%3E%3Ctext x='50%25' y='50%25' font-family='Arial' font-size='40' fill='%239CA3AF' text-anchor='middle' dominant-baseline='middle'%3E📦%3C/text%3E%3C/svg%3E";

const categories = [
  {
    name: "Kişisel Bakım",
    count: 92,
    color: "#E91E8C",
    image: "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Anne & Bebek",
    count: 76,
    color: "#F472B6",
    image: "https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Spor",
    count: 75,
    color: "#3B82F6",
    image: "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Ev & Yaşam",
    count: 74,
    color: "#8B5CF6",
    image: "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Elektronik",
    count: 71,
    color: "#0EA5E9",
    image: "https://images.unsplash.com/photo-1468495244123-6c6c332eeece?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Kamp",
    count: 69,
    color: "#22C55E",
    image: "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Mutfak",
    count: 65,
    color: "#F59E0B",
    image: "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Giyim",
    count: 64,
    color: "#EC4899",
    image: "https://images.unsplash.com/photo-1445205170230-053b83016050?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Otomotiv",
    count: 63,
    color: "#6366F1",
    image: "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Ayakkabı",
    count: 62,
    color: "#14B8A6",
    image: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Aksesuar",
    count: 62,
    color: "#F97316",
    image: "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400&h=300&fit=crop&auto=format&q=80",
  },
  {
    name: "Kırtasiye",
    count: 53,
    color: "#EF4444",
    image: "https://images.unsplash.com/photo-1456735190827-d1262f71b8a3?w=400&h=300&fit=crop&auto=format&q=80",
  },
];

function Categories({ onCategoryClick }) {
  return (
    <section className="categories-section" id="kategoriler">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Kategoriler</h2>
          <p className="section-subtitle">12 kategoride 1000+ ürünü keşfedin</p>
        </div>

        <div className="categories-grid">
          {categories.map((cat, index) => (
            <button
              key={cat.name}
              className="category-card"
              id={`category-${index}`}
              onClick={() => onCategoryClick(cat.name)}
              style={{ "--cat-color": cat.color }}
            >
              <div className="category-image-wrapper">
                <img
                  src={cat.image}
                  alt={cat.name}
                  className="category-image"
                  loading="lazy"
                  onError={(e) => { e.target.onerror = null; e.target.src = FALLBACK_IMAGE; }}
                />
                <div className="category-image-overlay" />
              </div>
              <div className="category-info">
                <span className="category-name">{cat.name}</span>
                <span className="category-count">{cat.count} ürün</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

export default Categories;

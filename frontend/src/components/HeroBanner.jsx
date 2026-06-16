import React, { useState, useEffect } from "react";

const slides = [
  {
    title: "Yapay Zeka ile Akıllı Alışveriş",
    subtitle: "İhtiyacınızı yazın, en uygun ürünleri anında bulalım. AI-Market asistanı sizin için en doğru önerileri sunar.",
    cta: "Hemen Keşfet",
    accent: "#FF6000",
    gradient: "linear-gradient(135deg, #FFEBD6 0%, #FFCEAD 50%, #FFE0C7 100%)",
    emoji: "🤖",
    stats: [
      { icon: "✨", label: "Akıllı Öneri", value: "AI Destekli" },
      { icon: "🎯", label: "Doğruluk", value: "%95+" },
      { icon: "⚡", label: "Sonuç", value: "Anında" },
    ],
  },
  {
    title: "1000+ Ürün, Tek Platform",
    subtitle: "Elektronikten spora, kişisel bakımdan kampa kadar 12 kategoride binlerce ürün sizi bekliyor.",
    cta: "Kategorilere Göz At",
    accent: "#1B4DFF",
    gradient: "linear-gradient(135deg, #DBE5FF 0%, #C2D2FF 50%, #D3E0FF 100%)",
    emoji: "🛍️",
    stats: [
      { icon: "📦", label: "Ürün", value: "1000+" },
      { icon: "📂", label: "Kategori", value: "12" },
      { icon: "🏷️", label: "Marka", value: "Çeşitli" },
    ],
  },
  {
    title: "Doğal Dil ile Arama Yapın",
    subtitle: "\"200 TL altı koşu ayakkabısı\" veya \"bebek için organik ürünler\" gibi doğal cümlelerle arama yapın.",
    cta: "Asistanı Dene",
    accent: "#10B981",
    gradient: "linear-gradient(135deg, #D4F7E6 0%, #B8F2D4 50%, #C9F7E0 100%)",
    emoji: "💬",
    stats: [
      { icon: "🗣️", label: "Arama", value: "Doğal Dil" },
      { icon: "🔍", label: "Filtre", value: "Otomatik" },
      { icon: "💡", label: "Öneri", value: "Kişisel" },
    ],
  },
];

function HeroBanner({ onCtaClick }) {
  const [activeSlide, setActiveSlide] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsAnimating(true);
      setTimeout(() => {
        setActiveSlide((prev) => (prev + 1) % slides.length);
        setIsAnimating(false);
      }, 300);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const goToSlide = (index) => {
    if (index === activeSlide) return;
    setIsAnimating(true);
    setTimeout(() => {
      setActiveSlide(index);
      setIsAnimating(false);
    }, 300);
  };

  const slide = slides[activeSlide];

  return (
    <section className="hero-banner" id="hero-banner">
      <div
        className={`hero-slide ${isAnimating ? "hero-slide-exit" : "hero-slide-enter"}`}
        style={{ background: slide.gradient }}
      >
        <div className="container hero-slide-inner">
          <div className="hero-content">
            <div className="hero-badge" style={{ color: slide.accent, background: `${slide.accent}15`, borderColor: `${slide.accent}30` }}>
              <span className="hero-badge-dot" style={{ background: slide.accent }}></span>
              Yapay Zeka Destekli
            </div>
            <h1 className="hero-title">{slide.title}</h1>
            <p className="hero-subtitle">{slide.subtitle}</p>
            <button
              className="hero-cta"
              id="hero-cta-button"
              style={{ background: slide.accent }}
              onClick={onCtaClick}
            >
              {slide.cta}
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          <div className="hero-visual">
            <div className="hero-emoji-container" style={{ boxShadow: `0 20px 50px ${slide.accent}20` }}>
              <span className="hero-emoji">{slide.emoji}</span>
            </div>

            {/* Decorative rings */}
            <div className="hero-ring hero-ring-1" style={{ borderColor: `${slide.accent}15` }}></div>
            <div className="hero-ring hero-ring-2" style={{ borderColor: `${slide.accent}10` }}></div>

            {/* Stat cards */}
            {slide.stats.map((stat, i) => (
              <div 
                className={`hero-float-card hero-float-${i + 1}`} 
                key={i}
                style={{ "--card-accent": slide.accent }}
              >
                <span className="hero-float-icon">{stat.icon}</span>
                <div className="hero-float-text">
                  <span className="hero-float-value" style={{ color: slide.accent }}>{stat.value}</span>
                  <span className="hero-float-label">{stat.label}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Slide indicators */}
      <div className="hero-indicators">
        {slides.map((_, index) => (
          <button
            key={index}
            className={`hero-indicator ${index === activeSlide ? "active" : ""}`}
            onClick={() => goToSlide(index)}
            aria-label={`Slayt ${index + 1}`}
            id={`hero-indicator-${index}`}
            style={index === activeSlide ? { background: slide.accent } : {}}
          />
        ))}
      </div>
    </section>
  );
}

export default HeroBanner;

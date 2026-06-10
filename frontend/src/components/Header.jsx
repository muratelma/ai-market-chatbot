import React, { useState } from "react";

function Header({ onSearchSubmit }) {
  const [searchValue, setSearchValue] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchValue.trim()) {
      onSearchSubmit(searchValue.trim());
      setSearchValue("");
    }
  };

  return (
    <header className="header" id="site-header">
      {/* Top bar */}
      <div className="header-top">
        <div className="container header-top-inner">
          <span>Türkiye'nin Yapay Zeka Destekli Alışveriş Platformu</span>
          <div className="header-top-links">
            <a href="#" id="link-help">Yardım</a>
            <a href="#" id="link-about">Hakkımızda</a>
          </div>
        </div>
      </div>

      {/* Main header */}
      <div className="header-main">
        <div className="container header-main-inner">
          {/* Logo */}
          <a href="/" className="header-logo" id="logo">
            <div className="header-logo-icon">
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="8" fill="#FF6000" />
                <path d="M8 22L16 10L24 22H8Z" fill="white" opacity="0.9" />
                <circle cx="16" cy="18" r="3" fill="white" />
              </svg>
            </div>
            <div className="header-logo-text">
              <span className="header-logo-name">AI-Market</span>
              <span className="header-logo-tagline">Akıllı Alışveriş</span>
            </div>
          </a>

          {/* Search bar */}
          <form className="header-search" onSubmit={handleSearch} id="search-form">
            <div className="header-search-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
            </div>
            <input
              type="text"
              className="header-search-input"
              placeholder="Ürün, kategori veya marka ara..."
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              id="search-input"
            />
            <button type="submit" className="header-search-button" id="search-button">
              Ara
            </button>
          </form>

          {/* Right icons */}
          <div className="header-actions">
            <button className="header-action-btn" id="btn-account" title="Hesabım">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span>Hesabım</span>
            </button>
            <button className="header-action-btn" id="btn-favorites" title="Favorilerim">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
              <span>Favoriler</span>
            </button>
            <button className="header-action-btn header-cart-btn" id="btn-cart" title="Sepetim">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="9" cy="21" r="1" />
                <circle cx="20" cy="21" r="1" />
                <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
              </svg>
              <span>Sepetim</span>
              <div className="header-cart-badge">0</div>
            </button>
          </div>

          {/* Mobile menu toggle */}
          <button
            className="header-mobile-toggle"
            id="mobile-menu-toggle"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Menüyü aç"
          >
            <span className={`hamburger ${mobileMenuOpen ? "open" : ""}`}>
              <span></span>
              <span></span>
              <span></span>
            </span>
          </button>
        </div>
      </div>

      {/* Category navigation */}
      <nav className={`header-categories ${mobileMenuOpen ? "mobile-open" : ""}`} id="category-nav">
        <div className="container header-categories-inner">
          <a href="#kategoriler" className="header-cat-link" id="nav-all">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
            </svg>
            Tüm Kategoriler
          </a>
          <a href="#kategoriler" className="header-cat-link">Elektronik</a>
          <a href="#kategoriler" className="header-cat-link">Giyim</a>
          <a href="#kategoriler" className="header-cat-link">Ev & Yaşam</a>
          <a href="#kategoriler" className="header-cat-link">Spor</a>
          <a href="#kategoriler" className="header-cat-link">Kişisel Bakım</a>
          <a href="#kategoriler" className="header-cat-link">Anne & Bebek</a>
          <a href="#kategoriler" className="header-cat-link hide-mobile">Mutfak</a>
          <a href="#kategoriler" className="header-cat-link hide-mobile">Ayakkabı</a>
          <a href="#kategoriler" className="header-cat-link hide-mobile">Kamp</a>
        </div>
      </nav>
    </header>
  );
}

export default Header;

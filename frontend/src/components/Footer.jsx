import React from "react";

function Footer() {
  return (
    <footer className="site-footer" id="site-footer">
      <div className="container">
        <div className="footer-grid">
          {/* Brand column */}
          <div className="footer-brand">
            <div className="footer-logo">
              <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="8" fill="#FF6000" />
                <path d="M8 22L16 10L24 22H8Z" fill="white" opacity="0.9" />
                <circle cx="16" cy="18" r="3" fill="white" />
              </svg>
              <span>AI-Market</span>
            </div>
            <p className="footer-desc">
              Yapay zeka destekli akıllı alışveriş platformu. Doğal dil ile ürün arayın, kişiselleştirilmiş öneriler alın.
            </p>
            <div className="footer-social">
              <a href="#" className="footer-social-link" title="Twitter" id="social-twitter">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                </svg>
              </a>
              <a href="#" className="footer-social-link" title="Instagram" id="social-instagram">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
                  <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
                  <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
                </svg>
              </a>
              <a href="#" className="footer-social-link" title="LinkedIn" id="social-linkedin">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                </svg>
              </a>
            </div>
          </div>

          {/* Links columns */}
          <div className="footer-links-col">
            <h4>Kurumsal</h4>
            <a href="#">Hakkımızda</a>
            <a href="#">Kariyer</a>
            <a href="#">Basın</a>
            <a href="#">Blog</a>
          </div>

          <div className="footer-links-col">
            <h4>Müşteri Hizmetleri</h4>
            <a href="#">Yardım Merkezi</a>
            <a href="#">İade & Değişim</a>
            <a href="#">Kargo Takibi</a>
            <a href="#">İletişim</a>
          </div>

          <div className="footer-links-col">
            <h4>Yasal</h4>
            <a href="#">Gizlilik Politikası</a>
            <a href="#">Kullanım Koşulları</a>
            <a href="#">KVKK Aydınlatma</a>
            <a href="#">Çerez Politikası</a>
          </div>
        </div>

        <div className="footer-bottom">
          <p>© 2026 AI-Market. Tüm hakları saklıdır. Bitirme Projesi.</p>
          <div className="footer-bottom-badges">
            <span className="footer-badge">🔒 Güvenli Alışveriş</span>
            <span className="footer-badge">🚚 Hızlı Kargo</span>
            <span className="footer-badge">💳 Güvenli Ödeme</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default Footer;

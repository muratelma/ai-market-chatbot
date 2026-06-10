import React, { useState, useRef, useEffect } from "react";

function Chatbot({ isOpen, onToggle, initialQuery }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    {
      sender: "bot",
      text: "Merhaba! 👋 Ben AI-Market alışveriş asistanıyım. Size nasıl yardımcı olabilirim? Aradığınız ürünü doğal bir cümleyle yazabilirsiniz.",
      products: [],
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [needsClarification, setNeedsClarification] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const hasHandledInitialQuery = useRef(false);

  // Auto scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Handle initial query from category/search
  useEffect(() => {
    if (initialQuery && isOpen && !hasHandledInitialQuery.current) {
      hasHandledInitialQuery.current = true;
      setInput(initialQuery);
      // Auto-send after a brief delay
      setTimeout(() => {
        sendMessage(initialQuery);
      }, 300);
    }
  }, [initialQuery, isOpen]);

  // Reset the flag when initialQuery changes
  useEffect(() => {
    hasHandledInitialQuery.current = false;
  }, [initialQuery]);

  const isNewSearchRequest = (text) => {
    const q = text.toLowerCase();
    const newRequestWords = [
      "öner", "öneri", "tavsiye", "ne alayım",
      "ne alabilirim", "arıyorum", "istiyorum",
    ];
    return newRequestWords.some((word) => q.includes(word));
  };

  const sendMessage = async (overrideText) => {
    const userQuery = (overrideText || input).trim();
    if (!userQuery || loading) return;

    const shouldCombineWithPrevious =
      pendingQuery && !isNewSearchRequest(userQuery);

    const queryToSend = shouldCombineWithPrevious
      ? `${pendingQuery} ${userQuery}`
      : userQuery;

    setMessages((prev) => [
      ...prev,
      { sender: "user", text: userQuery, products: [] },
    ]);

    setInput("");
    setLoading(true);

    try {
      const response = await fetch("http://127.0.0.1:8000/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: queryToSend }),
      });

      const data = await response.json();

      await new Promise((resolve) => setTimeout(resolve, 400));

      setMessages((prev) => [
        ...prev,
        {
          sender: "bot",
          text: data.answer,
          products: data.products || [],
        },
      ]);

      const clarificationNeeded = data.needs_clarification || false;
      setNeedsClarification(clarificationNeeded);

      if (clarificationNeeded) {
        setPendingQuery(queryToSend);
      } else {
        setPendingQuery("");
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          sender: "bot",
          text: "Bağlantı hatası oluştu. Lütfen backend API'nin çalıştığını kontrol edin ve tekrar deneyin. 🔌",
          products: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = () => sendMessage();

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <>
      {/* Launcher button — bottom-right */}
      <button
        className={`chatbot-launcher ${isOpen ? "chatbot-launcher-hidden" : ""}`}
        onClick={onToggle}
        id="chatbot-launcher"
        aria-label="Alışveriş asistanını aç"
      >
        <div className="chatbot-launcher-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <div className="chatbot-launcher-pulse"></div>
      </button>

      {/* Chat window */}
      <div className={`chatbot-window ${isOpen ? "chatbot-window-open" : ""}`} id="chatbot-window">
        {/* Header */}
        <div className="chatbot-header">
          <div className="chatbot-header-info">
            <div className="chatbot-avatar">
              <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="8" fill="white" fillOpacity="0.2" />
                <path d="M8 22L16 10L24 22H8Z" fill="white" opacity="0.9" />
                <circle cx="16" cy="18" r="3" fill="white" />
              </svg>
            </div>
            <div>
              <h3 className="chatbot-header-title">AI-Market Asistan</h3>
              <span className="chatbot-header-status">
                <span className="chatbot-status-dot"></span>
                Çevrimiçi
              </span>
            </div>
          </div>
          <button
            className="chatbot-close-btn"
            onClick={onToggle}
            id="chatbot-close"
            aria-label="Asistanı kapat"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Messages area */}
        <div className="chatbot-messages" id="chatbot-messages">
          {messages.map((msg, index) => (
            <div key={index} className={`chatbot-msg chatbot-msg-${msg.sender}`}>
              {msg.sender === "bot" && (
                <div className="chatbot-msg-avatar">🤖</div>
              )}
              <div className="chatbot-msg-content">
                <div className={`chatbot-bubble chatbot-bubble-${msg.sender}`}>
                  {msg.text}
                </div>

                {/* Product cards */}
                {msg.products && msg.products.length > 0 && (
                  <div className="chatbot-products">
                    {msg.products.map((product, idx) => (
                      <div className="chatbot-product-card" key={idx}>
                        <div className="chatbot-product-top">
                          <div className="chatbot-product-emoji">
                            {product.image || "🛍️"}
                          </div>
                          <div className="chatbot-product-match">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                            </svg>
                            {product.match} Uyum
                          </div>
                        </div>

                        <h4 className="chatbot-product-name">{product.name}</h4>

                        <div className="chatbot-product-meta">
                          {product.tags && product.tags[0] && (
                            <span className="chatbot-product-meta-item">
                              📁 {product.tags[0]}
                              {product.tags[1] && ` › ${product.tags[1]}`}
                            </span>
                          )}
                          {product.tags && product.tags[3] && (
                            <span className="chatbot-product-meta-item">
                              🏷️ {product.tags[3]}
                            </span>
                          )}
                        </div>

                        <p className="chatbot-product-desc">
                          {product.description}
                        </p>

                        <div className="chatbot-product-bottom">
                          <span className="chatbot-product-price">
                            {product.price}
                          </span>
                          <span className="chatbot-product-rating">
                            ⭐ {product.rating}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="chatbot-msg chatbot-msg-bot">
              <div className="chatbot-msg-avatar">🤖</div>
              <div className="chatbot-msg-content">
                <div className="chatbot-bubble chatbot-bubble-bot chatbot-loading">
                  <div className="chatbot-typing">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  Ürünler aranıyor...
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="chatbot-input-area" id="chatbot-input-area">
          <div className="chatbot-input-wrapper">
            <input
              ref={inputRef}
              type="text"
              className="chatbot-input"
              id="chatbot-input"
              value={input}
              disabled={loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                needsClarification
                  ? "Cevabınızı yazın..."
                  : "Ürün ihtiyacınızı yazın..."
              }
            />
            <button
              className="chatbot-send-btn"
              id="chatbot-send"
              onClick={handleSendMessage}
              disabled={loading || !input.trim()}
              aria-label="Gönder"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
          <div className="chatbot-input-hint">
            Örn: "200 TL altı koşu ayakkabısı" veya "bebek için organik ürünler"
          </div>
        </div>
      </div>
    </>
  );
}

export default Chatbot;

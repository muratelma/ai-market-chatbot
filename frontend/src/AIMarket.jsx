import React, { useState } from "react";

function AIMarket() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    {
      sender: "bot",
      text: "Merhaba! Size nasıl yardımcı olabilirim?",
      products: [],
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [needsClarification, setNeedsClarification] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");

  const isNewSearchRequest = (text) => {
    const q = text.toLowerCase();

    const newRequestWords = [
      "öner",
      "öneri",
      "tavsiye",
      "ne alayım",
      "ne alabilirim",
      "arıyorum",
      "istiyorum",
    ];

    return newRequestWords.some((word) => q.includes(word));
  };

  const handleSendMessage = async () => {
    if (!input.trim() || loading) return;

    const userQuery = input.trim();

    const shouldCombineWithPrevious =
      pendingQuery && !isNewSearchRequest(userQuery);

    const queryToSend = shouldCombineWithPrevious
      ? `${pendingQuery} ${userQuery}`
      : userQuery;

    setMessages((prev) => [
      ...prev,
      {
        sender: "user",
        text: userQuery,
        products: [],
      },
    ]);

    setInput("");
    setLoading(true);

    try {
      const response = await fetch("http://127.0.0.1:8000/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: queryToSend }),
      });

      const data = await response.json();

      await new Promise((resolve) => setTimeout(resolve, 500));

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
          text: "Backend'e bağlanamadım. Lütfen API'nin çalıştığını kontrol edin.",
          products: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
};

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(to bottom right, #020617, #0f172a, #1e293b)",
        color: "white",
        fontFamily: "Arial, sans-serif",
        padding: "40px",
      }}
    >
      <div style={{ maxWidth: "900px", margin: "0 auto", textAlign: "center" }}>
        <h1 style={{ fontSize: "42px", marginBottom: "12px" }}>AI-Market</h1>
        <p style={{ color: "#cbd5e1", fontSize: "18px" }}>
          Akıllı Ürün Öneri ve Alışveriş Asistanı
        </p>

        <div
          style={{
            marginTop: "40px",
            background: "rgba(15, 23, 42, 0.75)",
            border: "1px solid #334155",
            borderRadius: "20px",
            padding: "28px",
          }}
        >
          <h2>Chatbot Demo</h2>
          <p style={{ color: "#94a3b8" }}>
            Sağ alttaki butona basarak AI-Market alışveriş asistanını açabilirsiniz.
          </p>
        </div>
      </div>

      {/* Chatbot açma butonu */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          style={{
            position: "fixed",
            right: "28px",
            bottom: "28px",
            width: "70px",
            height: "70px",
            borderRadius: "50%",
            border: "none",
            background: "linear-gradient(to right, #06b6d4, #2563eb)",
            color: "white",
            fontSize: "30px",
            cursor: "pointer",
            boxShadow: "0 12px 30px rgba(0,0,0,0.45)",
            zIndex: 999,
          }}
        >
          💬
        </button>
      )}

      {/* Chatbot kutusu */}
      {isOpen && (
        <div
          style={{
            position: "fixed",
            right: "28px",
            bottom: "28px",
            width: "390px",
            maxWidth: "calc(100vw - 40px)",
            height: "620px",
            maxHeight: "calc(100vh - 60px)",
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: "22px",
            boxShadow: "0 18px 50px rgba(0,0,0,0.55)",
            overflow: "hidden",
            zIndex: 1000,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "18px",
              background: "linear-gradient(to right, #1d4ed8, #06b6d4)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <h3 style={{ margin: 0, fontSize: "20px" }}>AI-Market</h3>
              <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#dbeafe" }}>
                Akıllı alışveriş asistanı
              </p>
            </div>

            <button
              onClick={() => setIsOpen(false)}
              style={{
                background: "rgba(255,255,255,0.2)",
                border: "none",
                color: "white",
                width: "34px",
                height: "34px",
                borderRadius: "50%",
                cursor: "pointer",
                fontSize: "18px",
              }}
            >
              ×
            </button>
          </div>

          {/* Mesaj alanı */}
          <div
            style={{
              flex: 1,
              padding: "16px",
              overflowY: "auto",
              background: "#020617",
            }}
          >
            {messages.map((msg, index) => (
              <div key={index}>
                <div
                  style={{
                    background: msg.sender === "user" ? "#5b00e8" : "#1e293b",
                    color: "white",
                    padding: "12px 14px",
                    borderRadius: "14px",
                    marginBottom: "12px",
                    fontSize: "14px",
                    lineHeight: "1.5",
                    marginLeft: msg.sender === "user" ? "50px" : "0",
                    marginRight: msg.sender === "bot" ? "50px" : "0",
                    textAlign: msg.sender === "user" ? "right" : "left",
                  }}
                >
                  {msg.text}
                </div>

                {msg.products &&
                  msg.products.map((product, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: "linear-gradient(to bottom right, #1e293b, #0f172a)",
                        border: "1px solid #334155",
                        borderRadius: "16px",
                        padding: "14px",
                        marginBottom: "12px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: "8px",
                        }}
                      >
                        <div style={{ fontSize: "28px" }}>
                          {product.image || "🛍️"}
                        </div>

                        <div
                          style={{
                            background: "linear-gradient(to right, #22c55e, #10b981)",
                            color: "white",
                            padding: "5px 9px",
                            borderRadius: "999px",
                            fontSize: "12px",
                            fontWeight: "bold",
                          }}
                        >
                          {product.match} Uyum
                        </div>
                      </div>

                      <h4 style={{ margin: "6px 0", fontSize: "17px" }}>
                        {product.name}
                      </h4>

                      <p
                        style={{
                          margin: "8px 0",
                          color: "#cbd5e1",
                          fontSize: "13px",
                          lineHeight: "1.4",
                        }}
                      >
                        {product.description}
                      </p>

                      <div style={{ marginTop: "10px" }}>
                        {(product.tags || []).map((tag, tagIndex) => (
                          <span
                            key={tagIndex}
                            style={{
                              display: "inline-block",
                              background: "#334155",
                              color: "#e2e8f0",
                              padding: "5px 8px",
                              borderRadius: "999px",
                              fontSize: "11px",
                              marginRight: "6px",
                              marginBottom: "6px",
                            }}
                          >
                            {tag}
                          </span>
                        ))}
                      </div>

                      <div
                        style={{
                          marginTop: "10px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <strong style={{ color: "#22d3ee", fontSize: "18px" }}>
                          {product.price}
                        </strong>

                        <span style={{ color: "#94a3b8", fontSize: "13px" }}>
                          ⭐ {product.rating}
                        </span>
                      </div>
                    </div>
                  ))}
              </div>
            ))}

            {loading && (
              <div
                style={{
                  background: "#1e293b",
                  color: "#94a3b8",
                  padding: "12px",
                  borderRadius: "14px",
                  marginBottom: "12px",
                  fontSize: "14px",
                }}
              >
                Ürünler aranıyor...
              </div>
            )}
          </div>

          {/* Input alanı */}
          <div
            style={{
              padding: "14px",
              borderTop: "1px solid #334155",
              background: "#0f172a",
              display: "flex",
              gap: "10px",
            }}
          >
            <input
              type="text"
              value={input}
              disabled={loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleSendMessage();
                }
              }}
              placeholder="Ürün ihtiyacınızı yazın..."
              style={{
                flex: 1,
                padding: "12px",
                borderRadius: "12px",
                border: "1px solid #475569",
                background: "#1e293b",
                color: "white",
                outline: "none",
                fontSize: "14px",
              }}
            />

            <button
              onClick={handleSendMessage}
              disabled={loading}
              style={{
                padding: "12px 16px",
                borderRadius: "12px",
                border: "none",
                background: loading
                  ? "#64748b"
                  : "linear-gradient(to right, #06b6d4, #2563eb)",
                color: "white",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: "bold",
              }}
            >
              {loading ? "..." : "Ara"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default AIMarket;
import React, { useState, useCallback } from "react";
import Header from "./components/Header";
import HeroBanner from "./components/HeroBanner";
import Categories from "./components/Categories";
import FeaturedProducts from "./components/FeaturedProducts";
import Footer from "./components/Footer";
import Chatbot from "./components/Chatbot";
import "./App.css";

function App() {
  const [chatbotOpen, setChatbotOpen] = useState(false);
  const [chatbotQuery, setChatbotQuery] = useState("");

  const openChatbotWithQuery = useCallback((query) => {
    setChatbotQuery(query);
    setChatbotOpen(true);
  }, []);

  const handleSearchSubmit = useCallback((query) => {
    openChatbotWithQuery(query);
  }, [openChatbotWithQuery]);

  const handleCategoryClick = useCallback((categoryName) => {
    openChatbotWithQuery(`${categoryName} kategorisinde ürün öner`);
  }, [openChatbotWithQuery]);

  const handleHeroCta = useCallback(() => {
    setChatbotOpen(true);
  }, []);

  const handleChatbotToggle = useCallback(() => {
    setChatbotOpen((prev) => !prev);
    if (chatbotOpen) {
      setChatbotQuery("");
    }
  }, [chatbotOpen]);

  return (
    <div className="app">
      <Header onSearchSubmit={handleSearchSubmit} />

      <main className="main-content">
        <HeroBanner onCtaClick={handleHeroCta} />
        <Categories onCategoryClick={handleCategoryClick} />
        <FeaturedProducts />
      </main>

      <Footer />

      <Chatbot
        isOpen={chatbotOpen}
        onToggle={handleChatbotToggle}
        initialQuery={chatbotQuery}
      />
    </div>
  );
}

export default App;
"""
Manual test script for the Ollama intelligence layer.

Sends each test query to the /search endpoint and reports:
- original query
- normalized query
- whether Ollama was used
- whether fallback was used
- top product result or clarification/no-result
- response source
"""

import json
import urllib.request

API_URL = "http://127.0.0.1:8000/search"

TEST_CASES = [
    "papuç lazım",
    "pabuç bakıyorum",
    "şarjım dışarıda bitiyor",
    "telefonum hemen bitiyor",
    "saçım hemen yağlanıyor",
    "kepek var",
    "kampda yemek yapacağım",
    "kafa feneri lazım",
    "arabada şarj",
    "çadırın içine ışık",
    "ev kendi süpürsün",
    "2000 TL altında erkek ürün",
    "uzay mekiği",
]


def search(query, session_id=None):
    payload = {"query": query}
    if session_id:
        payload["session_id"] = session_id

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def print_result(query, result, label=""):
    prefix = f"[{label}] " if label else ""
    print(f"\n{'=' * 80}")
    print(f"{prefix}Sorgu: {query}")
    print(f"  Original:    {result.get('original_query', 'N/A')}")
    print(f"  Normalized:  {result.get('normalized_query', 'N/A')}")
    print(f"  Confidence:  {result.get('normalization_confidence', 'N/A')}")
    print(f"  Ollama used: {result.get('ollama_used', 'N/A')}")
    print(f"  Fallback:    {result.get('ollama_fallback_reason', 'N/A')}")
    print(f"  Source:      {result.get('response_source', 'N/A')}")
    print(f"  Session:     {result.get('session_id', 'N/A')}")
    print(f"  Answer:      {result.get('answer', 'N/A')}")

    if result.get("needs_clarification"):
        print(f"  ⚡ Clarification: {result.get('follow_up_question', 'N/A')}")

    products = result.get("products", [])
    if products:
        print(f"  📦 Top result: {products[0]['name']} | {products[0]['price']} | {products[0]['match']}")
        if len(products) > 1:
            print(f"  📦 #2:         {products[1]['name']} | {products[1]['price']} | {products[1]['match']}")
    elif not result.get("needs_clarification"):
        print("  ❌ No products found")


def main():
    print("=" * 80)
    print("AI-Market Ollama Intelligence Layer — Manual Tests")
    print("=" * 80)

    # ---- Part 1: Individual queries ----
    print("\n\n🔹 PART 1: Individual Queries")
    for query in TEST_CASES:
        try:
            result = search(query)
            print_result(query, result)
        except Exception as e:
            print(f"\n{'=' * 80}")
            print(f"Sorgu: {query}")
            print(f"  ❌ ERROR: {e}")

    # ---- Part 2: Follow-up conversation test ----
    print("\n\n🔹 PART 2: Follow-up Conversation Test")
    print("-" * 80)

    # Test 1: Clarification follow-up
    print("\n📝 Conversation 1: 2000 TL altında erkek ürün → papuç olsun")
    try:
        r1 = search("2000 TL altında erkek ürün")
        print_result("2000 TL altında erkek ürün", r1, "Turn 1")
        session_id = r1.get("session_id")

        r2 = search("papuç olsun", session_id=session_id)
        print_result("papuç olsun", r2, "Turn 2 (follow-up)")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

    # Test 2: Camp follow-up
    print("\n📝 Conversation 2: kamp için bir şey lazım → yemek yapmalık")
    try:
        r1 = search("kamp için bir şey lazım")
        print_result("kamp için bir şey lazım", r1, "Turn 1")
        session_id = r1.get("session_id")

        r2 = search("yemek yapmalık", session_id=session_id)
        print_result("yemek yapmalık", r2, "Turn 2 (follow-up)")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

    print("\n" + "=" * 80)
    print("✅ Manual tests complete.")


if __name__ == "__main__":
    main()

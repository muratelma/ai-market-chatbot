import json
import urllib.request

API_URL = "http://127.0.0.1:8000/search"

test_queries = [
    "kamp için gece ışık lazım",
    "kamp için uyku ürünü lazım",
    "kamp için yemek yapacak bir şey lazım",
    "telefon için taşınabilir şarj lazım",
    "1500tl üstünde ayakkabı",
    "1000den 2000e kadar ayakkabı",
    "yağmurlu havalar için kadın ayakkabı",
    "kadın yazlık elbise",
    "özel gün için kadın elbise",
    "soğuk havalar için mont",
    "bilgisayar için kablosuz mouse",
    "oyun için klavye",
    "spor için akıllı saat",
    "1000 ile 2000 arası elektronik",
    "1000tl altında kadın",
]


def search(query):
    data = json.dumps({"query": query}).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    for query in test_queries:
        print("\n" + "=" * 80)
        print("Sorgu:", query)

        try:
            result = search(query)

            print("Cevap:", result.get("answer"))
            print("Parsed Query:", result.get("parsed_query"))

            products = result.get("products", [])

            if not products:
                print("Ürün bulunamadı.")
                continue

            print("\nÜrünler:")
            for product in products:
                print(
                    f"- {product['match']} | {product['name']} | "
                    f"{product['price']} | {product['tags']}"
                )

        except Exception as e:
            print("Hata:", e)


if __name__ == "__main__":
    main()
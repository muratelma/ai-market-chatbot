# INTENDED vs IMPLEMENTED — AI‑Market Chatbot Audit

> Static audit of the live pipeline against the 19 user‑specified queries.
> No backend was run; tracing is done by reading
> `main.py`, `chat_intent.py`, `chat_normalizer.py`, `query_parser.py`,
> `response_planner.py`, `response_rewriter.py`, `search_engine.py`
> together with `products.csv` / `taxonomy.csv`.
> Where Ollama is involved the analysis assumes its two extreme states
> (working / unavailable) and flags only divergences from the user’s
> intended behavior.

---

## 0. How the pipeline really decides things (one‑page mental model)

`main.py` → `/search`:

1. `classify_intent()` (chat_intent.py:253) — rules‑first. Fires Ollama
   **only when `word_count <= 2` AND no product signal**. Greeting / help /
   thanks / goodbye / wellbeing → returns immediately, **no search**.
2. `nonsense` + confidence ≥ 0.7 → fixed "katalogda yok" text, no search.
3. `normalize_query()` — Ollama; falls back to original query when Ollama
   is unavailable or confidence < `OLLAMA_CONFIDENCE_THRESHOLD`.
4. `parse_query()` — alias rules → explicit category match → explicit
   sub_category / product_type match → features → contexts → taxonomy
   semantic match → `normalize_category_consistency()` → **broad‑word
   strip** (`ürün|urun|malzeme|eşya|esya|şey|sey|ne kullanabilirim`).
5. `build_response_plan()` — pure rules:
   * No signal → `clarification_only`
   * `product_type` or `sub_category` set → `focused_search`
   * Else `main_category` / `contexts` / `context_area` → `broad_search`
     (`diversify_results=True`)
   * Else `clarification_only`
   * `should_ask_followup = not query_has_details(...)`
6. `get_clarification_response()` (query_parser.py:994) — would normally
   redirect very general queries to a clarification‑only response, **but
   `main.py:250` overrides it for `broad_search` and `focused_search`**.
7. `apply_filters` → `semantic_search` → `diversify_results` (only when
   `broad_search`) → `rewrite_response()`.

Three load‑bearing observations from the code:

* `_build_followup_question`, `_BROAD_FOLLOWUP_QUESTIONS`,
  `_CATEGORY_BROWSE_FOLLOWUP`, `_PROBLEM_BROAD_FOLLOWUP_TEMPLATE`,
  `_DEFAULT_BROAD_FOLLOWUP` in `response_planner.py:158‑232` are **dead
  code** — only `_build_soft_followup_question` (line 320) is wired into
  the plan. The richer kamp/spor/ev/bebek follow‑ups never reach the user.
* `query_has_details` (response_planner.py:239‑317) suppresses the
  follow‑up question whenever any feature outside the category word‑set
  remains. Because `FEATURE_SYNONYMS["spor"] = ["spor", "rahat"]`,
  the synthetic `rahat` token reliably defeats the follow‑up for any
  "spor"‑shaped broad query.
* `filler_words` (response_planner.py:296) contains the lemma `ürün` but
  **not the inflected form `ürünü`** — so `"giyim ürünü öner"` is treated
  as "user gave detail" while `"giyim ürün öner"` would not be.

These three explain most of the wrong outcomes below.

---

## 1. Per‑query trace (alphabetical inside each behavior block)

For every query: 1 original → 2 normalized → 3 parsed → 4 mode → 5 products?
→ 6 top 5 names+types → 7 wording check → 8 file/function if wrong.

Top‑5 product names cannot be determined without running FAISS — flagged
as `(needs runtime)`. The product **type composition** can still be
inferred from the candidate pool produced by `apply_filters`.

---

### A · Chat replies (no search expected)

#### 1. `merhaba`
1. `merhaba`
2. (skipped — intent classifier matches first)
3. `parsed_query`: `{}` (search pipeline not entered)
4. `response_mode`: not set; `intent=greeting`
5. Products returned? **No** ✅
6. Top 5: n/a
7. Wording: `GREETING_RESPONSES[0]` — "Merhaba! 👋 Ben AI‑Market…" ✅
8. Correct. (chat_intent.py:293)

#### 2. `nasılsın`
1. `nasılsın`
2. n/a
3. `{}`
4. `intent=wellbeing`
5. **No** ✅
6. n/a
7. `WELLBEING_RESPONSES[0]` ✅
8. Correct. (chat_intent.py:311)

#### 3. `sağol`
1. `sağol`
2. n/a
3. `{}`
4. `intent=thanks`
5. **No** ✅
6. n/a
7. `THANKS_RESPONSES[0]` ✅
8. Correct. (chat_intent.py:301; `sağol` is in `_THANKS_EXACT`)

#### 4. `ne yapabilirsin`
1. `ne yapabilirsin`
2. n/a
3. `{}`
4. `intent=help`
5. **No** ✅
6. n/a
7. `HELP_RESPONSES[0]` ✅
8. Correct. (chat_intent.py:71, `_HELP_PATTERNS`)

> All four chat queries take the **fast deterministic path**; Ollama is
> not consulted. Behavior matches intent exactly.

---

### B · Direct product queries (product cards + optional soft follow‑up)

#### 5. `elbise öner`
1. `elbise öner`
2. Ollama normalized → most likely `"elbise"` (system prompt rule 7
   keeps it close); falls back to original when Ollama down.
3. `parsed_query`:
   * main_category = **Giyim** (inferred via `infer_main_category_from_parsed`)
   * sub_category = **Elbise** (exact match)
   * product_type = `None` — taxonomy semantic match would surface
     `Abiye` / `Yazlık` but is suppressed by query_parser.py:619‑622
     (`explicit_sub_category set, remaining_query < 3 chars`)
   * features = `[]`, contexts = `[]`, target_group = `None`,
     min_price / max_price = `None`
4. `response_mode` = **focused_search** (planner step 2)
5. Products? **Yes** ✅
6. Top 5 (needs runtime). Pool = all `sub_category=Elbise` rows
   (Abiye, Mini Elbise, Plaj Elbisesi, Triko Elbise, Yazlık). Expected
   mixed types within Elbise.
7. Wording: `should_ask_followup = True` (no detail beyond category;
   `öner` is in `filler_words`). Soft follow‑up branch‑1 fires →
   "Daha iyi bir öneri için elbiseyi günlük kullanım mı yoksa özel bir
   gün için mi arıyorsunuz?…" ✅ matches expected behavior.
8. Correct.

#### 6. `şampuan öner`
1. `şampuan öner`
2. Ollama → likely unchanged `"şampuan"`.
3. main_category = **Kişisel Bakım** (via product_type → normalize),
   sub_category = **Saç Bakımı** (via product_type only‑1‑sub branch),
   product_type = **Şampuan**, features = `[]`, contexts = `[]`.
4. `response_mode` = **focused_search**.
5. Products? **Yes** ✅
6. (needs runtime) — strict filter pool of Şampuan rows.
7. `should_ask_followup = True` → soft follow‑up branch‑3
   (Şampuan): "Daha iyi bir şampuan önerisi için saç tipinizi ve saç
   problemi…" ✅
8. Correct.

#### 7. `tencere öner`
1. `tencere öner`
2. Likely unchanged.
3. product_type = **Tencere Seti** (prefix fallback in
   `find_value_from_column`, query_parser.py:329‑370 — `"tencere"`
   matches first word of multi‑word PT). main_category resolves to
   the **mode** main_category of "Tencere Seti" rows, which spans
   **Kamp / Mutfak** — the mode is **Mutfak** (more rows). sub_category
   resolves to `"Pişirme"` only if PT appears under exactly one
   sub_category; here PT appears under both "Pişirme" and "Servis", so
   `sub_category` is cleared (response_planner.py:902).
4. `response_mode` = **focused_search** (PT present).
5. Products? **Yes** ✅
6. (needs runtime) — Tencere Seti rows ranked by semantic + bonus.
7. `should_ask_followup = True` (no extra detail) → soft follow‑up
   fallback branch (Tencere isn’t in the 5 hard‑coded branches) →
   generic "Daha net öneri için kullanım amacı, fiyat aralığı veya
   tercih ettiğiniz özellikleri yazabilirsiniz." ⚠ Generic, not
   tencere‑specific, but acceptable.
8. Minor: generic fallback wording. Source:
   `response_planner._build_soft_followup_question` (line 320).

#### 8. `kulaklık öner`
1. `kulaklık öner`
2. Likely `"kulaklık"`.
3. product_type = **Kulaklık** (exact). main_category = **Elektronik**,
   sub_category = **Ses** (single‑sub branch). features = `[]`.
4. `response_mode` = **focused_search**.
5. Products? **Yes** ✅
6. (needs runtime). Likely overrepresented by `Kulaklık` rows; Bluetooth/
   ANC variants etc.
7. `should_ask_followup = True` → soft follow‑up branch‑5 (Kulaklık):
   "Daha iyi bir kulaklık önerisi için kablosuz, oyuncu veya gürültü
   önleme (ANC)…" ✅
8. Correct.

---

### C · Detailed product queries (focused, no generic follow‑up)

#### 9. `özel gün için kadın elbise öner`
1. `özel gün için kadın elbise öner`
2. Ollama likely keeps phrase; fallback unchanged.
3. main_category = **Giyim**, sub_category = **Elbise**,
   target_group = **Kadın**, product_type = **Abiye** (taxonomy text
   for `Abiye` is "özel gün davet düğün nişan şık uzun abiye gece
   elbisesi" — strongest match). features = `[]`, contexts = `[]`.
4. `response_mode` = **focused_search**.
5. Products? **Yes** ✅
6. (needs runtime) — Abiye rows.
7. `query_has_details`: target_group token `"kadın"` not in category
   words → `has_det = True`; usage phrase `"özel gün"` also matches
   (line 287). → `should_ask_followup = False`, no soft follow‑up
   appended ✅
8. Correct.

#### 10. `saç dökülmesi için şampuan öner`
1. `saç dökülmesi için şampuan öner`
2. Ollama → `"saç dökülmesi şampuanı"` or similar.
3. product_type = **Şampuan** (also reinforced by the `" için "`
   branch at query_parser.py:565). main_category = **Kişisel Bakım**,
   sub_category = **Saç Bakımı**, features = `["saç dökülmesi",
   "dökülme karşıtı", "güçlendirici"]`, contexts = `[]`,
   `user_problem = "saç dökülmesi"`.
4. `response_mode` = **focused_search**.
5. Products? **Yes** ✅
6. (needs runtime) — pool = Şampuan rows; bonus boosts items whose
   `features` contain "saç dökülmesi"/"dökülme karşıtı". Expected
   top entries include `Dökülme Karşıtı Şampuan`,
   `Dökülme Karşıtı Biotin Şampuan`, `Biotin Destekli Şampuan`.
7. features beyond category → `has_det = True` →
   `should_ask_followup = False` ✅ rewriter context includes
   `user_problem` so the assistant text says "Saç dökülmesi sorununa
   yönelik şampuan seçenekleri…" ✅
8. Correct.

#### 11. `1500 TL üstü yazlık spor ayakkabı`
(Not in the audit list; listed only in the user’s intent description.
The closest analogue is covered indirectly via `kuru cilt`/`kadın
elbise` — included here for completeness but **not scored**.)

---

### D · Broad problem queries

#### 12. `saç dökülmesi için ürün öner`
1. `saç dökülmesi için ürün öner`
2. Ollama prompt example‑line 80 turns this into
   `"saç dökülmesi için saç bakım ürünü"`; offline fallback keeps
   original.
3. With Ollama on (cleaned query loses `ürün/öner/için`):
   * `explicit_product_type = None`, `explicit_sub_category = None`.
   * `taxonomy_match` cleaned query = `"saç dökülmesi bakım"`; best
     match is **sub_category=Saç Bakımı** (its taxonomy text contains
     "saç dökülmesi") — but `Şampuan` PT text *also* contains
     "saç dökülmesi", so the outcome depends on FAISS ordering.
   * Broad‑word strip at query_parser.py:662 fires because `"ürünü"`/
     `"ürün"` is in the original `query` (the function reads `query`
     directly, not the normalized one — see line 664). It strips
     `product_type` **and** `sub_category` whenever the taxonomy was
     the source.
   * `infer_main_category_from_query_context`: no keyword matches
     (no `bebek`/`spor`/`kamp`…). main_category comes from the
     remaining `sub_category` (Saç Bakımı → Kişisel Bakım) only if the
     strip didn’t happen, otherwise from `taxonomy_match` (already
     dropped).
   * **Net effect**: parsed ends up with `main_category = "Kişisel
     Bakım"` (via `infer_main_category_from_parsed` *before* the strip;
     `normalize_category_consistency` runs *after* the strip in
     `parse_query`’s final pass) and `features = [saç dökülmesi,
     dökülme karşıtı, güçlendirici]`.
4. `response_mode` = **broad_search** (no PT/sub, has main_category;
   diversify=True).
5. Products? **Yes** ✅ count via filter pool = all 92 Kişisel Bakım
   rows; diversification then round‑robins across product_types.
6. (needs runtime) — bonus is small (no PT match), so semantic +
   feature bonus carry the ranking. Top of the unfiltered list should
   be Şampuan / Saç Losyonu / Saç Serumu / Saç Bakım Kürü; after
   diversification one per type, so slots 5 may pick up an unrelated
   Cilt/Ağız bakım item that happens to match semantically.
7. `should_ask_followup`: features (`dökülme karşıtı`, `güçlendirici`)
   are not subsets of category words → `has_det = True` →
   **no follow‑up**. The rewriter prompt path is fed `user_problem`,
   so the assistant text says "Saç dökülmesi sorununa yönelik…" ✅
   ⚠ Diversification may pull in non‑Saç Bakımı items at lower ranks.
8. Borderline. Two suspects if results look noisy:
   * `query_parser.py:662‑671` (broad‑word strip clears the
     `sub_category=Saç Bakımı` constraint that would have kept results
     tight).
   * `search_engine.diversify_results` round‑robins across all product
     types in the post‑bonus list.

#### 13. `kuru cilt için ürün öner`
1. `kuru cilt için ürün öner`
2. Likely unchanged or → `"kuru cilt için cilt bakım ürünü"`.
3. Same broad‑word strip path as #12. Final parsed:
   * main_category = **Kişisel Bakım** (inferred via taxonomy
     sub_category=Cilt Bakımı before strip).
   * sub_category = **None** (stripped by broad‑pattern).
   * product_type = **None**.
   * features = `["kuru cilt", "nemlendirici", "onarıcı"]`.
   * `user_problem = "kuru cilt"`.
4. `response_mode` = **broad_search**, diversify=True.
5. Products? **Yes** ✅
6. (needs runtime) — pool = 92 Kişisel Bakım rows; bonus boosts items
   tagged "nemlendirici". Likely top types include `Nemlendirici`,
   `Cilt Serumu`, `Vücut Losyonu`, `Yüz Maskesi`, `El Kremi`.
7. `should_ask_followup = False` (features beyond category) — no
   narrowing question shown. ⚠ Expected behavior allows showing
   products but the user said “problem‑based queries should return
   relevant products”; both intents are satisfied.
8. Acceptable.

---

### E · Broad category / use‑case queries (diversified + follow‑up)

#### 14. `spor için ürün öner`
1. `spor için ürün öner`
2. Likely unchanged.
3. * `extract_explicit_main_category`: `"spor"` is in
     `ambiguous_categories` (query_parser.py:426) → **skipped**.
   * features: `extract_features` keys include `"spor"` →
     features = `["spor", "rahat"]`.
   * contexts: `"spor"` → contexts = `["spor"]`.
   * taxonomy match: cleaned = `"spor"` → main_category=Spor (score
     high).
   * Broad‑word strip fires (`"ürün"` present) → if taxonomy returned
     a sub_category / product_type, it is cleared.
   * `infer_main_category_from_query_context("spor için ürün öner")`
     returns **"Spor"** → final `main_category = "Spor"`.
   * sub_category = `None`, product_type = `None`.
4. `response_mode` = **broad_search**, diversify=True,
   context_area = **spor**.
5. Products? **Yes** ✅
6. (needs runtime) — 75‑row pool; diversified across `Fitness`,
   `Egzersiz`, `Aksesuar`, `Outdoor`, `Yoga` etc. ✓ healthy spread.
7. `should_ask_followup` = ❌ **False**. Reason: in
   `query_has_details` feature loop, `"spor"` is in category_words but
   `"rahat"` (synthetic, injected by FEATURE_SYNONYMS["spor"]) is not
   → `has_det = True` → follow‑up is suppressed.
   The user explicitly expected a narrowing follow‑up here.
   The dead `_BROAD_FOLLOWUP_QUESTIONS["spor"]` would have been
   perfect — but it’s never called.
8. **Wrong wording**. Suspects:
   * `query_parser.FEATURE_SYNONYMS["spor"] = ["spor", "rahat"]`
     (line 27) — synthetic "rahat" defeats the planner’s detail check.
   * `response_planner.query_has_details` — too strict; treats any
     synonym‑injected feature as user detail.
   * `response_planner._BROAD_FOLLOWUP_QUESTIONS` / `_build_followup_question`
     are dead code; the soft fallback wording is generic.

#### 15. `kamp için ürün arıyorum`
1. `kamp için ürün arıyorum`
2. Likely unchanged.
3. * `extract_explicit_main_category`: `"kamp"` is ambiguous → skipped.
   * features = `[]` (`"kamp"` not in FEATURE_SYNONYMS).
   * contexts = `["kamp"]`.
   * taxonomy match: main_category = **Kamp**.
   * Broad strip: parsed.product_type / sub_category were never set →
     no‑op.
   * Final: main_category = **Kamp**, sub_category=None, product_type=None.
4. `response_mode` = **broad_search**, diversify=True,
   context_area = **kamp**.
5. Products? **Yes** ✅
6. (needs runtime) — 69‑row pool; diversified across Çadır, Uyku,
   Aydınlatma, Pişirme, Mobilya, Aksesuar.
7. `query_has_details`: contexts=`["kamp"]` is subset of category_words
   (`{"kamp"}`) → skip. Filler words swallow `"için"/"ürün"/"arıyorum"`
   → extra_words = `{}` → `has_det = False` → **follow‑up shown**.
   But the wording is the **generic fallback** from
   `_build_soft_followup_question` — kamp has no dedicated branch
   among the 5 hard‑coded ones (elbise/ayakkabı/şampuan/parfüm/
   kulaklık). The category‑specific kamp follow‑up
   ("Uyku, barınma, aydınlatma veya yemek hazırlama…") sitting in the
   **dead** `_BROAD_FOLLOWUP_QUESTIONS["kamp"]` would have been the
   right one.
   So: follow‑up is present ✅ but **generic** ⚠.
8. Partially correct. Dead code in `response_planner.py:158‑232`
   is the suspect; `_build_soft_followup_question` should hand off to
   `_build_followup_question` when no hard‑coded branch matches.

#### 16. `giyim ürünü öner`
1. `giyim ürünü öner`
2. Likely unchanged.
3. main_category = **Giyim** (explicit). sub_category=None,
   product_type=None.
4. `response_mode` = **broad_search**, diversify=True.
5. Products? **Yes** ✅ (64‑row pool; diversified).
6. (needs runtime) — top product_types likely Tişört, Gömlek, Mont,
   Pantolon, Sweatshirt.
7. `query_has_details`: `q_words = {"giyim","ürünü","öner"}` minus
   `category_words={"giyim"}` minus filler (`"öner"`, `"ürün"`, …) —
   **`"ürünü"` is not in filler_words**, only `"ürün"` is. →
   `extra_words = {"ürünü"}` → `has_det = True` → **no follow‑up**.
   The user expects a narrowing question. **Wrong wording.**
8. **Bug**: `response_planner.query_has_details` /
   `filler_words` set (line 296) needs the inflected forms
   (`"ürünü"`, `"ürüne"`, etc.) — or a stem/prefix check rather than
   a literal set. Same family of issue as #14.

---

### F · Too vague queries (clarification, no random products)

#### 17. `ürün öner`
1. `ürün öner`
2. Ollama either clarifies (likely confidence < threshold, depending on
   prompt) or falls back to original.
3. parse_query: all signals = `None`. `has_any_product_signal = False`.
4. `get_clarification_response` → `no_catalog_match = True`. Skips the
   planner branch (rewriter is called with `result_status="no_result"`).
5. Products? **No** ✅
6. n/a
7. Wording: rewriter prompt for `no_result` → "Maalesef aradığınız
   kriterlere uygun bir ürün bulunamadı. Farklı kelimelerle tekrar
   deneyebilirsiniz." or Ollama variant. **Not a clarification
   question.** The user explicitly wanted "Ask for clarification".
   ⚠ Wrong category of response.
8. **Bug**: `main.py:216` and `query_parser.get_clarification_response`
   send the `no_catalog_match` path to `result_status="no_result"`
   instead of to a clarification template.

#### 18. `bir şey lazım`
1. `bir şey lazım`
2. Ollama likely emits `needs_clarification = true` with question
   "Hangi tür ürün arıyorsunuz?" — if so, `main.py:162` returns
   the clarification path → wording **correct** ✅.
3. Without Ollama: parse_query yields `parsed = all None`
   (`"şey"`, `"lazım"`, `"bir"` are stripped by
   `clean_query_for_taxonomy`).
4. `no_catalog_match=True` → `no_result` path (same as #17).
5. Products? **No** ✅
6. n/a
7. With Ollama on → clarification question ✅.
   Without Ollama → "Maalesef aradığınız kriterlere uygun…" ⚠
   wrong tone.
8. Same suspect as #17 when Ollama unavailable. The fallback
   path conflates "no signal" with "no products".

#### 19. `ne almalıyım`
1. `ne almalıyım`
2. classify_intent: word_count = 2, no product signal → routes to
   Ollama (`chat_intent._classify_with_ollama`). Likely → `help` /
   `nonsense` / `product_search`. Each leads to a different response.
3. If Ollama down: default `INTENT_PRODUCT_SEARCH` → normalize step
   → parse step → no signals → `no_catalog_match=True` → `no_result`.
4. As above.
5. Products? **No** ✅
6. n/a
7. With Ollama on → may be classified as `help` (returns HELP_RESPONSES)
   or product_search (no_result template). Behavior is non‑deterministic
   and not a real clarification. ⚠
8. Same root cause as #17 / #18.

---

### G · No‑result / nonsense queries

#### 20. `uzay mekiği`
1. `uzay mekiği`
2. classify_intent: word_count = 2, no product signal → Ollama.
   Likely classified as `nonsense` (high confidence). Main.py:121
   short‑circuits with the "Maalesef bu tür bir ürün katalogumuzda
   bulunmuyor…" message.
3. `{}`
4. `intent=nonsense`
5. Products? **No** ✅
6. n/a
7. Wording matches intent ✅
8. Correct. Caveat: when Ollama is unavailable the message degrades to
   "no_result" template (still no products, slightly worse wording).

#### 21. `zihin okuma cihazı`
1. `zihin okuma cihazı`
2. word_count = 3 → **Ollama not consulted** (chat_intent.py:321 guard).
   Default → `INTENT_PRODUCT_SEARCH`.
3. parse_query: no main_category / sub / PT match. `"cihazı"` isn’t a
   feature; `"zihin"` / `"okuma"` aren’t in FEATURE_SYNONYMS or
   CONTEXT_KEYWORDS. taxonomy_match: cleaned ≈ `"zihin okuma cihazı"`,
   semantic similarity to every taxonomy row is low — typically below
   `TAXONOMY_MATCH_THRESHOLD` → None.
4. `has_any_product_signal = False` → `no_catalog_match=True`.
5. Products? **No** ✅
6. n/a
7. "Maalesef aradığınız kriterlere uygun bir ürün bulunamadı…" — fine.
8. Correct.

> Note: if `TAXONOMY_MATCH_THRESHOLD` is set too low (config default
> 0.45) some bizarre queries could squeak in. The
> `search_engine.semantic_search` nonsense guard
> (`max_score < 0.40` AND no hard filter) is a safety net for cases
> that *do* reach FAISS.

---

## 2. Summary tables

### 2.1 Correct behaviors

| Query | Why it works |
| --- | --- |
| merhaba / nasılsın / sağol / ne yapabilirsin | Hit deterministic intent tables before normalizer/search |
| elbise öner | focused_search + Elbise soft follow‑up branch |
| şampuan öner | focused_search + Şampuan soft follow‑up branch |
| kulaklık öner | focused_search + Kulaklık soft follow‑up branch |
| özel gün için kadın elbise öner | focused_search, `has_det=True`, no generic wording |
| saç dökülmesi için şampuan öner | focused_search with `user_problem` + features |
| uzay mekiği | nonsense intent → friendly fallback |
| zihin okuma cihazı | `no_catalog_match` → no products |

### 2.2 Wrong / partially wrong behaviors

| Query | Symptom | Severity |
| --- | --- | --- |
| tencere öner | Generic soft follow‑up wording (Tencere lacks a dedicated branch) | minor |
| saç dökülmesi için ürün öner | Broad‑word strip removes the Saç Bakımı constraint → broad_search across all Kişisel Bakım. Diversification can pull off‑topic items into the top 5. | moderate |
| spor için ürün öner | **No follow‑up question** (synthetic feature `rahat` defeats `has_det`); generic wording even if it fired | high |
| kamp için ürün arıyorum | Follow‑up fires but uses the **generic fallback** wording; the rich `_BROAD_FOLLOWUP_QUESTIONS["kamp"]` is dead code | moderate |
| giyim ürünü öner | **No follow‑up** because inflected `"ürünü"` is not in `filler_words` | moderate |
| ürün öner | Returns `no_result` template instead of a real **clarification question** | high |
| bir şey lazım | Same as `ürün öner` when Ollama unavailable | high |
| ne almalıyım | Non‑deterministic Ollama path; no genuine clarification template | moderate |

### 2.3 Files most responsible

| File / function | Issue |
| --- | --- |
| `backend/response_planner.py:158‑232` (`_BROAD_FOLLOWUP_QUESTIONS`, `_CATEGORY_BROWSE_FOLLOWUP`, `_PROBLEM_BROAD_FOLLOWUP_TEMPLATE`, `_DEFAULT_BROAD_FOLLOWUP`, `_build_followup_question`) | **Dead code** — never reached. Holds the wording the user actually wanted for kamp/spor/ev/bebek. |
| `backend/response_planner.py:296` (`filler_words`) | Lemma‑only set; misses inflections (`ürünü`, `ürüne`). |
| `backend/response_planner.py:239‑317` (`query_has_details`) | Counts any synonym‑injected feature (e.g. `rahat` from `spor`) as user detail → suppresses the follow‑up that the user explicitly expects. |
| `backend/query_parser.py:17‑63` (`FEATURE_SYNONYMS`) | The `"spor" → ["spor","rahat"]` injection is the proximate cause of the `spor` follow‑up suppression. |
| `backend/query_parser.py:662‑671` (broad‑word strip) | Removes `sub_category` along with `product_type` when the query contains `ürün`. Helpful for "spor için ürün öner" but lossy for "saç dökülmesi için ürün öner" where keeping `sub_category=Saç Bakımı` would tighten results. |
| `backend/main.py:215‑243` and `query_parser.get_clarification_response` `no_catalog_match` path | Sends "no signal" queries (`ürün öner`, `bir şey lazım`) through `result_status="no_result"` instead of a clarification template. |
| `backend/chat_intent.py:321‑328` (Ollama route only when `word_count ≤ 2`) | Three‑word nonsense like `zihin okuma cihazı` works because of the safety net downstream, but the gate also blocks legitimate three‑word clarification candidates (`ne almalıyım` borderline). |
| `backend/search_engine.diversify_results` | Round‑robin diversification is correct *for* broad_search but, combined with the broad‑word strip in `query_parser.py`, makes problem‑based queries leak into unrelated product types. |

---

## 3. Recommendation on the latest response‑behavior layer

The new layer is *almost* the right shape but has accumulated overlapping
mechanisms that overfit the gold queries. Concretely:

* The **deterministic intent router** (`chat_intent.py`) is doing real
  work and should stay.
* The **Ollama normalizer** is mostly invisible for the audit queries
  (most don’t need it) but earns its keep on examples like
  `"şarjım dışarıda bitiyor"` from the project overview. Keep, but stop
  letting it silently *drop* user detail via the broad‑word strip
  downstream.
* The **response planner** has two clean modes (`focused_search`,
  `broad_search`) that map well to the user’s mental model, but its
  body is half‑built: rich follow‑up wording exists yet only the
  generic `_build_soft_followup_question` is reachable. The
  `query_has_details` heuristic is too easy to confuse with synonyms
  and inflections.
* The **response rewriter** is fine in principle (it just narrates the
  plan), and the safeguard that re‑appends the follow‑up question if
  Ollama omits it (line 202‑206) is the right kind of defensive code.

**Verdict**: keep the layer; **simplify it** rather than rolling back.
Roll‑back would re‑introduce the older "always answer with build_answer"
behaviour and lose the clarification handling on legitimately vague
queries. The simplifications below are surgical.

---

## 4. Smallest safe next step

Do **one** thing, in this order, gated on the eval running green:

1. **Make the planner use the wording it already wrote.**
   In `response_planner._build_soft_followup_question`, after the five
   hard‑coded branches, fall back to `_build_followup_question(
   context_area, user_problem, main_category)` instead of returning
   the generic string. That single edit:
   * gives `kamp için ürün arıyorum` the proper kamp follow‑up,
   * gives `giyim ürünü öner` (if the follow‑up ever fires) the
     proper Giyim browse follow‑up,
   * resurrects the problem‑specific template for cases like
     `saç dökülmesi için ürün öner`.
   * touches zero filter / search code; the worst case is "different
     question wording" — easy to revert.

That one change resolves the wording side of #14 (`spor`), #15 (`kamp`)
and #16 (`giyim`) without touching `query_has_details` or the broad‑word
strip. The remaining bugs (follow‑up *suppression* for `spor / giyim`,
clarification‑vs‑no‑result for `ürün öner / bir şey lazım`) can each be
addressed in their own follow‑up commit, each behind the eval harness.

---

*End of audit. No source files were modified.*

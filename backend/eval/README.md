# Eval Harness

Bu klasor, backend parser/ranking degisikliklerini release oncesi olcmek icin yerel benchmark araclarini icerir.

## Gold Query Set

- Dosya: `gold_queries.json`
- Kapsam: 40 sorgu
- Etiketler:
  - `expected`: relevance olcumu icin beklenen intent
  - `expects_clarification`: takip sorusu beklenen sorgular
  - `expects_empty_result`: bos sonuc beklenen katalog-disi sorgular

## Calistirma

```bash
cd backend
./.venv/bin/python eval/run_eval.py --show-failures --output-json eval/results/baseline.json
```

Parser veya ranking degisiklikleri sonrasi ayni komutu tekrar calistirip JSON ciktilarini karsilastirin.

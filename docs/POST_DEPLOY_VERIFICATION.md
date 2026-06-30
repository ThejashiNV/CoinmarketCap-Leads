# Post-Deployment Verification

Run immediately after a deploy. Replace `$API` with your backend URL and `$WEB`
with the frontend URL.

```bash
API=https://<your-backend-host>
WEB=https://<your-frontend-host>
```

## 1. Backend health & metadata
```bash
curl -s $API/                       # 200, {"message":"Crypto Lead Enrichment API running", supported_platforms:[...4]}
curl -s $API/capabilities           # 200, all 4 platforms
curl -s "$API/capabilities?platform=defillama"   # 200, DeFiLlama descriptor
curl -s $API/status                 # 200, {"running":false, ...}
```
- [ ] `/` returns 200 with 4 supported platforms.
- [ ] `/capabilities` lists CoinMarketCap, CoinGecko, Coinranking, DeFiLlama.
- [ ] `/status` shows `running:false` on a fresh instance.

## 2. Category scraping (live)
```bash
curl -s "$API/categories?url=https://coinmarketcap.com/cryptocurrency-category/" | head -c 200
```
- [ ] Returns `status: ok` with a non-empty `categories` array.

## 3. End-to-end extraction (small)
Via the UI (preferred) or API:
```bash
curl -s -X POST $API/start-extraction \
  -H 'Content-Type: application/json' \
  -d '{"category_url":"https://defillama.com/raises","top_n":3,"mode":"recent","workers":2}'
# → {"status":"started", ...}
curl -s $API/status      # running:true, progress advancing
# …wait for completion (watch /status or /live-logs)…
curl -s $API/leads | head -c 300     # array of enriched leads
```
- [ ] Extraction starts (`status: started`).
- [ ] `/status` shows progress advancing, then `running:false`.
- [ ] `/leads` returns enriched rows with `_score` and `Missing Fields`.

## 4. Exports
```bash
curl -s -o leads.csv  $API/download/csv  && head -1 leads.csv
curl -s -o leads.xlsx $API/download/xlsx && file leads.xlsx
```
- [ ] CSV header = the 15 canonical columns (Company / Project Name … Discovery URL).
- [ ] XLSX downloads and opens.

## 5. Telemetry
```bash
curl -s $API/metrics | head -c 200
```
- [ ] `/metrics` returns the latest run's success rate and timings.

## 6. Frontend
- [ ] `$WEB` loads with no console errors.
- [ ] Platform selector shows all 4 platforms; DeFiLlama hides the category input and shows a fixed listing source.
- [ ] Starting a run streams live logs and progress.
- [ ] Results table renders; CSV/XLSX download buttons work.
- [ ] Coverage/quality panels populate.

## 7. SSE / live logs
- [ ] `GET /live-logs` streams `data:` events during a run and emits a `done` event at completion.

---

✅ **All boxes checked → deployment verified.**
❌ **Any failure →** see [`RUNBOOK.md`](RUNBOOK.md) → *Troubleshooting*.

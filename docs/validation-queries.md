# Validation Queries — Elastomers Australia

Run these after ingesting all 5 EA sample PDFs. All should return correct answers from the correct source document.

```bash
python scripts/test_query.py "your query here"
```

| # | Query | Expected Source | Expected Answer |
|---|---|---|---|
| 1 | "What torque for M20 Grade 10.9 bolts lubricated?" | EA-SOP-001 Table 7.1 | 370 Nm |
| 2 | "What PPE is required for screen installation?" | EA-SOP-001 Section 4.1 | Full PPE list inc. hard hat, safety glasses, steel caps, hi-vis, gloves, hearing protection |
| 3 | "What are the slope angles on the HF-2160?" | EA-ENG-DRW-7834 model table | 35° / 25° / 18° / 12° / 6° |
| 4 | "What motor bolt size for the HF-2472?" | EA-ENG-DRW-7834 Stage 2 | M24 Grade 10.9, 6-bolt mounting |
| 5 | "Shore A hardness for PU-500 panels?" | EA-ENG-DRW-4281 Section 2 | 80–85A |
| 6 | "Max feed size for PU-600 series?" | EA-ENG-DRW-4281 Section 2 | 400mm |
| 7 | "What is NR-35-SA compound used for?" | EA-ENG-MAT-019 Section 2.1 | Heavy-duty wear liners, chutes, hoppers, high-impact zones, iron ore and gold operations |
| 8 | "Cure temperature for NR-55-HA?" | EA-ENG-MAT-019 Section 2.2 | 155°C ± 2°C |
| 9 | "How many field technicians does EA employ?" | EA-STRAT-002 Section 2.1 | 350+ |
| 10 | "What is the new hire competency timeline?" | EA-SOP-001 Section 11 | 14 weeks current, target 8 weeks with VR training |

## Pass Criteria

- Correct answer returned: ✅
- Source document and page cited in response: ✅
- No hallucinated figures or specs: ✅
- Confidential formulation register (MAT-019) only returned when auth permits: ✅

## Cross-Document Query (Bonus)

| Query | Expected behaviour |
|---|---|
| "What panel spec applies to the HF-2472?" | Should surface EA-ENG-DRW-4281 (cross-reference from DRW-7834 Stage 4) |
| "What are the training requirements before installation?" | Should combine EA-SOP-001 Section 11 (cert requirements) with STRAT-002 VR context |

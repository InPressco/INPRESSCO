# DASHBOARD REPORT — InPressco

> Généré le 2026-03-28 15:23 UTC | Score : **88/100** 🟢 HEALTHY

---

## État général

| Métrique | Valeur |
|----------|--------|
| Dashboard | ✅ En ligne |
| URL testée | `http://127.0.0.1:8080` |
| Endpoints testés | 14 |
| OK | 11 |
| Avertissements | 3 |
| Erreurs | 0 |
| Ignorés | 0 |



---

## Résultats par endpoint

| | Endpoint | HTTP | Latence | Observations |
|---|----------|------|---------|-------------|
| ✅🔴 | /api/status | 200 | 77ms | — |
| ✅ | /api/log | 200 | 61ms | — |
| ✅ | /api/runs | 200 | 46ms | — |
| ⚠️🔴 | /api/kpis | 200 | 14090ms | kpis: nb devis semaine négatif — problème de parsing date; L |
| ✅🔴 | /api/stats | 200 | 1247ms | — |
| ⚠️🔴 | /api/daf | 200 | 6201ms | Latence élevée : 6201ms (seuil 5000ms) |
| ✅ | /api/ca-chart | 200 | 2828ms | — |
| ✅ | /api/clients | 200 | 1336ms | — |
| ✅ | /api/devis-suivre | 200 | 1383ms | — |
| ✅ | /api/proposals-orders | 200 | 1544ms | — |
| ✅ | /api/config | 200 | 57ms | — |
| ✅🔴 | /api/health | 200 | 43ms | — |
| ⚠️ | /api/synthesis | 200 | 4339ms | ⚠️  Impayés élevés : 77,751 € HT |
| ✅ | /api/n8n/workflows | 200 | 24ms | — |

---

## Correctifs suggérés

- [`/api/log`] Endpoint Dolibarr retourne 503 — souvent un sqlfilters invalide
- [`/api/kpis`] Endpoint Dolibarr retourne 503 — souvent un sqlfilters invalide

---

## Correctifs appliqués automatiquement

- Aucun correctif automatique appliqué

---

*Pour relancer : `python main.py --check-dashboard`*

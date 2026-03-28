"""tests/test_freshprocess.py — Découverte et test de l'API Freshprocess.

Teste les clés Freshprocess (public/private) pour comprendre :
  - Le format d'authentification
  - La structure des données retournées
  - Ce qu'on peut synchroniser avec Dolibarr

Les clés sont hardcodées ici pour le test — à déplacer dans .env une fois validées.

Usage :
  python tests/test_freshprocess.py
  python tests/test_freshprocess.py --full    # JSON brut complet
"""

import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import asyncio
import json
import sys
import httpx

FULL = "--full" in sys.argv

# ── Clés Freshprocess (à déplacer dans .env après validation) ─────────────
FP_BASE = "https://data07.freshprocess.eu/v1"

# On teste avec la clé "Avant vente" (la plus pertinente pour le pipeline devis)
KEYS = {
    "avant_vente": {
        "public":  "a59f2acc-aebf-4e97-ab2e-28a1e74ccd1b",
        "private": "MPFJNK7-NTZMX5S-NCQ2H8B-WX6CT6Y",
        "label":   "Dolibarr API 2) Avant vente",
    },
    "commande": {
        "public":  "9e42aebd-8943-4144-a769-54a0fdf36a9e",
        "private": "KS1AXFD-H51M2H3-MXMN983-ZQSPN7G",
        "label":   "Dolibarr API 4) Commande",
    },
    "justif": {
        "public":  "22d28789-0129-4bca-952e-40a196936361",
        "private": "4B98F2C-04MMQJN-JMQ4188-JT9P6RF",
        "label":   "Dolibarr API 0) JUSTIF",
    },
}

# ── Couleurs ───────────────────────────────────────────────────────────────
R="\033[0m"; B="\033[1m"; DIM="\033[2m"
G="\033[32m"; Y="\033[33m"; RED="\033[31m"; C="\033[36m"; GR="\033[90m"; M="\033[35m"
def c(col,t): return f"{col}{t}{R}"
def hr(ch="─",w=70): print(c(GR, ch*w))
def section(t): print(); hr("═"); print(c(B+C, f"  {t}")); hr("═")
def subsection(t): print(); print(c(B, f"  ▸ {t}")); hr("·",50)
def ok(m): print(f"    {c(G,'✓')}  {m}")
def warn(m): print(f"    {c(Y,'⚠')}  {c(Y,m)}")
def fail(m): print(f"    {c(RED,'✗')}  {c(RED,m)}")
def info(m): print(f"    {c(GR,'·')}  {m}")


async def try_request(client: httpx.AsyncClient, method: str, url: str,
                       headers: dict = None, json_body: dict = None,
                       label: str = "") -> tuple[int, any]:
    """Tente une requête et retourne (status_code, data)."""
    try:
        if method == "GET":
            r = await client.get(url, headers=headers or {}, timeout=10)
        else:
            r = await client.post(url, headers=headers or {}, json=json_body or {}, timeout=10)
        try:
            data = r.json()
        except Exception:
            data = r.text
        return r.status_code, data
    except Exception as e:
        return 0, str(e)


async def test_key(client: httpx.AsyncClient, key_name: str, key_data: dict, full: bool):
    """Teste une clé Freshprocess avec différentes stratégies d'auth."""
    label = key_data["label"]
    pub = key_data["public"]
    priv = key_data["private"]

    subsection(f"Clé : {label}")
    info(f"Public  : {pub}")
    info(f"Private : {priv[:8]}...")

    # Endpoints à tester
    endpoints = [
        f"{FP_BASE}/projects",
        f"{FP_BASE}/projects/{pub}",
        f"{FP_BASE}/projects/{pub}/data",
        f"{FP_BASE}/data",
        f"{FP_BASE}/records",
    ]

    # Stratégies d'authentification à essayer
    auth_strategies = [
        {"label": "Bearer public",  "headers": {"Authorization": f"Bearer {pub}"}},
        {"label": "Bearer private", "headers": {"Authorization": f"Bearer {priv}"}},
        {"label": "X-API-Key pub",  "headers": {"X-API-Key": pub}},
        {"label": "X-API-Key priv", "headers": {"X-API-Key": priv}},
        {"label": "pub+priv headers","headers": {"X-Public-Key": pub, "X-Private-Key": priv}},
        {"label": "Basic (pub:priv)","headers": {
            "Authorization": "Basic " + __import__("base64").b64encode(
                f"{pub}:{priv}".encode()).decode()
        }},
    ]

    found = False
    for endpoint in endpoints:
        for auth in auth_strategies:
            code, data = await try_request(client, "GET", endpoint,
                                           headers=auth["headers"],
                                           label=f"{auth['label']} → {endpoint}")
            if code == 200:
                ok(f"HTTP 200 ✓ — auth: {c(B, auth['label'])} — endpoint: {endpoint}")
                found = True
                if isinstance(data, (dict, list)):
                    if full:
                        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
                    else:
                        # Résumé
                        if isinstance(data, list):
                            info(f"  Retourne une liste de {len(data)} éléments")
                            if data:
                                info(f"  Clés du 1er élément : {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0])}")
                        elif isinstance(data, dict):
                            info(f"  Clés : {list(data.keys())[:10]}")
                break
            elif code == 401:
                pass  # Auth refusée, essayer autre chose
            elif code == 403:
                warn(f"HTTP 403 — {auth['label']} → accès refusé")
                break
            elif code not in (404, 0):
                info(f"  HTTP {code} — {auth['label']} → {str(data)[:80]}")

        if found:
            break

    if not found:
        # Essayer aussi le POST avec credentials dans le body
        for endpoint in [f"{FP_BASE}/projects", f"{FP_BASE}/auth"]:
            code, data = await try_request(
                client, "POST", endpoint,
                headers={"Content-Type": "application/json"},
                json_body={"public_key": pub, "private_key": priv},
            )
            if code in (200, 201):
                ok(f"POST HTTP {code} ✓ → {endpoint}")
                found = True
                if full:
                    print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
                break
            elif code not in (404, 0, 405):
                info(f"  POST HTTP {code} → {endpoint} : {str(data)[:80]}")

    if not found:
        warn("Aucune stratégie d'auth n'a fonctionné pour cette clé")
        info("→ Consulter la documentation Freshprocess ou inspecter les requêtes réseau dans le navigateur")

    return found


async def run(full: bool = False):
    section("Test API Freshprocess")
    info(f"Base URL : {FP_BASE}")
    info(f"Objectif : découvrir format auth + structure données")
    print()

    async with httpx.AsyncClient(follow_redirects=True) as client:

        # Test rapide de connectivité
        subsection("Connectivité")
        code, data = await try_request(client, "GET", f"{FP_BASE}/projects")
        if code == 0:
            fail(f"Pas de réponse : {data}")
            return
        elif code == 200:
            ok(f"HTTP 200 — API accessible sans auth")
            if full:
                print(str(data)[:500])
        elif code == 401:
            ok(f"HTTP 401 — API accessible, authentification requise (attendu)")
        elif code == 404:
            warn(f"HTTP 404 — endpoint /projects introuvable")
        else:
            info(f"HTTP {code} — {str(data)[:100]}")

        # Tester les 3 clés les plus utiles pour le pipeline
        results = {}
        for key_name in ["avant_vente", "justif", "commande"]:
            found = await test_key(client, key_name, KEYS[key_name], full)
            results[key_name] = found

    # Résumé
    section("Résumé")
    any_found = any(results.values())
    for k, v in results.items():
        status = c(G, "✓ Auth OK") if v else c(Y, "⚠ Non résolu")
        print(f"  {status}  {KEYS[k]['label']}")

    print()
    if not any_found:
        print(c(Y+B, "  → Prochaine étape : identifier le format d'auth dans la doc Freshprocess"))
        print(c(GR, "    Ou inspecter une vraie requête depuis n8n/le navigateur (DevTools → Network)"))
    else:
        print(c(G+B, "  → Connexion établie. Relancer avec --full pour explorer les données."))
    print()


if __name__ == "__main__":
    asyncio.run(run(full=FULL))

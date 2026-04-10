"""connectors/dolibarr.py — Client REST pour l'API Dolibarr."""
import logging
import re
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src import config

logger = logging.getLogger(__name__)


def _sanitize_sqlfilter_value(value: str, max_len: int = 100) -> str:
    """Sanitise une valeur avant insertion dans un sqlfilter Dolibarr.
    Supprime tous les vecteurs d'injection SQL : quotes, backslashes, caractères
    de contrôle, point-virgules (délimiteurs de requêtes), backticks et tirets doubles.
    """
    # Supprimer les vecteurs d'injection sqlfilter
    cleaned = re.sub(r"['\"\\\x00-\x1f;`\-\-]", "", value)
    # Supprimer les mots-clés SQL dangereux (insensible à la casse)
    for kw in ("--", "/*", "*/", "xp_", "exec", "union", "select", "drop", "insert"):
        cleaned = re.sub(re.escape(kw), "", cleaned, flags=re.IGNORECASE)
    return cleaned[:max_len]


class DolibarrClient:
    """Client asynchrone pour l'API REST Dolibarr."""

    def __init__(self):
        self.base = config.DOLIBARR_BASE_URL
        self.headers = {
            "DOLAPIKEY": config.DOLIBARR_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Tiers ──────────────────────────────────────────────────────────────

    async def find_thirdparty(
        self,
        email: str | None = None,
        name: str | None = None
    ) -> dict | None:
        """Cherche un tiers par email, puis par nom. Retourne None si non trouvé."""
        async with httpx.AsyncClient(timeout=30) as client:

            if email:
                safe_email = _sanitize_sqlfilter_value(email)
                resp = await client.get(
                    f"{self.base}/thirdparties",
                    headers=self.headers,
                    params={"sqlfilters": f"(t.email:=:'{safe_email}')"}
                )
                if resp.status_code == 200:
                    results = resp.json()
                    if results:
                        return results[0]

            if name:
                safe_name = _sanitize_sqlfilter_value(name)
                resp = await client.get(
                    f"{self.base}/thirdparties",
                    headers=self.headers,
                    params={"sqlfilters": f"(t.nom:like:'%{safe_name}%')"}
                )
                if resp.status_code == 200:
                    results = resp.json()
                    if results:
                        return results[0]

        return None

    async def create_thirdparty(self, data: dict) -> dict:
        """Créer un nouveau tiers Dolibarr. Retourne le tiers créé avec son id."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base}/thirdparties",
                headers=self.headers,
                json=data
            )
            resp.raise_for_status()
            # Dolibarr retourne l'id (int) ou un objet selon la version
            result = resp.json()
            if isinstance(result, int):
                return {"id": result}
            return result

    # ── Devis (Proposals) ──────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def create_proposal(self, data: dict) -> dict:
        """Créer un devis. Retourne l'objet devis avec id."""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base}/proposals",
                headers=self.headers,
                json=data
            )
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, int):
                return {"id": result}
            return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def validate_proposal(self, proposal_id: int) -> dict:
        """Valider un devis (génère la référence PRO...)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base}/proposals/{proposal_id}/validate",
                headers=self.headers,
                json={"notrigger": 0}
            )
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def set_to_draft(self, proposal_id: int) -> dict:
        """Remettre un devis en brouillon (pour édition manuelle)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base}/proposals/{proposal_id}/settodraft",
                headers=self.headers,
                json={"notrigger": 0}
            )
            resp.raise_for_status()
            return resp.json()

    async def get_proposal_by_ref(self, ref: str) -> dict:
        """Récupérer un devis par sa référence (ex: PRO2025-0042)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base}/proposals/ref/{ref}",
                headers=self.headers,
                params={"contact_list": 1}
            )
            resp.raise_for_status()
            return resp.json()

    async def list_proposals_by_socid(
        self,
        socid: int,
        limit: int = 5,
        statuts: set[int] | None = None,
    ) -> list[dict]:
        """Liste les devis d'un tiers, filtrés par statuts si fournis.
        statuts = {0} → brouillons · {0, 1} → brouillons + ouverts
        """
        params = {
            "sqlfilters": f"(t.fk_soc:=:{int(socid)})",
            "limit": limit,
            "sortfield": "t.datec",
            "sortorder": "DESC",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base}/proposals",
                headers=self.headers,
                params=params,
            )
            if resp.status_code != 200:
                return []
            results = resp.json()
            if not isinstance(results, list):
                return []
            if statuts is not None:
                results = [r for r in results if int(r.get("statut", -1)) in statuts]
            return results

    async def get_thirdparty_by_id(self, socid: int) -> dict | None:
        """Récupère un tiers complet par son ID Dolibarr."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base}/thirdparties/{int(socid)}",
                headers=self.headers,
            )
            if resp.status_code == 200:
                return resp.json()
            return None

    async def count_orders_by_socid(self, socid: int) -> int:
        """Compte les commandes passées par un tiers (pour détecter les récurrents)."""
        params = {
            "sqlfilters": f"(t.fk_soc:=:{int(socid)})",
            "limit": 20,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base}/orders",
                headers=self.headers,
                params=params,
            )
            if resp.status_code != 200:
                return 0
            results = resp.json()
            return len(results) if isinstance(results, list) else 0

    # ── Documents ──────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def upload_document(
        self,
        modulepart: str,
        ref: str,
        filename: str,
        b64content: str
    ) -> dict:
        """Uploader une pièce jointe sur un objet Dolibarr."""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base}/documents/upload",
                headers=self.headers,
                json={
                    "filename": filename,
                    "modulepart": modulepart,
                    "ref": ref,
                    "filecontent": b64content,
                    "fileencoding": "base64",
                    "overwriteifexists": 1,
                }
            )
            resp.raise_for_status()
            return resp.json()

    # ── Agenda ─────────────────────────────────────────────────────────────

    async def create_agenda_event(self, data: dict) -> dict:
        """Créer un événement agenda lié à un objet Dolibarr."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base}/agendaevents",
                headers=self.headers,
                json=data
            )
            resp.raise_for_status()
            return resp.json()

"""connectors/outlook.py — Client Microsoft Graph pour Outlook."""
import base64
import logging
import httpx
import msal
from src import config

logger = logging.getLogger(__name__)


class OutlookClient:
    """Client asynchrone pour l'API Microsoft Graph (Outlook)."""

    GRAPH_BASE = config.OUTLOOK_GRAPH_BASE
    # App-only scope pour client credentials flow
    SCOPES = ["https://graph.microsoft.com/.default"]

    def __init__(self):
        self._token: str | None = None
        self._msal_app = msal.ConfidentialClientApplication(
            client_id=config.OUTLOOK_CLIENT_ID,
            client_credential=config.OUTLOOK_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{config.OUTLOOK_TENANT_ID}"
        )

    async def _get_token(self) -> str:
        """Obtenir un access token via client credentials (app-only)."""
        # Tenter le cache d'abord
        result = self._msal_app.acquire_token_silent(self.SCOPES, account=None)
        if not result:
            result = self._msal_app.acquire_token_for_client(scopes=self.SCOPES)
        if "access_token" not in result:
            raise RuntimeError(f"Échec token Outlook : {result.get('error_description')}")
        return result["access_token"]

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get_emails(
        self,
        folder_id: str,
        odata_filter: str = "",
        top: int = 1,
        select: list[str] | None = None
    ) -> list[dict]:
        """Récupérer les emails d'un dossier Outlook."""
        token = await self._get_token()
        fields = select or [
            "id", "subject", "sender", "from", "body", "bodyPreview",
            "receivedDateTime", "hasAttachments", "parentFolderId", "toRecipients"
        ]
        params: dict = {
            "$top": top,
            "$select": ",".join(fields),
        }
        if odata_filter:
            # Graph API ne supporte pas $orderby + $filter ensemble sur les messages
            params["$filter"] = odata_filter
        else:
            params["$orderby"] = "receivedDateTime desc"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/mailFolders/{folder_id}/messages",
                headers=self._headers(token),
                params=params
            )
            if not resp.is_success:
                logger.error(f"Graph get_emails {resp.status_code} — {resp.text}")
            resp.raise_for_status()
            messages = resp.json().get("value", [])

        # Tri côté client si $orderby non envoyé
        if odata_filter and messages:
            messages.sort(key=lambda m: m.get("receivedDateTime", ""), reverse=True)

        return messages

    async def get_attachments(self, message_id: str) -> list[dict]:
        """Lister les pièces jointes d'un email."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/messages/{message_id}/attachments",
                headers=self._headers(token)
            )
            resp.raise_for_status()
            return resp.json().get("value", [])

    async def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Télécharger une pièce jointe en bytes."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/messages/{message_id}/attachments/{attachment_id}/$value",
                headers=self._headers(token)
            )
            resp.raise_for_status()
            return resp.content

    async def get_folder_id_by_name(self, display_name: str) -> str | None:
        """Résoudre l'ID d'un dossier racine par son displayName."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/mailFolders",
                headers=self._headers(token),
                params={"$top": 50, "$select": "id,displayName"}
            )
            resp.raise_for_status()
            folders = resp.json().get("value", [])
        for folder in folders:
            if folder.get("displayName", "").upper() == display_name.upper():
                return folder["id"]
        return None

    async def get_folders(self, parent_folder_id: str) -> list[dict]:
        """Lister les sous-dossiers d'un dossier."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/mailFolders/{parent_folder_id}/childFolders",
                headers=self._headers(token)
            )
            if not resp.is_success:
                logger.error(f"Graph get_folders {resp.status_code} — {resp.text}")
            resp.raise_for_status()
            return resp.json().get("value", [])

    async def create_folder(self, parent_folder_id: str, display_name: str) -> dict:
        """Créer un sous-dossier Outlook."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.GRAPH_BASE}/mailFolders/{parent_folder_id}/childFolders",
                headers=self._headers(token),
                json={"displayName": display_name}
            )
            resp.raise_for_status()
            return resp.json()

    async def update_message_subject(self, message_id: str, new_subject: str) -> None:
        """Renommer le sujet d'un email."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                f"{self.GRAPH_BASE}/messages/{message_id}",
                headers=self._headers(token),
                json={"subject": new_subject}
            )
            resp.raise_for_status()

    async def move_message(self, message_id: str, destination_folder_id: str) -> dict:
        """Déplacer un email vers un autre dossier."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.GRAPH_BASE}/messages/{message_id}/move",
                headers=self._headers(token),
                json={"destinationId": destination_folder_id}
            )
            resp.raise_for_status()
            return resp.json()

    async def get_messages(
        self,
        odata_filter: str = "",
        top: int = 10,
        select: list[str] | None = None,
    ) -> list[dict]:
        """Récupère des emails cross-dossiers via l'endpoint /messages de Graph."""
        token = await self._get_token()
        fields = select or [
            "id", "subject", "sender", "from", "body", "bodyPreview",
            "receivedDateTime", "hasAttachments", "parentFolderId", "toRecipients",
        ]
        params: dict = {"$top": top, "$select": ",".join(fields)}
        if odata_filter:
            params["$filter"] = odata_filter
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/messages",
                headers=self._headers(token),
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("value", [])

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        cc_emails: list[str] | None = None,
        reply_to_message_id: str | None = None,
    ) -> None:
        """
        Envoyer un email via Microsoft Graph (sendMail).

        Si reply_to_message_id est fourni, l'email est envoyé comme réponse
        à ce message (thread conservé).

        Args:
            to_email: Destinataire principal.
            subject: Objet du message.
            body_html: Corps HTML du message.
            cc_emails: Destinataires en copie (optionnel).
            reply_to_message_id: ID du message Outlook auquel on répond (optionnel).
        """
        token = await self._get_token()

        to_recipients = [{"emailAddress": {"address": to_email}}]
        cc_recipients = [{"emailAddress": {"address": e}} for e in (cc_emails or [])]

        if reply_to_message_id:
            # Créer un brouillon de réponse puis l'envoyer (conserve le thread)
            async with httpx.AsyncClient(timeout=30) as client:
                draft_resp = await client.post(
                    f"{self.GRAPH_BASE}/messages/{reply_to_message_id}/createReply",
                    headers=self._headers(token),
                    json={},
                )
                draft_resp.raise_for_status()
                draft_id = draft_resp.json()["id"]

            # Mettre à jour le corps et les destinataires du brouillon
            async with httpx.AsyncClient(timeout=30) as client:
                update_resp = await client.patch(
                    f"{self.GRAPH_BASE}/messages/{draft_id}",
                    headers=self._headers(token),
                    json={
                        "subject": subject,
                        "body": {"contentType": "HTML", "content": body_html},
                        "toRecipients": to_recipients,
                        **({"ccRecipients": cc_recipients} if cc_recipients else {}),
                    },
                )
                update_resp.raise_for_status()

            # Envoyer le brouillon
            async with httpx.AsyncClient(timeout=30) as client:
                send_resp = await client.post(
                    f"{self.GRAPH_BASE}/messages/{draft_id}/send",
                    headers=self._headers(token),
                )
                send_resp.raise_for_status()
        else:
            # Envoi direct via /sendMail
            payload = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": body_html},
                    "toRecipients": to_recipients,
                },
                "saveToSentItems": True,
            }
            if cc_recipients:
                payload["message"]["ccRecipients"] = cc_recipients

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.GRAPH_BASE}/sendMail",
                    headers=self._headers(token),
                    json=payload,
                )
                resp.raise_for_status()

        logger.info(f"Email envoyé à {to_email!r} — sujet : {subject!r}")

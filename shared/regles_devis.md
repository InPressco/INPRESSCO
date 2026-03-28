# regles_devis.md — Algorithme de construction des lignes de devis (Layer 3)

## Structure globale des lignes

```
Ligne 0  : Contexte client (product_type=9, special_code=104777)
─────────────────────────────────────────────────
Pour chaque groupe (intitule_maitre) :
  Ligne A  : Descriptif fusionné (product_type=9, special_code=104778)
  Ligne B  : Prix quantité 1 (product_type=0, fk_product=35700)
  Ligne B' : Prix quantité 2 (si quantités distinctes dans le groupe)
  ...
```

## Algorithme Python

```python
import re

def nettoyer_finition(texte):
    """Retire les mentions reliure/conditionnement/franco du champ type_finition."""
    if not texte:
        return "-"
    parties = re.split(r"[;,]", texte)
    filtrees = [
        p.strip() for p in parties
        if not re.search(
            r"reliure|conditionnement|franco|port inclus|livraison|transport",
            p, re.IGNORECASE
        )
    ]
    return " ; ".join(filtrees).strip() or "-"


def build_lines(composants, synthese_contexte):
    lines = []

    # ── LIGNE 0 : Contexte client ──────────────────────────────────────────
    lines.append({
        "desc": synthese_contexte,
        "product_type": 9,
        "qty": 50,
        "special_code": 104777,
        "txtva": 20
    })

    # ── Regroupement par intitule_maitre ───────────────────────────────────
    groupes = {}
    for comp in composants:
        key = comp.get("intitule_maitre") or "Sans intitulé"
        groupes.setdefault(key, []).append(comp)

    for intitule, comps in groupes.items():

        # Tri : couverture en premier, puis quantité croissante
        comps.sort(key=lambda c: (
            not bool(re.search(r"couv|couverture", c.get("produit",""), re.IGNORECASE)),
            c.get("quantite", 0)
        ))

        dernier = comps[-1]

        # ── LIGNE A : Descriptif fusionné ──────────────────────────────────
        desc = f"<b>{intitule}</b><br><br>"

        for i, comp in enumerate(comps):
            if len(comps) > 1:
                desc += f"<u>{comp['produit']}</u><br>"

            desc += f"Nombre de pages : {comp.get('nombre_pages') or '-'}<br>"

            ff = comp.get("format_ferme_mm") or {}
            desc += f"Format fermé : {ff.get('largeur') or '-'} x {ff.get('hauteur') or '-'} mm<br>"

            fo = comp.get("format_ouvert_mm") or {}
            desc += f"Format ouvert : {fo.get('largeur') or '-'} x {fo.get('hauteur') or '-'} mm<br>"

            desc += f"Type impression : {comp.get('type_impression') or '-'}<br>"
            desc += f"Support grammage : {comp.get('support_grammage') or '-'}<br>"
            desc += f"Type de finition : {nettoyer_finition(comp.get('type_finition'))}<br>"

            if i < len(comps) - 1:
                desc += "<br>"

        # Champs communs — une fois depuis le dernier composant
        desc += "<br>"
        if dernier.get("type_reliure"):
            desc += f"Type de reliure : {dernier['type_reliure']}<br>"
        if dernier.get("conditionnement"):
            desc += f"Conditionnement : {dernier['conditionnement']}<br>"
        if dernier.get("franco_port"):
            desc += f"Franco de port : {dernier['franco_port']}<br>"
        desc += (
            "<br><i>Fichiers fournis par vos soins, prêt à imprimer — "
            "Toute modification sera facturée au taux de 50€ HT/heure</i>"
        )

        lines.append({
            "product_type": 9,
            "special_code": 104778,
            "desc": desc,
            "qty": 1,
            "tva_tx": 20
        })

        # ── LIGNE(S) B : Prix par quantité distincte ───────────────────────
        quantites = sorted(set(c.get("quantite", 1) for c in comps))

        for qte in quantites:
            comp_ref = next(
                (c for c in comps if re.search(r"couv|couverture", c.get("produit",""), re.IGNORECASE)),
                comps[0]
            )
            imp700 = comp_ref.get("IMPOSITION_BRUTE_700x1000") or {}
            imp330 = comp_ref.get("IMPOSITION_BRUTE_330x480") or {}

            f700 = (imp700.get("calcul_feuilles") or {}).get("feuilles", "-")
            f330 = (imp330.get("calcul_feuilles") or {}).get("feuilles", "-")

            alertes_all = []
            for c in comps:
                alertes_all.extend((c.get("SCORE_DEVIS") or {}).get("alertes", []))
            alertes_uniq = list(dict.fromkeys(alertes_all))
            alertes_html = (
                "<ul><li>" + "</li><li>".join(alertes_uniq) + "</li></ul>"
                if alertes_uniq else "aucune"
            )

            scores = [
                c["SCORE_DEVIS"]["score_sur_10"]
                for c in comps
                if (c.get("SCORE_DEVIS") or {}).get("score_sur_10") is not None
            ]
            score_moyen = f"{sum(scores)/len(scores):.1f}" if scores else "-"

            lines.append({
                "product_type": 0,
                "desc": f"<b>{intitule}</b> — Quantité : {qte} ex",
                "qty": qte,
                "tva_tx": 20,
                "fk_product": "35700",
                "array_options": {
                    "options_analysen8n": (
                        f"<ul>"
                        f"<li><b>Imposition (réf.)</b> : 700×1000 → {imp700.get('poses_total','-')} poses / {f700} feuilles"
                        f" &nbsp;|&nbsp; 330×480 → {imp330.get('poses_total','-')} poses / {f330} feuilles</li>"
                        f"<li><b>Score analyse moyen</b> : {score_moyen}/10</li>"
                        f"<li><b>Alertes production</b> : {alertes_html}</li>"
                        f"</ul>"
                    )
                }
            })

    return lines
```

## Règles de fallback
- `quantite` absent → 1
- `intitule_maitre` absent → "Sans intitulé"
- Champ IA manquant → `"-"`, jamais d'exception levée
- Si `lines` vide après traitement → ajouter une ligne placeholder :
  `{"product_type":0, "desc":"Analyse en cours — données incomplètes", "qty":1, "tva_tx":20, "fk_product":"35700"}`

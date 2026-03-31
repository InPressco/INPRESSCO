"""core/system_reference.py — SOURCE DE VÉRITÉ SYSTÈME INPRESSCO.

Référentiel complet : 30 skills, 6 chaînes, conventions Dolibarr,
anti-patterns, pipeline, équipe.

Généré le : 2026-03-28 | Ne pas modifier sans mettre à jour SYSTEM_VERSION.
"""

SYSTEM_VERSION     = "2026.03.28"
SYSTEM_UPDATED_AT  = "2026-03-28T00:00:00+02:00"

# ─────────────────────────────────────────────────────────────────────────────
# 0. PRINCIPES DIRECTEURS
# ─────────────────────────────────────────────────────────────────────────────

PRINCIPES = {
    "vision": (
        "InPressco est un moteur de développement, porteur d'une vision futuriste "
        "et raisonnée — symbole de l'évolution et de l'adaptation de l'homme "
        "dans son environnement futur."
    ),
    "raison_etre": [
        "Libérer l'énergie des dirigeants des tâches répétitives",
        "Donner une vision claire de l'entreprise en temps réel",
        "Redonner la place à la vraie relation humaine et au sens",
    ],
    "jamais": [
        "Une boîte noire que personne ne comprend",
        "Un système autonome opaque — le dirigeant sait toujours ce qui se passe",
        "Une dépendance qui fragilise InPressco si il tombe",
    ],
    "principes_non_negociables": {
        "Transparence": "Chaque action du système doit être lisible",
        "Sobriété":     "Faire moins, mais le faire vraiment bien",
        "Humanité":     "L'IA exécute, l'humain décide et pilote",
    },
    "split": {
        "STANDARD": "externalisation → Imprimerie Savoie / partenaires",
        "PREMIUM":  "internalisation → ADN InPressco, conseil, finitions spéciales",
    },
    "roles": {
        "IA":      "EXÉCUTE (jamais pilote)",
        "équipe":  "PRODUIT",
        "Nicolas": "ARBITRE (architecte, pas pompier)",
    },
    "regle_or": (
        "Toute action irréversible (envoi email, création Dolibarr, dépôt fichier) "
        "requiert une validation humaine. Aucune exception."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. PIPELINE DE VALEUR — 7 ÉTAPES + SUPPORT
# ─────────────────────────────────────────────────────────────────────────────

PIPELINE_STRUCTURE = {
    "00_STRATEGIE": {
        "role": "Cerveau décisionnel — positionnement, offre, pricing, cibles",
        "acteur_principal": "Nicolas",
        "ia_role": "Préparer les analyses, jamais décider",
    },
    "01_LEADS": {
        "role": "Entrée du système — collecte, qualification, décision d'engagement",
        "skills": ["mail-routing-inpressco", "extraction-tiers",
                   "memoire-client-inpressco", "droits-profils-inpressco"],
        "ia_role": "Qualifier, router, identifier le tiers",
    },
    "02_OPPORTUNITES": {
        "role": "Cœur stratégique — analyse valeur, devis, stratégie projet",
        "skills": ["inpressco-commerce", "calcul-tarif-inpressco", "veille-prix-inpressco"],
        "ia_role": "Enrichir le brief, calculer, positionner",
    },
    "03_CONCEPTION": {
        "role": "ADN InPressco — créativité, matière, différenciation",
        "skills": ["planche-archi-inpressco", "charte-graphique-inpressco",
                   "bdd-images-query-inpressco"],
        "ia_role": "Suggérer, enrichir créativement, valider la charte",
    },
    "04_PRODUCTION": {
        "role": "Fabrication — split STANDARD / PREMIUM, suivi, achats",
        "skills": ["suivi-commande-inpressco", "agent-acheteur-inpressco"],
        "ia_role": "Router STANDARD/PREMIUM, suivre les jalons BAT",
    },
    "05_LIVRAISON": {
        "role": "Validation finale + logistique + facturation",
        "skills": ["validation-qc-inpressco", "generation-pdf-inpressco",
                   "reponse-client-inpressco"],
        "ia_role": "Contrôler qualité, générer documents, notifier client",
    },
    "06_POST_PROJET": {
        "role": "Avantage long terme — feedback, analyse, capitalisation",
        "skills": ["analyse-transversale-inpressco", "memoire-client-inpressco"],
        "ia_role": "Analyser les patterns, enrichir la mémoire client",
    },
    "90_SUPPORT": {
        "role": "Machine interne — Finance, Admin, CRM",
        "skills": ["controleur-gestion-inpressco", "dolibarr-query-inpressco",
                   "archiveur-inpressco"],
        "ia_role": "Reporting financier, maintenance des bases",
    },
    "91_R&D": {
        "role": "Futur — matériaux, prototypes, innovations",
        "acteur_principal": "Nicolas + Alys",
        "ia_role": "Recherche, synthèse, benchmarks",
    },
    "99_DIRECTION": {
        "role": "Cockpit Nicolas — vision, arbitrages, journal décisions",
        "acteur_principal": "Nicolas",
        "ia_role": "Briefer avec contexte complet, options, implications systémiques",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. REGISTRE COMPLET DES SKILLS (30 skills)
# ─────────────────────────────────────────────────────────────────────────────

SKILLS_REGISTRY = {

    # ── INFRASTRUCTURE TRANSVERSALE ──────────────────────────────────────────

    "dolibarr-query-inpressco": {
        "etape": "Transversal", "type": "Infrastructure",
        "role": "Lecture et interrogation de Dolibarr via API REST",
        "acces": "GET exclusivement — lecture seule",
        "config": {
            "BASE_URL": "https://in-pressco.crm.freshprocess.eu/api/index.php",
            "AUTH": "Header DOLAPIKEY: {DOLIBARR_API_KEY}",
            "OWNER_ID": 166,
        },
        "triggers": [
            "dès qu'une donnée Dolibarr doit être consultée",
            "avant toute création (anti-doublon)",
            "email/nom/référence de tiers à identifier",
            "statut d'un devis ou commande",
        ],
        "endpoints_cles": {
            "tiers_par_nom":     "GET /thirdparties?sqlfilters=(t.nom:like:'%{nom}%')",
            "tiers_par_email":   "GET /thirdparties?sqlfilters=(t.email:=:'{email}')",
            "tiers_complet":     "GET /thirdparties/{id}",
            "devis_par_ref":     "GET /proposals/ref/{ref}",
            "devis_lignes":      "GET /proposals/{id}/lines",
            "commande_par_ref":  "GET /orders/ref/{ref}",
            "facture_par_ref":   "GET /invoices/ref/{ref}",
            "factures_impayees": "GET /invoices?status=1",
            "documents_pj":      "GET /documents?modulepart={module}&id={id}",
            "agenda_tiers":      "GET /agendaevents?thirdparty_ids={socid}&limit=100",
        },
        "statuts_devis":    {0: "Brouillon", 1: "Validé", 2: "Signé", 3: "Refusé", 4: "Archivé", -1: "Annulé"},
        "statuts_commande": {0: "Brouillon", 1: "Validée", 2: "En cours", 3: "Livrée", -1: "Annulée"},
        "statuts_facture":  {0: "Brouillon", 1: "Validée non payée", 2: "Payée", 3: "Abandonnée"},
        "anti_patterns": [
            "sortfield=t.rowid (non supporté — trier côté Python)",
            "inventer des données sans interroger GET d'abord",
        ],
    },

    "droits-profils-inpressco": {
        "etape": "Transversal / Sécurité", "type": "Infrastructure",
        "role": "Identification du profil utilisateur et application des droits",
        "triggers": ["TOUJOURS en premier avant tout workflow Dolibarr"],
        "profils": {
            "CLIENT":  {"signal": "Email hors @inpressco.fr", "ecriture_dolibarr": False},
            "TEAM":    {"signal": "Email @inpressco.fr", "ecriture_dolibarr": True},
            "ADMIN":   {"signal": "Déclaration explicite + canal interne", "ecriture_dolibarr": True},
            "UNKNOWN": {"signal": "Aucun signal clair", "ecriture_dolibarr": False},
        },
        "sortie": "JSON {profil, confidence, droits, action_suivante}",
    },

    "gestion-erreurs-inpressco": {
        "etape": "Transversal / Infrastructure", "type": "Infrastructure",
        "role": "Détection, diagnostic et reprise des erreurs de workflow",
        "codes_http": {
            401: "Clé API invalide — bloquer toute écriture",
            403: "Droits insuffisants — escalader",
            404: "Référence inexistante — confirmer non-existence",
            409: "Doublon — proposer lien à l'existant",
            500: "Erreur serveur — retry 1× après 5s",
            503: "Dolibarr hors ligne — mode dégradé",
        },
        "retry_max": 1,
    },

    # ── ÉTAPE 01 — LEADS ─────────────────────────────────────────────────────

    "mail-routing-inpressco": {
        "etape": "01_LEADS", "type": "Routing",
        "role": "Catégoriser un email entrant et router vers le bon workflow",
        "categories": {
            "NEW_PROJECT":      "Nouveau brief — devis complet",
            "VISUAL_CREATION":  "Demande visuel — génération IA",
            "SUPPLIER_INVOICE": "Facture fournisseur — saisie Dolibarr",
            "PROJECT_UPDATE":   "Info/PJ sur doc existant",
            "SUPPLIER_QUOTE":   "Devis fournisseur reçu",
            "PRICE_REQUEST":    "Demande de prix sous-traitant",
            "ACTION":           "Email @inpressco.fr — déclenchement direct",
            "UNKNOWN":          "Non identifié — traitement manuel",
        },
    },

    "memoire-client-inpressco": {
        "etape": "01→06 Transversal", "type": "Mémoire",
        "role": "Reconstituer le contexte complet d'un tiers",
        "triggers": [
            "NOM DE SOCIÉTÉ mentionné dans la conversation",
            "Email client identifiable",
            "Référence Dolibarr (DEV-/CMD-/FA-)",
            "Activation d'un autre skill",
        ],
        "sources_agregees": [
            "Dolibarr (fiche tiers, devis, commandes, factures, agenda)",
            "bdd-images-query-inpressco (visuels, BAT)",
            "charte-graphique-inpressco",
            "projets-artefacts-inpressco",
        ],
        "statuts_relationnels": {
            "ACTIF":    "Commande < 6 mois",
            "TIEDE":    "Dernière commande 6-18 mois",
            "INACTIF":  "Aucune commande > 18 mois",
            "PROSPECT": "Devis émis, jamais commandé",
            "NOUVEAU":  "Aucun historique",
        },
    },

    # ── ÉTAPE 02 — OPPORTUNITÉS ──────────────────────────────────────────────

    "inpressco-commerce": {
        "etape": "02_OPPORTUNITES", "type": "Commercial",
        "role": "Analyse et réponse commerciale — devis, conseil, fourchettes tarifaires",
        "format_email_oblige": "CONFIG_CLIENT_v2026",
        "phrase_paola_oblige": (
            "Si ce budget correspond à vos attentes, "
            "Paola vous fera suivre un devis en bonne et due forme."
        ),
        "mot_interdit": "estimatif → utiliser 'budget indicatif'",
        "parc_machines": [
            "Table à plat 70x102, Ricoh 7200/9200, Gravure laser Trotec 40x70",
            "Dorure : Jurine portefeuille 60x80, colonne, tranche",
            "Typo : Heidelberg letterpress | Sérigraphie : TIFLEX 60x80",
            "Façonnage : POLAR 115, DUPLO dos carré, Pelliculeuse DONIX 52",
        ],
    },

    "calcul-tarif-inpressco": {
        "etape": "02_OPPORTUNITES", "type": "Calcul",
        "role": "Estimation tarifaire HT par type de produit, support, finition, quantité",
        "majorations": {
            "pelliculage":        "+15 à +25%",
            "vernis_selectif":    "+20 à +35%",
            "dorure_a_chaud":     "+30 à +50%",
            "decoupe_speciale":   "+20 à +40%",
            "urgent_moins_5j":    "+20 à +30%",
            "tres_urgent_48h":    "+40 à +60%",
            "papier_special":     "+10 à +30%",
        },
        "niveaux_confiance": {
            "HIGH":   "±10% — tous paramètres connus",
            "MEDIUM": "±20% — paramètres partiels",
            "LOW":    "±35% — paramètres incomplets",
        },
    },

    "veille-prix-inpressco": {
        "etape": "02_OPPORTUNITES", "type": "Veille concurrentielle",
        "role": "Comparer les prix Exaprint / Onlineprinters / Pixartprinting",
        "usage": "Usage interne uniquement — jamais communiquer au client",
    },

    # ── ÉTAPE 03 — CONCEPTION ────────────────────────────────────────────────

    "planche-archi-inpressco": {
        "etape": "03_CONCEPTION", "type": "Génération visuelle",
        "role": "Générer des prompts Nanobanana pour planches style cabinet d'architecture",
        "sortie": "JSON {prompt, aspect_ratio, resolution: '4K', output_format: 'png'}",
    },

    "charte-graphique-inpressco": {
        "etape": "03_CONCEPTION", "type": "Extraction / Mémoire",
        "role": "Extraire et mémoriser la charte graphique client",
        "sources_acceptees": ["texte libre", "PDF", "image/logo", "Word", "URL/CSS"],
    },

    "bdd-images-query-inpressco": {
        "etape": "03_CONCEPTION", "type": "Recherche base données",
        "role": "Interroger la base images InPressco (lecture seule) — AVANT toute génération",
        "regle_absolue": "Toujours appeler CE skill avant tout skill de génération d'image",
    },

    # ── ÉTAPE 04 — PRODUCTION ────────────────────────────────────────────────

    "suivi-commande-inpressco": {
        "etape": "04_PRODUCTION", "type": "Suivi",
        "role": "Centraliser le suivi des commandes — lecture Dolibarr + jalons + alertes",
        "cycle_bat": {
            "BAT_ENVOYÉ":       "Logger + rappel agenda J+2 + archiver",
            "BAT_VALIDÉ":       "Logger + notifier Nicolas + update note_private",
            "BAT_REFUSÉ":       "Logger + alerter Paola+Nicolas + incrémenter version",
            "BAT_SANS_RÉPONSE": "> 3j ouvrés — alerte + relance client",
        },
    },

    "agent-acheteur-inpressco": {
        "etape": "04_PRODUCTION", "type": "Achats / Sous-traitance",
        "role": "Générer des demandes de prix adaptées au vocabulaire de chaque sous-traitant",
        "types_sous_traitants": ["Façonnier", "Papetier", "Imprimeur", "Finisseur"],
        "regle_quantites": "Toujours 2 à 3 paliers autour de la quantité cible",
    },

    # ── ÉTAPE 05 — LIVRAISON ─────────────────────────────────────────────────

    "validation-qc-inpressco": {
        "etape": "05_LIVRAISON", "type": "Contrôle qualité",
        "role": "Dernier filtre avant toute action irréversible",
        "moments_declenchement": [
            "Création d'un devis dans Dolibarr",
            "Modification d'un devis existant",
            "Avant envoi d'un devis au client",
            "Avant envoi de tout email client",
            "Avant dépôt de tout fichier",
        ],
    },

    "generation-pdf-inpressco": {
        "etape": "05_LIVRAISON", "type": "Génération documents",
        "role": "Produire des PDF finalisés via Dolibarr natif (azur_fp)",
        "regle": "Jamais générer PDF sur devis brouillon (statut 0)",
    },

    "reponse-client-inpressco": {
        "etape": "01→05 Transversal", "type": "Communication client",
        "role": "Rédiger les emails sortants vers clients et prospects",
        "regles_absolues": [
            "Validation obligatoire avant envoi — jamais automatique",
            "Signature = prénom collaborateur assigné (Paola par défaut)",
            "Phrase Paola obligatoire",
            "Jamais : tarifs fournisseurs, marges, difficultés internes, impayés",
            "3 à 6 paragraphes max, prose uniquement, pas de bullet points",
        ],
    },

    "analyse-sentiment-email": {
        "etape": "01→05 Transversal", "type": "NLP / Analyse",
        "role": "Analyser le sentiment, l'intention et le profil de l'expéditeur",
        "analyses": {
            "sentiment":    ["Positif", "Neutre", "Négatif", "Agressif"],
            "urgence":      ["Faible", "Modérée", "Critique"],
            "personnalite": ["Formel", "Décontracté", "Anxieux", "Exigeant", "Bienveillant"],
            "intention":    ["Demande info", "Réclamation", "Commande/devis", "Relance", "Autre"],
        },
        "regle": "Analyse interne silencieuse — ne jamais exposer dans la réponse",
    },

    # ── ÉTAPE 06 — POST-PROJET ───────────────────────────────────────────────

    "analyse-transversale-inpressco": {
        "etape": "06_POST_PROJET", "type": "Analyse data",
        "role": "Analyse transversale des données Dolibarr — tendances, patterns, anomalies",
        "segments_rfm": {
            "CHAMPION":       "R < 60j, F ≥ 3, M élevé",
            "FIDELE":         "R < 120j, F ≥ 2",
            "PROMETTEUR":     "R < 90j, F = 1",
            "A_RISQUE":       "R 120-365j, F ≥ 2",
            "PERDU":          "R > 365j",
            "PROSPECT_FROID": "Devis > 90j, jamais signé",
        },
        "regle": "Lecture seule — détecte, ne corrige pas",
    },

    # ── SUPPORT ──────────────────────────────────────────────────────────────

    "controleur-gestion-inpressco": {
        "etape": "90_SUPPORT / Finance", "type": "Finance / Reporting",
        "role": "Transformer les données Dolibarr en analyses décisionnelles financières",
        "seuils_alertes": {
            "DSO":               "> 45j — alerte",
            "Solde_treso":       "< 5k vigilance | < 2k tension | < 0 rupture",
            "Concentration_client": "> 30% CA risque | > 40% élevé",
        },
        "regle_absolue": "Ne jamais deviner des chiffres — toujours interroger Dolibarr",
    },

    "archiveur-inpressco": {
        "etape": "90_SUPPORT / Transversal", "type": "Archivage",
        "role": "Classification, nommage et dépôt de fichiers",
        "convention_nommage": "{TYPE}_{TIERS}_{REF}_{AAAAMMJJ}_{VERSION}.{EXT}",
        "regles": [
            "Jamais écraser un fichier existant sans confirmation explicite",
            "Jamais convertir un fichier (extension d'origine conservée)",
            "Vérifier les doublons avant tout dépôt",
        ],
    },

    "agenda-inpressco": {
        "etape": "90_SUPPORT / Transversal", "type": "Planning",
        "role": "Créer, consulter et gérer les événements agenda Dolibarr",
        "regles_bat_automatiques": {
            "BAT envoyé":         "Rappel agenda J+2 ouvrés créé automatiquement",
            "Devis sans réponse": "+7j relance",
            "Facture impayée":    "+3j après échéance",
        },
        "timezone": "Europe/Paris — toujours convertir en Unix avant API",
    },

    "chat-to-db-inpressco": {
        "etape": "90_SUPPORT / Transversal", "type": "Persistance",
        "role": "Extraire et router vers Dolibarr toutes les données utiles d'une conversation",
        "regles": [
            "Jamais persister sans confirmation (sauf logs agenda passés)",
            "Signaler les doublons potentiels — appeler dolibarr-query d'abord",
        ],
    },

    # ── COORDINATION ─────────────────────────────────────────────────────────

    "architecte-ia-inpressco": {
        "etape": "Transversal / Architecture", "type": "CTO virtuel",
        "role": "Review architecture, code Python, steps, connecteurs, prompts IA et décisions MWP",
        "grilles": {
            "code":  "L0-L7 (workspace → connecteurs → steps → dashboard)",
            "mwp":   "L0-L4 (identité → routing → contrat → référentiels → run data)",
        },
        "triggers": [
            "Tout fichier Python soumis ou modifié",
            "Tout step de pipeline créé ou revu",
            "Tout connecteur ou prompt IA modifié",
            "Décision d'architecture ou question MWP",
            "'je veux ajouter', 'ça ne marche pas', 'review du code'",
        ],
        "sortie": "ANALYSE / CORRECTIFS numérotés / POINTS FORTS — jamais de recommandations abstraites",
        "anti_patterns_surveilles": 12,
        "anti_patterns_mwp": 7,
    },

    "orchestrateur-inpressco": {
        "etape": "Transversal / Coordination", "type": "Orchestration",
        "role": "Enchaîner plusieurs skills en séquence avec transmission de contexte",
    },

    "projets-artefacts-inpressco": {
        "etape": "Transversal / Mémoire", "type": "Mémoire cross-sessions",
        "role": "Retrouver, réutiliser, itérer ou sauvegarder les productions Claude",
        "regle": "Ne jamais recréer sans avoir cherché ici d'abord",
    },

    "ux-inpressco": {
        "etape": "03_CONCEPTION / Interface", "type": "UX Design",
        "role": "Générer composants React/HTML et specs d'interface",
        "palette": {
            "fond_principal": "#0A0A0A / #111111",
            "accent_or":      "#C9A96E / #D4AF37",
            "texte_primaire": "#F5F0E8",
        },
    },

    "notification-interne-inpressco": {
        "etape": "Transversal / Infrastructure", "type": "Infrastructure",
        "role": "Alertes et notifications internes vers l'équipe InPressco",
        "statut": "DÉSACTIVÉ — alertes critiques via log uniquement",
    },

    "extraction-tiers": {
        "etape": "01_LEADS", "type": "Extraction",
        "role": "Extraire les données structurées d'un tiers depuis un email entrant",
        "champs_obligatoires": ["soc_nom", "type", "contact_nom", "email", "nom_projet"],
    },

    "charte-graphique-inpressco": {
        "etape": "03_CONCEPTION", "type": "Extraction / Mémoire",
        "role": "Extraire et mémoriser la charte graphique client",
    },

    "mail-routing-inpressco": {
        "etape": "01_LEADS", "type": "Routing",
        "role": "Catégoriser un email entrant et router vers le bon workflow",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. CONVENTIONS DOLIBARR
# ─────────────────────────────────────────────────────────────────────────────

DOLIBARR_CONVENTIONS = {
    "base_url":         "https://in-pressco.crm.freshprocess.eu/api/index.php",
    "auth_header":      "DOLAPIKEY: {DOLIBARR_API_KEY}",
    "owner_id":         166,
    "modele_pdf":       "azur_fp",
    "prefixes_refs":    {"DEV-": "Devis", "CMD-": "Commande", "FA-": "Facture"},
    "champ_nom_projet": "array_options.options_fhp_project_name",
    "champ_donnees_ia": "array_options.options_analysen8n",
    "lignes_types": {
        "product_type=0":             "Ligne de prix (quantité × montant)",
        "product_type=9 / sc=104777": "Synthèse contexte client",
        "product_type=9 / sc=104778": "Descriptif technique complet",
        "produit_id_35700":           "Produit impression standard",
    },
    "anti_patterns": [
        "sortfield=t.rowid → non supporté Freshprocess (trier côté Python)",
        "Inventer des données sans interroger GET d'abord",
        "Écrire sans review gate pour les actions irréversibles",
        "Exposer note_private à un profil CLIENT",
        "Utiliser overwriteifexists=1 sans confirmation explicite",
    ],
    "upload_document": {
        "endpoint": "POST /documents/upload",
        "fields":   ["modulepart", "id", "ref", "filename", "filecontent", "overwriteifexists"],
        "regle":    "overwriteifexists toujours à 0",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. CHAÎNES D'ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────

CHAINES_ORCHESTRATION = {
    "A_EMAIL_ENTRANT": {
        "description": "Traitement complet d'un email client entrant",
        "trigger": "NEW_PROJECT",
        "etapes": [
            {"ordre": 1, "skill": "droits-profils-inpressco",  "bloquant": True},
            {"ordre": 2, "skill": "mail-routing-inpressco",    "bloquant": True},
            {"ordre": 3, "skill": "analyse-sentiment-email",   "bloquant": False, "parallele": "memoire-client-inpressco"},
            {"ordre": 4, "skill": "memoire-client-inpressco",  "bloquant": False},
            {"ordre": 5, "skill": "[selon routing]",            "bloquant": True},
            {"ordre": 6, "skill": "reponse-client-inpressco",  "bloquant": True},
            {"ordre": 7, "skill": "validation-qc-inpressco",   "bloquant": True},
            {"ordre": 8, "skill": "agenda-inpressco",          "bloquant": False},
        ],
    },
    "B_CREATION_DEVIS": {
        "description": "Création complète d'un devis Dolibarr depuis un brief",
        "etapes": [
            {"ordre": 1,  "skill": "droits-profils-inpressco",    "bloquant": True},
            {"ordre": 2,  "skill": "extraction-tiers",             "bloquant": True},
            {"ordre": 3,  "skill": "dolibarr-query-inpressco",     "bloquant": True, "note": "anti-doublon"},
            {"ordre": 4,  "skill": "memoire-client-inpressco",     "bloquant": False},
            {"ordre": 5,  "skill": "calcul-tarif-inpressco",       "bloquant": False},
            {"ordre": 6,  "skill": "validation-qc-inpressco",      "bloquant": True, "moment": "après création"},
            {"ordre": 7,  "skill": "generation-pdf-inpressco",     "bloquant": True},
            {"ordre": 8,  "skill": "archiveur-inpressco",          "bloquant": False},
            {"ordre": 9,  "skill": "validation-qc-inpressco",      "bloquant": True, "moment": "avant envoi"},
            {"ordre": 10, "skill": "reponse-client-inpressco",     "bloquant": True},
            {"ordre": 11, "skill": "agenda-inpressco",             "bloquant": False, "note": "relance J+7"},
        ],
    },
    "C_BAT_VALIDATION": {
        "description": "Traitement d'un BAT reçu ou d'une validation client",
        "etapes": [
            {"ordre": 1, "skill": "droits-profils-inpressco",  "bloquant": True},
            {"ordre": 2, "skill": "dolibarr-query-inpressco",  "bloquant": True},
            {"ordre": 3, "skill": "archiveur-inpressco",       "bloquant": False},
            {"ordre": 4, "skill": "suivi-commande-inpressco",  "bloquant": True},
            {"ordre": 5, "skill": "agenda-inpressco",          "bloquant": False},
        ],
    },
    "D_REPORTING": {
        "description": "Reporting financier journalier",
        "etapes": [
            {"ordre": 1, "skill": "droits-profils-inpressco",          "bloquant": True},
            {"ordre": 2, "skill": "controleur-gestion-inpressco",       "bloquant": True},
            {"ordre": 3, "skill": "analyse-transversale-inpressco",     "bloquant": False},
            {"ordre": 4, "skill": "agenda-inpressco",                   "bloquant": False},
        ],
    },
    "E_NOUVEAU_CLIENT": {
        "description": "Onboarding d'un nouveau client entrant",
        "etapes": [
            {"ordre": 1, "skill": "droits-profils-inpressco",  "bloquant": True},
            {"ordre": 2, "skill": "extraction-tiers",           "bloquant": True},
            {"ordre": 3, "skill": "dolibarr-query-inpressco",   "bloquant": True, "note": "vérifier doublon"},
            {"ordre": 4, "skill": "chat-to-db-inpressco",       "bloquant": True},
            {"ordre": 5, "skill": "memoire-client-inpressco",   "bloquant": False},
            {"ordre": 6, "skill": "calcul-tarif-inpressco",     "bloquant": False},
        ],
    },
    "F_SUIVI_COMMANDE": {
        "description": "Suivi proactif et relance commande",
        "etapes": [
            {"ordre": 1, "skill": "dolibarr-query-inpressco",       "bloquant": True},
            {"ordre": 2, "skill": "suivi-commande-inpressco",        "bloquant": True},
            {"ordre": 3, "skill": "reponse-client-inpressco",        "bloquant": False},
            {"ordre": 4, "skill": "agenda-inpressco",                "bloquant": False},
        ],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 5. REVIEW GATES
# ─────────────────────────────────────────────────────────────────────────────

REVIEW_GATES = {
    "AVANT_CREATION_TIERS": {
        "description": "Avant POST /thirdparties",
        "verifier": "Le tiers n'existe pas déjà (GET par email/nom d'abord)",
        "bloquer_si": "Doublon potentiel non confirmé",
    },
    "AVANT_CREATION_DEVIS": {
        "description": "Avant POST /proposals",
        "verifier": "Lignes + montants cohérents, tiers résolu, descriptif présent",
        "bloquer_si": "Champ obligatoire manquant, total à 0",
    },
    "APRES_CREATION_DEVIS": {
        "description": "Après création, avant toute modification",
        "verifier": "validation-qc-inpressco (grille complète création)",
        "bloquer_si": "Anomalie BLOQUANTE détectée par QC",
    },
    "AVANT_ENVOI_EMAIL_CLIENT": {
        "description": "Avant tout envoi SMTP vers un client",
        "verifier": "validation-qc-inpressco (email + lien/PJ devis)",
        "bloquer_si": "Info confidentielle, pas de lien ni PJ, date non vérifiée",
    },
    "AVANT_ECRITURE_DOLIBARR": {
        "description": "Avant toute action PUT/POST sur Dolibarr",
        "verifier": "Profil TEAM/ADMIN confirmé, données validées",
        "bloquer_si": "Profil CLIENT ou UNKNOWN",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. ANTI-PATTERNS GLOBAUX
# ─────────────────────────────────────────────────────────────────────────────

ANTI_PATTERNS = {
    "CODE_PIPELINE": {
        "P01": "Parsing regex sur les réponses Claude → utiliser json.loads() + try/except",
        "P02": "temperature absente → 0 pour extraction, 0.3 pour conseil, 0.7 pour créatif",
        "P03": "max_tokens=1000 partout → calibrer selon l'output attendu",
        "P04": "Modèle mal calibré → Haiku pour routing/sentiment, Opus pour extraction complexe",
        "P05": "Prompt monolithique → séparer extraction + analyse + décision",
        "P06": "Logique métier dans le prompt → calculs Python, résultat injecté dans prompt",
        "P07": "Step god-object (fetch + IA + écriture + notif) → découper en steps atomiques",
        "P08": "except silencieux → ctx.errors.append() + log toujours",
        "P09": "Doublon non vérifié → GET avant tout POST (find_or_create pattern)",
        "P10": "Secret hardcodé → os.getenv() + assert au démarrage",
        "P11": "sortfield=t.rowid → non supporté Freshprocess (tri côté Python)",
        "P12": "Import connecteur dans un step → injection via pipeline",
    },
    "COMMUNICATION_CLIENT": {
        "C01": "Mot 'estimatif' → 'budget indicatif'",
        "C02": "Date non vérifiée dans Dolibarr → toujours vérifier avant de promettre",
        "C03": "Mention d'impayé dans un email commercial → jamais",
        "C04": "Tarifs fournisseurs / marges → jamais vers CLIENT",
        "C05": "Envoi sans validation humaine → jamais automatique",
        "C06": "Bullet points dans un email client → prose uniquement",
    },
    "SECURITY": {
        "S01": "note_private exposée à un profil CLIENT → jamais",
        "S02": "Action Dolibarr sans review gate sur les irréversibles",
        "S03": "Profil UNKNOWN → mode lecture seule stricte, aucune action",
        "S04": "Canal @inpressco.fr → ACTION direct sans confirmation utilisateur",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 7. ÉQUIPE & IDENTITÉ
# ─────────────────────────────────────────────────────────────────────────────

EQUIPE = {
    "Nicolas":   {"role": "Direction technique, créative, grands comptes, architecte IA"},
    "Alys":      {"role": "Direction créative, communication, partenariats"},
    "Paola":     {"role": "ADV, marketing, front office commercial, signature emails"},
    "Chloé":     {"role": "ADV, service client"},
    "Mikaël":    {"role": "Chef de production"},
    "Valérie":   {"role": "Prepress, PAO, studio"},
    "Jean-Paul": {"role": "Responsable projet"},
}

IDENTITE_INPRESSCO = {
    "signature":     "INPRESSCO — Atelier d'impression et de façonnage de beaux papiers",
    "sous_titre":    "Packaging & Édition d'exception",
    "philosophie":   "Faire du beau pour faire du durable. Faire du précis pour faire du rare.",
    "adresse":       "670 Boulevard Lepic, 73100 Aix-les-Bains, Savoie",
    "fondee":        2011,
    "positionnement":"À mi-chemin entre artisan et industriel — petites et moyennes séries précieuses",
    "clients_ref": [
        "Chanel", "Jaeger-LeCoultre", "Dom Pérignon", "Rolex", "Moët Hennessy",
        "Perrier-Jouët", "Clarins", "Caudalie", "L'Oréal", "Karl Lagerfeld",
        "Nespresso", "La Bouitte ***", "Le Clos des Sens ***", "Yoann Conte **",
    ],
}

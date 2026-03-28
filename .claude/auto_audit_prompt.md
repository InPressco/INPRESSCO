# auto_audit_prompt.md — Instructions audit InPressco MWP

## Rôle
Ce système d'audit trace automatiquement toutes les actions de l'agent Claude dans le workspace InPressco MWP.

## Données loguées
Chaque entrée `audit_YYYY-MM-DD.jsonl` contient :
- `ts` : horodatage ISO 8601
- `payload` : payload brut de l'événement Claude Code (tool_name, tool_input, tool_result)

## Emplacement des logs
```
~/inpressco-mwp/.audit_logs/audit_YYYY-MM-DD.jsonl
```

## Rotation
Les logs de plus de 30 jours sont supprimés automatiquement.

## Intégration Claude Code (settings.json)
Pour activer ce hook, ajouter dans `~/.claude/settings.json` :

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/inpressco-mwp/.claude/auto_audit.sh"
          }
        ]
      }
    ]
  }
}
```

## Outils exclus de l'audit (optionnel)
Pour exclure certains outils (ex: Read), utiliser le champ `matcher` :
```json
"matcher": "^(?!Read$|Glob$)"
```

## Analyse des logs
Pour inspecter les actions d'une journée :
```bash
cat ~/inpressco-mwp/.audit_logs/audit_2026-03-28.jsonl | jq .
```

Pour filtrer par outil :
```bash
grep '"tool_name":"Write"' ~/inpressco-mwp/.audit_logs/audit_2026-03-28.jsonl | jq .
```

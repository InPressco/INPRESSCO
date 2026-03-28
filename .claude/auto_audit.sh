#!/bin/bash
# auto_audit.sh — Hook Claude Code PostToolUse pour InPressco MWP
# Logue chaque appel d'outil dans ~/inpressco-mwp/.audit_logs/

AUDIT_DIR="$HOME/Desktop/Bureau - MacBook Pro de nicolas/inpressco-mwp/.audit_logs"
DATE=$(date +"%Y-%m-%d")
TIMESTAMP=$(date +"%Y-%m-%dT%H:%M:%S")
LOG_FILE="$AUDIT_DIR/audit_${DATE}.jsonl"

# Lire le payload JSON depuis stdin (fourni par Claude Code)
INPUT=$(cat)

# Construire l'entrée de log
ENTRY=$(printf '{"ts":"%s","payload":%s}\n' "$TIMESTAMP" "$INPUT")

# Écrire dans le fichier de log journalier
echo "$ENTRY" >> "$LOG_FILE"

# Rotation : conserver les 30 derniers jours uniquement
find "$AUDIT_DIR" -name "audit_*.jsonl" -mtime +30 -delete 2>/dev/null

exit 0

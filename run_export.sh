#!/bin/bash
# Shell wrapper for export_streamed.py
# - Uses caffeinate to prevent macOS sleep
# - Auto-restarts on failure
# - Exits cleanly when export completes

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="export_streamed.log"
COMPLETE_MARKER="export_complete.marker"

# Remove old completion marker
rm -f "$COMPLETE_MARKER"

echo "$(date): Starting export pipeline with caffeinate..." | tee -a "$LOG_FILE"
echo "$(date): Press Ctrl+C to stop" | tee -a "$LOG_FILE"

# Run with caffeinate to prevent sleep
# -i: prevent idle sleep
# -s: prevent system sleep (when on AC power)
# -d: prevent display sleep
caffeinate -i -s -d bash -c '
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    LOG_FILE="export_streamed.log"
    COMPLETE_MARKER="export_complete.marker"
    MAX_RESTARTS=100
    RESTART_COUNT=0
    
    while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
        echo "$(date): Starting export_streamed.py (attempt $((RESTART_COUNT + 1)))..." | tee -a "$LOG_FILE"
        
        python3 export_streamed.py 2>&1 | tee -a "$LOG_FILE"
        EXIT_CODE=${PIPESTATUS[0]}
        
        if [ $EXIT_CODE -eq 0 ]; then
            echo "$(date): Export completed successfully!" | tee -a "$LOG_FILE"
            touch "$COMPLETE_MARKER"
            exit 0
        fi
        
        RESTART_COUNT=$((RESTART_COUNT + 1))
        echo "$(date): Script exited with code $EXIT_CODE. Restarting in 10 seconds... ($RESTART_COUNT/$MAX_RESTARTS)" | tee -a "$LOG_FILE"
        sleep 10
    done
    
    echo "$(date): Max restarts reached. Giving up." | tee -a "$LOG_FILE"
    exit 1
'

# Check if completed
if [ -f "$COMPLETE_MARKER" ]; then
    echo "$(date): Export finished successfully!" | tee -a "$LOG_FILE"
    rm -f "$COMPLETE_MARKER"
    exit 0
else
    echo "$(date): Export did not complete. Check $LOG_FILE for details." | tee -a "$LOG_FILE"
    exit 1
fi

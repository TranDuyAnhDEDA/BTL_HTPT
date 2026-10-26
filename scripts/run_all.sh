#!/bin/bash
echo "========================================================"
echo " P2P File-Sharing System (BitTorrent Simulation)"
echo " Starting Tracker and Dashboard on http://localhost:8000"
echo "========================================================"

python -m uvicorn src.tracker.server:app --host 0.0.0.0 --port 8000 --reload

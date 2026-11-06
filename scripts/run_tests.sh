#!/bin/bash
echo "========================================================"
echo " RUNNING ALL 5 DISTRIBUTED SYSTEMS TEST SUITES"
echo "========================================================"

echo ""
echo "[TEST 1/5] Step 1: Chunking, SHA-256 Hashing, Metadata & Merging"
python3 tests/test_step1.py || exit 1

echo ""
echo "[TEST 2/5] Step 2: FastAPI Tracker Server & Peer Discovery"
python3 tests/test_step2.py || exit 1

echo ""
echo "[TEST 3/5] Step 3: Direct 1-on-1 P2P TCP Socket Transfer"
python3 tests/test_step3.py || exit 1

echo ""
echo "[TEST 4/5] Step 4: Multi-Peer Parallel Download & Seed-while-Leeching"
python3 tests/test_step4.py || exit 1

echo ""
echo "[TEST 5/5] Step 5: Fault Tolerance, Peer Failover & Corrupted Chunk Detection"
python3 tests/test_step5.py || exit 1

echo ""
echo "========================================================"
echo " ALL 5 TEST SUITES PASSED PERFECTLY! 100% SUCCESS!"
echo "========================================================"

@echo off
REM Trustworthy Document Pipeline - Golden path demo for hackathon judges
REM Runs the complete pipeline demo. No API key required. Fully offline.

echo.
echo ============================================
echo   Trustworthy Document Pipeline - Judge Demo
echo ============================================
echo No API key needed. Fully offline. Deterministic.
echo.

echo [1] Processing clean invoice...
python -m trustdocs.cli --demo
echo.

echo [2] Processing inconsistent invoice...
python -m trustdocs.cli --demo-inconsistent --decision approve
echo.

echo [3] Generating evidence...
python -m trustdocs.cli process sample/invoice.pdf --decision approve --extractor local
echo.

echo [4] Verifying evidence...
python -m trustdocs.cli verify rejected.evidence.json
echo.

echo [5] Running attack demo...
python -m trustdocs.cli attack
echo.

echo [6] Provider swap - local extractor...
python -m trustdocs.cli process sample/invoice.pdf --extractor local --decision approve
echo.

echo ============================================
echo   Demo complete
echo ============================================
echo.
echo Key takeaways:
echo   1. Every decision produces a tamper-evident evidence record
echo   2. Chained ledger catches deletion, insertion, reordering
echo   3. Published head catches tail truncation
echo   4. Evidence layer survives extractor replacement
echo   5. Full attack demo: python -m trustdocs attack
echo.

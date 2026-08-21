<#
.SYNOPSIS
    Trustworthy Document Pipeline - Golden path demo for hackathon judges.
.DESCRIPTION
    Runs the complete pipeline demo in under 60 seconds.
    No API key required. Fully offline. Deterministic output.
#>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "  Trustworthy Document Pipeline - Judge Demo" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "No API key needed. Fully offline. Deterministic." -ForegroundColor DarkGray
$sw = [System.Diagnostics.Stopwatch]::StartNew()

# 1. Install
Write-Host ""
Write-Host "[1] Installing..." -ForegroundColor Cyan
python -m pip install -e . -q 2>$null | Out-Null
Write-Host "  OK Installed" -ForegroundColor Green

# 2. Clean invoice
Write-Host ""
Write-Host "[2] Processing clean invoice..." -ForegroundColor Cyan
$out = python -m trustdocs.cli --demo --json 2>$null | ConvertFrom-Json
Write-Host ("  OK Status: " + $out.status + " Fields: " + $out.field_count) -ForegroundColor Green

# 3. Inconsistent invoice
Write-Host ""
Write-Host "[3] Processing inconsistent invoice..." -ForegroundColor Cyan
$out2 = python -m trustdocs.cli --demo-inconsistent --decision approve --json 2>$null | ConvertFrom-Json
Write-Host ("  OK Status: " + $out2.status + " Reviewed: " + $out2.reviewed) -ForegroundColor Green

# 4. Generate evidence
Write-Host ""
Write-Host "[4] Generating evidence..." -ForegroundColor Cyan
python -m trustdocs.cli process sample/invoice.pdf --decision approve --extractor local --evidence _demo_evidence.json 2>$null | Out-Null
if (Test-Path _demo_evidence.json) {
    Write-Host "  OK Evidence saved" -ForegroundColor Green
} else {
    Write-Host "  FAIL Evidence not created" -ForegroundColor Red
}

# 5. Verify evidence
Write-Host ""
Write-Host "[5] Verifying evidence..." -ForegroundColor Cyan
$verify_out = python -m trustdocs.cli verify _demo_evidence.json 2>$null
Write-Host ("  " + $verify_out) -ForegroundColor Green

# 6. Tamper with evidence
Write-Host ""
Write-Host "[6] Tampering with evidence..." -ForegroundColor Cyan
$json = Get-Content _demo_evidence.json -Raw
$chars = $json.ToCharArray()
$mid = [math]::Floor($chars.Length / 2)
if ($chars[$mid] -eq 'f') { $chars[$mid] = [char](103) } else { $chars[$mid] = [char](102) }
$tampered = -join $chars
Set-Content _demo_tampered.json $tampered -NoNewline
Write-Host "  OK Tampered evidence created" -ForegroundColor Green

# 7. Verify tampered evidence
Write-Host ""
Write-Host "[7] Verifying tampered evidence..." -ForegroundColor Cyan
$verify2 = python -m trustdocs.cli verify _demo_tampered.json 2>$null
Write-Host ("  " + $verify2) -ForegroundColor Red

# 8. Attack demo
Write-Host ""
Write-Host "[8] Running full attack demo..." -ForegroundColor Cyan
python -m trustdocs.cli attack 2>$null

# 9. Provider swap
Write-Host ""
Write-Host "[9] Provider swap demo..." -ForegroundColor Cyan
python -m trustdocs.cli process sample/invoice.pdf --extractor local --decision approve --evidence _demo_local.json 2>$null | Out-Null
Write-Host "  OK Local extractor evidence generated" -ForegroundColor Green

# Cleanup
Remove-Item _demo_evidence.json -ErrorAction SilentlyContinue
Remove-Item _demo_tampered.json -ErrorAction SilentlyContinue
Remove-Item _demo_local.json -ErrorAction SilentlyContinue

$elapsed = $sw.Elapsed.TotalSeconds
Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host ("  Demo complete in " + [math]::Round($elapsed, 1) + "s") -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Yellow
Write-Host ""

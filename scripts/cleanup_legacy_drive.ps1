param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$master = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$keepNotebooks = @('Krishna_Warm_Production_Benchmark.ipynb', 'Krishna_Train_Resume.ipynb')
$legacyResults = @(
    'manual_batch_test_results_v1.json',
    'rag_comparison_results_v1.json',
    'rag_v2_comparison_results.json',
    'rag_v2_1_comparison_results.json',
    'rag_fast_regression_predictions.json',
    'rag_improved_regression_predictions.json'
)
$legacyGuides = @('FAST_RAG_RUN.md', 'IMPROVED_RAG_RUN.md')
$generatedDirectories = @(
    'backend\__pycache__',
    'backend\app\__pycache__',
    'frontend\dist',
    'frontend\.firebase'
)

foreach ($label in @('G', 'H')) {
    $root = [System.IO.Path]::GetFullPath("${label}:\My Drive\LegalAI")
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "Drive unavailable: $root" }
    Write-Output "Checking $root"
    $notebooks = Get-ChildItem -LiteralPath $root -File -Filter 'Krishna_*.ipynb'
    foreach ($file in $notebooks) {
        if ($file.Name -in $keepNotebooks) { continue }
        $archived = Join-Path $master ("archive\drive_notebooks\$label\" + $file.Name)
        if (-not (Test-Path -LiteralPath $archived -PathType Leaf)) { throw "Missing local archive: $archived" }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash -ne
            (Get-FileHash -Algorithm SHA256 -LiteralPath $archived).Hash) {
            throw "Archive mismatch: $($file.FullName)"
        }
        Write-Output "  archived old notebook: $($file.Name)"
        if ($Apply) { Remove-Item -LiteralPath $file.FullName -Force }
    }
    foreach ($name in $legacyResults) {
        $file = Join-Path $root $name
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
        $archived = Join-Path $master ("release_evidence\$label\$name")
        if (-not (Test-Path -LiteralPath $archived -PathType Leaf)) { throw "Missing local evidence: $archived" }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash -ne
            (Get-FileHash -Algorithm SHA256 -LiteralPath $archived).Hash) {
            throw "Evidence archive mismatch: $file"
        }
        Write-Output "  archived old result: $name"
        if ($Apply) { Remove-Item -LiteralPath $file -Force }
    }
    foreach ($name in $legacyGuides) {
        $file = Join-Path $root $name
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
        $archived = Join-Path $master ("archive\research_notebooks\$name")
        if (-not (Test-Path -LiteralPath $archived -PathType Leaf)) { throw "Missing local guide: $archived" }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash -ne
            (Get-FileHash -Algorithm SHA256 -LiteralPath $archived).Hash) {
            throw "Guide archive mismatch: $file"
        }
        Write-Output "  archived old guide: $name"
        if ($Apply) { Remove-Item -LiteralPath $file -Force }
    }
    foreach ($relative in $generatedDirectories) {
        $candidate = Join-Path $root $relative
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }
        $resolved = [System.IO.Path]::GetFullPath($candidate)
        if (-not $resolved.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Generated path outside Drive project: $resolved"
        }
        $item = Get-Item -LiteralPath $resolved -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to delete linked directory: $resolved"
        }
        Write-Output "  generated cache: $relative"
        if ($Apply) { Remove-Item -LiteralPath $resolved -Recurse -Force }
    }
}
if (-not $Apply) { Write-Output 'Dry run only. Run again with -Apply to remove these verified legacy files.' }

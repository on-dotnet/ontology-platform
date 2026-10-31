#Requires -Version 7.4
<#
.SYNOPSIS
编码早期复用正式构包器的证据规范化，不构包、不查询CI、不认证产品。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$EvidenceFile,
    [string]$ExpectedHead,
    [string]$ScreenshotSelection,
    [string]$IgnoredInventoryFile,
    [string]$Root = (Split-Path $PSScriptRoot -Parent)
)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'create-review-package.ps1') -Library
    if ($ExpectedHead -and $ExpectedHead -cnotmatch '^[0-9a-f]{40}$') { throw 'CI_EVIDENCE: full expected Head required' }
    $file = Get-Item -LiteralPath $EvidenceFile
    if ($file.LinkType -or $file.Length -gt 1MB) { throw 'EVIDENCE_SCHEMA: linked or oversized evidence refused' }
    $bytes = [IO.File]::ReadAllBytes($file.FullName)
    $value = Read-ReviewEvidenceSchema $bytes $ExpectedHead
    # 直接调用生产规范化函数，历史metadata仍保持非权威且不被丢失。
    $path = 'docs/evidence/PREFLIGHT/validation.json'
    $snapshot = @{ GitBytes = @{ $path = $bytes }; Mapping = @(); DiffCheckExit = 0 }
    $normalized = Get-ReviewEvidence $snapshot $path 'PARTIAL' $null
    if ($ExpectedHead -and $value.ContainsKey('validationSource') -and $value.validationSource -ceq 'LOCAL') { $null = Get-ReviewLocalBinding $Root $snapshot $path $ExpectedHead }
    if ($IgnoredInventoryFile) {
        $inventory = Get-Content -Raw -LiteralPath $IgnoredInventoryFile | ConvertFrom-Json -AsHashtable
        Assert-ReviewIgnoredInventory $inventory
    }
    $count = 0
    $compressedBytes = [long]0
    if ($ScreenshotSelection) {
        $selection = Get-Content -Raw -LiteralPath $ScreenshotSelection | ConvertFrom-Json -AsHashtable
        if ($selection.schemaVersion -ne 1 -or $selection.screenshots -isnot [array] -or $selection.screenshots.Count -gt 12) { throw 'SCREENSHOT_SELECTION: at most12 stable screenshots required' }
        $paths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $keys = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $payloads = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach ($shot in $selection.screenshots) {
            Assert-ReviewPath $shot.path
            if (-not $shot.path.StartsWith('docs/evidence/', [StringComparison]::Ordinal) -or -not $shot.path.EndsWith('.png', [StringComparison]::OrdinalIgnoreCase) -or $shot.stable -isnot [bool] -or -not $shot.stable -or -not $shot.page -or -not $shot.theme -or -not $shot.viewport -or -not $paths.Add($shot.path) -or -not $keys.Add(($shot.page + '|' + $shot.theme + '|' + $shot.viewport))) { throw 'SCREENSHOT_SELECTION: stable unique semantic selection required' }
            $image = Get-Item -LiteralPath (Join-Path $Root $shot.path)
            if ($image.LinkType -or $image.Length -gt 15MB) { throw 'SCREENSHOT_SELECTION: ordinary bounded image required' }
            $raw = [IO.File]::ReadAllBytes($image.FullName)
            Assert-ReviewPngDimensions $raw $shot.viewport
            if ($payloads.Add((Get-ReviewHash $raw))) { $compressedBytes += Get-ReviewDeflatedSize $raw }
            if ($compressedBytes -gt 3MB) { throw 'SCREENSHOT_BUDGET: compressed PNG budget exceeded' }
            $count++
        }
    }
    Write-Output (@{ status = 'PASS'; scope = 'EVIDENCE_SCHEMA_ONLY'; checks = @($normalized.checks).Count; screenshotCount = $count; screenshotCompressedBytes = $compressedBytes; actualCi = 'NOT_VERIFIED'; product = 'NOT_RUN' } | ConvertTo-Json -Compress)
    exit 0
} catch {
    Write-Error ('EVIDENCE_PREFLIGHT_REFUSED: ' + $_.Exception.Message)
    exit 1
}

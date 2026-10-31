#Requires -Version 7.4
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../verify.ps1') -Library
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('ontology-log-boundary-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path (Join-Path $fixture 'artifacts/process') -Force
$job = $null
try {
    $source = Join-Path $fixture 'source.cs'
    [IO.File]::WriteAllText($source, 'invalid-eof')
    # 并发过程输出包含故意错误格式，不能再次进入源码扫描；真实源码错误仍须发现。
    $writer = Join-Path $fixture 'artifacts/process/writer.ps1'
    [IO.File]::WriteAllText($writer, @'
param($folder)
foreach ($index in 1..40) {
    [IO.File]::AppendAllText((Join-Path $folder 'artifacts/process/failure.log'), "fixture`rbroken-$index")
    Start-Sleep -Milliseconds 10
}
'@)
    # 使用已核实可执行pwsh入口，避免Mac .NET tool的Start-Job自定位到不可执行DLL。
    $info = [Diagnostics.ProcessStartInfo]::new((Get-Command pwsh).Source)
    foreach ($arg in @('-NoProfile', '-File', $writer, $fixture)) { $info.ArgumentList.Add($arg) }
    $job = [Diagnostics.Process]::Start($info)
    foreach ($index in 1..4) {
        $files = @(Get-SourceFiles -Directory $fixture)
        if ($files.Count -ne 1 -or $files[0].FullName -ne $source) { throw 'Process output entered source enumeration' }
    }
    if (-not $job.WaitForExit(15000) -or $job.ExitCode -ne 0) { throw 'Concurrent writer did not finish' }
    $failed = @(Test-Repository -RepositoryRoot $fixture | Where-Object { $_.Check -eq 'text-format' })
    if ($failed.Count -ne 1 -or $failed[0].Message -notlike 'source.cs *') { throw 'Tracked source error was masked by output exclusion' }
    [IO.File]::WriteAllText($source, "valid-eof`n")
    $clean = @(Test-Repository -RepositoryRoot $fixture | Where-Object { $_.Check -eq 'text-format' })
    if ($clean.Count -ne 0) { throw 'Completed process output was scanned as source' }
    Write-Output 'PreflightLogs: 3 boundary/concurrent/source checks PASS; not product validation.'
} finally {
    if ($job) {
        if (-not $job.HasExited) { $job.Kill(); $job.WaitForExit() }
        $job.Dispose()
    }
    Remove-Item -LiteralPath $fixture -Recurse -Force
}

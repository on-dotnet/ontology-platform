#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PostgresContainer,
    [Parameter(Mandatory)][string]$FusekiContainer,
    [Parameter(Mandatory)][string]$RustfsContainer,
    [Parameter(Mandatory)][string]$KeycloakContainer,
    [ValidatePattern('^[a-z0-9][a-z0-9-]{0,47}$')][string]$VolumePrefix = 'ontology-platform',
    [uri]$FusekiEndpoint = 'http://localhost:13030',
    [uri]$RustfsEndpoint = 'http://localhost:19000',
    [uri]$KeycloakHealthEndpoint = 'http://localhost:19090/health/ready'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# 只使用当前进程已有秘密，不读取源文件、Docker认证或用户秘密存储文件。
$accessKey = [Environment]::GetEnvironmentVariable('Parameters__rustfs-access-key')
$secretKey = [Environment]::GetEnvironmentVariable('Parameters__rustfs-secret-key')
$postgresPassword = [Environment]::GetEnvironmentVariable('Parameters__postgres-password')
if ([string]::IsNullOrWhiteSpace($accessKey) -or [string]::IsNullOrWhiteSpace($secretKey) -or [string]::IsNullOrWhiteSpace($postgresPassword)) {
    throw '当前进程缺少PostgreSQL或RustFS秘密参数，不能执行实际S3持久化验证。'
}

function Invoke-DockerChecked {
    param([Parameter(Mandatory)][string[]]$DockerArguments)
    $result = & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker验证命令失败，退出码 $LASTEXITCODE。" }
    return $result
}

function Invoke-PostgresSql {
    param([string]$Database, [string]$Sql)
    # 将本次已注入的开发秘密只传给Docker子进程环境，命令行和输出均不含密码。
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'docker'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Environment['PGPASSWORD'] = $postgresPassword
    foreach ($argument in @('exec', '--env', 'PGPASSWORD', $PostgresContainer, 'psql', '-w', '-U', 'postgres', '-d', $Database, '-At', '-v', 'ON_ERROR_STOP=1', '-c', $Sql)) {
        $startInfo.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::new()
    try {
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $standardOutput = $process.StandardOutput.ReadToEndAsync()
        $standardError = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) { throw "PostgreSQL开发探针失败，退出码 $($process.ExitCode)，不输出连接凭证。" }
        return $standardOutput.GetAwaiter().GetResult().Trim()
    }
    finally { $process.Dispose() }
}

function Assert-Volume {
    param([string]$Container, [string]$Volume, [string]$Destination)
    $mounts = Invoke-DockerChecked -DockerArguments @('inspect', '--format', '{{json .Mounts}}', $Container) | ConvertFrom-Json
    if (-not @($mounts | Where-Object { $_.Type -eq 'volume' -and $_.Name -eq $Volume -and $_.Destination -eq $Destination }).Count) {
        throw "容器 $Container 缺少预期命名卷 $Volume 到 $Destination，停止重启验证。"
    }
}

function Wait-HttpReady {
    param([uri]$Endpoint)
    $deadline = [DateTimeOffset]::UtcNow.AddMinutes(3)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Endpoint -TimeoutSec 5 -SkipHttpErrorCheck
            if ($response.StatusCode -eq 200) { return }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "资源健康检查超时：$Endpoint"
}

function Get-HexHash {
    param([byte[]]$Bytes)
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}

function Get-Hmac {
    param([byte[]]$Key, [string]$Text)
    return ,([Security.Cryptography.HMACSHA256]::HashData($Key, [Text.Encoding]::UTF8.GetBytes($Text)))
}

function Invoke-S3Probe {
    param([string]$Method, [string]$Path, [string]$Payload = '')
    # 只签名本次确定性开发探针，不引入额外S3 SDK或持久化密钥。
    $timestamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $date = $timestamp.Substring(0, 8)
    $scope = "$date/us-east-1/s3/aws4_request"
    $payloadBytes = [Text.Encoding]::UTF8.GetBytes($Payload)
    $payloadHash = Get-HexHash $payloadBytes
    $canonicalHeaders = "host:$($RustfsEndpoint.Authority)`nx-amz-content-sha256:$payloadHash`nx-amz-date:$timestamp`n"
    $signedHeaders = 'host;x-amz-content-sha256;x-amz-date'
    $canonicalRequest = "$Method`n$Path`n`n$canonicalHeaders`n$signedHeaders`n$payloadHash"
    $stringToSign = "AWS4-HMAC-SHA256`n$timestamp`n$scope`n$(Get-HexHash ([Text.Encoding]::UTF8.GetBytes($canonicalRequest)))"
    $dateKey = Get-Hmac ([Text.Encoding]::UTF8.GetBytes("AWS4$secretKey")) $date
    $regionKey = Get-Hmac $dateKey 'us-east-1'
    $serviceKey = Get-Hmac $regionKey 's3'
    $signingKey = Get-Hmac $serviceKey 'aws4_request'
    $signature = [Convert]::ToHexString((Get-Hmac $signingKey $stringToSign)).ToLowerInvariant()
    $headers = @{
        Authorization = "AWS4-HMAC-SHA256 Credential=$accessKey/$scope, SignedHeaders=$signedHeaders, Signature=$signature"
        'x-amz-date' = $timestamp
        'x-amz-content-sha256' = $payloadHash
    }
    $request = @{
        Uri = [uri]::new($RustfsEndpoint, $Path)
        Method = $Method
        Headers = $headers
        TimeoutSec = 20
        SkipHttpErrorCheck = $true
        SkipHeaderValidation = $true
    }
    if ($Method -eq 'PUT') { $request.Body = $payloadBytes }
    try { $response = Invoke-WebRequest @request }
    catch { throw 'S3开发探针传输失败；隐藏原始异常以保护签名头和临时凭证。' }
    if ($response.StatusCode -notin @(200, 204)) {
        throw "S3开发探针失败：$Method $Path HTTP $($response.StatusCode)，不记录签名头或凭证。"
    }
    return $response
}

# 检查实际挂载后再写入随机探针，保护卷配置验证的有效性。
Assert-Volume $PostgresContainer "$VolumePrefix-postgres-data" '/var/lib/postgresql'
Assert-Volume $FusekiContainer "$VolumePrefix-fuseki-data" '/fuseki/databases'
Assert-Volume $RustfsContainer "$VolumePrefix-rustfs-data" '/data'
Wait-HttpReady ([uri]::new($FusekiEndpoint, '/$/ping'))
Wait-HttpReady ([uri]::new($RustfsEndpoint, '/health/ready'))
Wait-HttpReady $KeycloakHealthEndpoint

# 只使用独立probe schema、URN和bucket，不写入产品业务数据。
$marker = [Guid]::NewGuid().ToString('N')
$bucket = "g1infra-probe-$marker"
$subject = "urn:ontology-platform:development:probe:$marker"
$sql = "CREATE SCHEMA IF NOT EXISTS infrastructure_probe; CREATE TABLE IF NOT EXISTS infrastructure_probe.restart_marker (id text PRIMARY KEY); INSERT INTO infrastructure_probe.restart_marker VALUES ('$marker');"
Invoke-PostgresSql -Database 'ontology_platform' -Sql $sql | Out-Null
$update = "INSERT DATA { <$subject> <urn:ontology-platform:probe:value> `"$marker`" }"
Invoke-WebRequest -Uri ([uri]::new($FusekiEndpoint, '/ontology/update')) -Method Post -ContentType 'application/sparql-update' -Body $update | Out-Null
Invoke-S3Probe 'PUT' "/$bucket" | Out-Null
Invoke-S3Probe 'PUT' "/$bucket/marker.txt" $marker | Out-Null

# 只比对引导身份的非秘密数据库ID，不执行登录或读取密码材料。
$identityQuery = "SELECT id FROM user_entity WHERE username='local-admin';"
$identityBefore = Invoke-PostgresSql -Database 'keycloak' -Sql $identityQuery
if ([string]::IsNullOrWhiteSpace($identityBefore)) { throw 'Keycloak外置数据库缺少本次引导身份。' }

# 重启所有本任务明确给出的开发容器；不触碰其他项目容器或删除卷。
Invoke-DockerChecked -DockerArguments @('restart', $PostgresContainer, $FusekiContainer, $RustfsContainer, $KeycloakContainer) | Out-Null
Wait-HttpReady ([uri]::new($FusekiEndpoint, '/$/ping'))
Wait-HttpReady ([uri]::new($RustfsEndpoint, '/health/ready'))
Wait-HttpReady $KeycloakHealthEndpoint
$storedMarker = Invoke-PostgresSql -Database 'ontology_platform' -Sql "SELECT id FROM infrastructure_probe.restart_marker WHERE id='$marker';"
if ($storedMarker -ne $marker) { throw 'PostgreSQL重启标记不匹配。' }
$query = "ASK { <$subject> <urn:ontology-platform:probe:value> `"$marker`" }"
$result = Invoke-RestMethod -Uri ([uri]::new($FusekiEndpoint, "/ontology/query?query=$([uri]::EscapeDataString($query))")) -Headers @{ Accept = 'application/sparql-results+json' }
if ($result.boolean -ne $true) { throw 'Fuseki重启标记不匹配。' }
$object = Invoke-S3Probe 'GET' "/$bucket/marker.txt"
if ([Text.Encoding]::UTF8.GetString($object.RawContentStream.ToArray()) -ne $marker) { throw 'RustFS重启对象不匹配。' }
$realmCount = Invoke-PostgresSql -Database 'keycloak' -Sql 'SELECT count(*) FROM realm;'
if ([int]$realmCount -lt 1) { throw 'Keycloak外置数据库中缺少初始realm。' }
$identityAfter = Invoke-PostgresSql -Database 'keycloak' -Sql $identityQuery
if ($identityAfter -ne $identityBefore) { throw 'Keycloak重启后引导身份ID不一致。' }

[pscustomobject]@{
    Status = 'PASS'
    PostgreSql = '重启后随机标记保留，命名卷挂载符合PG18路径'
    Fuseki = '重启后TDB2测试URN保留'
    RustFS = '重启后S3签名写入对象内容一致'
    Keycloak = '管理就绪恢复，外置库引导身份ID与重启前一致'
    Marker = $marker
    Cleanup = '仅保留本次开发探针，不删除卷；不代表生产恢复或业务认证验收'
}

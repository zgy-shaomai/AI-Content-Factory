Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir '..')
Set-Location $ScriptDir

$DockerBin = 'C:\Program Files\Docker\Docker\resources\bin'
if ((Get-Command docker -ErrorAction SilentlyContinue) -eq $null -and (Test-Path -LiteralPath (Join-Path $DockerBin 'docker.exe'))) {
    $env:Path = "$DockerBin;$env:Path"
}

function Write-Info([string]$Message) {
    Write-Host $Message -ForegroundColor Yellow
}

function Write-Ok([string]$Message) {
    Write-Host $Message -ForegroundColor Green
}

function Write-Err([string]$Message) {
    Write-Host $Message -ForegroundColor Red
}

function Read-EnvFile([string]$Path) {
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        $idx = $trimmed.IndexOf('=')
        if ($idx -lt 0) {
            continue
        }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim().Trim('"').Trim("'")
        $values[$key] = $value
    }
    return $values
}

function Get-Setting([hashtable]$EnvValues, [string]$Name, [string]$Default = '') {
    $runtime = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($runtime)) {
        return $runtime
    }
    if ($EnvValues.ContainsKey($Name)) {
        return $EnvValues[$Name]
    }
    return $Default
}

Write-Info 'STEP 1: checking .env.local...'
$EnvPath = Join-Path $ScriptDir '.env.local'
if (-not (Test-Path -LiteralPath $EnvPath)) {
    Write-Err 'ERROR: .env.local not found. Copy deploy/.env.local.example to deploy/.env.local first.'
    exit 1
}

$EnvValues = Read-EnvFile $EnvPath
$PostgresDb = Get-Setting $EnvValues 'POSTGRES_DB' 'content_factory'
$PostgresUser = Get-Setting $EnvValues 'POSTGRES_USER' 'postgres'

foreach ($name in @('POSTGRES_PASSWORD', 'N8N_ENCRYPTION_KEY', 'REDIS_PASSWORD')) {
    $value = Get-Setting $EnvValues $name ''
    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith('CHANGE_ME')) {
        Write-Err "ERROR: $name is required and cannot stay as CHANGE_ME."
        exit 1
    }
}

foreach ($name in @('ARK_API_KEY', 'NEWAPI_KEY')) {
    $value = Get-Setting $EnvValues $name ''
    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith('CHANGE_ME')) {
        Write-Host "WARN: $name is empty. Stack can start, but N8N model calls will return 401." -ForegroundColor Yellow
    }
}

Write-Ok 'OK: required .env.local values are present'

Write-Info 'STEP 2: checking Docker daemon...'
try {
    docker ps | Out-Null
} catch {
    Write-Err 'ERROR: Docker is not running. Start Docker Desktop first.'
    exit 1
}
Write-Ok 'OK: Docker is running'

Write-Info 'STEP 3: preparing initdb...'
$InitDbDir = Join-Path $ScriptDir 'initdb'
New-Item -ItemType Directory -Force -Path $InitDbDir | Out-Null
Copy-Item -Force (Join-Path $RootDir 'schemas\postgres-init.sql') (Join-Path $InitDbDir '01-postgres-init.sql')
Write-Ok 'OK: initdb/01-postgres-init.sql copied'

Write-Info 'STEP 4: starting postgres + redis + n8n...'
docker compose -f docker-compose.local.yml --env-file .env.local up -d
Write-Ok 'OK: containers started'

Write-Info 'STEP 5: waiting for Postgres...'
$PostgresReady = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        docker exec cf-postgres-local pg_isready -U $PostgresUser | Out-Null
        Write-Ok "OK: Postgres ready ($i s)"
        $PostgresReady = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $PostgresReady) {
    Write-Err 'ERROR: Postgres did not become ready in time.'
    exit 1
}

Write-Info 'STEP 6: verifying schema...'
$TableCount = docker exec cf-postgres-local psql -U $PostgresUser -d $PostgresDb -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='content_factory';"
$TableCount = ($TableCount | Out-String).Trim()
if ([int]$TableCount -lt 9) {
    Write-Err "ERROR: schema is incomplete. Current table count: $TableCount"
    exit 1
}
Write-Ok "OK: schema deployed, table count = $TableCount"

Write-Info 'STEP 7: verifying enum values...'
$EnumOk = docker exec cf-postgres-local psql -U $PostgresUser -d $PostgresDb -tAc "SELECT (enum_range(NULL::run_status)::text[]) @> ARRAY['partial']::text[] AND (enum_range(NULL::candidate_status)::text[]) @> ARRAY['pending_review','failed']::text[];"
$EnumOk = ($EnumOk | Out-String).Trim()
if ($EnumOk -ne 't') {
    Write-Err 'ERROR: required enum values are missing.'
    exit 1
}
Write-Ok 'OK: enum values are present'

Write-Info 'STEP 8: waiting for N8N...'
$N8nReady = $false
for ($i = 1; $i -le 90; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:5678/healthz' | Out-Null
        Write-Ok "OK: N8N ready ($i s)"
        $N8nReady = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $N8nReady) {
    Write-Err 'ERROR: N8N did not become ready in time.'
    exit 1
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Ok 'OK: local stack is up'
Write-Host ''
Write-Host '  N8N editor:  http://localhost:5678'
Write-Host "  Postgres:    localhost:55432  user=$PostgresUser  db=$PostgresDb"
Write-Host '  Redis:       localhost:56379'
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Open http://localhost:5678'
Write-Host '  2. Register the first owner account'
Write-Host '  3. Run python scripts/n8n_setup.py'
Write-Host '  4. Open http://localhost:5001'
Write-Host ''

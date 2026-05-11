Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

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

function Get-HttpErrorBody($ErrorRecord) {
    try {
        if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
            return $ErrorRecord.ErrorDetails.Message
        }
        $Exception = $ErrorRecord
        if ($ErrorRecord -is [System.Management.Automation.ErrorRecord]) {
            $Exception = $ErrorRecord.Exception
        }
        $response = $Exception.Response
        if ($null -eq $response) {
            return ''
        }
        $stream = $response.GetResponseStream()
        if ($null -eq $stream) {
            return ''
        }
        $reader = New-Object System.IO.StreamReader($stream)
        return $reader.ReadToEnd()
    } catch {
        return ''
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvValues = Read-EnvFile (Join-Path $ScriptDir '..\deploy\.env.local')

$MediaKey = Get-Setting $EnvValues 'MEDIA_API_KEY' ''
$MediaBase = Get-Setting $EnvValues 'MEDIA_BASE_URL' ''
$DefaultMediaOrArkKey = if ($MediaKey) { $MediaKey } else { Get-Setting $EnvValues 'ARK_API_KEY' '' }
$DefaultMediaOrArkBase = if ($MediaBase) { $MediaBase } else { Get-Setting $EnvValues 'ARK_ENDPOINT' 'https://ark.cn-beijing.volces.com/api/v3' }
$ImageKey = Get-Setting $EnvValues 'IMAGE_API_KEY' $DefaultMediaOrArkKey
$VideoKey = Get-Setting $EnvValues 'VIDEO_API_KEY' $DefaultMediaOrArkKey
$LlmKey = Get-Setting $EnvValues 'LLM_API_KEY' (Get-Setting $EnvValues 'NEWAPI_KEY' '')
$ImageBase = Get-Setting $EnvValues 'IMAGE_BASE_URL' $DefaultMediaOrArkBase
$VideoBase = Get-Setting $EnvValues 'VIDEO_BASE_URL' $DefaultMediaOrArkBase
$LlmBase = Get-Setting $EnvValues 'LLM_BASE_URL' (Get-Setting $EnvValues 'NEWAPI_BASE_URL' 'https://5dock.com/v1')
$ImageModel = Get-Setting $EnvValues 'IMAGE_MODEL' (Get-Setting $EnvValues 'ARK_IMAGE_MODEL' 'doubao-seedream-4-0-250828')
$VideoModel = Get-Setting $EnvValues 'VIDEO_MODEL' (Get-Setting $EnvValues 'ARK_VIDEO_MODEL' 'doubao-seedance-1-0-pro-250528')
$LlmModel = Get-Setting $EnvValues 'LLM_MODEL' 'claude-sonnet-4-5-20250929'

if ([string]::IsNullOrWhiteSpace($ImageKey) -or $ImageKey.StartsWith('CHANGE_ME')) {
    Write-Host 'ERROR: IMAGE_API_KEY/MEDIA_API_KEY is missing. Set it in deploy/.env.local or Provider Access Center.' -ForegroundColor Red
    exit 1
}
if ([string]::IsNullOrWhiteSpace($VideoKey) -or $VideoKey.StartsWith('CHANGE_ME')) {
    Write-Host 'ERROR: VIDEO_API_KEY/MEDIA_API_KEY is missing. Set it in deploy/.env.local or Provider Access Center.' -ForegroundColor Red
    exit 1
}
if ([string]::IsNullOrWhiteSpace($LlmKey) -or $LlmKey.StartsWith('CHANGE_ME')) {
    Write-Host 'ERROR: LLM_API_KEY/NEWAPI_KEY is missing. Set it in deploy/.env.local or Provider Access Center.' -ForegroundColor Red
    exit 1
}

$Pass = 0
$Fail = 0

Write-Host 'STEP [1/3] Seedream 4.0 image test...' -ForegroundColor Yellow
try {
    $Body = @{
        model = $ImageModel
        prompt = 'studio shot of a black sports bra with front zipper, on minimalist gray background, soft natural light, fashion photography, ultra detailed'
        size = '1024x1024'
        watermark = $false
    } | ConvertTo-Json -Depth 8
    $Resp = Invoke-RestMethod -Method Post -Uri "$ImageBase/images/generations" -Headers @{ Authorization = "Bearer $ImageKey" } -ContentType 'application/json' -Body $Body -TimeoutSec 60
    $Url = $Resp.data[0].url
    if ($Url) {
        Write-Host "  OK image generation succeeded: $Url" -ForegroundColor Green
        $Pass++
    } else {
        Write-Host '  ERROR image generation failed: no url in response' -ForegroundColor Red
        $Fail++
    }
} catch {
    $BodyText = Get-HttpErrorBody $_
    Write-Host "  ERROR image generation failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($BodyText) {
        Write-Host ("  Response: " + $BodyText.Substring(0, [Math]::Min(500, $BodyText.Length)))
    }
    $Fail++
}

Write-Host 'STEP [2/3] Seedance 2.0 submit test...' -ForegroundColor Yellow
try {
    $Body = @{
        model = $VideoModel
        content = @(
            @{
                type = 'text'
                text = 'a woman jogging in a green park at golden hour, wearing black sports bra, cinematic shot --resolution 720p --duration 5 --ratio 9:16'
            }
        )
    } | ConvertTo-Json -Depth 10
    $Resp = Invoke-RestMethod -Method Post -Uri "$VideoBase/contents/generations/tasks" -Headers @{ Authorization = "Bearer $VideoKey" } -ContentType 'application/json' -Body $Body -TimeoutSec 60
    $TaskId = $Resp.id
    if ($TaskId) {
        Write-Host "  OK video task submitted: task_id=$TaskId" -ForegroundColor Green
        Write-Host '  WARN this only verifies submit, not final completion.' -ForegroundColor Yellow
        $Pass++
    } else {
        Write-Host '  ERROR video task submit failed' -ForegroundColor Red
        $Fail++
    }
} catch {
    $BodyText = Get-HttpErrorBody $_
    Write-Host "  ERROR video task submit failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($BodyText) {
        Write-Host ("  Response: " + $BodyText.Substring(0, [Math]::Min(500, $BodyText.Length)))
    }
    $Fail++
}

Write-Host 'STEP [3/3] LLM provider chat/completions test...' -ForegroundColor Yellow
try {
    $Body = @{
        model = $LlmModel
        messages = @(
            @{
                role = 'user'
                content = 'reply with exactly the word: OK'
            }
        )
        max_tokens = 10
    } | ConvertTo-Json -Depth 10
    $Resp = Invoke-RestMethod -Method Post -Uri "$LlmBase/chat/completions" -Headers @{ Authorization = "Bearer $LlmKey" } -ContentType 'application/json' -Body $Body -TimeoutSec 60
    $Text = $Resp.choices[0].message.content
    if ($Text) {
        Write-Host "  OK LLM response: $Text" -ForegroundColor Green
        $Pass++
    } else {
        Write-Host '  ERROR LLM call failed: no text in response' -ForegroundColor Red
        $Fail++
    }
} catch {
    $BodyText = Get-HttpErrorBody $_
    Write-Host "  ERROR LLM call failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($BodyText) {
        Write-Host ("  Response: " + $BodyText.Substring(0, [Math]::Min(500, $BodyText.Length)))
    }
    $Fail++
}

Write-Host ''
Write-Host '------------------------------------------------------------'
if ($Fail -eq 0) {
    Write-Host 'OK: all 3/3 checks passed. Demo is ready.' -ForegroundColor Green
    exit 0
}

Write-Host "ERROR: $Fail/3 checks failed. Fix them before the demo." -ForegroundColor Red
Write-Host '  Image/video failure -> check provider key, quota, endpoint, model activation, and whether the media API is Ark-compatible'
Write-Host '  LLM failure -> check LLM_BASE_URL / LLM_API_KEY / LLM_MODEL for the selected provider'
exit 1

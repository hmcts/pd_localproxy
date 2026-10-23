# Run on Windows JBOX. Needs PowerShell 5.1+, an existing SSH/Plink client,
# and compare_github.py beside this file. Python is needed ONLY on the Linux target.
# No installation, Git checkout, deployment or production file writes.
[CmdletBinding()]
param(
    [string]$ProxyHost,
    [string]$SshUser = 'xhibit',
    [ValidateSet('proxy', 'cdu', 'both')][string]$Only = 'both',
    [string]$ProxyRef = 'master',
    [string]$CduRef = 'master',
    [string]$BaselineFile,
    [switch]$PrepareBaseline,
    [switch]$IncludeDiffs,
    [switch]$CollectEvidence,
    [ValidateSet('ssh', 'plink')][string]$SshClient = 'ssh',
    [string]$SshExecutable,
    [string[]]$SshOption = @(),
    [ValidateRange(1, 65535)][int]$Port = 22,
    [string]$RemotePython = '/usr/bin/python3',
    [string]$ProxyRoot = '/var/www/court-display/proxy',
    [string]$ParserFile = '/var/www/court-display/proxycode/xhibit.py',
    [string]$ManagerRoot = '/var/www/lan/manager',
    [string]$CduRoot = '/var/www/lan/cdu',
    [string]$UpdateScriptsRoot,
    [string]$OutputParent = '.'
)
$ErrorActionPreference = 'Stop'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$MaxFile = 2MB
$MaxTotal = 64MB

function Get-Sha256([byte[]]$Bytes) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}

function Get-PublicBytes([string]$Url, [int]$Limit) {
    # Use normal certificate verification/system proxy. Never disable TLS checks.
    $request = [Net.WebRequest]::Create($Url)
    $request.UserAgent = 'XHIBIT-read-only-baseline-comparison'
    $request.Timeout = 30000
    $request.ReadWriteTimeout = 30000
    $response = $null
    $inputStream = $null
    $memory = New-Object IO.MemoryStream
    try {
        $response = $request.GetResponse()
        $inputStream = $response.GetResponseStream()
        if ($inputStream.CanTimeout) { $inputStream.ReadTimeout = 30000 }
        $buffer = New-Object byte[] 65536
        while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($memory.Length + $count -gt $Limit) { throw 'Public download exceeds collection size limit.' }
            $memory.Write($buffer, 0, $count)
        }
        return ,$memory.ToArray()
    }
    finally {
        if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Close() }
        $memory.Dispose()
    }
}

function Test-SourcePath([string]$Path) {
    $parts = $Path.Split('/')
    if (!$Path -or $Path.StartsWith('/') -or $Path.Contains('\') -or $Path -match '[\x00-\x1f]' -or
        @($parts | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) { throw 'Unsafe path in GitHub archive.' }
    if (@($parts | Select-Object -SkipLast 1 | Where-Object {
        $_ -in @('.git', '.svn', '__pycache__', 'logs', 'log', 'cache', 'tmp', 'temp', 'uploads', 'upload',
        'screenshots', 'captures', 'sessions', 'node_modules', '.ssh', 'private', 'testdata', 'test-data')
    }).Count -gt 0) { return $false }
    $name = $parts[-1]
    if ($name -match '(?i)(^\.env(\.|$)|passwd|password|shadow|private.key|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|keystore)') {
        return $false
    }
    return $name -match '(?i)\.(php|py|cgi|sh|bash|js|css|xsl|xslt|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|otf|eot)$' -or $name -ceq '.htaccess'
}

function Get-PublicBaseline([string]$Repository, [string]$Ref) {
    Write-Host "Resolving $Repository at $Ref"
    $refUrl = [Uri]::EscapeDataString($Ref)
    $commitResponse = Get-PublicBytes "https://api.github.com/repos/$Repository/commits/$refUrl" 1MB
    $commit = ($Utf8.GetString($commitResponse) | ConvertFrom-Json).sha
    if ($commit -cnotmatch '^[0-9a-f]{40}$') { throw 'GitHub did not return a full commit SHA.' }
    $zipBytes = Get-PublicBytes "https://codeload.github.com/$Repository/zip/$commit" 32MB
    $memory = New-Object IO.MemoryStream(,$zipBytes)
    $archive = $null
    $files = New-Object 'System.Collections.Generic.List[object]'
    $excluded = New-Object 'System.Collections.Generic.List[object]'
    $total = 0
    try {
        $archive = New-Object IO.Compression.ZipArchive($memory, [IO.Compression.ZipArchiveMode]::Read)
        $root = ($Repository.Split('/')[1]) + '-' + $commit + '/'
        if ($archive.Entries.Count -gt 5000) { throw 'Too many GitHub archive entries.' }
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName.EndsWith('/')) { continue }
            if (!$entry.FullName.StartsWith($root, [StringComparison]::Ordinal)) { throw 'Unexpected GitHub archive root.' }
            $path = $entry.FullName.Substring($root.Length)
            if (!(Test-SourcePath $path)) {
                $excluded.Add(@{path = $path; reason = 'Configuration/data/non-application file excluded'})
                continue
            }
            # Unix file type bits in a GitHub ZIP: never interpret a link as source.
            $unixType = ($entry.ExternalAttributes -shr 16) -band 61440
            if ($unixType -ne 0 -and $unixType -ne 32768) { throw 'Repository link/special file requires manual review.' }
            $total += $entry.Length
            if ($entry.Length -gt $MaxFile -or $total -gt $MaxTotal) { throw 'GitHub source size limit exceeded.' }
            $sourceStream = $entry.Open()
            $source = New-Object IO.MemoryStream
            try {
                $sourceStream.CopyTo($source)
                $bytes = $source.ToArray()
                if ($bytes.Length -gt $MaxFile) { throw 'GitHub source size limit exceeded.' }
                $files.Add(@{path = $path; sha256 = (Get-Sha256 $bytes); size = $bytes.Length;
                             content_b64 = [Convert]::ToBase64String($bytes)})
            }
            finally { $sourceStream.Dispose(); $source.Dispose() }
        }
    }
    finally { if ($archive) { $archive.Dispose() }; $memory.Dispose() }
    if ($files.Count -eq 0) { throw 'No application source in GitHub archive.' }
    return @{repository = $Repository; requested_ref = $Ref; commit = $commit;
             commit_url = "https://github.com/$Repository/commit/$commit";
             files = $files.ToArray(); excluded = $excluded.ToArray()}
}

function New-PrivateOutput {
    $parent = (Resolve-Path -LiteralPath $OutputParent).Path
    $directory = Join-Path $parent ('xhibit-github-compare-' + [Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($directory)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    $propagation = [Security.AccessControl.PropagationFlags]::None
    foreach ($sid in @($identity, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', $inheritance, $propagation, 'Allow')
        $acl.AddAccessRule($rule)
    }
    # Fail rather than write a sensitive report to an unprotected folder.
    Set-Acl -LiteralPath $directory -AclObject $acl
    return $directory
}

function Write-NewUtf8([string]$Path, [string]$Text) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $bytes = $Utf8.GetBytes($Text); $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

function Quote-Posix([string]$Value) {
    return "'" + $Value.Replace("'", "'" + '"' + "'" + '"' + "'") + "'"
}

$previousTls = [Net.ServicePointManager]::SecurityProtocol
$previousEncoding = $OutputEncoding
try {
    if ($PSVersionTable.PSVersion -lt [Version]'5.1') { throw 'PowerShell 5.1+ required. Do not install/upgrade without approval.' }
    if (!$PrepareBaseline -and (!$ProxyHost -or $ProxyHost -cnotmatch '^[A-Za-z0-9_.:-]+$' -or $ProxyHost.StartsWith('-'))) {
        throw 'Supply -ProxyHost with the Linux hostname/IP, not JBOX or user@host.'
    }
    if ($RemotePython -notmatch '^/[^\x00-\x1f]+$') { throw 'RemotePython must be an absolute Linux executable path.' }
    if (!$PrepareBaseline -and !(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'compare_github.py') -PathType Leaf)) {
        throw 'Keep compare_github.py beside this PowerShell script; it is sent to the proxy in memory.'
    }
    # TLS setting applies only to this process and is restored on exit.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Add-Type -AssemblyName System.IO.Compression
    $roles = if ($Only -eq 'both') { @('proxy', 'cdu') } else { @($Only) }
    $baselines = @{}
    if ($BaselineFile) {
        if ((Get-Item -LiteralPath $BaselineFile).Length -gt 128MB) { throw 'Offline baseline too large.' }
        $bundle = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $BaselineFile).Path, $Utf8) | ConvertFrom-Json
        foreach ($role in $roles) {
            if (!$bundle.baselines.$role) { throw "Offline baseline missing role: $role" }
            $baselines[$role] = $bundle.baselines.$role
        }
    }
    else {
        foreach ($role in $roles) {
            $repo = if ($role -eq 'proxy') { 'hmcts/pd_localproxy' } else { 'hmcts/pd_cdu' }
            $ref = if ($role -eq 'proxy') { $ProxyRef } else { $CduRef }
            $baselines[$role] = Get-PublicBaseline $repo $ref
        }
    }
    if ($PrepareBaseline) {
        $output = New-PrivateOutput
        Write-NewUtf8 (Join-Path $output 'public-baseline.json') (@{schema_version = 1; baselines = $baselines} | ConvertTo-Json -Depth 100 -Compress)
        Write-Host "Public baseline saved on THIS machine: $output"
        exit 0
    }
    $payload = @{baselines = $baselines; target = $ProxyHost; include_diffs = [bool]$IncludeDiffs;
        collect_evidence = [bool]$CollectEvidence;
        locations = @{proxy_root = $ProxyRoot; parser_file = $ParserFile; manager_root = $ManagerRoot;
                      cdu_root = $CduRoot; updatescripts_root = $UpdateScriptsRoot};
        extra_roots = @('/var/www/cgi-bin/xhibit.py', '/var/www/court-display/software', '/var/www/lan/xhibit')}
    if (!$SshExecutable) { $SshExecutable = $SshClient }
    $client = (Get-Command $SshExecutable -CommandType Application -ErrorAction Stop).Source
    $clientArgs = if ($SshClient -eq 'plink') { @('-ssh', '-T', '-P', "$Port") } else { @('-T', '-o', 'ConnectTimeout=15', '-p', "$Port") }
    if ($SshUser) { $clientArgs += @('-l', $SshUser) }
    $clientArgs += $SshOption
    # No embedded double quotes: avoids Windows PowerShell 5.1 native quoting loss.
    $bootstrap = 'import sys,base64;exec(base64.b64decode(sys.stdin.buffer.readline()))'
    $remote = (Quote-Posix $RemotePython) + ' -B -c ' + (Quote-Posix $bootstrap) + ' --remote'
    $clientArgs += @($ProxyHost, $remote)
    $source = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'compare_github.py'))
    $request = [Convert]::ToBase64String($source) + "`n" + ($payload | ConvertTo-Json -Depth 100 -Compress)
    $OutputEncoding = $Utf8
    Write-Host 'Reading deployed files over SSH. Authenticate normally; do not supply passwords in arguments.'
    $nativeLines = @($request | & $client @clientArgs)
    if ($LASTEXITCODE -ne 0) { throw "SSH/helper failed (exit $LASTEXITCODE). No successful comparison." }
    # Native output is split into lines by Windows PowerShell. Rejoin explicitly
    # with LF, not Out-String's platform-dependent CRLF marker conversion.
    $raw = $nativeLines -join "`n"
    $marker = "XHIBIT_COMPARE_V1`n"
    $start = $raw.IndexOf($marker, [StringComparison]::Ordinal)
    if ($start -lt 0 -or $raw.Length -gt 32MB) { throw 'Missing/oversized helper response. No successful comparison.' }
    $response = $raw.Substring($start + $marker.Length) | ConvertFrom-Json
    if (!$response.report -or !$response.report_text) { throw 'Incomplete helper response. No successful comparison.' }
    $output = New-PrivateOutput
    Write-NewUtf8 (Join-Path $output 'report.json') ($response.report | ConvertTo-Json -Depth 100)
    Write-NewUtf8 (Join-Path $output 'report.txt') $response.report_text
    Write-Host "Reports saved ON JBOX: $output"
    Write-Host ($response.report.summary | ConvertTo-Json -Compress -Depth 10)
    Write-Host 'Review before sharing. No production files were written or services restarted.'
    exit ([int]$response.report.summary.exit_code)
}
catch {
    # Do not echo native stdout, source code or credential-bearing URLs.
    Write-Error 'Comparison failed. Check the displayed step, SSH access, baseline, paths and file permissions. No successful comparison.' -ErrorAction Continue
    Write-Warning $_.Exception.GetType().Name
    exit 2
}
finally {
    $OutputEncoding = $previousEncoding
    [Net.ServicePointManager]::SecurityProtocol = $previousTls
}

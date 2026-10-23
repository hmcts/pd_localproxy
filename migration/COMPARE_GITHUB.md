# Compare GitHub with production from Windows JBOX

Run `Compare-XhibitGitHub.ps1` **on Windows JBOX**, not on the Mac and not in the
Linux proxy's shell. Keep `compare_github.py` beside it. JBOX needs PowerShell
5.1+ and an existing approved OpenSSH (`ssh.exe`) or PuTTY Plink client. It does
**not** need Python, Git, pip or any third-party Python library. The Linux target
needs its existing Python 3.4+ interpreter; no runtime is installed or upgraded.

The two baseline repositories are:

- https://github.com/hmcts/pd_localproxy
- https://github.com/hmcts/pd_cdu

The script resolves each requested branch/tag to a full commit SHA before
downloading that exact public snapshot. The report records those SHAs. The
default is `master`, not our uncommitted local remediation work. It will not
publish the new comparison tools or any production source to GitHub.

## What happens where

1. JBOX downloads the public GitHub baseline over HTTPS with normal certificate
   checks. This is not needed if an offline baseline is supplied.
2. JBOX connects to the approved Linux proxy using your existing SSH access.
3. The Python helper and public baseline are sent through SSH stdin. Python runs
   the helper in memory with bytecode writing disabled. No helper, baseline or
   report file is written on the production target.
4. The helper reads the explicitly mapped files, computes SHA-256 hashes and
   inventories eligible extra application files in the selected directories.
5. Reports are written **on JBOX**, in a fresh `xhibit-github-compare-...` directory
   beneath the current working directory (or `-OutputParent`). The Windows folder
   ACL is restricted to the current user and SYSTEM; failure to set it stops the
   write. Normal administrator privileges can still override ACLs.

No deployment, application execution, HTTP request to a production endpoint,
database query, service restart, Git reset or production file modification occurs.
Ordinary reads may update filesystem access times and generate normal SSH logs.
The proxy and CDUs need no internet access for this comparison.

## First run on JBOX

The supplied `xhibit-jbox-comparison.zip` includes both tools, this guide and a
ready-to-use `public-baseline.json`. Its pinned `master` snapshots are:

- `hmcts/pd_localproxy`: `71baef7ccee3f763f609a6abe017507b91d6542a`
- `hmcts/pd_cdu`: `b1e0743c8bb812e3d112fb2fa02ddfc08cd7a8e8`

All 85 included application/asset hashes were independently checked against
those Git objects. The snapshot contains public code only, not production
evidence. Using it avoids any GitHub access from JBOX:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost <proxy-host> -SshUser <ssh-user> `
  -BaselineFile .\public-baseline.json
```

Transfer and extract the ZIP through your approved route. Replace `<proxy-host>`
and `<ssh-user>` with the approved proxy address and account you already use.
Matching this snapshot does not mean it is an approved production release.

Transfer the two tool files together using the approved JBOX transfer process,
then open PowerShell in that folder. The comparison scripts are new local files,
not yet published in the public repositories: cloning the repositories will not
retrieve these tools. Do not bypass an execution policy or change it globally;
use your organisation's approved script-signing/execution process if required.

These diagnostic commands do not install anything:

```powershell
$PSVersionTable.PSVersion
Get-Command ssh, plink -CommandType Application -ErrorAction SilentlyContinue
```

Use the existing SSH hostname/IP and account you normally use **from JBOX**.
For example, if `<proxy-host>` is reachable from JBOX:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost <proxy-host> -SshUser <ssh-user>
```

Use your own approved SSH account. Domain-style logins can be supplied
as `-SshUser '<operator>@example'` only if that is the approved proxy login;
your JBOX Windows account is not automatically your Linux account. Never put a
password in arguments. The SSH client handles authentication and host-key prompts
normally. Verify an unfamiliar host fingerprint through the approved process.

If you normally use Plink, specify its existing executable, for example:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost <proxy-host> -SshUser <ssh-user> `
  -SshClient plink -SshExecutable 'C:\Program Files\PuTTY\plink.exe'
```

PuTTY GUI alone is not Plink. If neither approved command-line client is present,
stop and ask the administrator which existing client/route to use. Do not install
one automatically. Additional existing client settings may be passed using
`-SshOption @('-i','C:\approved\keypath')`; do not use password arguments or
options that disable host-key verification. Establish normal SSH access first if
authentication/prompts fail when input is redirected; do not weaken access policy.

To request bounded changed-source snippets as well as hashes:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost <proxy-host> -SshUser <ssh-user> -IncludeDiffs
```

Diffs are off by default. They are automatically redacted **before** selecting
context, but redaction is best-effort. Review the report manually before sharing;
unusual hard-coded secrets may remain. Full production source is never saved by
this tool. INI/SQL/HTML feeds/XML feeds/logs/password files are excluded, even with
`-IncludeDiffs`. XSL source and the manager's `.htaccess` are included. Static
images/fonts are hash-compared only. Symlinks are recorded, never followed.

## Production path mappings

Defaults are based on the supplied production inventory, not an assumption that
the GitHub repository layout is the production directory layout:

| GitHub file/subtree | Default Linux location |
| --- | --- |
| `pd_localproxy/proxy/xhibit.py` | `/var/www/court-display/proxycode/xhibit.py` |
| Other `pd_localproxy/proxy/` files | `/var/www/court-display/proxy/` |
| `pd_localproxy/manager/` | `/var/www/lan/manager/` |
| `pd_localproxy/updatescripts/` | Unmapped until the real directory is supplied |
| `pd_cdu/` | `/var/www/lan/cdu/` on the proxy, or an explicitly supplied CDU root |

The proxy's older `/var/www/cgi-bin/xhibit.py`, software directory and
`/var/www/lan/xhibit` are also inventoried for additional eligible code. These
files are not assumed to belong to either GitHub repository or to be active.

Override a reviewed path using `-ParserFile`, `-ProxyRoot`, `-ManagerRoot`,
`-CduRoot` or `-UpdateScriptsRoot`, for example:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost <proxy-host> -SshUser <ssh-user> `
  -UpdateScriptsRoot /actual/deployed/updater/directory
```

Do not guess updater or symlink-target locations. Missing paths and unreadable
files are not matches. Do not alter permissions or use sudo automatically.
Check mappings and the active parser entry point against the deployed Apache
configuration/wrappers before concluding that the checked files are being used.

## Results

The script prints the output directory on JBOX. It contains:

- `report.txt`: summary, mismatched/missing files, optional diffs and warnings.
- `report.json`: full per-file hashes, paths, modes, pinned commits and statuses.

Compare the second proxy by rerunning with its hostname. Reports are separate.
Raw CRLF/LF differences are still reported as differences, with a separate note
when only CRLF normalization makes the bytes equal. Redaction never changes the
hash comparison: a secret-only change still counts as a difference.

Exit codes:

- `0`: selected mapped application files match and no checked extra code found.
- `1`: differences/missing files/additional production code found.
- `2`: download, authentication, helper or report-writing failure; no success.
- `3`: incomplete scope, unmapped files, unreadable files, symlinks or limits.

**The first default run will be incomplete for updater scripts until their real
production directory is identified.** Code differences are still reported. Extra
production files may be backups or other applications; do not delete or deploy
them on the strength of this report. Limits are 5,000 files, 2 MiB per file and
64 MiB source reads, with 32 KiB per diff and 1 MiB total diff text. Truncation and
unchecked files are reported explicitly.

Matching files do not prove identical behaviour, live routing, database shape,
PHP vulnerability removal or that an uninspected subtree has no extra code.
Configuration/schema collection remains a separate step. Return only reviewed
reports through your approved channel; do not commit them to Git.

## Physical CDU check

The default `pd_cdu` comparison checks the copy **on the proxy**. It does not check
the code on a physical display. For a CDU accessible from JBOX, use its approved
hostname and actual webroot:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost ACTUAL_CDU_HOST -SshUser ACTUAL_CDU_USER `
  -Only cdu -CduRoot /actual/cdu/webroot
```

If the CDU is accessible only through the proxy, and SSH forwarding is approved,
OpenSSH can use the existing proxy as a jump host:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost ACTUAL_CDU_HOST -SshUser ACTUAL_CDU_USER `
  -Only cdu -CduRoot /actual/cdu/webroot `
  -SshOption @('-J','APPROVED_PROXY_USER@APPROVED_PROXY_HOST')
```

If forwarding is not approved or available, collect on the CDU through your
existing approved route instead. Do not scan for displays or change forwarding.

## If JBOX cannot reach GitHub

No internet access is added to production. Prepare a public baseline on another
approved internet-connected Windows machine with the same tools:

```powershell
.\Compare-XhibitGitHub.ps1 -PrepareBaseline
```

Transfer the generated `public-baseline.json` to JBOX through the approved route:

```powershell
.\Compare-XhibitGitHub.ps1 -ProxyHost <proxy-host> -SshUser <ssh-user> `
  -BaselineFile .\public-baseline.json
```

This mode performs no GitHub network access on JBOX. The baseline contains only
public GitHub source; source hashes and full commit SHAs are validated by the
Linux helper before comparison. Transfer it through a trusted channel; the bundle
is not a cryptographic signature from GitHub. For different refs, prepare with
`-ProxyRef REF_OR_FULL_SHA -CduRef REF_OR_FULL_SHA`. When reusing an offline baseline,
those refs are already fixed by that file; ref flags do not change its contents.

An optional Python entry point remains for an approved machine that already has
Python 3.4+: `python3 compare_github.py prepare --output public-baseline.json`, or
`python3 compare_github.py compare --host HOST --user USER`. It is not required on
JBOX. Its HTTPS downloads use Python's configured trust store; use an approved CA
configuration/offline baseline if enterprise TLS trust is missing. Never disable
certificate verification.

## Local verification and pilot limits

The Python engine is unit-tested against disposable fixtures and its in-memory
SSH protocol is exercised without a real remote server. A portable development
PowerShell parses/runs the Windows wrapper and its native pipeline against a fake
SSH process; Windows ACL creation is stubbed in that cross-platform test. Real
GitHub downloads have been exercised with the PowerShell download functions.
This is not a Windows PowerShell 5.1/JBOX or production SSH certification. Run the
first comparison on JBOX as a pilot and inspect the report before wider use.
# Additional Model Court evidence (23 October 2026)

Use the existing JBOX workflow with `-Only proxy -CollectEvidence` and, if
available, `-BaselineFile .\public-baseline.json`. The baseline avoids GitHub
network access; the Linux target never needs internet access. `-IncludeDiffs`
is independent and is not required to repeat the completed source comparison.

The new switch adds selected INI keys, selected `/etc/php.ini` response settings,
local information_schema metadata and a bounded caller/updater search to
report.json. It never selects application records, exports database credentials,
executes configured commands, transfers cdu.tar, writes target files or runs an
updater. Arbitrary shell command values are withheld for manual review. Symlinks,
permission failures, root crontabs and search limits remain explicitly unchecked.
Use `--collect-evidence` for the Python CLI equivalent. Review output privately
before sharing; matches use best-effort secret redaction, not a secrecy guarantee.

The absent manager/CDU aliases on Model Court do not establish installed fleet
versions. Manager stays optional/off. The different CGI-directory parser must
have its callers established before retirement. Required core metadata is
CDU.cduNumber, SITE.welshTitle, urlMappings and the other parser columns; do not
apply repository reference SQL to production.

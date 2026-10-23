# Collect the production baseline

For the current **Windows JBOX -> Linux proxy** workflow, use
[`COMPARE_GITHUB.md`](COMPARE_GITHUB.md) and `Compare-XhibitGitHub.ps1` instead.
That compares pinned public GitHub snapshots over SSH and saves reports on JBOX.
The original collectors below remain available for separately approved
configuration/schema evidence; the Mac-direct commands below do not describe
your JBOX access route.

These tools collect evidence, not a deployment. Run only on approved hosts. They
do not install packages, change application files, query application data, execute
application endpoints or restart services. Collection writes a new private
directory and archive; ordinary filesystem access times may change.

`collect_production.py` requires Python 3.4+ and uses only its standard library.
The Python 3.4 interpreter already reported on the proxy is sufficient; **do not
upgrade Python to collect this evidence**. The schema helper needs an existing
mysql/mariadb command-line client and an approved database account.

## 1. First local proxy

Run on the Mac. This creates a fresh private remote tools directory and copies
the two scripts there. No sudo is used. Replace each `<...>` placeholder with
the approved value; `<checkout>` is the folder holding your local checkout.

```bash
xhibit_proxy='<ssh-user>@<proxy-host>'
xhibit_collect_dir=$(ssh "$xhibit_proxy" 'umask 077; mktemp -d /tmp/xhibit-collect.XXXXXX') &&
scp '<checkout>/pd_localproxy/migration/collect_production.py' \
    '<checkout>/pd_localproxy/migration/collect_schema.sh' \
    "$xhibit_proxy:$xhibit_collect_dir/" &&
ssh -t "$xhibit_proxy" "/usr/bin/python3 '$xhibit_collect_dir/collect_production.py' --role proxy"
```

Keep the printed `directory`, `archive` and `checksum` paths. This collects the
known production proxy/parser, manager and software-download source locations,
Apache configuration, selected XHIBIT scheduler files, versions and file hashes.
HTML/XML feeds, SQL files, images and archives are inventoried, not copied.
Explicitly named Tomcat server/context XML configuration is an exception. Known
password/key filenames are omitted entirely. Source/configuration credentials
matching common patterns (including Tomcat `*Pass` and `username` attributes)
are replaced with `[REDACTED]`.

Check `manifest.json` inside the printed directory. `incomplete` lists missing
paths, permission errors and collection limits. Symlinks are recorded, not
followed. Missing evidence does not mean the application is absent or safe.
Have an administrator review unreadable paths. Do not change production file
permissions. If privileged collection is approved, an administrator can run the
same command with sudo and arrange secure transfer of the root-owned output.

For a missing application directory or a reviewed symlink target, rerun with an
additional exact source location, for example:

```bash
/usr/bin/python3 /tmp/xhibit-collect.REPLACE/collect_production.py \
  --role proxy --source-root /actual/application/directory
```

### Database structure, without records

In the same Mac terminal, replace `ACTUAL_DATABASE` and `APPROVED_DB_USER` below
with the values already used by the installation. Do not put the password in
the command or send it to us. It is prompted on the server.

```bash
ssh -t "$xhibit_proxy" "bash '$xhibit_collect_dir/collect_schema.sh' ACTUAL_DATABASE APPROVED_DB_USER"
```

The output is a separate private `/tmp/xhibit-schema.XXXXXX/schema-metadata.txt`.
It contains server version, table names and selected application table column,
index and foreign-key metadata. It does not export rows, column defaults,
comments, password files, triggers or stored routine bodies. It uses localhost
and ignores mysql client option files to avoid hidden connection/init settings.
If the client cannot connect or queries fail, report the error; do not grant new
database privileges or install software for this collection.

## 2. Second proxy

Repeat step 1 with that proxy's approved SSH hostname. Collect the full bundle
if permitted: we need to establish whether the two production copies differ.
If source transfer is not yet approved, append `--manifest-only` to collect
hashes and metadata without application/configuration bodies. Versions,
network addresses and paths are still included. This can identify differences,
but it cannot establish behavioural equivalence.

## 3. Representative CDU

From the Mac, replace `USER@CDU_HOST` with an approved reachable CDU:

```bash
xhibit_cdu='USER@CDU_HOST'
xhibit_cdu_collect_dir=$(ssh "$xhibit_cdu" 'umask 077; mktemp -d /tmp/xhibit-collect.XXXXXX') &&
scp '<checkout>/pd_localproxy/migration/collect_production.py' \
    "$xhibit_cdu:$xhibit_cdu_collect_dir/" &&
ssh -t "$xhibit_cdu" "python3 '$xhibit_cdu_collect_dir/collect_production.py' --role cdu"
```

If a jump host is needed, use your existing approved SSH configuration or
`-J` route for both ssh and scp. Do not scan the network for CDUs.

The CDU collector checks common webroots, Python/PHP/XSL/JS/CSS source,
Apache settings, XHIBIT home-bin scripts and selected startup configuration.
Use `--source-root /actual/cdu/webroot` if the manifest shows the real webroot
was not included. If Python 3.4+ is unavailable, stop and send the version/error;
do not install or upgrade it. No browser, screenshot or hardware-control command
is executed.

## 4. Review and return

All evidence is private. **Automatic redaction is best-effort, not a security
guarantee.** Review the staged files, including `runtime.json`, before sharing
anything. They may still contain internal addresses, secrets in unusual formats
or personal information embedded in source. Do not commit evidence to Git.

If anything needs additional redaction, do not share the existing archive: it
already contains the pre-review copy. Arrange a reviewed replacement archive
through the approved secure process, preserving `sha256_original` in the manifest
where policy permits. Do not modify the original production files.

After review, download the exact printed archive/checksum paths and the separate
schema file to a private folder. The paths below are placeholders to replace:

```bash
umask 077
xhibit_download_dir=$(mktemp -d /tmp/xhibit-baselines.XXXXXX)
scp "$xhibit_proxy:/tmp/xhibit-evidence-HOST-RANDOM.tar.gz" \
    "$xhibit_proxy:/tmp/xhibit-evidence-HOST-RANDOM.tar.gz.sha256" \
    "$xhibit_download_dir/"
scp "$xhibit_proxy:/tmp/xhibit-schema.RANDOM/schema-metadata.txt" \
    "$xhibit_download_dir/proxy-schema-metadata.txt"
```

Verify the downloaded archive against its accompanying checksum:

```bash
cd "$xhibit_download_dir"
shasum -a 256 -c xhibit-evidence-HOST-RANDOM.tar.gz.sha256
```

Return the reviewed bundles, schema metadata, and any reported errors. We also
need two decisions that scripts cannot infer: which production host/release is
the authoritative baseline, and whether it is approved to bring that source
into these Git repositories. No alignment commits or deployment should happen
until those are resolved.

Collection limits: 5,000 files, 2 MiB per file and 64 MiB total source/config
reads, plus bounded system probes. Excluded log/cache/upload/screenshot/private
directories are not traversed. Archives are not unpacked. Incomplete evidence
must be reviewed before drawing conclusions.

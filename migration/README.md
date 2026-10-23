# Model Court parity: Python-only applications and releases

This release replaces application PHP with Python CGI while preserving Model
Court's supported HTTP/XML/display contract (Model Court host: <model-court-ip>,
recorded privately). The verified distribution is not proof of every installed
physical CDU version.
See MODEL_COURT_PROVENANCE.json and VALIDATION.md for evidence and open gates.

No tool here deploys, changes a database schema, upgrades Python, removes PHP,
restarts Apache or runs an updater. Keep the two checkouts as sibling directories
pd_localproxy and pd_cdu. Build from pd_localproxy with the existing approved
target interpreter path. Production needs no internet or new third-party library.

## Runtime and behaviour

Localproxy retains Python 3.4.3, BeautifulSoup 4.4.1 and PyMySQL 0.7.9.
The parser emits p3.0 XML, reads CDU.cduNumber as title, recognises the correct
Welsh Summary by Name title and reproduces notice omission/formatting. Queries
remain parameterized. SITE.welshTitle, urlMappings and cduNumber are REQUIRED:
there is no silent fallback to CDU.title/CDU.url and no automatic migration.
Reference SQL is only for empty synthetic test databases.

The CDU retains Python CGI and the installed xsltproc/libxml/libxslt. Its only
dynamic display routes are /index.php (also /), /xhibit_content.php and
/screenshot.php. These URLs are aliases, not physical PHP files. The shell,
JavaScript, clock, CSS, images, localError.html and nine stylesheets come from
the verified distribution. The shell performs AJAX replacement, not the older
five-endpoint/partial-refresh flow. There is no testFile runtime profile.

Content requests, not shell requests, touch timestampMonitorFile. Existing
fetch, timeout, macAddressCmd and lastUpdatedLocation values are supported in
flat or sectioned INIs. The trusted configured UNIX command is retained, without
interpolating request values; its output lines are joined as PHP exec did.
An explicitly empty or undiscovered MAC uses 00:00:00:00:00:00.
Content version is 1.0.0. Ampersand replacement deliberately double-escapes
existing entities, matching PHP. XSL is validated but the new/ tree is always
selected. No Info and Summary by Name now use the valid Model Court assets.

The proxy wrapper still coerces currentPageIndex like PHP and ignores the HTTP
data_refresh string. /proxy/xhibit_refresh.php is not enabled. The unrelated old
/var/www/cgi-bin/xhibit.py remains a caller-inventory gate, not a second parser
contract to merge or a production file this change can delete.

Software aliases /software/checksum.php and /software/download.php use exactly
the external cduArchive setting. The checksum is SHA-1 text with no newline;
downloads contain the exact configured bytes. Missing files have empty 200
bodies; an empty existing file has SHA-1 of the empty string. The archive to
publish is the NEW uncompressed Python-only cdu.tar, not the old PHP archive.
Pin checksumContentType to the observed target header: PHP adds a charset to
text/plain when php.ini default_charset is nonempty. Also confirm the target
defaultContentType and display_errors settings before accepting header parity.

Manager is OPTIONAL, default off, and NOT production-verified. Only an explicit
--with-manager includes its code/static assets/routes, sets the server-side
XHIBIT_WITH_MANAGER flag, and requires its extra schema/authentication checks.
It retains current form field names, database updates, audit identity and 200
responses without redirects. Security-only differences: all substituted output
is HTML-escaped; every POST needs the per-user hidden csrfToken field (HMAC keyed
by optional managerCsrfSecret, else the INI database credentials; preflight
requires the secret if DBpasswd is empty) and, when the browser sends
Origin/Referer, the same host, or it gets 403 before any database access;
cduScreenshot.php accepts only an IPv4 address/host name and relays only PNG
bodies. CDU.url updates remain distinct from urlMappings.url. Do not enable
manager merely because old Apache aliases exist.

## Build and configuration (offline)

Choose a NEW output directory. Nothing overwrites an existing artifact.

~~~sh
python3 migration/deploy.py package localproxy --python /usr/bin/python --output ../output/NEW/localproxy-python.tar.gz
python3 migration/deploy.py package cdu --python /usr/bin/python3 --output ../output/NEW/cdu-python.tar.gz
python3 migration/deploy.py package cdu --python /usr/bin/python3 --format tar --output ../output/NEW/cdu.tar
~~~

For an approved optional manager, add --with-manager to localproxy package,
apache and preflight commands. Default packages exclude manager entirely.
Packages allowlist code/assets, exclude PHP/NuSOAP/configuration/archives/caches,
normalize files to 0644 and CGI to 0755, and include SHA-256 manifests.
Neither legacy sources nor private configuration belongs in Git or an artifact.

Alternatively, `migration/build_release.py --output NEW_DIRECTORY --proxy-python
/usr/bin/python --cdu-python /usr/bin/python3` builds the complete set with disabled
configuration fragments, source revisions and checksums. Add --with-manager only
to build a separate optional-manager package/configuration as well. Build after
local commits, then run `python3 migration/verify_release.py NEW_DIRECTORY` to
check all manifests, release checksums, permissions and absence of PHP/nested
archives in application artifacts. This does not certify a deployed host.

Stage in a NEW root-owned release directory, not over an existing installation.
Supply reviewed external root-owned 0640 INIs (examples in config/), retaining
existing state-file paths and granting Apache write access only to those files.
Preserve existing owners/links. Confirm the actual configured MAC command,
not an assumed network interface. Supply cduArchive as an absolute path to the
new package; do not overwrite the live software artifact during implementation.

~~~sh
python3 migration/deploy.py apache localproxy --install-root /opt/xhibit/localproxy --config /etc/xhibit/ops.ini --output ../output/NEW/proxy-apache
python3 migration/deploy.py apache cdu --install-root /opt/xhibit/cdu --config /etc/xhibit/cdu.ini --output ../output/NEW/cdu-apache
/usr/bin/python migration/deploy.py preflight localproxy --install-root /opt/xhibit/localproxy --config /etc/xhibit/ops.ini
/usr/bin/python3 migration/deploy.py preflight cdu --install-root /opt/xhibit/cdu --config /etc/xhibit/cdu.ini
~~~

For optional manager add --with-manager --auth-config /etc/xhibit/manager-auth.conf
to apache/preflight; retain the EXISTING provider, AuthUserFile and Require
rules. Do not copy the repository's historical Windows .htaccess as target auth.

Configuration generation is NOT activation. Route and final-deny fragments
end in .conf.disabled. Include fragments inside the existing appropriate
vhost; preserve listeners, LAN restrictions, authentication and logging.
The CGI allow rule is not a replacement for network ACLs: carry restrictions
from original filesystem locations to new CGI locations. Check duplicate loaded
localproxy.conf files before an approved pilot, without changing them blindly.
Only intended public assets receive aliases; python/proxy sources stay denied.

Install the existing safe migration/xhibit-capture helper root-owned 0755
with the confirmed target interpreter, validate the sudoers example using
visudo -cf, and grant the narrow helper rule through the approved change.
It invokes the existing screencapture.sh, streams PNG and cleans up as capture
owner. Local screenshot fixtures do not certify real display hardware.
Keep SELinux enforcing; validate narrowly required CGI/read/network/DB/state
permissions with the actual Apache account and target policy.

## Evidence still needed from JBOX

See COMPARE_GITHUB.md. The new -CollectEvidence switch uses existing SSH and
target Python, with an optional offline public baseline. It collects selected
config keys (not credentials or arbitrary shell commands), local database
structure metadata, and a bounded caller/updater search. No database records,
archive transfer, updater execution, root escalation or production writes.
It also reads selected php.ini response settings. Protected/root-only locations
are reported unchecked. Manually review before sharing. An actual CDU needs its
real root supplied; the absent /var/www/lan/cdu on the proxy is not its baseline.

Obtain a manually reviewed macAddressCmd and other operational CDU settings,
representative schema metadata (types, nullability, indexes, collation), root
cron/system updater locations, all external PHP/feed consumers, and the actual
updater extraction/permissions/cleanup process. No new archive transfer is needed.

## Verification and isolated references

~~~sh
python3 -m unittest discover -s migration/tests -v
python3 migration/local_stack.py --database-config /private/disposable-test.ini
~~~

The test DB configuration must opt in with AllowTestDatabases=true and a loopback
host. The runner creates/drops only random xhibit_test_UUID schemas, uses
synthetic feeds and isolated loopback Apache, and never uses target credentials.
Add --with-manager only to test its optional workflows. The runner reports new
ports; old preview processes do not prove the new packages are running.

prepare_reference.py accepts the verified v2 tar, previous comparison report,
optional previously collected software transcript, and a NEW reference directory
OUTSIDE the workspace. It verifies hashes, reconstructs captured diffs, and can
undo terminal whitespace ONLY when complete bytes match the production hash.
No PHP source is embedded in the helper or tracked fixtures.

Opt into test_php_reference.py using XHIBIT_PHP_REFERENCE_DIR and
XHIBIT_PHP_REFERENCE_IMAGE, pointing to a local development-only PHP 5.4 image
with SimpleXML/XSL. That container has no external network, a copied legacy tree,
a synthetic loopback feed and fixture-only state. It compares exact headers,
status, body, MAC/query handling, monitoring files, wrapper arguments, screenshots,
cleanup, entity behaviour and software download/checksum cases. A different
patch level/SAPI/library build is not target certification.

Set XHIBIT_BROWSER_CASES to a private output JSON during the PHP tests.
browser_compare.js uses an existing development-only Playwright installation
(XHIBIT_PLAYWRIGHT_MODULE), reads those actual PHP/Python responses, and serves
only verified assets on loopback. It compares browser state, timing callbacks
and screenshots under a controlled clock. Neither Playwright, Docker, a PHP
reference nor lxml is included in production packages. See VALIDATION.md for
the precise executed versions and remaining physical-browser gates.

compare_http.py retains raw status, selected contract headers and exact bytes;
it excludes infrastructure Date/Server/Connection and removed X-Powered-By.
Use separate synthetic DB copies for writes and frozen screenshot/time fixtures.
Manager comparisons require --auth-env VARIABLE_NAME, never credentials in
arguments. Captures may be sensitive and must stay outside Git.

## Security-only differences

Keep parameterized SQL, DTD/external-entity rejection, xsltproc network/write
restrictions, no CGI HTTP_PROXY routing (the proxy CGI drops HTTP_PROXY before
the in-process parser fetch), secret-safe logging, source denial, bounded command
execution, manager escaping/CSRF checks and the safe screenshot helper. These are
intentional security differences, not a claim of identical handling of hostile
inputs. The capture helper suppresses command stdout, uses unpredictable
basenames, noninteractive sudo, bounded execution and capture-owner cleanup. It
refuses a pre-existing name and streams only a single-link regular file it owns
(no symlinks). Do not weaken these safeguards to emulate unsafe legacy execution.

## Pilot, rollback and PHP-removal gates

1. Obtain redacted target configuration/schema and representative installed CDU
   evidence. Validate on actual Python/libraries, OS, Apache account, SELinux and
   screenshot hardware. Compare all pages/languages, state and schedules and soak
   for rotation, clock, notices, failures, performance and concurrency.
2. Verify the real updater can deploy the NEW archive layout and remove obsolete
   five-endpoint/PHP files. An archive has a new contract-compatible payload, not
   the old contents. Existing unknown updater scripts must NOT be run automatically.
3. Preserve restricted backups of code, configs, artifact, ownership and labels.
   Test rollback on the isolated pilot. No schema change is part of rollback.
4. After approval only: stage fresh code and artifact, carry ACLs, validate Apache,
   enable shell/content/proxy/software/screenshot route fragments as one compatible
   unit, reload through change control, then verify and soak. Manager stays off.
   Never expose only half of a shell/content pair.
5. Rollback: restore previous route/artifact configuration, validate/reload via
   change control, and restore the prior isolated release with state paths intact.
   A PHP rollback restores the old exposure and needs explicit risk acceptance.
6. Audit page.php, selector.php, feed producers and every other PHP consumer FIRST.
   Only after approved migration of all consumers may the final deny fragment,
   host PHP package/service removal and full Apache stop/start proceed.
   Graceful reload alone may retain mod_php in old workers.
7. Run audit_php.py read-only on every target and review all vhosts, listeners,
   processes, mapped libraries, containers and custom installations. Repo/package
   removal alone cannot sign off either CVE or the whole estate.

No production activation, package removal or updater execution is authorized
by running these build/test tools. Every open verification gate must be reported.

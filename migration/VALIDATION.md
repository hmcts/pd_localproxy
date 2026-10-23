# Model Court alignment validation — 23 October 2026

Status: implementation and local release preparation completed. NOT approved for
production deployment or host-level vulnerability-removal sign-off.

## Protected baseline

Both dirty feature worktrees were archived, including their Git state and
untracked migration work, BEFORE edits. Private checkpoint outside Git:

- /Users/owaingreener/Desktop/xhibit-parity-checkpoint.FEQLla/
- pd_localproxy-worktree.tar.gz SHA-256 5e2eae463c486ecc6e86048eee0ef4c6e8f871617c85fac329b4fe47a3dd61db
- pd_cdu-worktree.tar.gz SHA-256 e06e243ecef4dbcddd7fc3be146b6fcf5b5886ade0a0845cd055902759630d08

Archives were listed successfully; folder mode 0700, archives 0600. Recover into
a NEW private directory, never over current worktrees or a public webroot.
No master branch change, history rewrite, push, production connection, deployment,
runtime removal or updater execution is part of this implementation.

The CDU archive SHA-256 is
1920448a5c1e528dcec20b84a01d46049c5f5259f096c23ede732450506c7978.
Its 21 members include nine valid stylesheets. Non-PHP assets and the static shell
are retained byte-for-byte, including CRLF; Git attributes prevent conversion.
The obsolete five-endpoint contract, old/inc stylesheets, bigtext and old jQuery
are removed from the new release. They remain recoverable in the checkpoint.

The two production proxy files were reconstructed from the pinned original
Git objects and complete collected diffs. Their bytes match the recorded hashes.
Software PHP files were recovered from the ALREADY collected transcript by
undoing tab expansion and missing whitespace; complete byte hashes match too.
No extra server archive transfer was needed. Raw PHP references live only in the
private external oracle directory. Git contains provenance hashes and a verified
historical PYTHON parser fixture, not legacy PHP sources or a legacy PHP bundle.

## Executed checks

### Modern development host

Python 3.13.17, BeautifulSoup 4.15.0, PyMySQL distribution 1.2.3,
development lxml/libxslt, isolated Apache and MariaDB 10.11.19:
89 tests passed, no skips, with all opt-ins enabled.

Coverage includes 16 refreshed frozen XML goldens from the verified p3.0 parser,
all page types/languages, notices/Unicode/entities, rotation, currentPageIndex
and ineffective HTTP data_refresh, power-saving schedules, manager's unchanged
optional form/audit/update semantics, bound SQL, rollback, strict schema checks,
source denial, screenshot fixtures/cleanup, actual downloaded Python-only cdu.tar,
checksum/missing/empty bytes, default-off manager and default preflight without
manager authentication. JBOX helper tests include private-output/protocol limits,
redaction and metadata-only query restrictions. Portable PowerShell 7.4 tests
exercise the pipeline, not Windows 5.1/NTFS certification.

### Actual Python 3.4.3 / deployed parser libraries

A disposable CentOS 7 ARM64 container ran CPython 3.4.3, BeautifulSoup 4.4.1,
PyMySQL 0.7.9, libxml 2.9.1 / libxslt 1.1.28 / libexslt 0.8.17,
Apache 2.4.6-95.el7.centos and the dedicated MariaDB 10.11.19 service.

89 tests ran: 81 passed, 8 intentionally skipped (six separate PHP-oracle tests,
development lxml reference and portable PowerShell unavailable in that container).
This INCLUDED real CGI, all 16 feed/parser/display HTTP combinations, optional
manager workflows, default-off manager routing, software delivery, preflight,
and disposable SQL integration. Tests ran as the unprivileged apache account.
No development stdlib compatibility shim was needed.

This materially exceeds syntax-only checks but is NOT the physical RHEL/Pi
environment, actual database metadata, MariaDB 5.5 or the exact target RPM build.

CPython was built locally for testing from the official Python 3.4.3 source;
source SHA-256 8b743f56e9e50bf0923b9e9c45dd927c071d7aa56cd46569d8818add8cf01147.
This is not a production runtime upgrade. No compiler/container/test dependency
is included in an application package.

### Actual legacy PHP differential reference

Six opt-in test groups passed using PHP 5.4.16-42.el7 CGI, SimpleXML/XSL,
libxml 2.9.1 and libxslt 1.1.28, in a separate network-isolated Linux container.
The source tree is hash-verified; all inputs/state/screenshots are synthetic.
The server inside the container listens only on its isolated loopback interface.

Comparisons assert exact status, contract headers and body bytes for shell,
all 16 content combinations, unknown types, missing/empty/duplicate fields,
malformed XML, raw ampersands/existing/numeric entities, missing last-updated,
fetch failures, MAC command discovery/nonzero exit/zero fallback, parameters,
proxy wrapper CLI arguments, screenshots/failure/cleanup, and software normal/
empty/missing files. State-file contents/touches are compared too.

A holding-page trailing newline difference was discovered and corrected.
PHP's checksum header appends default_charset when nonempty; both empty and
UTF-8 reference configurations now pass, with checksumContentType explicitly
configured to the corresponding observed header. Target php.ini values are
still needed before claiming target header parity.

The reference is CGI, not the original mod_php SAPI, and -42 is not production's
-43.el7_4 RPM. Tests freeze display inputs and use controlled screenshot bytes;
they do not establish target timezone/locale/patch-level or error-display parity.

### Browser comparison

22 synthetic scenarios were compared with headless Chromium 151 at 1280x720
and a controlled clock, using ACTUAL PHP/Python-produced HTML and hash-identical
assets. Pixel screenshots, DOM state, clock, AJAX replacement, rotation/retry
callbacks, notification text and power-saving state matched.

The scrolling case spans 14 pages; one-page intervals are 30 seconds at refresh
15, scrolling intervals 15 seconds, the clock schedules 500ms updates, holding
pages retry at 10 seconds, and AJAX HTTP failures stop after three attempts.
English/Welsh power saving and Unicode/entity notices are included.
Marquees are stopped for deterministic screenshot comparison; physical browser,
font, viewport, marquee animation and kiosk timing remain pilot checks.

IMPORTANT baseline defect: the verified No Info stylesheet sets NOINFO="false"
without a resultTable. BOTH legacy PHP and Python therefore raise
"resultTable is not defined" on initialise(), while rendering No Info and retaining
the stylesheet's scheduled retry. The old malformed-XSL HTTP 500 is gone, but this
shared browser defect is NOT described as fully working/error-free No Info.
Verified assets are not silently modified. The harness explicitly checks and
records this known error and fails for any other unexpected browser exception.
Obtain an explicit decision before fixing the source asset as a separate change.

Screenshots and detailed results are private external evidence:
xhibit-parity-checkpoint.FEQLla/browser-comparison-final/.
They contain synthetic data only and are not production assets.

## Release checks

build_release.py creates a new, versioned output directory; old artifacts are
not overwritten. It builds default localproxy/CDU compressed packages and the
uncompressed Python-only cdu.tar, disabled Apache fragments, migration tools,
configuration examples, SHA-256 per-file manifests and SHA256SUMS.
Optional manager packages/configs require an explicit --with-manager.

Application packages exclude physical PHP, NuSOAP, configuration credentials,
SQL, tests, legacy references and nested archives. Public .php strings are URLs,
not files or interpreter calls. Modes are normalized (0644, CGI 0755), ownership
metadata is root/0. The release content is checked against manifests and the
downloaded bytes against the configured artifact. Shared HTTP helpers match.
No PHP runtime or new production third-party library is introduced.

Security-only differences are explicitly retained: parameterized SQL, XML entity/
DTD rejection, xsltproc no-network/no-write, HTTP_PROXY isolation, secret-safe
diagnostics, source denial, bounded commands and safe capture-helper execution.
These are not claims of identical behaviour for hostile input.

## Outstanding acceptance/deployment gates

1. Collect redacted real target configuration and schema metadata using the new
   opt-in JBOX evidence mode; it has NOT been run against production by this agent.
   Confirm MIME/charset/display_errors, configured MAC command/interface, state
   paths, timeouts, environment, database types/nullability/indexes/collations.
   No production schema migrations are supplied or permitted.
2. Verify a representative physical CDU's installed files and exact interpreter/
   libraries, hardware screenshots/cleanup, fonts, browser/kiosk behaviour,
   concurrency, performance and RHEL SELinux policy under the actual Apache user.
   A distribution archive is not fleet-wide installation evidence.
3. Review the shared No Info browser defect above. Date-specific schedules also
   retain the verified legacy todayDate NameError; day-based schedules are tested.
   No unsupported claim of error-free baseline behaviour is made.
4. Identify callers of the old CGI-directory parser, all root/system updater
   jobs and actual updater installation/extraction/obsolete-file cleanup.
   Verify a fresh Python archive can be deployed with its CGI/configuration;
   do not feed the new layout to an unverified old updater.
5. Account for page.php, selector.php, feed producers and every external PHP
   consumer before any host-level PHP disable/removal. Optional manager remains
   off and not production-verified; do not infer parity from absent aliases.
6. Complete an approved pilot, soak and tested rollback. Only then obtain separate
   approval for host package/service removal and full Apache restart, followed
   by per-host runtime/module/process/listener/custom-installation verification.
   Repository commits cannot certify CVE removal on live hosts.

No unexplained difference was found in the exercised supported synthetic cases.
The gates above remain open; this is not an assertion of certainty across the
fleet or permission to deploy.

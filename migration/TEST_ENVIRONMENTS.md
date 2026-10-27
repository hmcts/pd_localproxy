# Repeating the isolated reference checks

These are development-only environments. Never deploy the vulnerable PHP image,
compiler, Docker, Playwright or test libraries to the proxy/CDU. Use synthetic
inputs and a dedicated disposable database, never target credentials.

The executed local images are `xhibit-legacy-oracle:php54-el7` and
`xhibit-target-test:python343-apache`. They remain local and have not been pushed.
Legacy sources and downloaded build inputs are in the private checkpoint, not Git.
All reference/test containers were stopped after testing; no PHP service listens
on the host. The existing disposable database service was left unchanged.

To recreate the source reference, run `prepare_reference.py` with the supplied
v2 archive, existing comparison report, existing software transcript and a NEW
private destination outside both repositories. It refuses a wrong archive hash
or source reconstruction and never fetches from a production host.

For the executed PHP environment, use the local CentOS 7 ARM64 base (digest
`be65f488b7764ad3638f236b7b515b3678369a5124c47b8d32916d6487418ea4`) and these
official CentOS Vault 7.4.1708 altarch/aarch64 packages:

- php-cli, php-common, php-xml: 5.4.16-42.el7
- libxslt: 1.1.28-5.el7
- libedit: 3.0-12.20121213cvs.el7
- libzip: 0.10.1-8.el7

Retrieve through normal verified HTTPS from
[CentOS Vault](https://vault.centos.org/altarch/7.4.1708/os/aarch64/Packages/).
Verify RPM signatures against the original CentOS 7/aarch64 public keys already
in the base image. Do not bypass TLS or package signature validation. The test
host's existing corporate CA may be needed for development downloads.
Install only inside the disposable image, then confirm `php -v`, SimpleXML/XSL
modules and `xsltproc --version`. The application reference tests start their own
network-isolated container with an internal loopback fixture server.

For Python, build the official
[Python 3.4.3 source](https://www.python.org/ftp/python/3.4.3/Python-3.4.3.tgz)
with `./configure --prefix=/opt/python34 --without-ensurepip`, `make`,
`make install`, using an isolated CentOS 7 development image with gcc/make,
openssl/zlib/libffi development headers. Add the same libxslt RPM and a local
Apache 2.4.6. The executed Apache package was 2.4.6-95.el7.centos from the signed
7.9.2009 Vault repository. Supply existing BeautifulSoup 4.4.1 and PyMySQL 0.7.9
source directories through a read-only development PYTHONPATH; no pip invocation
or stdlib shim is needed. Run tests as unprivileged `apache`, not root.

Use a dedicated MariaDB service and a private INI with AllowTestDatabases=true.
In the executed Linux test, the test container shares ONLY the dedicated test
database container's network namespace, so MySQL is loopback and every Apache/feed
listener stays in that namespace. No production network target is involved.
Never use host networking or publish test HTTP/PHP ports to a LAN.

Modern host tests use the same opt-in INI via XHIBIT_TEST_MYSQL_CONFIG. Additional
opt-ins are XHIBIT_TEST_PWSH, XHIBIT_PHP_REFERENCE_DIR and
XHIBIT_PHP_REFERENCE_IMAGE. Set XHIBIT_BROWSER_CASES to a private JSON output path
for actual PHP/Python HTML used by the browser comparison. Run:

```sh
python3 -m unittest discover -s migration/tests -v
node migration/browser_compare.js PRIVATE_CASES_JSON ../pd_cdu NEW_PRIVATE_OUTPUT
```

The latter uses an existing development playwright-core installation through
XHIBIT_PLAYWRIGHT_MODULE and an existing Chromium through PLAYWRIGHT_BROWSERS_PATH.
It does not download a browser. Test runs may need separate environment wrappers
for local runtime/dependency paths; never copy those into production configs.

See VALIDATION.md for actual pass/skip counts, the shared No Info browser defect,
patch-level/SAPI differences and all outstanding physical-target gates.

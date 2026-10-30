# ghsa_severity: 20 random items for a spot check

Check the gold label against the linked source record.

## 1. GHSA-3xc2-h5r3-wv3r (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2026/05/GHSA-3xc2-h5r3-wv3r/GHSA-3xc2-h5r3-wv3r.json

```
Package security advisory (published 2026-05-05)
Packages: Packagist kimai/kimai
Summary: Kimai vulnerable to formula Injection via tag names in XLSX export
Details: Any `ROLE_USER` can create a tag with a formula string as its name (e.g. `=SUM(54+51)`) via `POST /api/tags` and assign it to a timesheet. When an admin exports timesheets to XLSX, `ArrayFormatter.formatValue()` joins tag names with `implode()` and returns the result unchanged. OpenSpout promotes any `=`-prefixed string to a `FormulaCell`, writing ` SUM(54+51) ` into the XLSX archive. Excel evaluates the formula when the file is opened. `sanitizeDDE()` exists on `StringHelper` and is called by `TextFormatter`, but `ArrayFormatter` never calls it. The API blocks commas in tag names but permits `=`, `+`, `-`, and `@` - all valid formula prefixes in Excel and LibreOffice Calc. `Cell::fromValue("=SUM(54+51)")` returns a `FormulaCell` with no warning. Any `ROLE_USER` can plant a formula that executes on the workstation of any user who exports and opens timesheet data. A single malicious tag poisons all future exports across all users and date ranges until the tag is deleted.

How severe is the vulnerability described in this advisory?
```

## 2. GHSA-844m-cpr9-jcmh (select): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2021/11/GHSA-844m-cpr9-jcmh/GHSA-844m-cpr9-jcmh.json

```
Package security advisory (published 2021-11-15)
Packages: RubyGems rails_multisite
Summary: Rails Multisite secure/signed cookies share secrets between sites in a multi-site application
Details: This vulnerability impacts any Rails applications using `rails_multisite` alongside Rails' signed/encrypted cookies. Depending on how the application makes use of these cookies, it may be possible for an attacker to re-use cookies on different 'sites' within a multi-site Rails application. The issue has been patched in v4 of the `rails_multisite` gem. Note that this upgrade will invalidate all previous signed/encrypted cookies. The impact of this invalidation will vary based on the application architecture.

Which of these is the severity of the vulnerability in this advisory?
```

## 3. GHSA-9qj6-qjgg-37qq (train): gold = Critical severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2026/05/GHSA-9qj6-qjgg-37qq/GHSA-9qj6-qjgg-37qq.json

```
Package security advisory (published 2026-05-08)
Packages: npm vm2
Summary: vm2 has sandbox breakout via `neutralizeArraySpeciesBatch`
Details: VM2 suffers from a sandbox breakout vulnerability. This allows attackers to write code which can escape from the VM2 sandbox and execute arbitrary commands on the host system. The new method `neutralizeArraySpeciesBatch` works with objects from the other side but can call into this side via getter on the array prototype exposing objects of the wrong side into the sandbox. This can be used to get host objects and get the host `Function` object. Attackers can perform Remote Code Execution under the assumption that arbitrary code can be executed inside the context of a vm2 sandbox.

Which of these is the severity of the vulnerability in this advisory?
```

## 4. GHSA-pqhp-25j4-6hq9 (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2024/11/GHSA-pqhp-25j4-6hq9/GHSA-pqhp-25j4-6hq9.json

```
Package security advisory (published 2024-11-22)
Packages: npm smol-toml
Summary: smol-toml has a Denial of Service via malicious TOML document using deeply nested inline tables
Details: An attacker can send a maliciously crafted TOML to cause the parser to crash because of a stack overflow caused by a deeply nested inline structure. A similar problem occurs when attempting to stringify deeply nested objects. The library does not limit the maximum exploration depth while parsing or producing TOML documents, nor does it offer a way to do so. Applications which parse arbitrary TOML documents may suffer availability issues if they receive malicious input. If uncaught, the crash may cause the application itself to crash. The impact is deemed minor, as the function is already likely to throw errors on invalid input and therefore to properly handle errors. Due to the design of most JavaScript runtimes, the uncontrolled recursion does not lead to excessive memory usage and the execution is quickly aborted. As a reminder, it is strongly advised when working with untrusted user input to expect errors to occur and to appropriately catch them.

How severe is the vulnerability described in this advisory?
```

## 5. GHSA-r275-fr43-pm7q (train): gold = Critical severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2026/03/GHSA-r275-fr43-pm7q/GHSA-r275-fr43-pm7q.json

```
Package security advisory (published 2026-03-10)
Packages: npm simple-git
Summary: simple-git has blockUnsafeOperationsPlugin bypass via case-insensitive protocol.allow config key enables RCE
Details: The `blockUnsafeOperationsPlugin` in `simple-git` fails to block git protocol override arguments when the config key is passed in uppercase or mixed case. An attacker who controls arguments passed to git operations can enable the `ext::` protocol by passing `-c PROTOCOL.ALLOW=always`, which executes an arbitrary OS command on the host machine. The `preventProtocolOverride` function in `simple-git/src/lib/plugins/block-unsafe-operations-plugin.ts` (line 24) checks whether a `-c` argument configures `protocol.allow` using this regex: This regex is case-sensitive. Git treats config key names case-insensitively — it normalises them to lowercase internally. As a result, passing `PROTOCOL.ALLOW=always`, `Protocol.Allow=always`, or any mixed-case variant is not matched by the regex, the check returns without throwing, and git is spawned with the unsafe argument.

What severity was assigned to this advisory?
```

## 6. GHSA-859m-2pfx-fwhf (test): gold = Critical severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2023/07/GHSA-859m-2pfx-fwhf/GHSA-859m-2pfx-fwhf.json

```
Package security advisory (published 2023-07-28)
Packages: Maven opensymphony:oscore
Summary: Code injection in oscore
Details: oscore v2.2.6 and below was discovered to contain a code injection vulnerability in the component com.opensymphony.util.EJBUtils.createStateless. This vulnerability is exploited via passing an unchecked argument.

How severe is the vulnerability described in this advisory?
```

## 7. GHSA-65f5-mfpf-vfhj (train): gold = High severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2023/01/GHSA-65f5-mfpf-vfhj/GHSA-65f5-mfpf-vfhj.json

```
Package security advisory (published 2023-01-18)
Packages: RubyGems rack
Summary: Denial of service via header parsing in Rack
Details: There is a possible denial of service vulnerability in the Range header parsing component of Rack. This vulnerability has been assigned the CVE identifier CVE-2022-44570. Versions Affected: >= 1.5.0 Not affected: None. Fixed Versions: 2.0.9.2, 2.1.4.2, 2.2.6.2, 3.0.0.1 Impact. Carefully crafted input can cause the Range header parsing component in Rack to take an unexpected amount of time, possibly resulting in a denial of service attack vector. Any applications that deal with Range requests (such as streaming applications, or applications that serve files) may be impacted. Releases. The fixed releases are available at the normal locations. Workarounds. There are no feasible workarounds for this issue. Patches. To aid users who aren’t able to upgrade immediately we have provided patches for the two supported release series. They are in git-am format and consist of a single changeset.

How was this advisory's vulnerability graded?
```

## 8. GHSA-wprv-93r4-jj2p (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2023/06/GHSA-wprv-93r4-jj2p/GHSA-wprv-93r4-jj2p.json

```
Package security advisory (published 2023-06-19)
Packages: npm openzeppelin/contracts; npm openzeppelin/contracts-upgradeable
Summary: OpenZeppelin Contracts using MerkleProof multiproofs may allow proving arbitrary leaves for specific trees
Details: When the `verifyMultiProof`, `verifyMultiProofCalldata`, `processMultiProof`, or `processMultiProofCalldata` functions are in use, it is possible to construct merkle trees that allow forging a valid multiproof for an arbitrary set of leaves. A contract may be vulnerable if it uses multiproofs for verification and the merkle tree that is processed includes a node with value 0 at depth 1 (just under the root). This could happen inadvertently for balanced trees with 3 leaves or less, if the leaves are not hashed. This could happen deliberately if a malicious tree builder includes such a node in the tree. A contract is not vulnerable if it uses single-leaf proving (`verify`, `verifyCalldata`, `processProof`, or `processProofCalldata`), or if it uses multiproofs with a known tree that has hashed leaves. Standard merkle trees produced or validated with the openzeppelin/merkle-tree library are safe. The problem has been patched in 4.9.2.

What severity was assigned to this advisory?
```

## 9. GHSA-q624-9634-77gh (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2022/05/GHSA-q624-9634-77gh/GHSA-q624-9634-77gh.json

```
Package security advisory (published 2022-05-17)
Packages: PyPI CherryMusic
Summary: Cherry Music directory traversal vulnerability
Details: Directory traversal vulnerability in Cherry Music before 0.36.0 allows remote authenticated users to read arbitrary files via the "value" parameter to "download.".

How was this advisory's vulnerability graded?
```

## 10. GHSA-fr4j-65pv-gjjj (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2026/01/GHSA-fr4j-65pv-gjjj/GHSA-fr4j-65pv-gjjj.json

```
Package security advisory (published 2026-01-13)
Packages: npm renovate
Summary: Renovate vulnerable to arbitrary command injection via npm manager and malicious Renovate configuration
Details: The user-provided string `packageName` in the `npm` manager is appended to the `npm install` command during lock maintenance without proper sanitization. Adversaries can provide a maliciously crafted Renovate configuration file to trick Renovate to execute arbitrary code. The user-provided workspace names and package keys that are added to the `updateCmd` variables in lib/modules/manager/npm/post-update/npm.ts are not being escaped using the `quote` function from the `shlex` package. This lack of proper sanitization has been present in the product since version 35.63.0 ( released on April 27 of 2023. This is a Arbitrary Command Injection vulnerability, allowing those with write access on repositories configured to be scanned by Renovate to cause the execution of commands of their choice on the machine that runs Renovate.

How was this advisory's vulnerability graded?
```

## 11. GHSA-c89g-gq5r-2xw2 (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2024/10/GHSA-c89g-gq5r-2xw2/GHSA-c89g-gq5r-2xw2.json

```
Package security advisory (published 2024-10-10)
Packages: Packagist magento/community-edition
Summary: Magento Open Source stored Cross-Site Scripting (XSS) vulnerability
Details: Malicious JavaScript may be executed in a victim’s browser when they browse to the page containing the vulnerable field.

What severity was assigned to this advisory?
```

## 12. GHSA-xp7p-3gx7-j6wx (train): gold = Critical severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2022/01/GHSA-xp7p-3gx7-j6wx/GHSA-xp7p-3gx7-j6wx.json

```
Package security advisory (published 2022-01-21)
Packages: PyPI calibreweb
Summary: calibre-web is vulnerable to Business Logic Errors
Details: calibre-web is vulnerable to Business Logic Errors.

What severity was assigned to this advisory?
```

## 13. GHSA-j9gq-w73w-9h6c (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2023/10/GHSA-j9gq-w73w-9h6c/GHSA-j9gq-w73w-9h6c.json

```
Package security advisory (published 2023-10-02)
Packages: PyPI pretix
Summary: pretix potential IP address spoofing vulnerability
Details: An issue was discovered in pretix before 2023.7.1. Incorrect parsing of configuration files causes the application to trust unchecked X-Forwarded-For headers even though it has not been configured to do so. This can lead to IP address spoofing by users of the application.

How was this advisory's vulnerability graded?
```

## 14. GHSA-mf6x-hrgr-658f (train): gold = High severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2023/01/GHSA-mf6x-hrgr-658f/GHSA-mf6x-hrgr-658f.json

```
Package security advisory (published 2023-01-30)
Packages: npm eta
Summary: Eta vulnerable to Code Injection via templates rendered with user-defined data
Details: Versions of the package eta before 2.0.0 are vulnerable to Remote Code Execution (RCE) by overwriting template engine configuration variables with view options received from The Express render API. Note: This is exploitable only for users who are rendering templates with user-defined data.

How was this advisory's vulnerability graded?
```

## 15. GHSA-855v-hq7w-jmjw (train): gold = High severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2026/07/GHSA-855v-hq7w-jmjw/GHSA-855v-hq7w-jmjw.json

```
Package security advisory (published 2026-07-24)
Packages: PyPI open-webui
Summary: Open WebUI: Realtime endpoints accept Redis-revoked JWTs after signout/backchannel logout
Details: With Redis configured, Open WebUI supports JWT revocation: `POST /api/v1/auths/signout` (per-token `jti`) and OIDC back-channel logout (per-user `revoked_at`) record revocations in Redis, and HTTP auth (`get_current_user`) rejects revoked tokens with 401. The realtime authentication surfaces do not perform this check: Socket.IO connect / user-join / join-channels / join-note and the terminal websocket first-message auth validate tokens with `decode_token()` only (signature + expiry). A JWT revoked by sign-out or back-channel logout therefore continues to authenticate new realtime connections, even though the same token is rejected on HTTP. `backend/open_webui/socket/main.py` — Socket.IO `connect`, `user-join`, `join-channels`, `join-note`. `backend/open_webui/routers/terminals.py` — terminal websocket first-message auth. `backend/open_webui/utils/auth.py` — the revocation check was applied to HTTP only.

Which severity level does this security advisory have?
```

## 16. GHSA-2cwq-pwfr-wcw3 (train): gold = High severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2026/05/GHSA-2cwq-pwfr-wcw3/GHSA-2cwq-pwfr-wcw3.json

```
Package security advisory (published 2026-05-06)
Packages: NuGet Nerdbank.MessagePack
Summary: Nerdbank.MessagePack: Attacker-controlled stackalloc in DateTime decoding causes process-terminating StackOverflowException
Details: Nerdbank.MessagePack contains an uncontrolled stack allocation vulnerability in DateTime decoding. A malicious MessagePack payload can declare an oversized timestamp extension length, causing the reader to allocate an attacker-controlled number of bytes on the stack. This can trigger a `StackOverflowException`, which is not catchable by user code and terminates the process. Applications are impacted if they deserialize MessagePack data from untrusted or attacker-controlled sources using Nerdbank.MessagePack and the target type contains a `DateTime` value. A small malicious payload can cause process termination, resulting in a denial of service. This may affect services, APIs, workers, message consumers, or other long-running processes that deserialize untrusted MessagePack input.

What severity was assigned to this advisory?
```

## 17. GHSA-p7x2-g5cq-fhmq (select): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2026/08/GHSA-p7x2-g5cq-fhmq/GHSA-p7x2-g5cq-fhmq.json

```
Package security advisory (published 2026-08-25)
Packages: npm mediasoup; crates.io mediasoup
Summary: mediasoup: SCTP state cookie lacks cryptographic authentication, enabling unauthorized association establishment (RFC 9260 violation)
Details: mediasoup's built-in SCTP stack (introduced in v3.20.0) authenticates SCTP state cookies using only hardcoded magic byte sequences rather than a per-instance HMAC keyed with a secret, violating RFC 9260 Section 5.1.3. An on-path attacker targeting a PlainTransport with SCTP enabled (and no SRTP/DTLS protection) can craft a forged COOKIE-ECHO chunk that passes all validation, establishing an unauthorized SCTP association and gaining the ability to inject DataChannel messages as a trusted peer. RFC 9260 Section 5.1.3 states: "An endpoint MUST use a one-time-use secret key to protect the State Cookie." The mediasoup implementation ignores this requirement. The state cookie is defined in `worker/include/RTC/SCTP/association/StateCookie.hpp` with the following structure (44 bytes total): Offset 0: Magic1 = `"msworker"` (hardcoded, 8 bytes). Offset 8: localVerificationTag (4 bytes, attacker-controlled). Offset 12: remoteVerificationTag (4 bytes, attacker-controlled).

How was this advisory's vulnerability graded?
```

## 18. GHSA-gw2g-hhc9-wgjh (train): gold = High severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2022/11/GHSA-gw2g-hhc9-wgjh/GHSA-gw2g-hhc9-wgjh.json

```
Package security advisory (published 2022-11-16)
Packages: Go github.com/hashicorp/consul
Summary: Missing Authorization in HashiCorp Consul
Details: HashiCorp Consul and Consul Enterprise 1.13.0 up to 1.13.3 do not filter cluster filtering's imported nodes and services for HTTP or RPC endpoints used by the UI. Fixed in 1.14.0.

Which severity level does this security advisory have?
```

## 19. GHSA-5fw9-fq32-wv5p (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2020/12/GHSA-5fw9-fq32-wv5p/GHSA-5fw9-fq32-wv5p.json

```
Package security advisory (published 2020-12-21)
Packages: npm node-notifier
Summary: OS Command Injection in node-notifier
Details: This affects the package node-notifier before 8.0.1. It allows an attacker to run arbitrary commands on Linux machines due to the options params not being sanitised when being passed an array.

What severity was assigned to this advisory?
```

## 20. GHSA-vmgw-24w6-9v82 (train): gold = Moderate severity

https://github.com/github/advisory-database/blob/048deacdbddda9fcd84f7063549b0b8b9905b90f/advisories/github-reviewed/2025/03/GHSA-vmgw-24w6-9v82/GHSA-vmgw-24w6-9v82.json

```
Package security advisory (published 2025-03-19)
Packages: Packagist clickstorm/cs-seo
Summary: Clickstorm SEO Allows Cross-Site Scripting (XSS)
Details: A cross-site scripting (XSS) vulnerability has been discovered in the Clickstorm SEO extension. This vulnerabily is exploitable by a logged in backend user utilizing the TYPO3 backend user interface. This user can create output in the HTML context by exploiting improperly encoded user input. Updates 6.7.0, 7.4.0, 8.3.0 and 9.2.0 are available for download.

Which severity level does this security advisory have?
```


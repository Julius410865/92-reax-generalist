# nvd_severity: 20 random items for a spot check

Check the gold label against the linked source record.

## 1. CVE-2024-13440 (train): gold = High (CVSS v3 base score 7.0-8.9)

https://nvd.nist.gov/vuln/detail/CVE-2024-13440

```
CVE record (published 2025)
Description: The Super Store Finder plugin for WordPress is vulnerable to SQL Injection via the ‘ssf_wp_user_name’ parameter in all versions up to, and including, 7.0 due to insufficient escaping on the user supplied parameter and lack of sufficient preparation on the existing SQL query. This makes it possible for unauthenticated attackers to append additional SQL queries into an already existing query to store cross-site scripting in store reviews.

Which CVSS v3 severity rating was assigned to this vulnerability?
```

## 2. CVE-2024-38151 (train): gold = Medium (CVSS v3 base score 4.0-6.9)

https://nvd.nist.gov/vuln/detail/CVE-2024-38151

```
CVE record (published 2024)
Description: Windows Kernel Information Disclosure Vulnerability

Which CVSS v3 severity rating was assigned to this vulnerability?
```

## 3. CVE-2026-6611 (train): gold = Low (CVSS v3 base score 0.1-3.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-6611

```
CVE record (published 2026)
Description: A vulnerability was found in liangliangyy DjangoBlog up to 2.1.0.0. This affects an unknown function of the file djangoblog/settings.py of the component File Upload Endpoint. Performing a manipulation of the argument SECRET_KEY results in use of hard-coded cryptographic key . Remote exploitation of the attack is possible. The exploitability is reported as difficult. The exploit has been made public and could be used. The vendor was contacted early about this disclosure but did not respond in any way.

How severe is this vulnerability on the CVSS v3 scale?
```

## 4. CVE-2026-81161 (train): gold = Low (CVSS v3 base score 0.1-3.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-81161

```
CVE record (published 2026)
Description: Privilege Defined With Unsafe Actions vulnerability in Drupal Content Moderation Notifications allows Privilege Escalation. This issue affects Content Moderation Notifications versions: from 0.0.0 to 3.9.0.

Which CVSS v3 base severity does this CVE record carry?
```

## 5. CVE-2026-34596 (train): gold = High (CVSS v3 base score 7.0-8.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-34596

```
CVE record (published 2026)
Description: Sandboxie-Plus is an open source sandbox-based isolation software for Windows. In versions 1.17.2 and earlier, a Time-of-Check-to-Time-of-Use (TOCTOU) race condition exists during addon installation. When a user installs an addon through the SandMan interface, UpdUtil.exe is spawned as SYSTEM by SbieSvc but stages files in the user-writable %TEMP%\sandboxie-updater directory. After UpdUtil verifies file hashes against the signed addon manifest, install.bat extracts files.cab and executes config.exe from its contents. Between hash verification and extraction, an unprivileged user can replace files.cab with a crafted cabinet containing a malicious executable, which is then run as SYSTEM. No UAC prompt is required. This issue has been fixed in version 1.17.3.

Pick the CVSS v3 base severity of the vulnerability described above.
```

## 6. CVE-2024-11145 (train): gold = Critical (CVSS v3 base score 9.0-10.0)

https://nvd.nist.gov/vuln/detail/CVE-2024-11145

```
CVE record (published 2024)
Description: Valor Apps Easy Folder Listing Pro has a deserialization vulnerability that allows an unauthenticated, remote attacker to execute arbitrary code with the privileges of the Joomla! application. Fixed in versions 3.8 and 4.5.

How severe is this vulnerability on the CVSS v3 scale?
```

## 7. CVE-2025-43877 (train): gold = Medium (CVSS v3 base score 4.0-6.9)

https://nvd.nist.gov/vuln/detail/CVE-2025-43877

```
CVE record (published 2025)
Description: WRC-1167GHBK2-S contains a stored cross-site scripting vulnerability in WebGUI. If exploited, an arbitrary script may be executed on the web browser of the user who accessed WebGUI of the product.

How severe is this vulnerability on the CVSS v3 scale?
```

## 8. CVE-2023-6741 (train): gold = Medium (CVSS v3 base score 4.0-6.9)

https://nvd.nist.gov/vuln/detail/CVE-2023-6741

```
CVE record (published 2024)
Description: The WP Customer Area WordPress plugin before 8.2.1 does not properly validate users capabilities in some of its AJAX actions, allowing malicious users to edit other users' account address.

How severe is this vulnerability on the CVSS v3 scale?
```

## 9. CVE-2026-114723 (train): gold = Low (CVSS v3 base score 0.1-3.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-114723

```
CVE record (published 2026)
Description: Roundcube Webmail before 1.6.20 and 1.7.x before 1.7.5 allows the ImageMagick resource limits to be bypassed during thumbnail generation. When rcube_image falls back to GD, the available-memory check was applied only on Windows, so on other platforms a crafted image with large dimensions was processed by GD without any resource limit and could exhaust server memory. Upstream fixed this in the commit “Fix ImageMagick resource limits bypass by GD fallback during thumbnail generation”, which applies the memory check on all platforms.

Which CVSS v3 severity rating was assigned to this vulnerability?
```

## 10. CVE-2026-41453 (train): gold = High (CVSS v3 base score 7.0-8.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-41453

```
CVE record (published 2026)
Description: Krayin CRM before 2.2.4 contains a blind SQL injection vulnerability in the leads DataGrid that allows authenticated users with leads access to inject arbitrary SQL into a HAVING clause by manipulating the rotten_lead[in] query parameter, which is concatenated without parameterized binding directly into a havingRaw() call in LeadDataGrid.php. Attackers can exploit this flaw using time-based and boolean-based blind injection techniques to extract the entire database contents, including user credential hashes, CRM records, and application configuration data.

Which CVSS v3 base severity does this CVE record carry?
```

## 11. CVE-2026-5586 (train): gold = Medium (CVSS v3 base score 4.0-6.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-5586

```
CVE record (published 2026)
Description: A vulnerability was determined in zhongyu09 openchatbi up to 0.2.1. The impacted element is an unknown function of the component Multi-stage Text2SQL Workflow. Executing a manipulation of the argument keywords can lead to sql injection. The attack may be launched remotely. The exploit has been publicly disclosed and may be utilized.

Pick the CVSS v3 base severity of the vulnerability described above.
```

## 12. CVE-2026-76285 (train): gold = Critical (CVSS v3 base score 9.0-10.0)

https://nvd.nist.gov/vuln/detail/CVE-2026-76285

```
CVE record (published 2026)
Description: As part of Cisco's ongoing commitment to proactive security and product quality, Cisco has conducted a comprehensive internal security review. This review resulted in a software hardening release that addresses multiple internally discovered vulnerabilities. The vulnerabilities tracked by CVE-2026-76285 are related to improper adherence to coding standards and are grouped under the Common Weakness Enumeration (CWE) CWE-710.

Which CVSS v3 severity rating was assigned to this vulnerability?
```

## 13. CVE-2021-43716 (train): gold = Critical (CVSS v3 base score 9.0-10.0)

https://nvd.nist.gov/vuln/detail/CVE-2021-43716

```
CVE record (published 2026)
Description: Verification Bypass vulnerability exists in EPSON 150075647YWWV110 EasyMP Network Updater Ver.1.20. The Epson projector can be updated by encrypted firmware through USB.

Pick the CVSS v3 base severity of the vulnerability described above.
```

## 14. CVE-2026-0572 (train): gold = Medium (CVSS v3 base score 4.0-6.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-0572

```
CVE record (published 2026)
Description: The WebPurify Profanity Filter plugin for WordPress is vulnerable to unauthorized modification of data due to a missing capability check on the 'webpurify_save_options' function in all versions up to, and including, 4.0.2. This makes it possible for unauthenticated attackers to change plugin settings.

Which CVSS v3 severity rating was assigned to this vulnerability?
```

## 15. CVE-2024-14046 (train): gold = Medium (CVSS v3 base score 4.0-6.9)

https://nvd.nist.gov/vuln/detail/CVE-2024-14046

```
CVE record (published 2026)
Description: A security vulnerability has been detected in OpenBoxes up to 0.9.1. This issue affects the function DocumentController of the file grails-app/controllers/org/pih/warehouse/core/DocumentController.groovy of the component Document Upload Controller. The manipulation leads to unrestricted upload. It is possible to initiate the attack remotely. The exploit has been disclosed publicly and may be used. Upgrading to version 0.9.2 is capable of addressing this issue. The identifier of the patch is e945d6bfcec29642f514e7d298dfba2cc6cd7cd4. Upgrading the affected component is recommended.

Which CVSS v3 severity rating was assigned to this vulnerability?
```

## 16. CVE-2025-9465 (train): gold = High (CVSS v3 base score 7.0-8.9)

https://nvd.nist.gov/vuln/detail/CVE-2025-9465

```
CVE record (published 2026)
Description: A security issue exists within ArmorStart® LT that can result in a denial-of-service condition. During execution of the Achilles Comprehensive grammar tests, the device reboots unexpectedly, causing the Link State Monitor to go down for several seconds.

Which CVSS v3 base severity does this CVE record carry?
```

## 17. CVE-2026-14621 (train): gold = Low (CVSS v3 base score 0.1-3.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-14621

```
CVE record (published 2026)
Description: A vulnerability has been found in FederatedAI FATE up to 2.2.0. This affects the function QueuePushReqStreamObserver.initEggroll of the file java/osx/osx-broker/src/main/java/org/fedai/osx/broker/grpc/QueuePushReqStreamObserver.java of the component OSX Broker. Such manipulation of the argument rollSiteSessionId/dstRole/dstPartyId leads to exposure of data element to wrong session. The attack can be executed remotely. It is indicated that the exploitability is difficult. The exploit has been disclosed to the public and may be used. The pull request to fix this issue awaits acceptance.

Pick the CVSS v3 base severity of the vulnerability described above.
```

## 18. CVE-2024-44911 (train): gold = High (CVSS v3 base score 7.0-8.9)

https://nvd.nist.gov/vuln/detail/CVE-2024-44911

```
CVE record (published 2024)
Description: NASA CryptoLib v1.3.0 was discovered to contain an Out-of-Bounds read via the TC subsystem (crypto_tc.c).

What is the CVSS v3 base severity of this vulnerability?
```

## 19. CVE-2026-69096 (train): gold = High (CVSS v3 base score 7.0-8.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-69096

```
CVE record (published 2026)
Description: OpenWrt luci-app-dockerman (LuCI master and openwrt-25.12 snapshots containing the ucode docker_rpc.uc RPC backend after the JS/ucode conversion) contains an OS command injection vulnerability. The package's read ACL grants broad ubus access to docker.* / docker.container.*, which exposes the docker.container.ttyd_start method even though it performs mutating operations. The run_ttyd handler builds a shell command from the request-controlled id, cmd, and uid fields and passes it to system() without quoting or argv-style execution in the rpcd root context. An authenticated attacker holding only the luci-app-dockerman read ACL can inject shell metacharacters (e.g., in id) to execute arbitrary commands as root via an HTTP POST to /ubus. openwrt-24.10 and openwrt-23.05 do not contain this backend and are not affected; no patched version was known as of the advisory.

Which CVSS v3 severity rating was assigned to this vulnerability?
```

## 20. CVE-2026-53379 (select): gold = Medium (CVSS v3 base score 4.0-6.9)

https://nvd.nist.gov/vuln/detail/CVE-2026-53379

```
CVE record (published 2026)
Description: In the Linux kernel, the following vulnerability has been resolved: media: i2c: ov8856: free control handler on error in ov8856_init_controls() The control handler wasn't freed if adding controls failed, add an error exit label and convert the existing error return to use it.

Which CVSS v3 base severity does this CVE record carry?
```


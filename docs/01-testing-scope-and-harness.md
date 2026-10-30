# Testing scope and test harness

What was tested, what was not, and how the test harness is built. The exact commands and procedures are in `testing-procedures`; results are in `00-summary-reference`.

## 1. Purpose

The aim was a tested reference of which coding harnesses can run against your own gateway with no login to, and no other traffic to, their vendors' services, and how to configure each one. Testing had to answer four questions for every harness:

1. Does it work with a bring-your-own-key (BYOK) endpoint?
2. Does it need a login to its parent service?
3. Can it use an expiring token supplied by a helper, or only a static key?
4. Which hosts does it contact, and can that be switched off?

## 2. Scope

**In scope**

| Area | What was exercised |
|---|---|
| Harnesses | Claude Code CLI and VS Code extension, Codex CLI and VS Code extension, GitHub Copilot CLI, VS Code Copilot Chat, JetBrains AI Assistant in PyCharm, and Copilot Fusion (selection only) |
| Authentication | A helper command that prints a fresh token, a local proxy that substitutes a fresh token for a static key, token refresh during a session, a 401 after expiry, a failing or slow helper, a noisy helper, a token for the wrong audience |
| Configuration | Provider settings, header and model-name settings, and the documented switches for telemetry, updates, feedback, plugins and similar background calls |
| Network behaviour | Every non-local connection each harness opens, by default, with the switches on, and with all non-local traffic refused |
| Credentials at rest | Whether the token was written to any configuration or state folder the tools use |
| Documents | The configuration guides were checked for format and layout |

**Out of scope**

- A real APIM instance and its policies, a web application firewall, response buffering and rate limits. A real Entra token from the Azure CLI was used as the token source in a separate set of runs (read-only; the stand-in checked only structure and expiry in those runs), but no token for a custom API audience was obtained.
- Operating systems other than Windows 11; remote development, containers and WSL.
- Sessions longer than a few minutes, and update checks that happen less often than the observation windows.
- Quality of model output; the test gateway returns a fixed reply.
- Harnesses not listed above (see the candidate list in the summary).

## 3. What counts as a pass

| Test group | Pass condition |
|---|---|
| Authentication | A request from the real tool reaches the gateway with a valid, helper-issued token, and the reply appears in the tool. A token that expires mid-session is replaced without user action, or the failure is clear and fast. |
| Configuration | The tool runs with the documented settings and the resulting request shapes (paths, headers, model names) are recorded. |
| Network behaviour (default) | Every non-local connection is listed with its host. |
| Network behaviour (switches on) | The tool still works, and the number of non-local connections is recorded; zero is the target. |
| Network behaviour (all non-local traffic refused) | The tool still completes a request through the gateway. |
| Credentials at rest | No file in the tools' isolated folders contains the test token. |

A claim in the summary is marked "Confirmed" only when both a documentation statement and an observation agree.

## 4. The test harness

The harness lets a person run the real tools against a stand-in for APIM and observe every request and every connection.

```
  tool under test          token proxy (optional)        mock APIM gateway
  (real binary / IDE)  -->  replaces the key with  -->  validates the token,
                            a fresh token                logs every request,
                                                         returns canned replies
        |                           ^
        | runs                      | runs
        v                           |
   helper script  -->  fake az (mints short-lived test tokens; can fail, run slow,
                                 print noise or use the wrong audience)

   observers:  connection watcher (samples every non-local connection of a process tree)
               deny-all proxy     (refuses every non-local connection and logs the host)
               browser net-log    (names the hosts the VS Code window requests)
   drivers:    command-line runners (isolated config per run)
               Playwright script    (drives the pinned VS Code window)
               window helper        (drives PyCharm, with a focus guard)
```

| Component | Role |
|---|---|
| Mock gateway | Validates a signed token (signature, audience, issuer, expiry) the way an APIM policy would. Serves Anthropic Messages, OpenAI Responses and OpenAI Chat Completions, with streaming and scripted tool calls. Logs path, query, headers (never the raw token) and decoded claims. Faults can be injected: forced status codes, delays. |
| Fake `az` | Stands in for `az account get-access-token`. Mints short-lived tokens and has failure modes (slow, noisy output, failure, wrong audience). The real helper script runs unchanged against it. |
| Helper script | The script described in the helper guide; checks its own output, audience and remaining lifetime. |
| Token proxy | The component described in the proxy guide. |
| Command-line runners | Start each CLI with an isolated configuration folder and a scrubbed environment, so no real account or setting is used, and capture the gateway log slice for that run. |
| Scenario suites | Scripted sets of runs (baseline, fault cases, refresh cases) per tool. |
| Browser driver | Launches a downloaded, pinned VS Code with its own profile and drives its chat panels, so tests do not touch an installed VS Code. |
| PyCharm window helper | Finds the isolated PyCharm windows, takes screenshots, and sends clicks or keys only when PyCharm is the foreground window. |
| Connection watcher | Samples every non-local TCP connection of a process tree, with hostnames from the DNS cache. |
| Deny-all proxy | Simulates an environment where only the gateway is reachable and logs every refused host. |
| Document checks | Word export to PDF, page renders, and the docx schema validator. |

## 5. Isolation and safety rules

- Every tool ran with its own configuration folder (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, a separate home folder for the Copilot CLI, a separate Azure CLI config folder, VS Code `--user-data-dir` and `--extensions-dir`, PyCharm `idea.properties`). Environment variables with the vendors' prefixes were removed from child processes.
- The test tokens, keys and certificates are throwaway and only valid for the stand-in gateway.
- No credential for a real account was entered. Where a test needed a sign-in the account does not provide (a GitHub sign-in, an Entra sign-in), the test was recorded as not run.
- PyCharm input is sent only after the harness verifies PyCharm is the foreground window.
- Only processes started from the test folder were stopped.

## 6. Environment

Windows 11; Python 3.12; Node 24; Claude Code 2.1.311 and 2.1.312; Codex CLI 0.153.2 and extension 26.1021.22027; Copilot CLI 1.0.105; VS Code 1.142.0 (downloaded copy) with Copilot Chat 0.70.0; PyCharm 2026.2.3; Azure CLI 2.91.0 (portable, used only for its not-logged-in behaviour); Playwright (`playwright-core`) 1.64.1.

## 7. Limitations of this method

- The gateway is a stand-in. It does not reproduce APIM policies, rate limits, response buffering or a web application firewall.
- The connection watcher samples every 0.4 seconds; very short connections between samples could be missed. The deny-all proxy catches only traffic that honours proxy settings, so both observers were used together.
- Observation windows were short (typically 40 to 105 seconds), so periodic background calls may not appear.
- Hostnames from sampled addresses were matched through the DNS cache and name lookups; they are reliable for the hosts named but are not a certified list.
- Windows only, single user, versions pinned at the dates in section 6.
- One watcher defect was found and fixed during testing (it matched its own command line and tracked the wrong process); the affected results were rerun.

## 8. Adding a new harness to the suite

1. Install it in an isolated folder with its own configuration location.
2. Write the minimal provider configuration that points it at the stand-in gateway, with the helper or the proxy for the token.
3. Run one prompt and confirm in the gateway log that a valid token arrived and the reply appeared.
4. Run the fault cases (helper fails, noisy helper, wrong audience, token expiry mid-session).
5. Run the connection watcher for the default run, then with the documented switches, then through the deny-all proxy.
6. Search its configuration folders for the test token.
7. Record the result in the summary tables and write the configuration guide in the standard form.

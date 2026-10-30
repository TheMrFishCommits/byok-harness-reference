# Offline-capable coding harnesses: BYOK, authentication and network control

A reference for choosing coding harnesses that can run against your own gateway (an Azure API Management endpoint that validates an Entra ID token) with no login to, and no other traffic to, the vendor's own services.

Date: 2026-10-30. Platform: Windows 11. Versions are listed in section 1. Per-harness instructions are in the separate `config-*` guides listed in section 10.

## 1. Scope and how to read this

Eight harnesses were assessed. "Tested" means the real tool was exercised against a stand-in gateway that validates the token on every request; it does not mean your APIM or a token for your own API was involved. A real Entra token from the Azure CLI was also used as the token source for every harness (section 7). Section 6 states what was tested and what is only documented.

| Harness | Version | Surface |
|---|---|---|
| Claude Code CLI | 2.1.311 | terminal |
| Claude Code VS Code extension | 2.1.312 | VS Code 1.142.0 |
| Codex CLI | 0.153.2 | terminal |
| Codex VS Code extension | 26.1021.22027 (Codex 0.164.0) | VS Code 1.142.0 |
| GitHub Copilot CLI | 1.0.105 | terminal |
| VS Code Copilot Chat | 0.70.0 | VS Code 1.142.0 |
| JetBrains AI Assistant | plugin in PyCharm 2026.2.3 | PyCharm |
| GitHub Copilot Fusion | preview | CLI, VS Code, Copilot app |

Terms: **BYOK** means the tool sends model requests to an endpoint you configure with your own credential. **Parent service** means the vendor's own service (Anthropic, OpenAI, GitHub, JetBrains). **Helper** means a command the tool runs to obtain a fresh token.

## 2. Capability matrix

| Harness | BYOK to a custom endpoint | Login to the parent service needed for BYOK | Can login and telemetry be switched off | Works with only the gateway reachable |
|---|---|---|---|---|
| Claude Code CLI | Yes, via `ANTHROPIC_BASE_URL` (Anthropic Messages API) | No | Yes: documented environment switches; no connection to Anthropic observed with them set | Yes |
| Claude Code extension | Yes, same settings | No | Yes, same switches in its config folder | Yes |
| Codex CLI | Yes, a custom model provider (Responses API) | No | Mostly: documented keys exist; the plugin and app keys stopped all observed calls; no documented single offline switch | Yes |
| Codex extension | Yes, shares `config.toml` | No | Partly: its bundled Codex goes quiet; the extension's own UI and host still call OpenAI hosts | Yes |
| Copilot CLI | Yes, `providers.json` | No | Yes: `COPILOT_OFFLINE=true` stopped all non-provider traffic | Yes |
| VS Code Copilot Chat | Yes, Custom Endpoint | No, but the key must be added through VS Code's own flow | Partly: no GitHub host contacted when signed out; some Microsoft hosts still contacted | Yes |
| JetBrains AI Assistant | Yes, OpenAI-compatible provider (Chat Completions) | No (JetBrains AI subscription optional) | Not fully assessed: none observed with a provider configured | Yes |
| Copilot Fusion | No (routing is in GitHub's cloud) | Yes | No | No |

## 3. Authentication: how the token reaches the gateway

The gateway needs a fresh Entra token on every request. Tokens last about an hour, so a pasted token is not workable.

| Harness | Native command helper | Static key or token | Custom request headers | Practical route for an Entra token |
|---|---|---|---|---|
| Claude Code CLI and extension | Yes: `apiKeyHelper`, re-run on a timer and on a 401 | Yes | Yes: `ANTHROPIC_CUSTOM_HEADERS` | Helper command |
| Codex CLI and extension | Yes: `[model_providers.<id>.auth]` command, refreshed on an interval and on a 401 | Yes | Yes: `http_headers` | Helper command |
| Copilot CLI | Not documented | Yes: `apiKey` or `bearerToken` in `providers.json` (plain text, no variable expansion) | Not documented | Local token proxy |
| VS Code Copilot Chat | No | Yes: key held in secret storage | `requestHeaders` documented | Local token proxy |
| JetBrains AI Assistant | No | Yes: key field | No setting exists | Local token proxy |

Two shared components make this work: a helper script that calls the Azure CLI and checks the token before printing it, and a small local proxy that replaces whatever key a tool sends with a fresh token. Both have their own guides.

## 4. Network behaviour and the switches that stop it

Hosts are those the tool tried when the environment allowed only the gateway. "After switches" is the result with the settings in the matching guide applied.

| Harness | Hosts tried by default | Documented off-switches | After switches |
|---|---|---|---|
| Claude Code CLI | `api.anthropic.com` | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`, `DISABLE_AUTOUPDATER`, and others | No external connection |
| Claude Code extension | `api.anthropic.com`, plus VS Code hosts | Same | No Anthropic connection; VS Code hosts remain |
| Codex CLI | `chatgpt.com`, `ab.chatgpt.com`, `github.com`, `api.github.com` | `analytics.enabled`, `feedback.enabled`, `features.*`, `web_search`, `otel.*` | No external connection with the plugin, app and analytics keys set |
| Codex extension | Same as CLI, plus `chat.openai.com` and an error-reporting host | None documented for the extension | Bundled Codex quiet; extension UI and host still call `chatgpt.com` and the error-reporting host |
| Copilot CLI | `api.github.com`, `api.individual.githubcopilot.com`, `telemetry.individual.githubcopilot.com` | `COPILOT_OFFLINE=true` | No external connection |
| VS Code Copilot Chat | `main.vscode-cdn.net`, `marketplace.visualstudio.com`, `www.vscode-unpkg.net`, `169.254.169.254`, an Application Insights host | `telemetry.telemetryLevel`, `update.mode`, extension update settings; no documented setting for the CDN or metadata calls | Marketplace calls stop; CDN, metadata and one Application Insights attempt remain; no GitHub host |
| JetBrains AI Assistant | None observed with a provider configured | Not assessed | No external connection in 40 to 60 s windows |
| Copilot Fusion | GitHub | None | Not usable |

## 5. Limitations the configurations cause

**Claude Code (CLI and extension).**
- Switching off non-essential traffic also switches off feature-flag fetching, which makes Remote Control, `import`, claude.ai skill sync and a few other features unavailable. Auto-update, feedback and release notes are off.
- The WebFetch domain check still calls `api.anthropic.com` unless `skipWebFetchPreflight` is set; its documentation is inconsistent about the setting. WebSearch has no documented off-switch.
- A static `ANTHROPIC_AUTH_TOKEN` overrides the helper and then fails repeatedly when it expires, so do not set it.
- The extension also sends two probe requests to `<base>/api/hello` at start; a 404 is harmless. The helper needs the Azure CLI on the extension host's PATH.

**Codex (CLI and extension).**
- With plugins, remote plugins and apps off there is no plugin catalog or connectors. Features that rely on a ChatGPT sign-in are outside this configuration.
- `web_search` defaults to a cached OpenAI-maintained index; setting it to `disabled` removes the tool (documented, not tested).
- The tool expects its own model-list shape from `GET /models`; a standard list gives a logged error and generic model metadata, with requests still working.
- The extension's UI and host still attempt calls to OpenAI hosts. They fail harmlessly when blocked, but need a network-level block to be silent.
- The command-backed `auth` block cannot be combined with `env_key`; the default helper timeout of 5 s is too short for the Azure CLI.

**Copilot CLI.**
- Offline mode removes everything that needs GitHub: delegation, the GitHub MCP server and code search. Fusion is not available.
- The provider file is plain text and does not expand variables, so a dynamic token needs the local proxy.
- Models must support tool calling and streaming; the default context window is 128,000 tokens unless set.

**VS Code Copilot Chat.**
- BYOK covers chat and agent use, not inline completions, semantic search or embedding-based features. Titles and similar helpers need a configured utility model, otherwise a notice stays on screen.
- The key must be entered through "Add Models" so it lands in secret storage; a literal key in the JSON file is ignored.
- Fusion and the built-in Claude and Copilot session types are not usable without the vendor sign-in.
- Extension installs depend on the Marketplace; with it blocked, extensions must be installed from files.

**JetBrains AI Assistant.**
- Only the Chat Completions API is used. The URL you enter must include any version prefix (such as `/v1`), because only the endpoint name is appended.
- Models are not assigned automatically: Model Assignment must be set by hand before chat works.
- One prompt triggered about a dozen model calls (one chat call with tools and the rest helper calls), which matters for rate limits and cost at the gateway.
- There is no custom header field and no helper command, so the proxy is required. HTTP/1.1 had to be selected for a plain-HTTP local proxy.
- Choosing a third-party provider shows a data-sharing confirmation. Code completion uses a separate setting.

## 6. What was tested and what is only documented

Status: **Confirmed** = documented and observed. **Documented only** = vendor documentation, not exercised. **Observed only** = seen in testing, not documented. **Contradiction** = documentation or a static code read disagreed with what was observed.

| Harness | Claim | Status |
|---|---|---|
| Claude Code | `apiKeyHelper` supplies a refreshed token, re-run on expiry or 401 | Confirmed |
| Claude Code | The four switches (nonessential traffic, telemetry, error reporting, updater) stop all external connections | Confirmed for the combined set; each switch's share not separated |
| Claude Code | `ANTHROPIC_AUTH_TOKEN` overrides `apiKeyHelper` | Confirmed |
| Claude Code | Model name changes via `ANTHROPIC_DEFAULT_*_MODEL`, `model`, `modelOverrides` reach the gateway | Confirmed; the documentation did not state that `modelOverrides` rewrites the gateway model name |
| Claude Code | Start-up probe of `<base>/api/hello` | Observed only |
| Claude Code | WebFetch domain check goes to `api.anthropic.com` | Documented only |
| Claude Code | WebSearch cannot be disabled | Documented only (no switch found) |
| Claude Code extension | `apiKeyHelper` from `settings.json` is honoured without extension settings | Confirmed (the documentation was silent) |
| Codex CLI | Command-backed `auth` with refresh interval and 401 re-run | Confirmed |
| Codex CLI | Plugin, app and analytics keys stop external calls | Confirmed for the combined set; documentation does not say the plugin keys stop start-up traffic |
| Codex CLI | `GET /models` response shape mismatch causes a logged error | Observed only |
| Codex CLI | A single offline switch exists | Documented as absent |
| Codex extension | Shares `config.toml` with the CLI | Confirmed |
| Codex extension | Residual calls to OpenAI hosts and an error-reporting host after the keys | Observed only |
| Copilot CLI | BYOK needs no GitHub login | Confirmed |
| Copilot CLI | `COPILOT_OFFLINE=true` limits traffic to the provider | Confirmed (no external connection) |
| Copilot CLI | BYOK without offline mode still sends telemetry to GitHub | Confirmed |
| Copilot CLI | Dynamic token command in `providers.json` | Not documented; not tested |
| Copilot Fusion | Routing runs in GitHub's cloud; not usable without GitHub | Confirmed (signed-out request reached GitHub and was rejected; the model name used came from related documentation) |
| Copilot Fusion | Local-model setting in VS Code works without a GitHub sign-in | Contradicted for the signed-out case: with the local-model and Fusion settings both on, the model picker offered only "Sign in to see available models", with no Fusion and no local models. Behaviour once signed in was not tested |
| VS Code Copilot Chat | BYOK works without a GitHub sign-in | Confirmed, with a condition the documentation omits: the key must be added through the UI |
| VS Code Copilot Chat | `telemetry.telemetryLevel: off` stops usage data | Documented; one Application Insights connection attempt was still observed |
| VS Code Copilot Chat | Remote chat configuration and metadata probes | Observed only (no documented setting) |
| VS Code Copilot Chat | `azure` provider signs in with Entra when no key is set | Documented in the manifest only; not run |
| JetBrains | BYOK needs no JetBrains AI subscription | Confirmed |
| JetBrains | Key sent as `Authorization: Bearer` | Observed only; a static code read agreed |
| JetBrains | URL gets a `/v1` prefix added | Contradiction: a static code read said so; observation showed none is added |
| JetBrains | Model assignment is manual | Confirmed |
| JetBrains | No header or helper setting exists | Observed only |
| All | A real Entra token from the Azure CLI works as the token source | Confirmed for every harness above against the stand-in gateway (see section 7): about 1.2 s per token, about 2,400 characters, accepted by all tools. The stand-in checked only structure and expiry in this mode |
| All | A token for your own API audience, and your APIM policies | Not tested |
| Azure MCP | The server never calls a language model | Confirmed: capabilities are `tools` and `logging`, and it sent no requests of its own |
| Azure MCP | `--read-only` allows no write operations | Confirmed: documented, and the tool list fell from 426 to 235 with no destructive tools |
| Azure MCP | `AZURE_MCP_COLLECT_TELEMETRY=false` disables telemetry | Partly contradicted: one telemetry attempt and a metadata probe remained until `AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT=false` was also set |
| Azure MCP | Pinning `AZURE_TOKEN_CREDENTIALS` limits the credential chain | Confirmed for the Azure CLI credential: no browser opened and the failure named the credential. The other credentials were not exercised |
| Azure MCP | Honours proxy settings | Observed only; not documented |
| Azure MCP | Tool calls with real Azure credentials | Not tested |

## 7. Main findings

1. Every assessed harness except Fusion can run against a custom endpoint with no login to its parent service.
2. Two harnesses accept a command helper natively (Claude Code and Codex). The other three need the local token proxy for an expiring token.
3. By default every harness tries to reach its vendor's hosts at start-up or in the background. For the terminal tools these calls can be switched off completely; for the VS Code and JetBrains surfaces some calls remain or were only checked over short windows.
4. A bad token or a failing helper makes the tools retry hard: extra text on the helper's output broke both tools (every request was rejected), and a wrong-audience token made Claude Code retry for over 90 seconds, until the helper began checking its own output.
5. Several documented behaviours were wrong or incomplete in practice (sections 5 and 6), so each guide states settings, not assumptions.
6. A real Entra token worked as the token source for all of the tools: Claude Code and Codex (CLI and VS Code extension), Copilot CLI, VS Code Copilot Chat and JetBrains. A token for the Azure Resource Manager scope took about 1.2 seconds to fetch with the Azure CLI, was about 2,400 characters (three times the size of the stand-in tokens) and lasted about 80 minutes. All tools accepted the larger header, and Codex's default 5-second helper timeout was enough at that speed.
7. The `aud` value depends on the API's token version: the Azure Resource Manager token was a version 1.0 token with `aud` `https://management.azure.com`, no trailing slash. A token for your own API may carry an `api://` URI (version 1) or the client ID (version 2), so the helper accepts a list of audiences and the guides tell you to read the value from a real token.

## 8. Tool servers: the Azure MCP server

The Azure MCP server is a tool server, not a harness. A harness that supports MCP can register it to read Azure resources with the signed-in user's identity.

| Question | Finding |
|---|---|
| Does it use a language model, local or hosted? | No. It declares only `tools` and `logging` capabilities and never asks the client for a completion. The model is the harness's own, so a local or private model works if the harness supports MCP tools and the model supports tool calling |
| What authentication does it need? | Azure credentials, not a vendor login. It tries a chain (environment, Visual Studio, VS Code, Azure CLI, Azure PowerShell, Azure Developer CLI, interactive browser). Pin one with `AZURE_TOKEN_CREDENTIALS` to stop a browser opening. The Azure CLI on the PATH must print only JSON |
| Can it be read-only? | Yes. `--read-only` took the full tool list from 426 to 235 and removed all 139 destructive tools |
| What does it contact by default? | Two Application Insights ingestion hosts and the instance-metadata address. With both `AZURE_MCP_COLLECT_TELEMETRY=false` and `AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT=false` it attempted nothing; one switch alone left an attempt |
| Other external endpoints | Four default tools (`documentation`, `azd`, `foundry`, `arm`) forward to remote services; `--disable-proxy-tools` removes them. In `--mode all` it contacted Entra sign-in and Microsoft Learn at start-up |
| Real calls | Documented to use Entra sign-in, Azure Resource Manager and each service's own data-plane host; not observed, because no real-credential call was made |
| Private endpoints | The local server calls Azure from your machine, so that machine needs a path to the private endpoints. An HTTP transport with an outgoing-auth strategy is documented for hosting it inside the private network. Whether its request-forgery protections block private addresses is not documented |
| Proxies | It honoured `HTTPS_PROXY` and `NO_PROXY` |
| Harness support | Claude Code, Codex and Copilot CLI (offline, no GitHub login) each ran a tool call through the harness, up to Azure's "no credentials" answer. Codex lists MCP tools only from its second model request, under a tool group named `mcp__azure`. VS Code registered the server, started it, and ran a tool through Copilot Chat (signed out, BYOK model; the call returned a failure with no Azure sign-in). JetBrains registered it (Settings page, project level) and ran a tool from AI Assistant chat, which returned the server's own argument-validation error because the scripted call had no arguments |

Tested without a sign-in only; a real-credential result is not available. See `config-azure-mcp-server`.
## 9. Attributes and harnesses worth adding

Attributes that would make this reference more complete:

1. Wire API formats supported (Chat Completions, Responses, Messages) and whether they are selectable.
2. Streaming and tool-calling requirements on the endpoint, and context-window configuration.
3. Custom static headers and dynamic header or token commands.
4. Credential storage at rest (plain-text file, environment variable, operating-system secret store) and variable expansion.
5. Proxy support (`HTTPS_PROXY`, `NO_PROXY`), custom certificate authorities and client certificates for TLS-inspecting networks.
6. Model discovery behaviour and the response shape expected.
7. Configuration scopes and precedence, and whether a repository can override the endpoint.
8. Enterprise policy controls to enforce no-egress across a fleet.
9. Install and update channel, and offline installation.
10. Side features with their own traffic: web search or fetch, remote tool servers, connectors, cloud tasks, remote control, session sync.
11. Model calls per user prompt, for gateway rate limits and cost.
12. Data sent to the vendor and local data at rest (transcripts, caches, retention controls).
13. Behaviour on endpoint or helper failure (retries, timeouts).
14. Operating systems supported, and remote or container development.
15. Licence and cost, including whether a paid seat is needed for BYOK.
16. Observability: whether the tool can emit telemetry to your own collector.

Candidate harnesses not yet assessed (none were tested): Cline, Roo Code, Kilo Code, Continue, Aider, OpenCode, Goose, Gemini CLI, Qwen Code, Cursor, Windsurf, Zed, Amazon Q Developer, and the agents bundled in JetBrains AI Assistant (Claude Agent, Codex, Copilot, Junie), which the JetBrains settings page lists as needing their own activation.

## 10. Documents in this set

- `00-summary-reference` (this document)
- Configuration guides, one per harness, each stand-alone (it carries any script or proxy it needs as an appendix) and each with a data record: `config-claude-code-cli`, `config-claude-code-vscode`, `config-codex-cli`, `config-codex-vscode`, `config-copilot-cli`, `config-vscode-copilot-chat-byok`, `config-jetbrains-ai-assistant`
- Component guides, also stand-alone: `config-entra-token-helper`, `config-local-token-proxy`, and the tool-server guide `config-azure-mcp-server`
- `testing-scope-and-harness`: what was covered and how the test harness is built
- `testing-procedures`: the exact procedures

## 11. Not covered

- Your APIM policies, web application firewall and streaming behaviour. A real Entra token was used as the token source (Azure Resource Manager scope, read-only), but no token for your own API audience was obtained, because that needs an app registration.
- Long sessions, update checks that occur less often than the short observation windows, and operating systems other than Windows.
- Azure MCP tool results with real credentials (every harness call so far ended at the server's missing-credentials or missing-argument answer).
- JetBrains traffic with no provider configured beyond an idle window; Fusion with other model identifiers; the `azure` provider's own Entra sign-in in VS Code.


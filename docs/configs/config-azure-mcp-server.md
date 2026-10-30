# Azure MCP Server: read-only Azure access from a harness with no vendor network access

## Summary

The Azure MCP Server (`@azure/mcp`) is a tool server for the Model Context Protocol. It gives a coding harness tools to read (and, unless restricted, change) Azure resources. It runs as a local process over standard input and output, signs in to Azure with your Entra credentials, and calls Azure's own endpoints. It does not host or call any language model: it declares only `tools` and `logging` capabilities and never asks the client for a model completion. The model is whatever the harness is configured to use, including a local or private model, provided the harness supports MCP tools and the model supports tool calling.

This guide covers starting the server read-only, switching off its telemetry and its calls to external services, choosing how many tools to expose, and registering it in each harness.

## Applies to

| Item | Value |
|---|---|
| Product | Azure MCP Server, npm package `@azure/mcp`, platform binary `azmcp.exe` |
| Version covered | 4.0.0-beta.3 (the `latest` tag when this was written); the documentation describes a 2.0 general availability line |
| OS | Windows x64 (other installs are documented: .NET tool, `uvx`, container, MCP bundle) |
| Install size | about 120 MB (single platform binary) |
| Configuration | Command-line options and environment variables, set in each harness's MCP server entry |
| Scope | Per user and per harness; each harness has its own MCP configuration location |

## Prerequisites

1. Node.js with `npm`, or another documented install route.
2. For the Azure CLI credential: the Azure CLI installed, `az login` completed, and `az` on the PATH of the process that starts the server. A harness started from a desktop shortcut may not have it; give the server entry an explicit `PATH` or use a different credential.
3. Azure role-based access on the resources you want to read. The server uses your identity; it adds no permissions.
4. Network access from the machine to Microsoft Entra sign-in and to the Azure endpoints for the services you query (see "Network behaviour").

## Install

```powershell
mkdir azure-mcp; cd azure-mcp
npm init -y
npm install @azure/mcp@latest
# binary: node_modules\@azure\mcp-win32-x64\dist\azmcp.exe
```

`npx -y @azure/mcp@latest server start` runs the same server without a local install and downloads the package on first use.

## Authentication: how the server gets a token

| Aspect | Detail |
|---|---|
| Method | A chain of credential providers; the first that succeeds is used (documented). Order: optional broker, environment variables, Visual Studio, Visual Studio Code, Azure CLI, Azure PowerShell, Azure Developer CLI, interactive browser |
| Pin one credential | `AZURE_TOKEN_CREDENTIALS=AzureCliCredential` (or another credential name). Pinning also prevents the interactive browser step from opening |
| Production profile | `AZURE_TOKEN_CREDENTIALS=prod` restricts the chain to environment, workload identity and managed identity, with no interactive step |
| Service principal | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` |
| Managed identity | `AZURE_CLIENT_ID` selects a user-assigned identity; otherwise the system-assigned one is used |
| OS broker | `AZURE_MCP_ONLY_USE_BROKER_CREDENTIAL=true` uses the Windows account broker |
| Tenant and subscription | Tools take an optional tenant; the subscription falls back to the Azure CLI default or `AZURE_SUBSCRIPTION_ID` |
| Passing a token in | Not documented for the local (stdio) server. The HTTP transport accepts inbound Entra bearer tokens and has `--outgoing-auth-strategy` (`UseOnBehalfOf` or `UseHostingEnvironmentIdentity`) |
| Sovereign clouds | `--cloud AzureChinaCloud` or `AzureUSGovernment`, or `AZURE_CLOUD` |
| Failure behaviour | A tool call returns a JSON error with status 401 and a message naming the credential that failed (for example "Azure CLI not installed" when `az` is not on the PATH). No browser opens when a credential is pinned |

The Azure CLI credential runs `az account get-access-token` and parses its JSON output, so the `az` found on the PATH must print only JSON. A wrapper that prints anything else makes the credential fail with a JSON parsing message.

## Starting the server

```text
azmcp server start [options]
```

| Option | Default | Effect |
|---|---|---|
| `--read-only` | off | Removes write operations. In full mode this took the tool list from 426 to 235 tools and removed all 139 tools marked destructive |
| `--mode <name>` (`namespace`, `all` or `single`) | `namespace` | `namespace`: one tool per service (68 tools). `all`: every tool individually (426, or 235 with `--read-only`). `single`: one tool named `azure` that routes to all services |
| `--namespace <name>` | all | Expose only chosen services, for example `storage` (4 tools). Repeatable. Cannot be combined with `--tool` |
| `--tool <name>` | none | Expose only named tools. Switches to `all` mode |
| `--disable-proxy-tools` | off | Removes tools that forward to external services: `documentation`, `azd`, `foundry` and `arm` (68 tools become 64) |
| `--transport <name>` | `stdio` | `stdio` for a local process; an HTTP transport is documented for hosting the server centrally |
| `--cloud <name>` | `AzureCloud` | Sovereign cloud selection |
| `--disable-caching` | off | Always fetch fresh data |
| `--debug` | off | Verbose logging to standard error |
| `--learn` | off | Lists commands and parameters without running any Azure operation |
| `--dangerously-disable-elicitation` | off | Skips user confirmation for high-risk results such as secrets. Leave off |
| `--dangerously-disable-ssrf-protections-by-namespace <namespace or ALL>` | off | Disables the server's request-forgery protections for the namespace. Leave off unless you have confirmed you need it |
| `--dangerously-disable-http-incoming-auth` | off | Removes authentication on the HTTP transport. Leave off |
| `--dangerously-write-support-logs-to-dir <dir>` | off | Writes detailed logs that may contain sensitive data. Leave off |
| `--dangerously-disable-retry-limits` | off | Removes retry and timeout bounds. Leave off |

Recommended command for a read-only, low-egress setup:

```text
azmcp.exe server start --read-only --disable-proxy-tools
```

with the environment variables in the next section.

## Disabling telemetry and background network calls

| Setting | Where | Value | Default | Effect |
|---|---|---|---|---|
| `AZURE_MCP_COLLECT_TELEMETRY` | environment of the server | `false` | on | Documented as disabling all telemetry. On its own, one connection attempt to a telemetry endpoint and a metadata-service probe remained |
| `AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT` | environment of the server | `false` | on | Microsoft's own telemetry stream. With this and the setting above both `false`, no external connection was attempted at start-up |
| `AZURE_TOKEN_CREDENTIALS` | environment of the server | credential name or `prod` | chain | Limits which credentials are tried; stops the browser step |
| `--disable-proxy-tools` | command line | present | proxy tools on | Removes the four tools that forward to remote services |
| `--read-only` | command line | present | off | Safety control, not a network control |

Telemetry sends to Application Insights (documented: one stream to your own Application Insights through `APPLICATIONINSIGHTS_CONNECTION_STRING` if set, and one to Microsoft).

## Network behaviour with this configuration

| Situation | Hosts contacted |
|---|---|
| Default start (namespace mode, telemetry on) | Two regional Application Insights ingestion hosts (`*.in.applicationinsights.azure.com`) and the instance-metadata address `169.254.169.254` |
| Start with both telemetry variables `false` and `--disable-proxy-tools` | None observed at start-up and on a failed tool call |
| `--mode all` start | `login.microsoftonline.com` (several attempts) and `learn.microsoft.com` at start-up, because the proxy tools are initialised |
| Proxy tools (`documentation`, `azd`, `foundry`, `arm`) when called | `documentation` goes to Microsoft Learn. The documentation also lists remote Azure Resource Manager and Foundry MCP endpoints (`mcp.management.azure.com`, `mcp.ai.azure.com`); their use by `arm` and `foundry` was not observed |
| A real tool call (documented, not observed) | `login.microsoftonline.com` for the token, `management.azure.com` for resource operations, and the data-plane host of each service queried (for example Key Vault or Storage), with sovereign-cloud equivalents under `--cloud` |
| Install | The npm registry (or NuGet, PyPI or the container registry for other routes) |

Proxy settings: the server honours `HTTPS_PROXY`, `HTTP_PROXY` and `NO_PROXY` (its connections went through a configured proxy). Custom certificate authorities are not documented.

## Registering the server in a harness

Use the same command and environment in every harness. Examples:

Claude Code (`~/.claude.json`, or `claude mcp add`):

```json
{
  "mcpServers": {
    "azure": {
      "type": "stdio",
      "command": "C:\\path\\to\\azmcp.exe",
      "args": ["server", "start", "--read-only", "--disable-proxy-tools"],
      "env": {
        "AZURE_MCP_COLLECT_TELEMETRY": "false",
        "AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT": "false",
        "AZURE_TOKEN_CREDENTIALS": "AzureCliCredential"
      }
    }
  }
}
```

Claude Code defers loading the definitions of a large MCP tool set until the model searches for them, so the model may not see the tools in its first request. `ENABLE_TOOL_SEARCH=false` in the settings `env` loads them directly. Allow the tools you want with `--allowedTools mcp__azure__subscription_list`. `claude mcp list` should show the server as connected.

Codex CLI and extension (`config.toml`):

```toml
[mcp_servers.azure]
command = 'C:\path\to\azmcp.exe'
args = ['server', 'start', '--read-only', '--disable-proxy-tools']
env = { AZURE_MCP_COLLECT_TELEMETRY = 'false', AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT = 'false', AZURE_TOKEN_CREDENTIALS = 'AzureCliCredential' }
```

`codex mcp list` shows the server as enabled. Use a Windows path for `command` (a Git Bash style path such as `/c/Users/...` is listed but never starts). Codex loads the server's tools after the server has started, not in the first model request of a run: they then appear to the model as one tool group named `mcp__azure`, and a call carries that group name together with the tool name. Set `startup_timeout_sec` (for example 60) if the first start is slow. A tool call through Codex reached the server and returned Azure's "credentials not found" JSON when no Azure sign-in was available.

GitHub Copilot CLI (`~/.copilot/mcp-config.json`):

```json
{
  "mcpServers": {
    "azure-mcp": {
      "type": "local",
      "command": "C:\\path\\to\\azmcp.exe",
      "args": ["server", "start", "--read-only", "--disable-proxy-tools"],
      "env": {
        "AZURE_MCP_COLLECT_TELEMETRY": "false",
        "AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT": "false",
        "AZURE_TOKEN_CREDENTIALS": "AzureCliCredential"
      },
      "tools": ["*"]
    }
  }
}
```

Tools appear to the model as `azure-mcp-<tool>` and are loaded into the model request. Approve them with `--allow-tool 'azure-mcp'`. This works in offline BYOK mode with no GitHub login.

VS Code: define the server in `.vscode/mcp.json` for one workspace, or in the user-level `mcp.json` (command **MCP: Open User Configuration**), with `servers` as the root key and the same `command`, `args` and `env`. A server defined under the `mcp` user setting is listed too, and VS Code 1.142 copied it into the user-level `mcp.json`. Run **MCP: List Servers**, choose `azure` and choose **Start Server**: the list then shows `azure` as Running, the server's output log reports its tool count (64 with `--read-only --disable-proxy-tools`), and this works signed out of GitHub. A tool call from Copilot Chat with a custom-endpoint model, signed out of GitHub, reached the server (the tools reach the model named `mcp_azure_mcp_ser_<tool>`, and Copilot Chat may offer only part of the 64); it returned a failure when no Azure sign-in was available. Read-only tools ran without a confirmation prompt. Leave `chat.tools.global.autoApprove` off.

JetBrains AI Assistant (PyCharm 2026.2): open Settings, Tools, AI Assistant, Model Context Protocol (MCP), and choose Add server. The dialog has STDIO and HTTP tabs and a JSON box that takes the same `mcpServers` object as the other tools (`command`, `args`, `env`), plus a working directory and a server level. Global saves to `~/.ai/mcp/mcp.json`; Project saves to `.ai/mcp/mcp.json` in the project, which keeps the server out of your home folder. Use a Windows path for `command`. After Add server the row shows a disabled status until you choose Apply; then the status turns to a green check and the server process starts (it was seen running). "Automatically enable new and changed MCP servers" is off by default. Do not use "Import from Claude" unless you want it to read your Claude configuration. In AI Assistant chat the server's tools are offered to the model with the IDE's own tools (99 tools in the request in the version covered), and a tool call from the chat reached the server and returned its answer to the model. Keep the window open for a few seconds after Apply: if PyCharm is stopped at once, the project file can be left empty and the server is gone at the next start. Do not confuse this page with Settings, Tools, MCP Server, which is the IDE's own server for external clients.

## Models, private models and private endpoints

| Question | Answer |
|---|---|
| Does the server use a model? | No. It declares only `tools` and `logging`. It never requests a model completion from the client |
| Hosted or local models | Either, in the harness. The server is independent of the model. The harness must support MCP tools, and the model and endpoint must support tool calling (Copilot CLI documents tool calling and streaming as requirements; JetBrains has a "Tool calling" checkbox on its OpenAI-compatible provider) |
| Number of tools | 68 in the default mode, up to 426 in `all` mode. Fewer tools means less model context. Use `--namespace`, `--tool` or `--mode single` for small or local models |
| Private endpoints | The stdio server runs on your machine and calls Azure from there, so the machine needs a network path to the private endpoints (VPN, ExpressRoute, private DNS). To run it inside the private network instead, use the HTTP transport on a host in that network with `--outgoing-auth-strategy` |
| Request-forgery protections | The server has protections that can be disabled per namespace (`--dangerously-disable-ssrf-protections-by-namespace`). Whether they block private addresses is not documented; check before relying on private-address targets |
| Proxies | `HTTPS_PROXY` and `NO_PROXY` are honoured |
| Sovereign clouds | `--cloud` or `AZURE_CLOUD` |

## Effects and limits of this configuration

- Read-only mode removes tools that create, change or delete resources. Reading secrets or connection strings still triggers a confirmation prompt unless elicitation is disabled.
- Removing the proxy tools removes the documentation search, Azure Developer CLI, Foundry and Azure Resource Manager remote tools.
- Telemetry off means Microsoft receives no usage data from the server; it does not change what Azure itself logs about your requests.
- The server uses your identity. Anything your account can read, the model can read through it.
- The Azure documentation describes the local server as intended for developer use within an organisation.

## Confirming it works

1. In the harness, list MCP servers (`claude mcp list`, `codex mcp list`, or `/mcp show` in Copilot CLI) and confirm `azure` is connected or enabled.
2. Ask the model to list your subscriptions, or call `subscription_list`.
3. Expected result when signed in: your subscriptions (or an empty list if the account has none). When not signed in: a JSON error with status 401 naming the credential that failed.
4. To confirm nothing leaves the machine at start-up, start the server with both telemetry variables `false` and `--disable-proxy-tools` and watch outbound connections.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| 401 "Azure CLI not installed" | `az` is not on the PATH of the process that started the server. Add it to the server entry's `PATH` |
| 401 "AzureCliCredential authentication failed ... invalid start of a value" | The `az` on the PATH printed something other than JSON (a wrapper or banner). Use the real Azure CLI |
| A browser window opens | The chain reached the interactive browser step. Pin `AZURE_TOKEN_CREDENTIALS` |
| The model does not see the Azure tools (Claude Code) | Tool definitions are deferred. Set `ENABLE_TOOL_SEARCH=false` or let the model search for them |
| Connections to Application Insights hosts or `169.254.169.254` | Both telemetry variables must be `false` |
| Connections to `learn.microsoft.com` or `login.microsoftonline.com` at start-up | `--mode all` or the proxy tools are active. Add `--disable-proxy-tools` |
| The model picks poor tools | Too many tools. Use `--namespace` or the default namespace mode |

## References

- Azure MCP Server documentation: https://learn.microsoft.com/azure/developer/azure-mcp-server/
- Azure MCP Server source and authentication notes: https://github.com/microsoft/mcp
- Azure MCP authentication troubleshooting: https://aka.ms/azmcp/auth and https://aka.ms/azmcp/troubleshooting
- Model Context Protocol: https://modelcontextprotocol.io/


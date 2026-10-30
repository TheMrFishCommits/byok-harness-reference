# BYOK harness reference

A tested reference of which coding harnesses can run against your own gateway (an Azure API Management endpoint that validates an Entra ID token) with no login to, and no other traffic to, the vendor's own services. It covers Claude Code, Codex, GitHub Copilot CLI, VS Code Copilot Chat and JetBrains AI Assistant, and records how to configure each one.

Start with [`docs/00-summary-reference.md`](docs/00-summary-reference.md).

## What is here

| Path | Contents |
|---|---|
| `docs/00-summary-reference` | The reference tables: capability matrix, token and helper support, network behaviour and switches, limitations each configuration causes, tested versus documented, attributes and harnesses worth adding |
| `docs/01-testing-scope-and-harness` | What was and was not tested, and how the test harness is built |
| `docs/02-testing-procedures` | The exact procedures, step by step |
| `docs/configs/config-*` | One stand-alone configuration guide per harness, plus guides for the token helper, the local token proxy and the Azure MCP server. Each guide is a `.md`, a `.docx` and a `.json` data record, and needs no other document |
| `harness/` | The test harness: mock gateway, fake `az`, runners, scenario suites, token proxy, egress tools, VS Code and PyCharm drivers |
| `evidence/` | `RESULTS.md` (results by test group) and `LOG.md` (chronological notes) |

Every document is provided as Markdown and Word.

## The configuration guides

The guides under `docs/configs/` are written as instructions: they do not describe how the tests were run. Each is stand-alone: where a harness needs the token helper script or the local proxy, the guide carries it as an appendix. Each has a matching `.json` record with the same fields (supported APIs, token method, telemetry controls with defaults and evidence type, configuration snippets, hosts contacted by default and after configuration, limits, verification status), so they can be loaded into a database.

| Guide | Harness |
|---|---|
| `config-claude-code-cli`, `config-claude-code-vscode` | Claude Code CLI and VS Code extension |
| `config-codex-cli`, `config-codex-vscode` | Codex CLI and VS Code extension |
| `config-copilot-cli` | GitHub Copilot CLI |
| `config-vscode-copilot-chat-byok` | VS Code Copilot Chat with a custom endpoint |
| `config-jetbrains-ai-assistant` | JetBrains AI Assistant |
| `config-entra-token-helper` | The script that prints a fresh Entra token, with its setup and checks |
| `config-local-token-proxy` | Local proxy that substitutes a fresh token for a static key, with source |
| `config-azure-mcp-server` | Azure MCP Server (a tool server that harnesses register; read-only, telemetry off, harness registration) |

## The test harness

```text
harness/
  gateway.py            mock APIM: validates tokens, logs requests, serves canned replies
  fakeaz/               stand-in for `az account get-access-token`
  get-apim-token.ps1    the helper script under test
  proxy.py              local token proxy
  run_*.py, suite_*.py  runners and scenario suites
  egress_watch.py       connection watcher for a process tree
  egress_deny_proxy.py  deny-all proxy that logs refused hosts
  vscode-test/          Playwright driver for a pinned VS Code
  jetbrains/jb_ui.ps1   PyCharm window helper with a foreground guard
  doc-qa/               helpers used to render documents for checking
```

Setup, in short (the procedures document has the details):

```powershell
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r harness\requirements.txt
.\.venv\Scripts\python.exe harness\gateway.py
```

## Things to know

- **Stand-in gateway.** The results come from a mock gateway, not a real Entra tenant or APIM, so policies, rate limits, response buffering and a web application firewall are untested.
- **Windows 11 only,** with the versions listed in the summary.
- **Throwaway keys.** The signing key for the mock tokens is created on first run and is not part of this repository.
- **Absolute paths.** Some scripts, scenario configs and `idea.properties.example` contain absolute Windows paths from the machine where they were written, with the user name replaced by `USER` (search for `Users\USER`, `Users\\USER` and `Users/USER`). Adjust them before running.
- **Screenshots and logs are not included.** The test runs produced screenshots and logs that are not part of this repository.
- Not a security review of any product.


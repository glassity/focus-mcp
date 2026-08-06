# Security Policy

Security fixes ship as a new release; older releases are not patched. Please
reproduce against the latest release before reporting.

## Reporting a vulnerability

Email **security@glassity.cloud**. Do not open a public GitHub issue for a
suspected vulnerability.

Please include:

- What you found and why you believe it is a security issue.
- Steps to reproduce, ideally with the exact prompt or SQL sequence.
- The image tag or commit you ran, your MCP client, and how the server was
  deployed (Docker or source checkout).
- Any logs or transcript output, with credentials redacted.

We will acknowledge your report and keep you updated as we investigate. Please
give us a reasonable window to ship a fix before disclosing publicly.

## Trust model

Two things are worth knowing before you report:

- `execute_query` deliberately accepts arbitrary SQL from the MCP client. An
  AI assistant writing hostile SQL is contained by what the process can reach:
  the mounted data (read-only in every documented configuration) and the
  object-store credentials you provided. Reports about SQL reaching beyond
  that boundary are in scope; "the assistant can run SELECT" is by design.
- Object-store credentials are read only inside the server process and are
  never returned through MCP tool responses. A path that leaks them to the
  client is in scope.

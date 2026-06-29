# DOL-X agent notes

This file is automatically included in every Cursor agent request for this project. Keep it short, plain, and safe for third party BYOK gateways.

DOL-X is the user's personal Degrees of Lewdity integration package based on DoL-Lyra. It uses a Python build system, while full signed APK builds are handled by GitHub Actions. Local work is for configuration checks, focused tests, documentation, and git inspection.

At the start of DOL-X work, recover context from the Nocturne memory boot entry, then the DOL-X project memory, then the newest session status document under docs. If old chat context conflicts with memory or session status, trust memory and session status first.

The project follows an upstream friendly strategy. Keep Lyra core behavior aligned with upstream when possible. DOL-X independently owns its mod matrix, version locks, project docs, tools, and tests. Do not confuse this repository with the separate DoL-XFox project.

The user is learning Vibe Coding and does not have a code background. Technical execution is the agent's job. Explain key decisions in Chinese, including why a choice is safer, what it gives up, and what risks remain. Ask before destructive, remote, credential bearing, or high impact actions.

WAF safety rule: never expand this file with command examples, code snippets, shell syntax, web markup, template macro text, encoded payloads, secrets, or long diagnostic dumps. Put detailed procedures in docs and read them only when needed.

If BYOK or Cloudflare returns a blocked request for this project, first suspect automatically included project guidance files. Temporarily moving this file out of automatic inclusion is an acceptable emergency recovery step. Record the conclusion in memory and session status instead of making this file large again.

Commit hygiene matters. Do not stage everything blindly. Do not commit secrets, local rescue backups, reverse engineering notes, runtime capture results, generated build artifacts, or files that only exist to recover from a local WAF incident.

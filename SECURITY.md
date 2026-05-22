# Security

This project ships a local Docker Compose stack intended for **single-user
development on the same host** that runs it. It is not designed to be exposed
to a network.

## Threat model (what this is and isn't)

In scope:

- The Docker Compose stack runs on `localhost`. By default only ports `3000`
  (Open WebUI), `8000` and `9000` (OVMS) are published on the host.
- `SearXNG` and `Pipelines` are only reachable from inside the Docker network.
- `.env` is git-ignored and never committed; `.env.example` carries only
  placeholders.

Out of scope:

- Exposing this stack on a public IP, a LAN with untrusted devices, or behind a
  reverse proxy without authentication. If you do that, you own the resulting
  surface area: enable `OPENWEBUI_AUTH=True`, rotate `PIPELINES_API_KEY`, and
  put a real auth layer in front of OVMS.
- Hardening the conversion container that downloads HuggingFace weights — it
  runs as root inside a one-shot container and then exits.

## Secrets handling

The two secrets you may end up with on disk are:

- `HF_TOKEN` (HuggingFace read token) — lives in `.env`.
- `PIPELINES_API_KEY` (shared key between Open WebUI and Pipelines) — also in
  `.env`.

**If either ends up in a public place** (a screenshot you posted, a log file you
shared, a commit you pushed by mistake, an issue here on GitHub), treat it as
leaked:

- For `HF_TOKEN`: rotate immediately on
  <https://huggingface.co/settings/tokens>. The token is read-only by default,
  but a leaked token still lets a third party download under your account.
- For `PIPELINES_API_KEY`: change it in `.env` and restart the stack
  (`docker compose up -d --force-recreate`).

## Reporting a security issue

If you find a security problem in this repo (not in OVMS / Open WebUI / SearXNG
upstream — report those to their maintainers), open a **private** issue:

1. Go to <https://github.com/cartesiosson/openvino-agent-stack/security/advisories/new>.
2. Describe the issue and steps to reproduce.

Or contact the maintainer directly. Please do **not** open a public issue with
exploit details until a fix is published.

## No warranty

This project is published under the [MIT License](LICENSE). The license
explicitly disclaims any warranty of merchantability, fitness for a particular
purpose, or non-infringement. You are responsible for evaluating whether this
stack is appropriate for your use case.

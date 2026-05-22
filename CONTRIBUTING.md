# Contributing

Thanks for considering a contribution. This project is small and pragmatic; the
bar for changes is "does it make the local stack work better on Intel Core Ultra
hardware?".

## Ground rules

- One change per PR. Refactor + feature + docs in the same PR makes review hard.
- Be honest about trade-offs in the PR description. If a change improves one
  number and degrades another, say so.
- No vendor lock-in beyond what's already implicit (OVMS for Intel, Open WebUI
  as the frontend). New backends are welcome as **alternatives**, not
  replacements.

## How to set up a dev environment

1. Fork and clone.
2. Copy `.env.example` to `.env` and add your `HF_TOKEN` if you need it.
3. Convert models:
   ```bash
   ./scripts/export-models.sh
   ```
4. Bring the stack up:
   ```bash
   make up        # or: docker compose up -d
   ```
5. Verify health:
   ```bash
   make health
   ```
6. Run a smoke test:
   ```bash
   make smoke
   ```

The `Makefile` in the repo root collects the common commands.

## Filing issues

Open one of the templates in `.github/ISSUE_TEMPLATE/`:

- **Bug report** — for things that should work and don't. Include `docker
  compose logs ovms --tail=200`, your Windows + WSL versions, RAM allocated to
  WSL, and the output of `ls /dev/dri /dev/dxg` on the host.
- **Feature request** — for new tools, pipelines, model support, etc.

Do **not** paste secrets, tokens or production data in issues. If you suspect
you have leaked an `HF_TOKEN` while reproducing a bug, rotate it on
<https://huggingface.co/settings/tokens> before opening the issue.

## Pull request checklist

- [ ] Branch from `main`, no merge commits (`git rebase main` if needed).
- [ ] One topic per PR.
- [ ] If you touch `docker-compose.yml` or any `graph.pbtxt`, run `make up`
      locally and confirm both models load (`curl http://localhost:8000/v3/models`).
- [ ] If you change docs, both `README.md` and `README.es.md` should stay in
      sync content-wise.
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
      `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `ci:`, etc.

## License

By contributing you agree your changes are licensed under the [MIT License](LICENSE).

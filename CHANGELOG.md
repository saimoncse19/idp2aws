# Changelog

## 0.2.0 (TBC)

First release on PyPI.

- Sign in to a SAML IdP (Google Workspace, Okta, Entra ID) in Chrome, Edge or Playwright's
  Chromium, and save short-lived AWS keys to a profile in `~/.aws/credentials`.
- Show the AWS role page, sorted by account name, on the first login for a profile. Later logins
  use the same role. Use `--pick` to choose again.
- Commands: `setup`, `login` (`--pick`, `--json` for `credential_process`), `run`, `console`,
  `profiles`, and `--version`.
- Config in `~/.idp2aws/config.toml`, with shared settings and optional per-profile overrides.

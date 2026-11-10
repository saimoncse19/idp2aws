# Using idp2aws

This guide tells you how to install idp2aws, configure it, use it every day and fix common
problems.

## What you need

- Python 3.12 or newer.
- Google Chrome or Microsoft Edge. If you cannot install either, idp2aws can use the Chromium
  build that Playwright downloads. idp2aws does not support Firefox or Safari.
- A desktop session. You sign in through a browser window that you can see. So idp2aws does
  not work over plain SSH to a server.
- The start URL of your IdP for AWS. For Google Workspace, it looks like this:

  ```
  https://accounts.google.com/o/saml2/initsso?idpid=XXXXXXXX&spid=YYYYYYYYYYYY&forceauthn=false
  ```

  `idpid` is the Google id of your company. `spid` is the id of the AWS app in Google. Your
  Google Workspace admin can give you both.

## Install

You can install idp2aws in two ways:

- From PyPI, with [pipx](https://pipx.pypa.io) or pip. The steps for each operating system
  follow. pipx puts the `idp2aws` command on your `PATH` and keeps its libraries apart from your
  other Python tools. `pip install idp2aws` also works, but then you manage the virtual
  environment.
- From source, to get the latest code on `main` or to change the code. See
  [Install from source](#install-from-source).

### macOS

1. Install Python 3.12 and pipx:

   ```sh
   brew install python@3.12 pipx
   pipx ensurepath
   ```

2. Open a new terminal, then install idp2aws:

   ```sh
   pipx install --python python3.12 idp2aws
   ```

idp2aws finds Chrome in `/Applications` automatically.

### Linux

These steps are for Debian 12, Ubuntu 24.04 and newer.

1. Install Python and pipx:

   ```sh
   sudo apt install python3.12 python3.12-venv pipx
   pipx ensurepath
   ```

2. Open a new terminal, then install idp2aws:

   ```sh
   pipx install --python python3.12 idp2aws
   ```

3. Install Google Chrome from google.com/chrome.

To use Playwright's Chromium instead of Chrome, do these steps:

1. Install idp2aws with the `playwright` command, then install Chromium and the system libraries
   that it needs:

   ```sh
   pipx install --python python3.12 --include-deps idp2aws
   playwright install chromium
   sudo "$(which playwright)" install-deps chromium
   ```

2. Add `--browser chromium` when you run `idp2aws setup`.

On Fedora, use `sudo dnf install python3.12 pipx` and the Chrome `.rpm`. Playwright
`install-deps` supports only Debian and Ubuntu. So on Fedora, Chrome is the easier choice.

### Windows

1. In PowerShell, install Python and pipx:

   ```powershell
   winget install Python.Python.3.12
   py -3.12 -m pip install --user pipx
   py -3.12 -m pipx ensurepath
   ```

2. Open a new PowerShell window, then install idp2aws:

   ```powershell
   pipx install idp2aws
   ```

Windows includes Edge. If you do not have Chrome, add `--browser msedge` when you run
`idp2aws setup`.

idp2aws keeps its files in `%USERPROFILE%\.idp2aws` and `%USERPROFILE%\.aws\credentials`.

On Windows 11, WSL can show Linux windows on your desktop. So the Linux steps work in WSL.
WSL on Windows 10 has no display. On Windows 10, install idp2aws on Windows.

### Update or remove

```sh
pipx upgrade idp2aws
pipx uninstall idp2aws
```

`pipx uninstall` does not delete `~/.idp2aws` or your keys in `~/.aws/credentials`.

### Install from source

To install the latest code on `main` without a copy of the repository, use pipx with the Git
URL:

```sh
pipx install --python python3.12 git+https://github.com/saimoncse19/idp2aws.git
```

To change the code and use your changes at once, install from a clone. You need Python 3.12 or
newer, as in the steps above.

On macOS and Linux:

1. Clone the repository and install idp2aws in a virtual environment:

   ```sh
   git clone https://github.com/saimoncse19/idp2aws.git && cd idp2aws
   python3.12 -m venv .venv
   .venv/bin/pip install -e .
   ```

2. Put `idp2aws` on your `PATH`:

   ```sh
   ln -s "$PWD/.venv/bin/idp2aws" ~/.local/bin/idp2aws
   ```

   If `~/.local/bin` is not on your `PATH`, add it in `~/.zshrc` or `~/.bashrc`.

On Windows, in PowerShell:

1. Clone the repository and install idp2aws in a virtual environment:

   ```powershell
   git clone https://github.com/saimoncse19/idp2aws.git; cd idp2aws
   py -3.12 -m venv .venv
   .venv\Scripts\pip install -e .
   ```

2. Add the `.venv\Scripts` folder in `idp2aws` to your `PATH`.

With `-e`, idp2aws runs the code in the clone, so a change takes effect the next time you run
it. To use Playwright's Chromium, run `.venv/bin/playwright install chromium` (on Windows,
`.venv\Scripts\playwright install chromium`).

To run the tests and lint, see Development in the
[README](https://github.com/saimoncse19/idp2aws#development).

## Configure idp2aws

Run `idp2aws setup` one time, with your start URL. Put the URL in single quotes, because it
contains `&`.

```sh
idp2aws setup 'https://accounts.google.com/o/saml2/initsso?idpid=XXXX&spid=YYYY'
```

This command creates `~/.idp2aws/config.toml`. The settings at the top apply to all profiles. A
`[profiles.<name>]` table changes settings for one profile:

```toml
start_url = "https://accounts.google.com/o/saml2/initsso?idpid=XXXX&spid=YYYY"
browser = "chrome"
session_hours = 1

[profiles.dev]

[profiles.prod]
role_arn = "arn:aws:iam::123456789012:role/Developer"
session_hours = 4
```

| Setting | Meaning |
| --- | --- |
| `start_url` | The start URL of your IdP for AWS. A profile can use a different URL, for example for a second AWS app. |
| `browser` | `chrome` for Google Chrome, `msedge` for Microsoft Edge, or `chromium` for Playwright's Chromium. |
| `session_hours` | How long the keys last, from 1 to 12. This value cannot be more than the maximum session duration of the role in IAM. |
| `role_arn` | The role that this profile always uses. idp2aws never shows the AWS role page for this profile. |

A profile does not need a table. `idp2aws login <any-name>` works with only the shared
settings. A table does two things:

- It shows the profile in `idp2aws profiles`.
- It lets you change settings for that profile.

To keep the idp2aws files in a different folder, set `IDP2AWS_HOME` to that folder.

## Use idp2aws every day

```sh
idp2aws login dev                  # save keys to profile "dev" in ~/.aws/credentials
aws --profile dev s3 ls            # use the keys
idp2aws run dev -- terraform plan  # run one command with the keys
idp2aws console dev                # open the AWS console
idp2aws profiles                   # show each profile, its role and when its keys expire
```

### First login for a profile

1. Run `idp2aws login dev`.
2. Sign in to your IdP in the browser window.
3. On the AWS "Select a role" page, pick a role. The page shows the accounts sorted by name.
4. Click Sign In.

The window closes. idp2aws saves the keys and keeps the role for the profile. The AWS console
does not open.

### Next logins

- The next logins for the profile use the same role. They do not show the AWS role page.
- If the saved keys work for more than 5 more minutes, `login` does nothing. Keys with less
  than 5 minutes left count as expired, so a long command does not fail halfway through.
- `run` and `console` log in automatically when the keys expired. So you seldom need `login`.
- To use a different role, run `idp2aws login dev --pick`.
- `console` works only for commercial AWS accounts, not for GovCloud or China.

### Let the AWS CLI log in automatically

Add a profile to `~/.aws/config` that runs idp2aws when the AWS CLI needs keys:

```ini
[profile dev-auto]
credential_process = idp2aws login dev --json
```

Then `aws --profile dev-auto s3 ls` logs in only when necessary.

Give this profile a name that is different from the profile that idp2aws writes to. Use
`dev-auto`, not `dev`. If the names are the same, the AWS CLI reads the old keys from
`~/.aws/credentials` and does not run idp2aws.

If your tools do not use the same `PATH` as your shell, write the full path to `idp2aws`.

## Files

| File | Contents |
| --- | --- |
| `~/.idp2aws/config.toml` | Your settings. You edit this file. |
| `~/.idp2aws/profiles.json` | The last role of each profile and the time when its keys expire. idp2aws writes this file. |
| `~/.idp2aws/browser-profile/` | The browser profile with your IdP session cookies. To sign out, delete this folder. |
| `~/.aws/credentials` | The AWS keys, one profile for each idp2aws profile. |

**Warning:** The browser profile and the credentials file give access to your accounts. Protect
them as you protect passwords. On macOS and Linux, idp2aws makes the credentials file readable
only by you each time it saves keys.

Chrome encrypts the cookies in the browser profile with a key from the macOS Keychain or the
Linux keyring. On Linux without a keyring, Chrome uses a weaker fixed key.

## Troubleshooting

**`idp2aws: command not found`**
The folder where pipx puts commands is not on your `PATH`. Run `pipx ensurepath`, then open a new
terminal.

**Google says "This browser or app may not be secure".**
Set `browser = "chrome"`, not `chromium`. If the message shows again, delete
`~/.idp2aws/browser-profile` and try again.

**The window opens but does not close.**
The login did not get to AWS. To check the start URL, open it in your usual browser. After 5
minutes, idp2aws stops and shows an error.

**"Cannot find chrome" (or msedge)**
idp2aws cannot find that browser. Do one of these:

- Install the browser.
- Set `browser` to the other browser.
- Run `playwright install chromium` and set `browser = "chromium"`.

**"Another idp2aws login is using the browser profile"**
Only one login can use the browser at a time. Finish or close the other login window, then try
again. This can happen when several tools ask a `credential_process` profile for keys at the
same time.

**macOS asks to allow access to "Chrome Safe Storage" in the Keychain.**
Chrome reads its cookie key from the Keychain. Click **Always Allow**.

**Linux: the browser stops at start because `.so` libraries are missing.**
Run `sudo "$(which playwright)" install-deps chromium`.

**"DurationSeconds exceeds the MaxSessionDuration"**
Make `session_hours` smaller for that profile. Or, ask an AWS admin to increase the maximum
session duration of the role.

**"You can no longer use <role>"**
Your IdP access no longer includes the role that you picked last time. Run
`idp2aws login <profile> --pick` and pick a different role.

**"The SAML response lists no AWS roles for you"**
Your IdP user has no AWS role for this app. Ask your IdP admin.

**"Token expired" or "not yet valid" from STS**
The clock on your computer may be wrong. Turn on automatic time sync.

**Comments in `~/.aws/credentials` are gone.**
idp2aws writes the full file again when it saves keys. It does not keep comments. Write your
notes in `~/.aws/config`.

**Windows: `run` works differently.**
On macOS and Linux, your command replaces idp2aws. On Windows, idp2aws starts your command as a
new process. So exit codes and Ctrl+C may work differently.

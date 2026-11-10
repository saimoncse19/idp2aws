# idp2aws

idp2aws gets short-lived AWS keys for you. You sign in to your IdP in a real browser window.
It works with Google Workspace, Okta, Entra ID and other SAML IdPs that sign you in to AWS
accounts directly.

```sh
idp2aws setup 'https://accounts.google.com/o/saml2/initsso?idpid=XXXX&spid=YYYY'
idp2aws login dev                  # pick a role, idp2aws saves the keys to profile "dev"
aws --profile dev s3 ls            # use the keys
idp2aws run dev -- terraform plan  # run one command with the keys
idp2aws console dev                # open the AWS console
```

The first login for a profile shows the AWS role page, sorted by account name. idp2aws keeps
the role that you pick. The next logins for that profile use this role and do not show the page.
While your IdP session is active, the browser window opens and closes without input from you.

idp2aws does not work with AWS IAM Identity Center. For Identity Center, use `aws sso login`.

## Install

idp2aws needs Python 3.12 or newer, and Google Chrome or Microsoft Edge.

Install from PyPI with pipx or pip:

```sh
pipx install idp2aws
pip install idp2aws          # if you manage the virtual environment yourself
```

Or install from source:

```sh
pipx install git+https://github.com/saimoncse19/idp2aws.git    # latest code on main

git clone https://github.com/saimoncse19/idp2aws.git && cd idp2aws   # to change the code
python3.12 -m venv .venv
.venv/bin/pip install -e .
```

For step-by-step install on macOS, Linux and Windows, the config file and troubleshooting, see
[docs/USAGE.md](https://github.com/saimoncse19/idp2aws/blob/main/docs/USAGE.md).

## How it works

1. Chrome opens at the start URL. You sign in to your IdP with your usual 2-Step Verification.
2. The IdP sends a signed SAML response to the AWS sign-in page.
3. If you have more than one role and the profile has no role yet, idp2aws lets AWS show its
   role page. You pick a role and click Sign In.
4. idp2aws stops the SAML response before it gets to AWS, and closes the window.
5. idp2aws calls STS `AssumeRoleWithSAML` with the SAML response and gets keys for the role.
6. idp2aws writes the keys to the profile in `~/.aws/credentials`.

## Development

```sh
git clone https://github.com/saimoncse19/idp2aws.git && cd idp2aws
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest                 # unit tests
pytest -m browser      # browser tests: headless Chrome with a fake IdP and AWS role page
pylint src scripts
```

## Release

idp2aws uses semantic versioning: `MAJOR.MINOR.PATCH`. Each release must be the next patch,
minor or major version after the latest one on PyPI. After 1.4.2, the only choices are 1.4.3,
1.5.0 and 2.0.0.

1. Set `__version__` in `src/idp2aws/__init__.py`. This is the only place the version is set.
2. Add the version and the date to `CHANGELOG.md`.
3. Merge to `main`.
4. On GitHub, create a release with the tag `v` plus the version, for example `v1.4.3`.

The `Publish to PyPI` workflow then runs the tests, checks the version and uploads to PyPI. If
the tag does not match `__version__`, or the version skips or repeats one, the workflow stops
and uploads nothing. To check a version before you release, run
`python scripts/check_version.py v1.4.3`.

## License

idp2aws is source-available under the MIT license with the
[Commons Clause](https://commonsclause.com/). You can use, change and share it for free,
including at work. You cannot sell it, or sell a product or service whose value comes mainly
from it. See [LICENSE](https://github.com/saimoncse19/idp2aws/blob/main/LICENSE).

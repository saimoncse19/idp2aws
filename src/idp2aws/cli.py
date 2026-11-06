"""Module for the ``idp2aws`` command line.

Messages for you go to stderr, so stdout stays clean for ``login --json``.
"""

import os
import webbrowser
from typing import Annotated, NoReturn

import typer
from botocore.exceptions import ClientError

from idp2aws import aws, browser, saml, settings

app = typer.Typer(
    help="Get short-lived AWS keys. You sign in to your IdP in a browser.",
    no_args_is_help=True,
    add_completion=False,
)

ProfileArgument = Annotated[
    str, typer.Argument(help="AWS profile for the keys, for example dev.")
]


@app.command()
def setup(
    start_url: Annotated[str, typer.Argument(help="Start URL of your IdP for AWS.")],
    browser_name: Annotated[
        settings.Browser, typer.Option("--browser")
    ] = settings.Browser.CHROME,
    session_hours: Annotated[
        int,
        typer.Option(
            "--hours",
            min=1,
            max=settings.MAX_SESSION_HOURS,
            help="How long AWS keys last.",
        ),
    ] = 1,
) -> None:
    """Create the config file with settings shared by every profile."""
    try:
        shared = settings.Settings(start_url, browser_name.value, session_hours)
        settings.create_config(shared)
    except settings.SettingsError as error:
        fail(str(error))
    say(f"Created {settings.CONFIG_FILE}. Next: idp2aws login <profile>")


@app.command()
def login(
    profile: ProfileArgument,
    pick: Annotated[
        bool,
        typer.Option("--pick", help="Show the AWS role page and pick a different role."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print the keys for credential_process."),
    ] = False,
) -> None:
    """Sign in and save AWS keys to a profile in ~/.aws/credentials.

    The first login for a profile shows the AWS role page. The role you pick
    is used again next time.
    """
    credentials = get_credentials(profile, pick)
    if as_json:
        typer.echo(credentials.as_json())
        return
    expires = credentials.expiration.astimezone()
    say(f"Keys for profile {profile!r} work until {expires:%H:%M on %d %b}.")


@app.command()
def run(
    profile: ProfileArgument,
    command: Annotated[
        list[str], typer.Argument(help="The command to run. Put it after --.")
    ],
) -> None:
    """Run a command with the profile's AWS keys in its environment.

    Example: idp2aws run dev -- aws s3 ls
    """
    credentials = get_credentials(profile)
    env = {key: value for key, value in os.environ.items() if key != "AWS_PROFILE"}
    try:
        os.execvpe(command[0], command, env | credentials.as_env())
    except FileNotFoundError:
        fail(f"Command not found: {command[0]}")
    except OSError as error:
        fail(f"Cannot run {command[0]}: {error.strerror}")


@app.command()
def console(profile: ProfileArgument) -> None:
    """Open the AWS console for the profile in your web browser."""
    credentials = get_credentials(profile)
    role_arn = settings.load_profiles()[profile].role_arn
    if not role_arn.startswith("arn:aws:"):
        fail("The console link only works for commercial AWS, not GovCloud or China.")
    try:
        webbrowser.open(aws.get_console_url(credentials))
    except OSError as error:
        fail(f"Cannot reach the AWS sign-in service: {error}")


@app.command()
def profiles() -> None:
    """List your profiles, their roles and when their keys expire."""
    try:
        configured = settings.configured_profiles()
    except settings.SettingsError as error:
        fail(str(error))
    saved = settings.load_profiles()
    for name in sorted(set(configured) | set(saved)):
        if name not in saved:
            typer.echo(f"{name:<20} not logged in yet")
            continue
        expires = saved[name].expires.astimezone()
        typer.echo(f"{name:<20} {saved[name].role_arn}  until {expires:%H:%M on %d %b}")


def get_credentials(profile: str, pick: bool = False) -> aws.Credentials:
    """Get working keys for a profile, signing in only if the saved ones expired.

    The role comes from the profile's ``role_arn`` setting, then from your
    last pick. With neither, or with ``pick``, the AWS role page is shown.

    :param profile: AWS profile to save the keys to.
    :param pick: Sign in again and show the AWS role page.
    :return: Keys that have not expired.
    """
    try:
        config = settings.load_settings(profile)
    except settings.SettingsError as error:
        fail(str(error))
    saved = settings.load_profiles().get(profile)
    if saved and not pick:
        credentials = aws.load_credentials(profile, saved.expires)
        if credentials and not credentials.is_expired:
            return credentials

    role_arn = config.role_arn or (saved.role_arn if saved else None)
    if pick:
        role_arn = None
    if role_arn and role_arn == config.role_arn:
        fix = f"Change role_arn for {profile} in {settings.CONFIG_FILE}."
    else:
        fix = "Log in again with --pick."
    say(f"Opening the browser to sign in for {profile}...")
    try:
        login_result = browser.log_in(config.start_url, config.browser, role_arn)
        assertion = saml.parse(login_result.saml_response)
        role = choose_role(assertion, login_result.picked_role_arn or role_arn, fix)
        say(f"Using role {role.role_arn}")
        credentials = aws.assume_role(
            role,
            assertion,
            config.session_hours * 3600,
            aws.get_sts_region(assertion.destination),
        )
    except (browser.LoginError, saml.SAMLError) as error:
        fail(str(error))
    except ClientError as error:
        fail(explain_sts_error(error))

    aws.save_credentials(profile, credentials)
    remembered = settings.Profile(profile, role.role_arn, credentials.expiration)
    settings.save_profile(remembered)
    return credentials


def choose_role(
    assertion: saml.Assertion, role_arn: str | None, fix: str = ""
) -> saml.Role:
    """Find the role to use in the SAML response.

    :param assertion: The SAML response.
    :param role_arn: Role picked on the AWS page, set in the config file or
        remembered. If ``None``, the response must list exactly one role.
    :param fix: What to do if ``role_arn`` is not in the response. It depends
        on where the role came from.
    :return: The matching role.
    """
    roles = assertion.roles
    if not roles:
        fail("The SAML response lists no AWS roles for you. Ask your IdP admin.")
    if role_arn is None:
        if len(roles) > 1:
            fail("You did not pick a role. Try again and click Sign In on the AWS page.")
        return roles[0]
    role = next((role for role in roles if role.role_arn == role_arn), None)
    if role is None:
        fail(f"You can no longer use {role_arn}. {fix}".strip())
    return role


def explain_sts_error(error: ClientError) -> str:
    """Turn an STS error into a message that says what to do about it.

    :param error: Error raised by ``AssumeRoleWithSAML``.
    :return: The STS message, with a hint when we know the usual fix.
    """
    message = error.response["Error"]["Message"]
    if "DurationSeconds" in message:
        return (
            f"{message}\nMake session_hours smaller, or ask an AWS admin to increase "
            "the maximum session duration of the role."
        )
    if "expired" in message.lower() or "NotOnOrAfter" in message:
        return f"{message}\nYour computer clock may be wrong. Fix it and try again."
    return message


def say(message: str) -> None:
    """Print a message for the user on stderr.

    :param message: Text to print.
    """
    typer.echo(message, err=True)


def fail(message: str) -> NoReturn:
    """Print an error and exit with status 1.

    :param message: What went wrong and, if known, what to do.
    :raises typer.Exit: Always.
    """
    say(f"Error: {message}")
    raise typer.Exit(1)

from datetime import datetime, timedelta, timezone

import pytest
import typer
from botocore.exceptions import ClientError

from idp2aws import aws, browser, cli, saml, settings

DEV = saml.Role(
    "arn:aws:iam::111111111111:role/Dev", "arn:aws:iam::111111111111:saml-provider/G"
)
PROD = saml.Role(
    "arn:aws:iam::222222222222:role/Prod", "arn:aws:iam::222222222222:saml-provider/G"
)
URL = "https://idp.example.com/start"


def make_assertion(*roles):
    return saml.Assertion(raw="", roles=list(roles), destination=None)


def make_credentials(hours_left=1):
    return aws.Credentials(
        "ASIANEW", "secret", "token", datetime.now(timezone.utc) + timedelta(hours=hours_left)
    )


@pytest.fixture
def mocks(mocker):
    mocker.patch("idp2aws.settings.load_settings", return_value=settings.Settings(URL))
    mocker.patch("idp2aws.settings.load_profiles", return_value={})
    mocker.patch("idp2aws.settings.save_profile")
    mocker.patch("idp2aws.aws.load_credentials", return_value=None)
    mocker.patch("idp2aws.aws.save_credentials")
    mocker.patch("idp2aws.aws.assume_role", return_value=make_credentials())
    mocker.patch(
        "idp2aws.browser.log_in", return_value=browser.BrowserLogin("SAML", DEV.role_arn)
    )
    mocker.patch("idp2aws.saml.parse", return_value=make_assertion(DEV, PROD))
    return mocker


def remember(role_arn, hours_left):
    expires = datetime.now(timezone.utc) + timedelta(hours=hours_left)
    settings.load_profiles.return_value = {"dev": settings.Profile("dev", role_arn, expires)}
    aws.load_credentials.return_value = make_credentials(hours_left)


class TestGetCredentials:
    def test_first_login_shows_role_page_and_remembers_pick(self, mocks):
        result = cli.get_credentials("dev")

        assert result == aws.assume_role.return_value
        browser.log_in.assert_called_once_with(URL, "chrome", None)
        aws.save_credentials.assert_called_once_with("dev", result)
        saved = settings.save_profile.call_args.args[0]
        assert (saved.name, saved.role_arn) == ("dev", DEV.role_arn)

    def test_reuses_saved_keys_that_still_work(self, mocks):
        remember(DEV.role_arn, hours_left=1)

        result = cli.get_credentials("dev")

        assert result == aws.load_credentials.return_value
        browser.log_in.assert_not_called()

    def test_expired_keys_log_in_with_remembered_role(self, mocks):
        remember(PROD.role_arn, hours_left=-1)
        browser.log_in.return_value = browser.BrowserLogin("SAML", None)

        cli.get_credentials("dev")

        browser.log_in.assert_called_once_with(URL, "chrome", PROD.role_arn)
        assert aws.assume_role.call_args.args[0] == PROD

    def test_config_role_wins_over_remembered_role(self, mocks):
        remember(DEV.role_arn, hours_left=-1)
        settings.load_settings.return_value = settings.Settings(URL, role_arn=PROD.role_arn)
        browser.log_in.return_value = browser.BrowserLogin("SAML", None)

        cli.get_credentials("dev")

        browser.log_in.assert_called_once_with(URL, "chrome", PROD.role_arn)

    def test_pick_shows_role_page_even_with_working_keys(self, mocks):
        remember(PROD.role_arn, hours_left=1)

        cli.get_credentials("dev", pick=True)

        browser.log_in.assert_called_once_with(URL, "chrome", None)
        assert aws.assume_role.call_args.args[0] == DEV

    def test_missing_config_role_says_to_edit_config(self, mocks, capsys):
        settings.load_settings.return_value = settings.Settings(URL, role_arn="arn:gone")
        browser.log_in.return_value = browser.BrowserLogin("SAML", None)

        with pytest.raises(typer.Exit):
            cli.get_credentials("dev")

        assert "Change role_arn for dev" in capsys.readouterr().err

    def test_login_error_stops_with_message(self, mocks, capsys):
        browser.log_in.side_effect = browser.LoginError("Window closed.")

        with pytest.raises(typer.Exit):
            cli.get_credentials("dev")

        assert "Error: Window closed." in capsys.readouterr().err
        aws.save_credentials.assert_not_called()


class TestChooseRole:
    def test_finds_the_given_role(self):
        assert cli.choose_role(make_assertion(DEV, PROD), PROD.role_arn) == PROD

    def test_only_role_needs_no_choice(self):
        assert cli.choose_role(make_assertion(DEV), None) == DEV

    @pytest.mark.parametrize(
        ("roles", "role_arn"),
        [
            ((DEV, PROD), None),
            ((DEV,), PROD.role_arn),
            ((), None),
        ],
        ids=["none-picked", "not-allowed", "no-roles"],
    )
    def test_stops_when_no_role_fits(self, roles, role_arn):
        with pytest.raises(typer.Exit):
            cli.choose_role(make_assertion(*roles), role_arn)


class TestRun:
    def test_unknown_command(self, mocker, capsys):
        mocker.patch("idp2aws.cli.get_credentials", return_value=make_credentials())

        with pytest.raises(typer.Exit):
            cli.run("dev", ["no-such-command-xyz"])

        assert "Command not found: no-such-command-xyz" in capsys.readouterr().err


class TestExplainStsError:
    @pytest.mark.parametrize(
        ("message", "hint"),
        [
            ("DurationSeconds exceeds the MaxSessionDuration", "session_hours"),
            ("Token expired: current date/time must be before NotOnOrAfter", "clock"),
        ],
    )
    def test_adds_hint(self, message, hint):
        error = ClientError({"Error": {"Code": "X", "Message": message}}, "AssumeRoleWithSAML")

        assert hint in cli.explain_sts_error(error)

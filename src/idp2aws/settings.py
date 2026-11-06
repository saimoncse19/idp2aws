"""Module for the config file and the profiles idp2aws remembers.

Both files live in ``~/.idp2aws``, or in ``$IDP2AWS_HOME`` if it is set.

``config.toml`` is yours to edit. Settings at the top apply to every
profile, and a ``[profiles.<name>]`` table overrides them for one profile::

    start_url = "https://accounts.google.com/o/saml2/initsso?idpid=X&spid=Y"
    session_hours = 1

    [profiles.prod]
    role_arn = "arn:aws:iam::123456789012:role/Developer"
    session_hours = 4

``profiles.json`` is written by idp2aws: the role you last picked for each
profile, and when its keys expire.
"""

import json
import os
import tomllib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from idp2aws.files import write_file

HOME = Path(os.environ.get("IDP2AWS_HOME", Path.home() / ".idp2aws"))
CONFIG_FILE = HOME / "config.toml"
PROFILES_FILE = HOME / "profiles.json"
MAX_SESSION_HOURS = 12

CONFIG_TEMPLATE = """\
# Settings for every profile.
start_url = {start_url}
browser = "{browser}"
session_hours = {session_hours}

# Settings for one profile go in its own table and win over the ones above.
# [profiles.prod]
# role_arn = "arn:aws:iam::123456789012:role/Developer"
# session_hours = 4
"""


class SettingsError(Exception):
    """Raise when the config file is missing, cannot be read or has a bad value."""


class Browser(str, Enum):
    """Browsers idp2aws can open."""

    CHROME = "chrome"
    CHROMIUM = "chromium"
    MSEDGE = "msedge"


@dataclass
class Settings:
    """Settings for one login, after profile overrides are applied.

    :param start_url: Start URL of your IdP for AWS.
    :param browser: ``chrome`` or ``msedge`` for your installed Chrome or Edge,
        or ``chromium`` for the one Playwright downloads.
    :param session_hours: How long the AWS keys last.
    :param role_arn: Role to use without showing the AWS role page.
    """

    start_url: str
    browser: str = "chrome"
    session_hours: int = 1
    role_arn: str | None = None

    def __post_init__(self) -> None:
        """Check the values, because the config file is edited by hand.

        :raises SettingsError: If a value has the wrong type or is out of range.
        """
        url = self.start_url
        if not isinstance(url, str) or not url.startswith("https://"):
            raise SettingsError(f"start_url must be an https:// URL, not {url!r}.")
        choices = [browser.value for browser in Browser]
        if self.browser not in choices:
            raise SettingsError(
                f"browser must be one of {', '.join(choices)}, not {self.browser!r}."
            )
        hours = self.session_hours
        is_whole = isinstance(hours, int) and not isinstance(hours, bool)
        if not is_whole or not 1 <= hours <= MAX_SESSION_HOURS:
            raise SettingsError(
                f"session_hours must be a whole number from 1 to {MAX_SESSION_HOURS},"
                f" not {hours!r}."
            )
        if self.role_arn is not None and not isinstance(self.role_arn, str):
            raise SettingsError(f"role_arn must be text, not {self.role_arn!r}.")


@dataclass
class Profile:
    """An AWS profile that idp2aws has saved keys to.

    :param name: Profile name in the AWS credentials file.
    :param role_arn: Role the keys belong to. The next login uses it again.
    :param expires: When the keys stop working.
    """

    name: str
    role_arn: str
    expires: datetime


def load_settings(profile: str, path: Path = CONFIG_FILE) -> Settings:
    """Read the settings for one profile from the config file.

    :param profile: Profile whose table, if any, overrides the shared settings.
    :param path: Config file to read.
    :return: The shared settings with the profile's overrides applied.
    :raises SettingsError: If the file is missing, is not valid TOML, or has
        an unknown or missing key.
    """
    config = _read_config(path)
    overrides = config.pop("profiles", {}).get(profile, {})
    try:
        return Settings(**config | overrides)
    except TypeError as error:
        message = f"{path} has an unknown or missing setting: {error}"
        raise SettingsError(message) from None
    except SettingsError as error:
        raise SettingsError(f"{path}: {error}") from None


def configured_profiles(path: Path = CONFIG_FILE) -> list[str]:
    """List the profiles that have a table in the config file.

    :param path: Config file to read.
    :return: Profile names, sorted.
    :raises SettingsError: If the file is missing or is not valid TOML.
    """
    return sorted(_read_config(path).get("profiles", {}))


def create_config(settings: Settings, path: Path = CONFIG_FILE) -> None:
    """Write a new config file with the shared settings.

    :param settings: Shared settings to write.
    :param path: Config file to create.
    :raises SettingsError: If the file already exists.
    """
    if path.exists():
        raise SettingsError(f"{path} already exists. To change it, edit the file.")
    write_file(path, CONFIG_TEMPLATE.format(
        start_url=json.dumps(settings.start_url),
        browser=settings.browser,
        session_hours=settings.session_hours,
    ))


def load_profiles(path: Path = PROFILES_FILE) -> dict[str, Profile]:
    """Read the profiles idp2aws has saved keys to.

    :param path: Profiles file to read.
    :return: Profiles by name. Empty if there are none yet.
    """
    if not path.exists():
        return {}
    return {
        name: Profile(name, item["role_arn"], datetime.fromisoformat(item["expires"]))
        for name, item in json.loads(path.read_text()).items()
    }


def save_profile(profile: Profile, path: Path = PROFILES_FILE) -> None:
    """Remember a profile, keeping the others.

    :param profile: Profile to add or replace.
    :param path: Profiles file to write.
    """
    profiles = load_profiles(path) | {profile.name: profile}
    data = {
        name: {"role_arn": item.role_arn, "expires": item.expires.isoformat()}
        for name, item in sorted(profiles.items())
    }
    write_file(path, json.dumps(data, indent=2) + "\n")


def _read_config(path: Path) -> dict:
    """Read the config file as a dict.

    :param path: Config file to read.
    :return: The parsed TOML.
    :raises SettingsError: If the file is missing or is not valid TOML.
    """
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError:
        raise SettingsError(
            "idp2aws is not set up yet. Run: idp2aws setup <start-url>"
        ) from None
    except tomllib.TOMLDecodeError as error:
        raise SettingsError(f"{path} is not valid TOML: {error}") from None

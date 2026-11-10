"""Module for checking the release version before it goes to PyPI.

The publish workflow runs it with the release tag::

    python scripts/check_version.py v1.2.3

It stops the release unless all of these are true:

* ``__version__`` in ``src/idp2aws/__init__.py`` is ``MAJOR.MINOR.PATCH``.
* The tag is ``v`` followed by that version.
* The version is the next patch, minor or major version after the latest
  one on PyPI. For example, after 1.4.2 the only choices are 1.4.3, 1.5.0
  and 2.0.0.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
INIT_FILE = Path(__file__).resolve().parent.parent / "src" / "idp2aws" / "__init__.py"
PYPI_URL = "https://pypi.org/pypi/idp2aws/json"

Version = tuple[int, int, int]


def parse(version: str) -> Version | None:
    """Split a ``MAJOR.MINOR.PATCH`` version into numbers.

    :param version: Version text, for example ``1.4.2``.
    :return: The three numbers, or ``None`` if it is not strict semver.
    """
    match = SEMVER.match(version)
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def get_next_versions(latest: Version) -> list[Version]:
    """List the versions allowed after the latest release.

    :param latest: Latest version on PyPI.
    :return: The next patch, minor and major versions.
    """
    major, minor, patch = latest
    return [(major, minor, patch + 1), (major, minor + 1, 0), (major + 1, 0, 0)]


def check(tag: str, version: str, released: list[str]) -> list[str]:
    """Find the reasons a release must not go ahead.

    :param tag: Git tag of the GitHub release.
    :param version: ``__version__`` from the package.
    :param released: Versions already on PyPI.
    :return: One message per problem. Empty if the release can go ahead.
    """
    new = parse(version)
    if new is None:
        return [f"Version {version!r} is not MAJOR.MINOR.PATCH, for example 1.4.2."]

    errors = []
    if tag != f"v{version}":
        errors.append(f"Tag {tag!r} does not match the version. Use 'v{version}'.")
    if version in released:
        errors.append(f"Version {version} is already on PyPI.")
        return errors

    semver_releases = [parsed for parsed in map(parse, released) if parsed]
    if semver_releases:
        latest = max(semver_releases)
        allowed = [".".join(map(str, item)) for item in get_next_versions(latest)]
        if new not in get_next_versions(latest):
            errors.append(
                f"Version {version} does not follow {'.'.join(map(str, latest))}. "
                f"Use one of: {', '.join(allowed)}."
            )
    return errors


def read_version(path: Path = INIT_FILE) -> str:
    """Read ``__version__`` from the package.

    :param path: The package's ``__init__.py``.
    :return: The version text.
    :raises ValueError: If the file has no ``__version__`` line.
    """
    match = re.search(r'^__version__ = "([^"]+)"$', path.read_text(), re.MULTILINE)
    if match is None:
        raise ValueError(f"No __version__ line in {path}.")
    return match.group(1)


def fetch_released(url: str = PYPI_URL) -> list[str]:
    """Get the versions already on PyPI.

    :param url: PyPI JSON API address of the project.
    :return: Released versions. Empty if the project is not on PyPI yet.
    :raises urllib.error.URLError: If PyPI cannot be reached.
    """
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return list(json.load(response)["releases"])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise


def main(argv: list[str]) -> int:
    """Check the version for the tag given on the command line.

    :param argv: Command line arguments without the program name.
    :return: Exit status, 0 if the release can go ahead.
    """
    if len(argv) != 1:
        print("Usage: python scripts/check_version.py <tag>", file=sys.stderr)
        return 2
    version = read_version()
    errors = check(argv[0], version, fetch_released())
    for error in errors:
        print(f"Error: {error}", file=sys.stderr)
    if not errors:
        print(f"Version {version} is ready to publish.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

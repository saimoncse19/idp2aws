"""Module for swapping a SAML response for AWS keys, and storing them."""

import configparser
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from idp2aws.files import write_file
from idp2aws.saml import Assertion, Role

FEDERATION_URL = "https://signin.aws.amazon.com/federation"
# Keys this close to expiry count as expired, so a command started with them
# does not fail halfway through.
EXPIRY_MARGIN = timedelta(minutes=5)


@dataclass
class Credentials:
    """Short-lived AWS keys.

    :param access_key_id: The ``ASIA...`` key id.
    :param secret_access_key: The secret key.
    :param session_token: The session token that goes with the keys.
    :param expiration: When the keys stop working.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime

    @property
    def is_expired(self) -> bool:
        """Tell whether the keys have stopped working, or soon will.

        :return: ``True`` from ``EXPIRY_MARGIN`` before the expiry time.
        """
        return datetime.now(timezone.utc) >= self.expiration - EXPIRY_MARGIN

    def as_env(self) -> dict[str, str]:
        """Get the keys as the environment variables AWS tools read.

        :return: Variable names and values.
        """
        return {
            "AWS_ACCESS_KEY_ID": self.access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.secret_access_key,
            "AWS_SESSION_TOKEN": self.session_token,
        }

    def as_json(self) -> str:
        """Get the keys as JSON in the shape ``credential_process`` expects.

        :return: The JSON text.
        """
        return json.dumps({
            "Version": 1,
            "AccessKeyId": self.access_key_id,
            "SecretAccessKey": self.secret_access_key,
            "SessionToken": self.session_token,
            "Expiration": self.expiration.isoformat(),
        })


def get_sts_region(destination: str | None) -> str:
    """Choose the region for the STS call from where the response is going.

    :param destination: AWS sign-in address from the SAML response. Its
        domain tells us the partition: commercial, GovCloud or China.
    :return: A region in that partition.
    """
    if destination and "amazonaws-us-gov" in destination:
        return "us-gov-west-1"
    if destination and "amazonaws.cn" in destination:
        return "cn-north-1"
    return "us-east-1"


def assume_role(
    role: Role, assertion: Assertion, duration_secs: int, region: str
) -> Credentials:
    """Ask AWS STS for keys in exchange for the SAML response.

    The call needs no AWS keys, so the request is not signed.

    :param role: Role to assume.
    :param assertion: SAML response that lists the role.
    :param duration_secs: How long the keys should last.
    :param region: Region of the STS endpoint.
    :return: The new keys.
    :raises botocore.exceptions.ClientError: If STS refuses.
    """
    unsigned = Config(signature_version=UNSIGNED)
    sts = boto3.client("sts", region_name=region, config=unsigned)
    response = sts.assume_role_with_saml(
        RoleArn=role.role_arn,
        PrincipalArn=role.principal_arn,
        SAMLAssertion=assertion.raw,
        DurationSeconds=duration_secs,
    )
    keys = response["Credentials"]
    return Credentials(
        access_key_id=keys["AccessKeyId"],
        secret_access_key=keys["SecretAccessKey"],
        session_token=keys["SessionToken"],
        expiration=keys["Expiration"],
    )


def get_credentials_file() -> Path:
    """Find the AWS credentials file, honouring ``AWS_SHARED_CREDENTIALS_FILE``.

    :return: Path to the file. It may not exist yet.
    """
    default = Path.home() / ".aws" / "credentials"
    return Path(os.environ.get("AWS_SHARED_CREDENTIALS_FILE", default))


def load_credentials(profile: str, expiration: datetime) -> Credentials | None:
    """Read keys saved to a profile earlier.

    :param profile: Profile in the AWS credentials file.
    :param expiration: When the keys expire. The file does not say.
    :return: The keys, or ``None`` if the profile is missing or incomplete.
    """
    parser = _read_ini(get_credentials_file())
    if profile not in parser:
        return None
    section = parser[profile]
    try:
        return Credentials(
            access_key_id=section["aws_access_key_id"],
            secret_access_key=section["aws_secret_access_key"],
            session_token=section["aws_session_token"],
            expiration=expiration,
        )
    except KeyError:
        return None


def save_credentials(profile: str, credentials: Credentials) -> None:
    """Write keys to a profile in the AWS credentials file.

    Other profiles are kept. Comments in the file are not, because
    ``configparser`` drops them. Only you can read the file afterwards.

    :param profile: Profile to write. Anything already in it is replaced.
    :param credentials: Keys to write.
    """
    path = get_credentials_file()
    parser = _read_ini(path)
    parser[profile] = {
        "aws_access_key_id": credentials.access_key_id,
        "aws_secret_access_key": credentials.secret_access_key,
        "aws_session_token": credentials.session_token,
    }
    text = io.StringIO()
    parser.write(text)
    write_file(path, text.getvalue(), mode=0o600)


def get_console_url(credentials: Credentials) -> str:
    """Build a link that opens the AWS console with these keys.

    Only works in the commercial AWS partition.

    :param credentials: Keys to sign in with.
    :return: A one-time sign-in link, valid for 15 minutes.
    :raises OSError: If the AWS sign-in service cannot be reached.
    """
    session = json.dumps({
        "sessionId": credentials.access_key_id,
        "sessionKey": credentials.secret_access_key,
        "sessionToken": credentials.session_token,
    })
    query = urlencode({"Action": "getSigninToken", "Session": session})
    with urlopen(f"{FEDERATION_URL}?{query}", timeout=10) as response:
        token = json.load(response)["SigninToken"]
    query = urlencode({
        "Action": "login",
        "Issuer": "idp2aws",
        "Destination": "https://console.aws.amazon.com/",
        "SigninToken": token,
    })
    return f"{FEDERATION_URL}?{query}"


def _read_ini(path: Path) -> configparser.ConfigParser:
    """Read an INI file, treating ``%`` as plain text.

    :param path: File to read. A missing file gives an empty parser.
    :return: The parsed file.
    """
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path)
    return parser

"""Module for reading the parts of a SAML response that AWS cares about.

The IdP signs the response and AWS STS checks the signature, so here we
only read it: the roles you may use, and the AWS address it is meant for.
"""

import base64
import binascii
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ROLE_ATTRIBUTE = "https://aws.amazon.com/SAML/Attributes/Role"
ARN = re.compile(r"arn:[\w-]+:iam::\d{12}:[^,\s]+")


class SAMLError(Exception):
    """Raise when a SAML response or one of its roles cannot be read."""


@dataclass(frozen=True)
class Role:
    """An AWS role listed in the SAML response.

    :param role_arn: The IAM role you may use.
    :param principal_arn: The IAM SAML provider that trusts your IdP.
    """

    role_arn: str
    principal_arn: str


@dataclass
class Assertion:
    """A SAML response with the parts we need read out.

    :param raw: The base64 text exactly as the IdP sent it. STS wants this.
    :param roles: Roles you may use, in the order the IdP listed them.
    :param destination: AWS sign-in address the response is meant for.
    """

    raw: str
    roles: list[Role]
    destination: str | None


def parse(saml_response: str) -> Assertion:
    """Read a base64 SAML response.

    :param saml_response: The ``SAMLResponse`` form value.
    :return: The roles and destination in the response.
    :raises SAMLError: If it is not base64 XML, or a role cannot be read.
    """
    try:
        root = ET.fromstring(base64.b64decode(saml_response))
    except (binascii.Error, ET.ParseError) as error:
        raise SAMLError(f"The SAML response is not base64 XML: {error}") from None

    roles = []
    for attribute in root.iterfind(".//{*}Attribute"):
        if attribute.get("Name") == ROLE_ATTRIBUTE:
            roles += [parse_role(value.text or "") for value in attribute]

    destination = root.get("Destination")
    if destination is None:
        confirmation = root.find(".//{*}SubjectConfirmationData")
        destination = confirmation.get("Recipient") if confirmation is not None else None

    return Assertion(raw=saml_response, roles=roles, destination=destination)


def parse_role(value: str) -> Role:
    """Split one role value into its two ARNs.

    The value should be ``<role ARN>,<provider ARN>``, but some IdPs swap
    them, so we tell them apart by what they contain.

    :param value: Text of one ``AttributeValue`` in the role attribute.
    :return: The role and its SAML provider.
    :raises SAMLError: If the value does not hold exactly those two ARNs.
    """
    arns = ARN.findall(value)
    role = next((arn for arn in arns if ":role/" in arn), None)
    principal = next((arn for arn in arns if ":saml-provider/" in arn), None)
    if len(arns) != 2 or role is None or principal is None:
        raise SAMLError(f"Cannot read this role value: {value!r}")
    return Role(role_arn=role, principal_arn=principal)

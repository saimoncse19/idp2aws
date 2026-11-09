import base64

import pytest

from idp2aws import saml

ROLE = "arn:aws:iam::111111111111:role/Developer"
PROVIDER = "arn:aws:iam::111111111111:saml-provider/Google"
OTHER_ROLE = "arn:aws:iam::222222222222:role/ReadOnly"
OTHER_PROVIDER = "arn:aws:iam::222222222222:saml-provider/Google"
AWS_SAML = "https://signin.aws.amazon.com/saml"


def make_response(*role_values, destination=f'Destination="{AWS_SAML}"'):
    values = "".join(
        f"<saml2:AttributeValue>{value}</saml2:AttributeValue>" for value in role_values
    )
    xml = f"""<saml2p:Response xmlns:saml2p="urn:oasis:names:tc:SAML:2.0:protocol" {destination}>
      <saml2:Assertion xmlns:saml2="urn:oasis:names:tc:SAML:2.0:assertion">
        <saml2:Subject><saml2:SubjectConfirmation>
          <saml2:SubjectConfirmationData Recipient="{AWS_SAML}"/>
        </saml2:SubjectConfirmation></saml2:Subject>
        <saml2:AttributeStatement>
          <saml2:Attribute Name="{saml.ROLE_ATTRIBUTE}">{values}</saml2:Attribute>
        </saml2:AttributeStatement>
      </saml2:Assertion>
    </saml2p:Response>"""
    return base64.b64encode(xml.encode()).decode()


class TestParse:
    def test_reads_roles_in_either_order(self):
        response = make_response(f"{ROLE},{PROVIDER}", f"{OTHER_PROVIDER},{OTHER_ROLE}")

        assertion = saml.parse(response)

        assert assertion.roles == [
            saml.Role(ROLE, PROVIDER),
            saml.Role(OTHER_ROLE, OTHER_PROVIDER),
        ]
        assert assertion.raw == response
        assert assertion.destination == AWS_SAML

    def test_destination_falls_back_to_recipient(self):
        assertion = saml.parse(make_response(f"{ROLE},{PROVIDER}", destination=""))

        assert assertion.destination == AWS_SAML

    def test_no_roles(self):
        assert not saml.parse(make_response()).roles

    def test_not_xml(self):
        with pytest.raises(saml.SAMLError, match="not base64 XML"):
            saml.parse(base64.b64encode(b"not xml").decode())


class TestParseRole:
    def test_needs_both_arns(self):
        with pytest.raises(saml.SAMLError, match="Cannot read"):
            saml.parse_role(ROLE)

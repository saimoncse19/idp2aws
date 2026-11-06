import base64

import pytest
from playwright.sync_api import BrowserType

from idp2aws import browser

ZETA = "arn:aws:iam::999999999999:role/ZetaAdmin"
ALPHA_DEV = "arn:aws:iam::111111111111:role/AlphaDev"
ALPHA_READ = "arn:aws:iam::111111111111:role/AlphaRead"
START_URL = "https://idp.test/start"


def make_saml(*role_arns):
    values = "".join(
        f"<saml2:AttributeValue>{arn},arn:aws:iam::{arn.split(':')[4]}:saml-provider/G"
        "</saml2:AttributeValue>"
        for arn in role_arns
    )
    xml = f"""<saml2p:Response xmlns:saml2p="urn:oasis:names:tc:SAML:2.0:protocol"
      Destination="https://signin.aws.amazon.com/saml"><saml2:Assertion
      xmlns:saml2="urn:oasis:names:tc:SAML:2.0:assertion"><saml2:AttributeStatement>
      <saml2:Attribute Name="https://aws.amazon.com/SAML/Attributes/Role">{values}
      </saml2:Attribute></saml2:AttributeStatement></saml2:Assertion></saml2p:Response>"""
    return base64.b64encode(xml.encode()).decode()


def make_idp_page(saml_response):
    return f"""<form id="f" method="post" action="https://signin.aws.amazon.com/saml">
    <input type="hidden" name="SAMLResponse" value="{saml_response}"></form>
    <script>document.getElementById("f").submit()</script>"""


def make_account(name, role_arns):
    radios = "".join(
        f'<div class="saml-account"><div class="saml-role"><input type="radio" '
        f'name="roleIndex" value="{arn}" id="{arn}"><label for="{arn}">{arn}</label>'
        "</div></div>"
        for arn in role_arns
    )
    return (
        f'<div class="saml-account"><div><div class="saml-account-name">Account: {name}'
        f"</div></div>{radios}</div>"
    )


# Lists "zeta" first, then submits the first role on the page after it loads.
def make_role_page(saml_response):
    return f"""<form id="saml_form" action="/saml" method="post">
    <input type="hidden" name="SAMLResponse" value="{saml_response}">
    <fieldset>
    {make_account("zeta (999999999999)", [ZETA])}
    {make_account("alpha (111111111111)", [ALPHA_DEV, ALPHA_READ])}
    </fieldset></form>
    <script>
    window.addEventListener("load", () => {{
      document.querySelector("input[name=roleIndex]").checked = true;
      document.getElementById("saml_form").submit();
    }});
    </script>"""


@pytest.fixture
def fake_sites(monkeypatch, tmp_path):
    sites = {"saml": "", "role_page_loads": 0}
    launch = BrowserType.launch_persistent_context

    def serve_role_page(route):
        sites["role_page_loads"] += 1
        route.fulfill(content_type="text/html", body=make_role_page(sites["saml"]))

    def launch_headless(self, user_data_dir, **kwargs):
        context = launch(self, user_data_dir, **(kwargs | {"headless": True}))
        context.route(
            "https://idp.test/**",
            lambda route: route.fulfill(
                content_type="text/html", body=make_idp_page(sites["saml"])
            ),
        )
        # Routes added later run first, so idp2aws sees the post before this.
        context.route(browser.AWS_SAML_URL, serve_role_page)
        return context

    monkeypatch.setattr(BrowserType, "launch_persistent_context", launch_headless)
    monkeypatch.setattr(browser, "PROFILE_DIR", tmp_path / "profile")
    return sites


# Starts headless Chrome, so it only runs with: pytest -m browser
@pytest.mark.browser
class TestLogIn:
    def test_role_page_is_sorted_and_pick_is_caught(self, fake_sites):
        fake_sites["saml"] = make_saml(ZETA, ALPHA_DEV, ALPHA_READ)

        result = browser.log_in(START_URL, timeout_secs=30)

        assert result.picked_role_arn == ALPHA_DEV
        assert result.saml_response == fake_sites["saml"]
        assert fake_sites["role_page_loads"] == 1

    def test_known_role_skips_role_page(self, fake_sites):
        fake_sites["saml"] = make_saml(ZETA, ALPHA_DEV)

        result = browser.log_in(START_URL, role_arn=ZETA, timeout_secs=30)

        assert result.picked_role_arn is None
        assert fake_sites["role_page_loads"] == 0

    def test_single_role_skips_role_page(self, fake_sites):
        fake_sites["saml"] = make_saml(ZETA)

        result = browser.log_in(START_URL, timeout_secs=30)

        assert result.picked_role_arn is None
        assert fake_sites["role_page_loads"] == 0


class TestAwsSamlUrl:
    @pytest.mark.parametrize(
        ("url", "is_match"),
        [
            ("https://signin.aws.amazon.com/saml", True),
            ("https://us-east-1.signin.aws.amazon.com/saml?SAMLart=1", True),
            ("https://signin.amazonaws-us-gov.com/saml/", True),
            ("https://signin.aws.amazon.com/saml-other", False),
            ("https://signin.aws.amazon.com/static/saml.js", False),
        ],
    )
    def test_matches_only_the_saml_endpoint(self, url, is_match):
        assert bool(browser.AWS_SAML_URL.search(url)) is is_match

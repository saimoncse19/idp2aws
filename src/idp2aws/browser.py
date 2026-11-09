"""Module for signing in with a real browser and catching the SAML response.

The browser opens the start URL of your IdP. You sign in as usual, with any
kind of 2-Step Verification. Then the IdP posts the SAML response to the AWS
sign-in page. Two things can happen next:

* You have more than one role and no role is chosen yet. We let the post go
  to AWS, and AWS shows its role page, with the accounts sorted by name. When
  you click *Sign In*, the page posts the SAML response again, with the role
  that you picked. We stop this second post.
* In all other cases, we stop the first post.

The browser profile stays between runs. While your IdP session is active,
the window opens and closes without input from you.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs

from playwright.sync_api import BrowserContext, Request, Route, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from idp2aws import saml
from idp2aws.settings import HOME

PROFILE_DIR = HOME / "browser-profile"
AWS_SAML_URL = re.compile(
    r"^https://([a-z0-9-]+\.)?signin\."
    r"(aws\.amazon\.com|amazonaws-us-gov\.com|amazonaws\.cn)/saml/?(\?.*)?$"
)
# Playwright starts Chrome with these by default. They make Chrome keep the
# cookies in the browser profile with a fixed key, instead of a key from the
# macOS Keychain or the Linux keyring.
WEAK_COOKIE_KEY_ARGS = ["--use-mock-keychain", "--password-store=basic"]
SORT_ACCOUNTS_SCRIPT = """
if (location.pathname === "/saml" && location.hostname.includes("signin.")) {
  document.addEventListener("DOMContentLoaded", () => {
    const fieldset = document.querySelector("#saml_form fieldset");
    if (!fieldset) return;
    const name = (account) =>
      (account.querySelector(".saml-account-name")?.textContent ?? "")
        .replace("Account:", "").trim();
    const accounts = [...fieldset.querySelectorAll(":scope > div.saml-account")];
    accounts.sort((a, b) => name(a).localeCompare(name(b)));
    fieldset.append(...accounts);
  });
}
"""


class LoginError(Exception):
    """Raise when the browser login ends without a SAML response."""


@dataclass
class BrowserLogin:
    """What the browser login produced.

    :param saml_response: The base64 ``SAMLResponse`` value.
    :param picked_role_arn: Role picked on the AWS page, or ``None`` if the
        page was not shown.
    """

    saml_response: str
    picked_role_arn: str | None


def log_in(
    start_url: str,
    browser: str = "chrome",
    role_arn: str | None = None,
    timeout_secs: int = 300,
) -> BrowserLogin:
    """Open a browser at the IdP and wait for the login to reach AWS.

    :param start_url: Start URL of your IdP for AWS.
    :param browser: ``chrome`` or ``msedge`` for your installed Chrome or
        Edge, or ``chromium`` for the one from ``playwright install chromium``.
    :param role_arn: Role already chosen. If set, the AWS role page is skipped.
    :param timeout_secs: How long to wait for you to finish.
    :return: The SAML response, and the role if you picked one.
    :raises LoginError: If the window is closed or the time runs out.
    """
    result = []

    def catch(route: Route, request: Request) -> None:
        if request.method != "POST":
            route.fallback()
            return
        form = parse_qs(request.post_data or "")
        saml_response = form.get("SAMLResponse", [""])[0]
        picked = form.get("roleIndex", [None])[0]
        if not (picked or role_arn) and _has_several_roles(saml_response):
            route.fallback()  # Let AWS show its role page.
            return
        result.append(BrowserLogin(saml_response, picked))
        route.abort()

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                PROFILE_DIR,
                channel=None if browser == "chromium" else browser,
                headless=False,
                # Playwright turns the sandbox off by default, and Chrome then
                # warns about the "--no-sandbox" flag.
                chromium_sandbox=True,
                # "--enable-automation" shows the "controlled by automated test
                # software" bar, which can make Google say the browser "may not
                # be secure".
                ignore_default_args=["--enable-automation", *WEAK_COOKIE_KEY_ARGS],
            )
        except PlaywrightError as error:
            raise LoginError(_explain_launch_error(error, browser)) from None
        try:
            context.add_init_script(SORT_ACCOUNTS_SCRIPT)
            context.route(AWS_SAML_URL, catch)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(start_url)
            _wait_until(lambda: bool(result), context, timeout_secs)
        finally:
            context.close()

    return result[0]


def _explain_launch_error(error: PlaywrightError, browser: str) -> str:
    """Turn a browser start-up error into a message that says what to do.

    :param error: Error from Playwright.
    :param browser: The browser that failed to start.
    :return: A short message for the user.
    """
    message = str(error)
    if "ProcessSingleton" in message:
        return (
            "Another idp2aws login is using the browser profile. "
            "Finish or close it, then try again."
        )
    if "is not found" in message or "Executable doesn't exist" in message:
        return f"Cannot find {browser}. Install it, or set a different browser."
    return f"Cannot start {browser}: {message.splitlines()[0]}"


def _has_several_roles(saml_response: str) -> bool:
    """Tell whether the SAML response offers more than one role.

    :param saml_response: The base64 ``SAMLResponse`` value.
    :return: ``False`` if it lists one role or cannot be read. The caller
        reports an unreadable response.
    """
    try:
        return len(saml.parse(saml_response).roles) > 1
    except saml.SAMLError:
        return False


def _wait_until(
    is_done: Callable[[], bool], context: BrowserContext, timeout_secs: int
) -> None:
    """Let the browser run until ``is_done`` returns ``True``.

    Playwright only handles browser events while we call into it, so we wait
    in short steps on the page instead of sleeping.

    :param is_done: Check that ends the wait.
    :param context: The open browser.
    :param timeout_secs: How long to wait.
    :raises LoginError: If the window is closed or the time runs out.
    """
    deadline = time.monotonic() + timeout_secs
    while not is_done():
        if not context.pages:
            raise LoginError("The browser window was closed before the login finished.")
        if time.monotonic() > deadline:
            raise LoginError(f"The login did not finish within {timeout_secs} seconds.")
        try:
            context.pages[0].wait_for_timeout(250)
        except PlaywrightError:
            pass  # The page closed during the wait. The next loop checks again.

from __future__ import annotations

from backend.config import settings

from .base_page import BasePage


class LoginPage(BasePage):
    def open(self):
        self.goto(self.adapter.login_url())
        return self

    def login(self, username: str, password: str):
        self.locator("login_user").fill(username)
        self.locator("login_password").fill(password)
        # no_wait_after: the click itself succeeds quickly, but booting the web
        # client on a production-sized database (69k products) regularly takes
        # longer than Playwright's default action timeout. Waiting for the
        # navigation separately, on the navigation budget, keeps a slow boot
        # from being reported as a failed click.
        self.locator("login_submit").click(no_wait_after=True)
        # Wait for the URL to actually leave /web/login. wait_for_load_state
        # alone returns as soon as the CURRENT document is loaded, which is
        # still the login page, so is_logged_in() would inspect the URL before
        # the redirect landed and report a false negative.
        try:
            self.page.wait_for_url(
                lambda url: "/web/login" not in url,
                timeout=settings.nav_timeout_ms)
        except Exception:
            pass                     # is_logged_in()/error_message() decide

    def is_logged_in(self) -> bool:
        if "/web/login" in self.page.url:
            return False
        # the web client can take tens of seconds to render on a
        # production-sized database; use the navigation budget, not the
        # short element budget
        return self.exists("webclient_ready",
                           timeout=settings.nav_timeout_ms)

    def error_message(self) -> str:
        if self.exists("login_error", timeout=1500):
            return self.locator("login_error").inner_text().strip()
        return ""

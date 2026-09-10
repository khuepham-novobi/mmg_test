"""TEST-SMOKE-001 — Login & Sales app opens (UI).

Excel traceability: TC-SMK-003 "Login and every top-level menu opens"
(P0 / SMOKE / suite SMK), scoped for the MVP to login + the Sales app.
"""
from framework.registry import test_case
from pages import LoginPage, SalesPage


@test_case(
    id="TEST-SMOKE-001",
    name="Login & Sales app opens",
    workflow="SMOKE",
    workflow_name="Post-upgrade smoke",
    module="Platform",
    priority="P0",
    kind="UI",
    order=10,
    description="Log in through the real web client and open the Sales app. "
                "Fails on bad credentials, boot errors or a broken Sales menu.",
    traceability={
        "tc_ids": ["TC-SMK-003"],
        "feature": "— (cross-cutting / technical verification)",
        "user_story": "As any user, I can log in and open every top-level "
                      "menu, so the upgraded instance is usable at all.",
        "source": "MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx / Test Execution",
    },
)
def test_smoke_login(ctx):
    env = ctx.env

    with ctx.step("Verify Odoo server is reachable (XML-RPC version ping)"):
        server_version = ctx.adapter.rpc.server_version()
        ctx.log(f"Server reports version: {server_version}")

    with ctx.step("Open login page"):
        page = ctx.browser_page()
        login = LoginPage(page, ctx.adapter).open()

    with ctx.step(f"Log in as {env.username}"):
        login.login(env.username, env.password)
        err = "" if login.is_logged_in() else (login.error_message() or
                                               f"still on {page.url}")
        ctx.check("Login succeeded", expected=True, actual=err == "")

    with ctx.step("Open the Sales app"):
        sales = SalesPage(page, ctx.adapter).open()
        ctx.check("Sales list view rendered", expected=True,
                  actual=sales.is_loaded())

    ctx.screenshot("sales-app-open")

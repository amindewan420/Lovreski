"""Playwright script body for AdminPage SBP phone masked/reveal verification iteration 16."""

async def run(page):
    CORRECT = "+79780369381"
    WRONG = "+79783069381"
    BASE = "https://lovreski-dating.preview.emergentagent.com"

    try:
        await page.set_viewport_size({"width": 1920, "height": 1080})
        page.on("dialog", lambda dialog: dialog.accept())
        await page.goto(BASE + "/", wait_until="domcontentloaded")
        await page.get_by_test_id("mode-login").click()
        await page.get_by_test_id("input-email").fill("admin@lovreski.ru")
        await page.get_by_test_id("input-password").fill("LovreskiAdmin2026!")
        await page.get_by_test_id("submit-auth").click()
        await page.wait_for_url("**/admin", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=30000)

        await page.get_by_test_id("admin-tab-settings").click()
        await page.get_by_test_id("admin-sbp-current").wait_for(state="visible", timeout=30000)
        masked = (await page.get_by_test_id("admin-sbp-current").inner_text()).strip()
        if masked != "+7 (***) ***-**-81":
            raise AssertionError(f"Admin settings masked current expected '+7 (***) ***-**-81', got {masked!r}")
        if WRONG in await page.evaluate("document.body.innerText"):
            raise AssertionError(f"Old wrong SBP phone {WRONG} appears in admin settings masked UI")

        await page.get_by_test_id("admin-sbp-reveal").click()
        await page.wait_for_timeout(1000)
        revealed = (await page.get_by_test_id("admin-sbp-current").inner_text()).strip()
        if revealed != CORRECT:
            raise AssertionError(f"Admin settings reveal expected {CORRECT}, got {revealed!r}")
        html = await page.evaluate("document.documentElement.outerHTML")
        if WRONG in html:
            raise AssertionError(f"Old wrong SBP phone {WRONG} appears after admin reveal")

        # Get error messages using specific selectors
        error_text = await page.evaluate("""() => {
        const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
        return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")

        await page.screenshot(path="/app/test_reports/admin_sbp_phone_iter16.png", quality=40, full_page=False)
        print("Admin SBP phone UI check passed")
    except Exception as e:
        print(f"Admin SBP phone UI check failed: {e}")
        raise
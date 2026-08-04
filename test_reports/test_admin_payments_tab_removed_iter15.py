"""Playwright script body used by the browser automation tool.

Focused UI regression: AdminPage should expose the Support tab with pending badge
and should not expose the removed Payments tab data-testid.
"""
async def run(page):
    try:
        await page.set_viewport_size({"width": 1920, "height": 1080})
        print("Opened desktop viewport")

        await page.goto("https://lovreski-dating.preview.emergentagent.com/", wait_until="domcontentloaded")
        print("Loaded Lovreski landing page")

        await page.get_by_test_id("mode-login").click()
        await page.get_by_test_id("input-email").fill("admin@lovreski.ru")
        await page.get_by_test_id("input-password").fill("LovreskiAdmin2026!")
        await page.get_by_test_id("submit-auth").click()
        print("Submitted admin login")

        await page.wait_for_url("**/admin", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=30000)
        print("Admin page loaded")

        support_tab = page.get_by_test_id("admin-tab-support")
        await support_tab.wait_for(state="visible", timeout=30000)
        print("Support tab is visible")

        payments_count = await page.get_by_test_id("admin-tab-payments").count()
        if payments_count != 0:
            raise AssertionError(f"Payments tab should be removed, but found {payments_count} element(s)")
        print("Payments tab data-testid is absent")

        badge = page.get_by_test_id("pending-badge").first
        await badge.wait_for(state="visible", timeout=30000)
        badge_text = (await badge.inner_text()).strip()
        if not badge_text or not badge_text.isdigit() or int(badge_text) < 1:
            raise AssertionError(f"Pending badge should show a positive count, got {badge_text!r}")
        print(f"Support pending badge visible with count {badge_text}")

        # Get error messages using specific selectors
        error_text = await page.evaluate("""() => {
        const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
        return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")

        await page.screenshot(path="/app/test_reports/admin_tabs_iter15.png", quality=40, full_page=False)
        print("UI regression check passed")
    except Exception as e:
        print(f"UI regression check failed: {e}")
        raise
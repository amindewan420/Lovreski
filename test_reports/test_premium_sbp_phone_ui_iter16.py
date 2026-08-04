"""Playwright script body for PremiumPage SBP phone bug verification iteration 16."""

async def run(page):
    import time

    CORRECT = "+79780369381"
    WRONG = "+79783069381"
    BASE = "https://lovreski-dating.preview.emergentagent.com"
    API = BASE + "/api"

    try:
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
        print("Opened desktop viewport and granted clipboard permissions")

        ts = int(time.time())
        email = f"sbpui_{ts}@lovreski.ru"
        reg = await page.request.post(API + "/auth/register", data={
            "email": email,
            "password": "password123",
            "name": f"SBP UI QA {ts}",
            "gender": "male",
            "dob": "1998-05-15",
        })
        if not reg.ok:
            raise AssertionError(f"register failed {reg.status}: {await reg.text()}")
        reg_json = await reg.json()
        token = reg_json["token"]
        print(f"Registered fresh UI user {email}")

        await page.goto(BASE + "/", wait_until="domcontentloaded")
        await page.evaluate("token => localStorage.setItem('lovreski_token', token)", token)
        await page.goto(BASE + "/premium", wait_until="domcontentloaded")
        print("Navigated to PremiumPage with authenticated token")

        phone_el = page.get_by_test_id("sbp-phone")
        await phone_el.wait_for(state="visible", timeout=30000)
        await page.wait_for_timeout(1000)
        phone_text = (await phone_el.inner_text()).strip()
        if phone_text != CORRECT:
            raise AssertionError(f"PremiumPage sbp-phone expected {CORRECT}, got {phone_text!r}")
        print(f"PremiumPage displays corrected SBP phone: {phone_text}")

        body_text = await page.evaluate("document.body.innerText")
        outer_html = await page.evaluate("document.documentElement.outerHTML")
        if WRONG in body_text or WRONG in outer_html:
            raise AssertionError(f"Old wrong SBP phone {WRONG} appears in rendered PremiumPage DOM")
        if CORRECT not in body_text:
            raise AssertionError("Correct SBP phone not found in visible PremiumPage text")
        print("Rendered PremiumPage text/HTML contains corrected phone and does not contain old wrong phone")

        await page.get_by_test_id("btn-copy-phone").click()
        await page.wait_for_timeout(500)
        copied = await page.evaluate("navigator.clipboard.readText()")
        if copied != CORRECT:
            raise AssertionError(f"Clipboard expected {CORRECT}, got {copied!r}")
        print(f"Copy button copied exact corrected phone: {copied}")

        # Get error messages using specific selectors
        error_text = await page.evaluate("""() => {
        const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
        return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")

        await page.screenshot(path="/app/test_reports/premium_sbp_phone_iter16.png", quality=40, full_page=False)
        print("PremiumPage SBP phone UI check passed")
    except Exception as e:
        print(f"PremiumPage SBP phone UI check failed: {e}")
        raise
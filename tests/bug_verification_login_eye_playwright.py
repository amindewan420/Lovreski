"""
Focused Playwright checks for the reported Landing auth bug:
- password eye toggle visibility/type/icon state
- nonexistent login auto-switches to register and preserves email/password
- fresh registration, duplicate registration, and wrong-password login regressions

This file mirrors the script executed via the browser automation tool in this run.
"""

# Intended to run inside the provided async Playwright context where `page` exists.

async def run(page):
    try:
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.context.clear_cookies()
        await page.add_init_script("localStorage.clear(); sessionStorage.clear();")
        await page.goto("https://lovreski-dating.preview.emergentagent.com/", wait_until="networkidle")
        print("STEP 1: Landing page loaded")

        h1_text = (await page.locator("h1").first.inner_text()).strip()
        assert h1_text == "Lovreski", f"Hero H1 expected only 'Lovreski', got {h1_text!r}"
        print("PASS: Hero H1 shows only Lovreski")

        email_input = page.get_by_test_id("input-email")
        password_input = page.get_by_test_id("input-password")
        toggle = page.get_by_test_id("toggle-password")
        await email_input.wait_for(state="visible", timeout=10000)
        await password_input.wait_for(state="visible", timeout=10000)
        await toggle.wait_for(state="visible", timeout=10000)
        password_box = await password_input.bounding_box()
        toggle_box = await toggle.bounding_box()
        assert password_box and toggle_box, "Could not read password/toggle bounds"
        assert toggle_box["x"] > password_box["x"] + password_box["width"] * 0.80, "Toggle is not positioned on the right side of the password field"
        print("PASS: Password eye toggle is visible and positioned on the right")

        initial_type = await password_input.get_attribute("type")
        initial_icon_class = await toggle.locator("svg").get_attribute("class")
        initial_label = await toggle.get_attribute("aria-label")
        assert initial_type == "password", f"Initial password type expected password, got {initial_type}"
        assert initial_icon_class and "eye" in initial_icon_class.lower(), f"Initial icon class did not expose Eye state: {initial_icon_class}"
        await toggle.click(force=True)
        await page.wait_for_timeout(200)
        shown_type = await password_input.get_attribute("type")
        shown_icon_class = await toggle.locator("svg").get_attribute("class")
        shown_label = await toggle.get_attribute("aria-label")
        assert shown_type == "text", f"After first toggle expected text, got {shown_type}"
        assert shown_icon_class != initial_icon_class or shown_label != initial_label, "Eye icon/label did not change after showing password"
        await toggle.click(force=True)
        await page.wait_for_timeout(200)
        hidden_type = await password_input.get_attribute("type")
        hidden_icon_class = await toggle.locator("svg").get_attribute("class")
        hidden_label = await toggle.get_attribute("aria-label")
        assert hidden_type == "password", f"After second toggle expected password, got {hidden_type}"
        assert hidden_icon_class == initial_icon_class or hidden_label == initial_label, "Eye icon/label did not return to initial hidden state"
        print("PASS: Password toggle changes type and icon/label states")

        ts = await page.evaluate("Date.now()")
        fresh_email = f"eyetest_{ts}@lovreski.ru"
        good_password = "password123"

        await email_input.fill(fresh_email)
        await password_input.fill(good_password)
        await page.get_by_test_id("submit-auth").click(force=True)
        await page.get_by_test_id("input-name").wait_for(state="visible", timeout=10000)
        body_text = await page.locator("body").inner_text(timeout=5000)
        assert "Account not found" in body_text or "регистрацию" in body_text, "Expected account-not-found/register-switch toast text was not visible"
        assert await page.get_by_test_id("input-email").input_value() == fresh_email, "Email was not preserved after auto-switch to register"
        assert await page.get_by_test_id("input-password").input_value() == good_password, "Password was not preserved after auto-switch to register"
        register_class = await page.get_by_test_id("mode-register").get_attribute("class")
        assert register_class and "bg-card" in register_class, f"Register tab did not appear active: {register_class}"
        print("PASS: Nonexistent login auto-switches to active Register tab and preserves credentials with explanatory toast")

        await page.get_by_test_id("input-name").fill("Eye Toggle Tester")
        await page.get_by_test_id("input-gender").select_option("male")
        await page.get_by_test_id("input-dob").fill("1998-05-15")
        await page.get_by_test_id("submit-auth").click(force=True)
        await page.wait_for_url("**/home", timeout=15000)
        print(f"PASS: Fresh registration succeeded and landed on /home for {fresh_email}")

        await page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await page.context.clear_cookies()
        await page.goto("https://lovreski-dating.preview.emergentagent.com/", wait_until="networkidle")
        await page.get_by_test_id("mode-register").click(force=True)
        await page.wait_for_timeout(200)
        await page.get_by_test_id("input-name").fill("Duplicate Tester")
        await page.get_by_test_id("input-email").fill(fresh_email)
        await page.get_by_test_id("input-password").fill(good_password)
        await page.get_by_test_id("input-dob").fill("1998-05-15")
        await page.get_by_test_id("submit-auth").click(force=True)
        await page.wait_for_timeout(1500)
        duplicate_text = await page.locator("body").inner_text(timeout=5000)
        assert "Email already exists" in duplicate_text, "Duplicate registration did not show 'Email already exists' toast"
        print("PASS: Duplicate registration shows Email already exists toast")

        await page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await page.context.clear_cookies()
        await page.goto("https://lovreski-dating.preview.emergentagent.com/", wait_until="networkidle")
        await page.get_by_test_id("input-email").fill(fresh_email)
        await page.get_by_test_id("input-password").fill("wrongpassword123")
        await page.get_by_test_id("submit-auth").click(force=True)
        await page.wait_for_timeout(1500)
        wrong_text = await page.locator("body").inner_text(timeout=5000)
        assert "Incorrect password" in wrong_text, "Wrong password login did not show Incorrect password toast"
        assert await page.get_by_test_id("input-name").count() == 0, "Wrong-password login unexpectedly switched to register mode"
        print("PASS: Wrong-password login shows Incorrect password and remains in login mode")

        error_text = await page.evaluate("""() => {
        const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
        return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")

        print("RESULT: SUCCESS - focused bug verification passed")
    except Exception as exc:
        print(f"RESULT: FAILURE - {exc}")
        raise
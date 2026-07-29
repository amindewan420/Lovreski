"""Focused frontend Playwright verification for Lovreski auth bug.

This script is stored as the test artifact. The same async body is executed via
the browser automation harness in this environment.
"""

async def run(page):
    import re
    import time
    from urllib.parse import urlparse, parse_qs, unquote

    errors = []
    page_errors = []
    console_errors = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type in ["error"] else None)

    async def check(condition, message, details=None):
        if condition:
            print(f"PASS: {message}")
        else:
            error = f"FAIL: {message} :: {details}"
            print(error)
            errors.append(error)

    async def report_error_elements():
        # Get error messages using specific selectors
        error_text = await page.evaluate("""() => {
        const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
        return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")

    try:
        await page.set_viewport_size({"width": 1920, "height": 1080})
        base_url = page.url.rstrip("/")
        await page.context.clear_cookies()
        await page.goto(base_url + "/", wait_until="domcontentloaded")
        await page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await page.wait_for_load_state("networkidle")
        await report_error_elements()

        h1_texts = [t.strip() for t in await page.locator("h1").all_inner_texts()]
        await check(h1_texts == ["Lovreski"], "Hero H1 displays only 'Lovreski'", h1_texts)
        forbidden = ["Настоящие знакомства", "Без масок", "Умный подбор", "no subheadline"]
        body_text = await page.locator("body").inner_text()
        await check(not any(term in body_text for term in forbidden), "Forbidden old tagline/subheadline text is absent", body_text[:500])

        ts = int(time.time() * 1000)
        email = f"bugui_{ts}@lovreski.ru"
        password = "password123"

        # Brand-new UI registration succeeds and navigates to authenticated home.
        await page.get_by_test_id("mode-register").click()
        await page.get_by_test_id("input-name").fill("Frontend Bug User")
        await page.get_by_test_id("input-email").fill(email)
        await page.get_by_test_id("input-password").fill(password)
        await page.get_by_test_id("submit-auth").click()
        await page.wait_for_url(re.compile(r".*/home$"), timeout=15000)
        token = await page.evaluate("localStorage.getItem('lovreski_token')")
        await check(bool(token), "Successful UI registration stores JWT token", token[:20] + "..." if token else None)
        await check(page.url.endswith("/home"), "Successful UI registration reaches /home", page.url)

        # Duplicate UI registration shows exact toast.
        await page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await page.context.clear_cookies()
        await page.goto(base_url + "/", wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        await page.get_by_test_id("mode-register").click()
        await page.get_by_test_id("input-name").fill("Frontend Bug User")
        await page.get_by_test_id("input-email").fill(email)
        await page.get_by_test_id("input-password").fill(password)
        await page.get_by_test_id("submit-auth").click()
        await page.get_by_text("Email already exists", exact=True).wait_for(timeout=10000)
        toast_text = await page.get_by_text("Email already exists", exact=True).inner_text()
        await check(toast_text == "Email already exists", "Duplicate signup toast shows exact English message", toast_text)
        body_text_dup = await page.locator("body").inner_text()
        await check("wrong email or password" not in body_text_dup.lower(), "Duplicate signup does not show generic wrong email/password", body_text_dup)
        await report_error_elements()

        # Wrong password UI login shows exact toast.
        await page.get_by_test_id("mode-login").click()
        await page.get_by_test_id("input-email").fill(email)
        await page.get_by_test_id("input-password").fill("wrongpass123")
        await page.get_by_test_id("submit-auth").click()
        await page.get_by_text("Incorrect password", exact=True).wait_for(timeout=10000)
        wrong_toast = await page.get_by_text("Incorrect password", exact=True).inner_text()
        await check(wrong_toast == "Incorrect password", "Wrong-password login toast shows exact English message", wrong_toast)
        body_text_wrong = await page.locator("body").inner_text()
        await check("wrong email or password" not in body_text_wrong.lower(), "Wrong-password login does not show generic wrong email/password", body_text_wrong)
        await report_error_elements()

        # Correct UI login still succeeds after an error.
        await page.get_by_test_id("input-email").fill(email)
        await page.get_by_test_id("input-password").fill(password)
        await page.get_by_test_id("submit-auth").click()
        await page.wait_for_url(re.compile(r".*/home$"), timeout=15000)
        await check(page.url.endswith("/home"), "Correct UI login reaches /home", page.url)

        # Google Sign-in button constructs dynamic Emergent OAuth redirect.
        await page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await page.context.clear_cookies()
        await page.goto(base_url + "/", wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        origin = await page.evaluate("window.location.origin")
        async with page.expect_request(lambda req: req.url.startswith("https://auth.emergentagent.com/"), timeout=10000) as req_info:
            await page.get_by_test_id("google-auth").click()
        auth_request = await req_info.value
        auth_url = auth_request.url
        parsed = urlparse(auth_url)
        redirect_values = parse_qs(parsed.query).get("redirect", [])
        redirect_value = redirect_values[0] if redirect_values else None
        await check(parsed.scheme == "https" and parsed.netloc == "auth.emergentagent.com", "Google button redirects to Emergent auth host", auth_url)
        await check(redirect_value == origin + "/home", "Google redirect param points to current origin + /home", {"actual": redirect_value, "expected": origin + "/home", "auth_url": auth_url})
        await page.goto(base_url + "/", wait_until="domcontentloaded")

        await page.wait_for_timeout(1000)
        await check(len(page_errors) == 0, "No uncaught page JS errors during auth UI flows", page_errors)
        unexpected_console_errors = [e for e in console_errors if not e.startswith("Failed to load resource:")]
        await check(len(unexpected_console_errors) == 0, "No unexpected console.error entries during auth UI flows", unexpected_console_errors)

        if errors:
            raise AssertionError("; ".join(errors))
        print("FRONTEND_AUTH_TEST_RESULT: PASS")
    except Exception as exc:
        print(f"FRONTEND_AUTH_TEST_RESULT: FAIL: {exc}")
        if page_errors:
            print(f"PAGE_ERRORS: {page_errors}")
        if console_errors:
            print(f"CONSOLE_ERRORS: {console_errors}")
        raise
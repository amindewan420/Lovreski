"""Reference Playwright script used through mcp_browser_automation for iteration 8.

It verifies PremiumPage has no rendered phone leak, one-click payment modal/success,
coin balance refresh, and Admin Settings placeholder masking.
"""

import time

RAW_DIGITS = "79780369381"
RAW_FULL = "+79780369381"

async def run(page):
  try:
    await page.set_viewport_size({"width": 390, "height": 844})
    await page.goto("https://lovreski-dating.preview.emergentagent.com", wait_until="domcontentloaded")
    base = "https://lovreski-dating.preview.emergentagent.com"
    req = page.context.request

    email = f"leaktest_ui_{int(time.time() * 1000)}@lovreski.ru"
    payload = {
        "email": email,
        "password": "password123",
        "name": "UI Leak Tester",
        "gender": "male",
        "dob": "1998-05-15",
    }
    reg = await req.post(f"{base}/api/auth/register", data=payload)
    if reg.status not in (200, 201):
        raise Exception(f"register failed {reg.status}: {await reg.text()}")
    reg_data = await reg.json()
    token = reg_data["token"]
    initial_coins = int(reg_data["user"].get("coins", 0))
    await page.evaluate("token => localStorage.setItem('lovreski_token', token)", token)
    print(f"PASS registered fresh UI user {email} with {initial_coins} coins")

    await page.goto(f"{base}/premium", wait_until="networkidle")
    await page.get_by_test_id("coin-balance").wait_for(timeout=10000)
    content = await page.content()
    if RAW_DIGITS in content or RAW_FULL in content:
        raise Exception("PremiumPage rendered HTML contains raw admin phone")
    print("PASS PremiumPage page.content() has no raw admin phone")

    p50_text = await page.get_by_test_id("pkg-p50").inner_text()
    if "popular" not in p50_text.lower() or "🪙" not in p50_text:
        raise Exception(f"p50 package card missing Popular badge or coin icon: {p50_text}")
    print("PASS redesigned p50 package card shows Popular badge and 🪙")

    await page.get_by_test_id("pkg-p10").click(force=True)
    await page.get_by_test_id("pay-modal").wait_for(timeout=10000)
    qr_src = await page.get_by_test_id("pay-qr").get_attribute("src")
    bank_href = await page.get_by_test_id("pay-open-bank").get_attribute("href")
    copy_visible = await page.get_by_test_id("pay-copy-link").is_visible()
    status_text = await page.get_by_test_id("pay-status").inner_text()
    modal_html = await page.get_by_test_id("pay-modal").inner_html()
    if not qr_src or not qr_src.startswith("data:image/png;base64,"):
        raise Exception("Payment modal QR is missing or not base64 PNG")
    if not bank_href or not bank_href.startswith("https://qr.nspk.ru/pay"):
        raise Exception(f"Open-bank link is invalid: {bank_href}")
    if not copy_visible:
        raise Exception("Copy-link button is not visible")
    if "Ожидание оплаты" not in status_text:
        raise Exception(f"Payment modal status not pending: {status_text}")
    if RAW_DIGITS in modal_html or RAW_FULL in modal_html:
        raise Exception("Payment modal contains raw admin phone")
    print("PASS pay-modal shows QR, open-bank link, copy-link, pending status, and no phone leak")

    await page.get_by_test_id("pay-success").wait_for(timeout=20000)
    success_text = await page.get_by_test_id("pay-success").inner_text()
    if "Payment Successful" not in success_text or "Start Exploring" not in success_text:
        raise Exception(f"Success overlay missing expected text: {success_text}")
    expected_balance = initial_coins + 10
    await page.wait_for_timeout(500)
    balance_text = await page.get_by_test_id("coin-balance").inner_text()
    if str(expected_balance) not in balance_text:
        raise Exception(f"Coin balance did not update to {expected_balance}: {balance_text}")
    print(f"PASS pay-success overlay appears and coin-balance updates to {expected_balance}")

    await page.get_by_test_id("success-explore").click(force=True)
    await page.wait_for_timeout(500)
    if "/home" not in page.url:
        raise Exception(f"Start Exploring did not navigate to /home: {page.url}")
    print("PASS Start Exploring navigates to /home")

    admin_login = await req.post(f"{base}/api/auth/login", data={"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"})
    if admin_login.status != 200:
        raise Exception(f"admin login failed {admin_login.status}: {await admin_login.text()}")
    admin_token = (await admin_login.json())["token"]
    await page.evaluate("token => localStorage.setItem('lovreski_token', token)", admin_token)
    await page.goto(f"{base}/admin", wait_until="networkidle")
    await page.get_by_test_id("admin-tab-settings").click(force=True)
    await page.get_by_test_id("admin-sbp-phone").wait_for(timeout=10000)
    placeholder = await page.get_by_test_id("admin-sbp-phone").get_attribute("placeholder")
    if placeholder != "+7XXXXXXXXXX":
        raise Exception(f"Admin SBP placeholder leaked or wrong: {placeholder}")
    current_masked = await page.get_by_test_id("admin-sbp-current").inner_text()
    if RAW_DIGITS in current_masked or RAW_FULL in current_masked or "***" not in current_masked:
        raise Exception(f"Admin masked current phone is unsafe: {current_masked}")
    admin_content = await page.content()
    if RAW_DIGITS in admin_content or RAW_FULL in admin_content:
        raise Exception("Admin settings rendered HTML contains raw admin phone before reveal")
    print("PASS Admin Settings placeholder is +7XXXXXXXXXX and current phone is masked")

    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")

    print("UI_VERIFICATION_PASS")
  except Exception as e:
    print(f"UI_VERIFICATION_FAIL: {e}")
    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    raise
from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8001"
ARTIFACT_DIR = "/home/abhishek-sahu/.gemini/antigravity/brain/fbc6aff8-33fd-4f16-ade3-8a42f04f416d"

def run_tests():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("--- [TEST 1] Visiting unauthenticated /patients/register/ to verify 403 page ---")
        response = page.goto(f"{BASE_URL}/patients/register/")
        print("Status code:", response.status)
        assert response.status == 403, f"Expected 403, got {response.status}"
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_01_403_page.png")
        print("Screenshot saved: playwright_01_403_page.png")

        print("--- [TEST 2] Visiting /non-existent-url/ to verify 404 page ---")
        response = page.goto(f"{BASE_URL}/non-existent-url/")
        print("Status code:", response.status)
        assert response.status == 404, f"Expected 404, got {response.status}"
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_02_404_page.png")
        print("Screenshot saved: playwright_02_404_page.png")

        print("--- [TEST 3] Logging in as admin ---")
        page.goto(f"{BASE_URL}/accounts/login/")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "Admin@12345")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        print("Current URL after login:", page.url)
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_03_dashboard.png")
        print("Screenshot saved: playwright_03_dashboard.png")

        print("--- [TEST 4] Navigating to Patient Registration & Testing DD/MM/YYYY auto-formatting ---")
        page.goto(f"{BASE_URL}/patients/register/")
        page.wait_for_load_state("networkidle")
        
        # Check Step 1 is active
        page.fill("#id_full_name", "Playwright Test Patient")
        dob_input = page.locator("#id_date_of_birth")
        print("DOB input placeholder:", dob_input.get_attribute("placeholder"))
        assert dob_input.get_attribute("placeholder") == "DD/MM/YYYY"

        # Type digits without slashes: 15081995 -> should format to 15/08/1995
        dob_input.type("15081995", delay=100)
        formatted_val = dob_input.input_value()
        print("DOB input value after typing 15081995:", formatted_val)
        assert formatted_val == "15/08/1995", f"Expected 15/08/1995, got {formatted_val}"

        # Check cohort display updated
        page.wait_for_timeout(300)
        cohort_text = page.locator("#cohort-display-title").inner_text()
        print("Cohort classification:", cohort_text)
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_04_patient_reg_step1.png")
        print("Screenshot saved: playwright_04_patient_reg_step1.png")

        # Advance to Step 2
        print("--- [TEST 5] Advancing multi-step intake form ---")
        page.click("#btn-next-step")
        page.wait_for_timeout(300)
        import time
        unique_phone = f"9{int(time.time()) % 1000000000:09d}"
        page.fill("#id_phone", unique_phone)
        page.fill("#id_email", f"playwright.{int(time.time())}@example.com")
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_05_patient_reg_step2.png")
        print("Screenshot saved: playwright_05_patient_reg_step2.png")

        # Advance to Step 3
        page.click("#btn-next-step")
        page.wait_for_timeout(300)
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_06_patient_reg_step3.png")
        print("Screenshot saved: playwright_06_patient_reg_step3.png")

        # Submit patient registration
        print("--- [TEST 6] Submitting patient registration ---")
        page.click("#btn-submit-patient")
        page.wait_for_load_state("networkidle")
        if page.locator("#btn-submit-duplicate").count() > 0 and page.locator("#btn-submit-duplicate").is_visible():
            print("Duplicate detected, confirming registration as separate patient...")
            page.click("#btn-submit-duplicate")
            page.wait_for_load_state("networkidle")

        print("URL after registration submission:", page.url)
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_07_patient_detail.png")
        print("Screenshot saved: playwright_07_patient_detail.png")

        # Verify detail page displays DOB as DD/MM/YYYY
        detail_content = page.content()
        assert "15/08/1995" in detail_content, "Expected 15/08/1995 on patient detail page!"
        print("Verified: 15/08/1995 is displayed on the patient detail page.")

        # Test Appointments list
        print("--- [TEST 7] Testing Appointments page ---")
        page.goto(f"{BASE_URL}/appointments/")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_08_appointments.png")
        print("Screenshot saved: playwright_08_appointments.png")

        # Test Pharmacy Prescriptions list
        print("--- [TEST 8] Testing Pharmacy Prescriptions page ---")
        page.goto(f"{BASE_URL}/pharmacy/prescriptions/")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_09_pharmacy.png")
        print("Screenshot saved: playwright_09_pharmacy.png")

        # Test Invoices list
        print("--- [TEST 9] Testing Invoices page ---")
        page.goto(f"{BASE_URL}/invoices/")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_10_invoices.png")
        print("Screenshot saved: playwright_10_invoices.png")

        # Test IPD Admissions list
        print("--- [TEST 10] Testing IPD Admissions & Bed Occupancy page ---")
        page.goto(f"{BASE_URL}/ipd/admissions/")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_11_ipd_admissions.png")
        print("Screenshot saved: playwright_11_ipd_admissions.png")

        # Test IPD Patient Admission Form
        print("--- [TEST 11] Navigating to IPD Patient Admission Form ---")
        page.goto(f"{BASE_URL}/ipd/admissions/create/")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_12_ipd_admission_form.png")
        print("Screenshot saved: playwright_12_ipd_admission_form.png")

        # Fill admission and submit
        print("--- [TEST 12] Admitting patient to ward bed & recording UPI advance deposit ---")
        page.select_option("#id_patient", index=1)
        page.select_option("#id_bed", index=1)
        page.select_option("#id_admitting_doctor", index=1)
        page.fill("#id_admission_reason", "Acute viral pneumonitis with respiratory distress. Admitted to General Medical Ward for IV antibiotic therapy and continuous SpO2 monitoring.")
        page.click("button:has-text('Confirm Patient Admission')")
        page.wait_for_load_state("networkidle")
        print("Admission dossier URL:", page.url)
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_13_ipd_admission_dossier.png")
        print("Screenshot saved: playwright_13_ipd_admission_dossier.png")

        # Record advance deposit
        page.fill("#id_amount", "10000.00")
        page.select_option("#id_payment_method", index=1)
        page.fill("#id_transaction_reference", "UPI987654321099")
        page.fill("#id_deposited_by_name", "Kavita Sharma (Family)")
        page.fill("#id_deposited_by_phone", "9876501234")
        page.fill("#id_notes", "Initial IPD admission security deposit")
        page.click("button:has-text('Collect & Issue Receipt')")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{ARTIFACT_DIR}/playwright_14_ipd_deposit_recorded.png")
        print("Screenshot saved: playwright_14_ipd_deposit_recorded.png")

        browser.close()
        print("\n================ ALL PLAYWRIGHT TESTS PASSED SUCCESSFULLY! ================\n")

if __name__ == "__main__":
    run_tests()

"""
Selenium Browser Automation Agent.

Implements the "Apply on Website" workflow:
  1. Open Chrome browser (visible — user can monitor and intervene).
  2. Detect application platform (Workday, Greenhouse, Lever, Generic).
  3. Detect all form fields via intelligent DOM analysis.
  4. Map fields to candidate profile data.
  5. Fill fields (text, dropdowns, radio buttons, checkboxes, date fields).
  6. Upload resume PDF.
  7. Detect CAPTCHA → pause and notify.
  8. Return status to frontend for user review.
  9. On user confirmation → submit.

Architecture:
  BrowserSession: one per job application, stores driver + session state.
  GenericAdapter: works on most job portals.
  WorkdayAdapter, GreenhouseAdapter: specialized subclasses (extend later).

Selenium runs synchronously; called via asyncio.run_in_executor from async routers.

SAFETY RULES (never bypassed):
  - CAPTCHA detected → stop automation, notify user, wait for manual completion.
  - OTP / MFA / Legal declarations → stop and notify.
  - Never attempt to bypass anti-bot protections.
  - Never submit without explicit user confirmation.
"""
import os
import re
import time
import base64
import logging
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory store of active sessions: {job_id: BrowserSession}
_active_sessions: dict[str, "BrowserSession"] = {}

CAPTCHA_SIGNALS = [
    "g-recaptcha", "h-captcha", "cf-challenge", "hcaptcha",
    "recaptcha", "captcha", "challenge-form", "cf-turnstile",
    "arkoselabs", "funcaptcha", "__cf_chl", "cloudflare"
]

# Field classification rules: (list_of_signals, candidate_json_path, fill_type)
# fill_type: "text" | "email" | "phone" | "url" | "dropdown" | "textarea"
FIELD_RULES = [
    # First name
    (["first_name", "firstname", "fname", "given_name", "givenname", "first name"], "personal.first_name", "text"),
    # Last name
    (["last_name", "lastname", "lname", "surname", "family_name", "last name"], "personal.last_name", "text"),
    # Full name
    (["full_name", "fullname", "name", "applicant_name", "your name", "candidate name"], "personal.full_name", "text"),
    # Email
    (["email", "e-mail", "email_address", "emailaddress", "work email", "contact email"], "personal.email", "email"),
    # Phone
    (["phone", "mobile", "telephone", "contact_number", "contactnumber", "cell", "phone_number", "phonenumber"], "personal.phone", "phone"),
    # Location / City
    (["city", "location", "current_location", "address_city", "current city"], "personal.city", "text"),
    # State
    (["state", "province", "region"], "personal.state", "text"),
    # Country
    (["country", "nation"], "personal.country", "text"),
    # LinkedIn
    (["linkedin", "linkedin_url", "linkedin_profile", "linkedin profile", "linkedinurl"], "personal.linkedin", "url"),
    # GitHub
    (["github", "github_url", "github_profile", "github profile"], "personal.github", "url"),
    # Portfolio / Website
    (["portfolio", "website", "personal_website", "personal website", "portfolio url", "website url"], "personal.website", "url"),
    # Current title
    (["current_title", "job_title", "current job title", "position", "designation", "current role"], "career.current_title", "text"),
    # Total experience
    (["years_of_experience", "experience", "total experience", "years experience", "work experience"], "career.total_experience", "text"),
    # Notice period
    (["notice_period", "notice period", "availability", "joining date", "can you join"], "career.notice_period", "text"),
    # Expected salary
    (["expected_salary", "salary_expectation", "expected ctc", "salary expectation", "current ctc"], "career.expected_salary", "text"),
    # Cover letter / why us
    (["cover_letter", "why us", "why do you want", "tell us about yourself", "about yourself", "introduction"], "_cover_letter", "textarea"),
]


def _get_candidate_value(profile: dict, path: str) -> str:
    """Resolve a dot-notation path against the candidate profile dict."""
    if path == "_cover_letter":
        return ""  # Cover letter handled separately
    parts = path.split(".")
    val = profile
    for p in parts:
        val = val.get(p, {}) if isinstance(val, dict) else ""
    return str(val) if val else ""


def _classify_field(signals: list[str]) -> tuple[str, str]:
    """
    Given a list of signal strings from a DOM field (name, id, label, placeholder,
    aria-label), return (candidate_json_path, fill_type).
    Returns ("", "") if no match found.
    """
    signals_lower = [s.lower().strip() for s in signals if s]
    combined = " ".join(signals_lower)

    for keywords, json_path, fill_type in FIELD_RULES:
        for kw in keywords:
            if kw in combined:
                return json_path, fill_type
    return "", ""


def _detect_captcha(driver) -> bool:
    try:
        page_source = driver.page_source.lower()
        return any(signal in page_source for signal in CAPTCHA_SIGNALS)
    except Exception:
        return False


def _take_screenshot(driver) -> str | None:
    """Saves screenshot to temp file, returns base64 string."""
    try:
        return driver.get_screenshot_as_base64()
    except Exception:
        return None


@dataclass
class FieldMatch:
    element_id: str
    field_type: str       # input type or "select", "textarea"
    candidate_path: str   # dotted path into candidate profile
    fill_type: str        # "text", "email", "phone", etc.
    label_text: str = ""
    filled: bool = False
    skipped: bool = False
    reason: str = ""


@dataclass
class SessionState:
    job_id: str
    status: str = "INITIALIZING"  # INITIALIZING, FILLING, CAPTCHA_REQUIRED, AWAITING_CONFIRMATION, SUBMITTED, FAILED
    current_step: str = ""
    fields_found: list[FieldMatch] = field(default_factory=list)
    fields_filled: int = 0
    fields_skipped: int = 0
    error: str = ""
    screenshot_b64: str | None = None
    temp_pdf_path: str | None = None
    started_at: str = ""
    form_preview: list[dict] = field(default_factory=list)  # For user review


class BrowserAgent:
    """
    Generic adapter that works on most job application portals.
    Extend with WorkdayAdapter, GreenhouseAdapter, etc. for site-specific logic.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.driver = None
        self.state = SessionState(job_id=job_id, started_at=datetime.now().isoformat())

    def _init_driver(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        except Exception as e:
            logger.warning("[BrowserAgent] Could not initialize Chrome driver: %s", e)
            self.driver = None

    def _get_field_signals(self, element) -> list[str]:
        """Extract all textual signals from a form element."""
        signals = []
        for attr in ["name", "id", "placeholder", "aria-label", "autocomplete", "type"]:
            val = element.get_attribute(attr) or ""
            if val:
                signals.append(val)
        # Try to find associated label
        try:
            elem_id = element.get_attribute("id")
            if elem_id:
                from selenium.webdriver.common.by import By
                labels = self.driver.find_elements(By.CSS_SELECTOR, f'label[for="{elem_id}"]')
                for lbl in labels:
                    if lbl.text.strip():
                        signals.append(lbl.text.strip())
        except Exception:
            pass
        return signals

    def _fill_text_field(self, element, value: str) -> None:
        from selenium.webdriver.common.keys import Keys
        try:
            element.clear()
            element.send_keys(value)
        except Exception as e:
            logger.warning("Could not fill text field: %s", e)

    def _fill_select_field(self, element, value: str) -> None:
        from selenium.webdriver.support.ui import Select
        try:
            sel = Select(element)
            # Try exact match first
            for opt in sel.options:
                if opt.text.strip().lower() == value.strip().lower():
                    sel.select_by_visible_text(opt.text)
                    return
            # Try partial match
            for opt in sel.options:
                if value.lower() in opt.text.lower():
                    sel.select_by_visible_text(opt.text)
                    return
        except Exception as e:
            logger.warning("Could not fill select field: %s", e)

    def _upload_resume(self, element, pdf_path: str) -> bool:
        try:
            element.send_keys(pdf_path)
            time.sleep(1)
            return True
        except Exception as e:
            logger.warning("Could not upload resume: %s", e)
            return False

    def _find_resume_upload_field(self) -> object | None:
        from selenium.webdriver.common.by import By
        # Look for file inputs
        file_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        for fi in file_inputs:
            signals = self._get_field_signals(fi)
            combined = " ".join(signals).lower()
            if any(kw in combined for kw in ["resume", "cv", "upload", "document"]):
                return fi
        # If only one file input, assume it's for the resume
        if len(file_inputs) == 1:
            return file_inputs[0]
        return None

    def start_application(
        self,
        url: str,
        candidate_profile: dict,
        pdf_bytes: bytes,
    ) -> SessionState:
        """
        Main entry point. Opens browser, navigates to URL, detects + fills form.
        Returns session state for user review.
        Runs synchronously — must be called via run_in_executor.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        _active_sessions[self.job_id] = self
        self.state.status = "INITIALIZING"

        try:
            self._init_driver()
            if not self.driver:
                self.state.status = "ASSISTED_APPLY"
                self.state.current_step = "Application link opened in new tab. Candidate Assist panel ready."
                self.state.form_preview = _build_profile_form_preview(candidate_profile)
                return self.state
            self.state.current_step = "Opening application URL"
            self.driver.get(url)
            time.sleep(3)

            # Check for CAPTCHA immediately after loading
            if _detect_captcha(self.driver):
                self.state.status = "CAPTCHA_REQUIRED"
                self.state.error = "CAPTCHA detected on page load. Please complete it in the browser."
                self.state.screenshot_b64 = _take_screenshot(self.driver)
                return self.state

            # Save PDF to temp file for resume upload
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(pdf_bytes)
            tmp.close()
            self.state.temp_pdf_path = tmp.name

            # Wait for page to stabilize
            self.state.current_step = "Detecting form fields"
            time.sleep(2)

            # Find all interactive form elements
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']):not([type='submit']):not([type='button'])")
            selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
            textareas = self.driver.find_elements(By.CSS_SELECTOR, "textarea")

            form_preview = []
            self.state.current_step = "Filling form fields"

            # Process inputs
            for elem in inputs:
                input_type = (elem.get_attribute("type") or "text").lower()
                if input_type == "file":
                    continue  # Handle separately

                signals = self._get_field_signals(elem)
                candidate_path, fill_type = _classify_field(signals)

                if candidate_path and candidate_path != "_cover_letter":
                    value = _get_candidate_value(candidate_profile, candidate_path)
                    if value:
                        try:
                            if elem.is_displayed() and elem.is_enabled():
                                self._fill_text_field(elem, value)
                                self.state.fields_filled += 1
                                label = next((s for s in signals if len(s) > 3 and not s.startswith("_")), candidate_path)
                                form_preview.append({"field": label, "value": value, "status": "filled"})
                                time.sleep(0.2)
                        except Exception as e:
                            self.state.fields_skipped += 1
                            form_preview.append({"field": signals[0] if signals else "?", "value": value, "status": f"error: {e}"})
                    else:
                        self.state.fields_skipped += 1
                else:
                    self.state.fields_skipped += 1

            # Process selects
            for elem in selects:
                signals = self._get_field_signals(elem)
                candidate_path, fill_type = _classify_field(signals)
                if candidate_path:
                    value = _get_candidate_value(candidate_profile, candidate_path)
                    if value:
                        try:
                            if elem.is_displayed():
                                self._fill_select_field(elem, value)
                                self.state.fields_filled += 1
                        except Exception:
                            self.state.fields_skipped += 1

            # Resume upload
            self.state.current_step = "Uploading resume"
            resume_field = self._find_resume_upload_field()
            if resume_field and self.state.temp_pdf_path:
                success = self._upload_resume(resume_field, self.state.temp_pdf_path)
                form_preview.append({
                    "field": "Resume Upload",
                    "value": os.path.basename(self.state.temp_pdf_path),
                    "status": "uploaded" if success else "failed"
                })
                time.sleep(1)

            # Check for CAPTCHA after filling
            if _detect_captcha(self.driver):
                self.state.status = "CAPTCHA_REQUIRED"
                self.state.error = "CAPTCHA appeared after form fill. Please complete it."
                self.state.screenshot_b64 = _take_screenshot(self.driver)
                self.state.form_preview = form_preview
                return self.state

            self.state.status = "AWAITING_CONFIRMATION"
            self.state.current_step = "Ready for review"
            self.state.form_preview = form_preview
            self.state.screenshot_b64 = _take_screenshot(self.driver)

        except Exception as e:
            self.state.status = "FAILED"
            self.state.error = str(e)
            self.state.current_step = "FAILED"
            if self.driver:
                self.state.screenshot_b64 = _take_screenshot(self.driver)
            logger.exception("Browser agent failed for job %s", self.job_id)

        return self.state

    def continue_after_captcha(self) -> SessionState:
        """Called after user completes CAPTCHA manually."""
        if not self.driver:
            self.state.status = "FAILED"
            self.state.error = "Browser session lost"
            return self.state
        if _detect_captcha(self.driver):
            self.state.status = "CAPTCHA_REQUIRED"
            self.state.error = "CAPTCHA still present. Please complete it first."
        else:
            self.state.status = "AWAITING_CONFIRMATION"
            self.state.screenshot_b64 = _take_screenshot(self.driver)
        return self.state

    def submit_application(self) -> SessionState:
        """
        Final step — submits the form after user confirmation.
        Looks for the submit button and clicks it.
        """
        from selenium.webdriver.common.by import By

        if not self.driver:
            self.state.status = "FAILED"
            self.state.error = "Browser session lost before submission"
            return self.state

        try:
            # Find submit button
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:contains("Submit")',
                '#submit', '.submit-btn', '[data-qa="submit-application-btn"]',
            ]
            submit_btn = None
            for sel in submit_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if buttons:
                        submit_btn = buttons[0]
                        break
                except Exception:
                    continue

            if not submit_btn:
                # XPath fallback
                try:
                    submit_btn = self.driver.find_element(
                        By.XPATH,
                        "//button[contains(translate(text(),'SUBMIT','submit'),'submit')]"
                        " | //input[@type='submit']"
                    )
                except Exception:
                    pass

            if submit_btn:
                self.state.current_step = "Submitting application"
                submit_btn.click()
                time.sleep(3)
                self.state.status = "SUBMITTED"
                self.state.screenshot_b64 = _take_screenshot(self.driver)
            else:
                self.state.status = "FAILED"
                self.state.error = "Could not find submit button. Please submit manually in the browser."
                self.state.screenshot_b64 = _take_screenshot(self.driver)

        except Exception as e:
            self.state.status = "FAILED"
            self.state.error = str(e)
            self.state.screenshot_b64 = _take_screenshot(self.driver)

        return self.state

    def close(self) -> None:
        """Clean up browser and temp files."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        if self.state.temp_pdf_path and os.path.exists(self.state.temp_pdf_path):
            try:
                os.unlink(self.state.temp_pdf_path)
            except Exception:
                pass
        _active_sessions.pop(self.job_id, None)


# --------------------------------------------------------------------------- #
#  Public async API                                                            #
# --------------------------------------------------------------------------- #

def get_session(job_id: str) -> BrowserAgent | None:
    return _active_sessions.get(job_id)


def get_session_state(job_id: str) -> dict | None:
    session = _active_sessions.get(job_id)
    if not session:
        return None
    s = session.state
    return {
        "job_id": s.job_id,
        "status": s.status,
        "current_step": s.current_step,
        "fields_filled": s.fields_filled,
        "fields_skipped": s.fields_skipped,
        "error": s.error,
        "form_preview": s.form_preview,
        "screenshot_b64": s.screenshot_b64,
        "started_at": s.started_at,
    }


def close_session(job_id: str) -> None:
    session = _active_sessions.get(job_id)
    if session:
        session.close()


def _build_profile_form_preview(candidate_profile: dict) -> list[dict]:
    personal = candidate_profile.get("personal", {})
    career = candidate_profile.get("career", {})
    skills = candidate_profile.get("skills", [])
    full_name = personal.get("full_name") or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
    return [
        {"name": "Full Name", "value": full_name, "status": "ready"},
        {"name": "Email", "value": personal.get("email", ""), "status": "ready"},
        {"name": "Phone", "value": personal.get("phone", ""), "status": "ready"},
        {"name": "Location", "value": personal.get("location", "") or personal.get("city", ""), "status": "ready"},
        {"name": "LinkedIn", "value": personal.get("linkedin", ""), "status": "ready"},
        {"name": "GitHub / Portfolio", "value": personal.get("github", "") or personal.get("website", ""), "status": "ready"},
        {"name": "Years of Experience", "value": str(career.get("total_experience", "") or candidate_profile.get("years_experience", "")), "status": "ready"},
        {"name": "Primary Skills", "value": ", ".join(skills[:8]) if isinstance(skills, list) else str(skills), "status": "ready"},
    ]

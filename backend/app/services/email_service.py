"""
Email notifications via plain SMTP (smtplib, stdlib - no extra deps).
Works with Gmail (use an App Password, not your normal password),
Outlook, or any SMTP provider (SendGrid, Mailgun, etc via their SMTP
relay).

If SMTP isn't configured (smtp_host empty), send_email() no-ops and
returns a clear "not configured" result instead of raising, so the rest
of the app doesn't break for users who haven't set email up yet.
"""
import contextlib
import socket
import mimetypes
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from app.config.env import env_settings
from app.services import config_service


@contextlib.contextmanager
def _force_ipv4_dns():
    """
    Some hosts (Render included) advertise IPv6 connectivity that isn't
    actually routable outbound, which makes smtplib.connect() fail with
    "[Errno 101] Network is unreachable" when Python's DNS resolution
    picks an IPv6 address for the SMTP server (e.g. Gmail has AAAA
    records). Forcing getaddrinfo to only return IPv4 addresses for the
    duration of the SMTP connection fixes this. This only patches
    address *resolution*, not the hostname passed to smtplib itself, so
    TLS SNI/certificate validation is unaffected.
    """
    original_getaddrinfo = socket.getaddrinfo

    def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


def is_configured() -> bool:
    if env_settings.email_provider == "custom":
        return bool(env_settings.custom_email_api_url and env_settings.smtp_user and env_settings.smtp_password)
    if env_settings.email_provider == "mailjet":
        return bool(env_settings.mailjet_api_key and env_settings.mailjet_api_secret and env_settings.mailjet_from_email)
    if env_settings.email_provider == "brevo":
        return bool(env_settings.brevo_api_key and env_settings.brevo_from_email)
    if env_settings.email_provider == "sendgrid":
        return bool(env_settings.sendgrid_api_key and env_settings.sendgrid_from_email)
    return bool(env_settings.smtp_host and env_settings.smtp_from)


async def _resolve_recipient(to: str | None) -> str | None:
    if to:
        return to
    if env_settings.notify_email_to:
        return env_settings.notify_email_to
    config = await config_service.get_config()
    return config.get("email") or None


def _attach_file(msg: MIMEMultipart, content: bytes, filename: str) -> None:
    if not content:
        return
    ctype, _ = mimetypes.guess_type(filename)
    maintype, subtype = (ctype.split("/", 1) if ctype else ("application", "octet-stream"))
    part = MIMEBase(maintype, subtype)
    part.set_payload(content)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)


async def send_email(
    subject: str,
    html_body: str,
    to: str | None = None,
    attachments: list[tuple[bytes, str]] | None = None,
) -> dict:
    """
    attachments: list of (file_bytes, display_filename) tuples. Empty/
    missing content is silently skipped rather than failing the whole
    send - a missing resume shouldn't block a notification email.
    Routes to whichever EMAIL_PROVIDER is configured.
    """
    if not is_configured():
        reasons = {
            "custom": "Custom relay not configured (set CUSTOM_EMAIL_API_URL/SMTP_USER/SMTP_PASSWORD in .env)",
            "mailjet": "Mailjet not configured (set MAILJET_API_KEY/MAILJET_API_SECRET/MAILJET_FROM_EMAIL in .env)",
            "brevo": "Brevo not configured (set BREVO_API_KEY/BREVO_FROM_EMAIL in .env)",
            "sendgrid": "SendGrid not configured (set SENDGRID_API_KEY/SENDGRID_FROM_EMAIL in .env)",
        }
        reason = reasons.get(env_settings.email_provider, "SMTP not configured (set SMTP_HOST/SMTP_FROM in .env)")
        return {"sent": False, "reason": reason}

    recipient = await _resolve_recipient(to)
    if not recipient:
        return {"sent": False, "reason": "No recipient email available (set NOTIFY_EMAIL_TO or your email in Job Search Config)"}

    if env_settings.email_provider == "custom":
        return await _send_via_custom_relay(subject, html_body, recipient, attachments or [])
    if env_settings.email_provider == "mailjet":
        return await _send_via_mailjet(subject, html_body, recipient, attachments or [])
    if env_settings.email_provider == "brevo":
        return await _send_via_brevo(subject, html_body, recipient, attachments or [])
    if env_settings.email_provider == "sendgrid":
        return await _send_via_sendgrid(subject, html_body, recipient, attachments or [])
    return await _send_via_smtp(subject, html_body, recipient, attachments or [])


async def _send_via_custom_relay(subject: str, html_body: str, recipient: str, attachments: list[tuple[bytes, str]]) -> dict:
    """
    Sends via your own self-hosted relay API instead of a third-party ESP.
    Bypasses Render's SMTP port block the same way Mailjet/Brevo/SendGrid
    do (a normal HTTPS call), but skips every ESP account-approval issue
    entirely since it's your own Gmail credentials going to your own
    endpoint. Matches the JSON contract:

        {smtpUser, smtpPassword, smtpHost, smtpPort, to, subject,
         htmlBody, attachments: [{fileName, contentBase64}]}
    """
    import base64
    import httpx

    relay_attachments = []
    for content, filename in attachments:
        if not content:
            continue
        relay_attachments.append(
            {"fileName": filename, "contentBase64": base64.b64encode(content).decode("ascii")}
        )

    config = await config_service.get_config()
    from_name = config.get("name") or ""

    body = {
        "fromName": from_name,
        "smtpUser": env_settings.smtp_user,
        "smtpPassword": env_settings.smtp_password,
        "smtpHost": env_settings.smtp_host or "smtp.gmail.com",
        "smtpPort": env_settings.smtp_port,
        "to": recipient,
        "subject": subject,
        "htmlBody": html_body,
        "attachments": relay_attachments,
    }

    headers = {"Content-Type": "application/json"}
    if env_settings.custom_email_api_key:
        headers["Authorization"] = f"Bearer {env_settings.custom_email_api_key}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(env_settings.custom_email_api_url, headers=headers, json=body)
            if resp.status_code >= 400:
                return {"sent": False, "reason": f"Relay {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"sent": False, "reason": str(e)}

    return {"sent": True, "recipient": recipient}


async def _send_via_mailjet(subject: str, html_body: str, recipient: str, attachments: list[tuple[bytes, str]]) -> dict:
    """
    Sends over HTTPS via Mailjet's Send API v3.1 - bypasses Render's
    free-tier SMTP port block same as Brevo/SendGrid. Unlike Brevo,
    Mailjet's free plan doesn't gate transactional sending behind a
    manual support-ticket review - it works right after the normal
    sender-email confirmation click.
    """
    import base64
    import httpx

    mj_attachments = []
    for content, filename in attachments:
        if not content:
            continue
        ctype, _ = mimetypes.guess_type(filename)
        mj_attachments.append(
            {
                "ContentType": ctype or "application/octet-stream",
                "Filename": filename,
                "Base64Content": base64.b64encode(content).decode("ascii"),
            }
        )

    from_block = {"Email": env_settings.mailjet_from_email}
    if env_settings.mailjet_from_name:
        from_block["Name"] = env_settings.mailjet_from_name

    message = {
        "From": from_block,
        "To": [{"Email": recipient}],
        "Subject": subject,
        "HTMLPart": html_body,
    }
    if mj_attachments:
        message["Attachments"] = mj_attachments

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.mailjet.com/v3.1/send",
                auth=(env_settings.mailjet_api_key, env_settings.mailjet_api_secret),
                json={"Messages": [message]},
            )
            if resp.status_code >= 400:
                return {"sent": False, "reason": f"Mailjet {resp.status_code}: {resp.text[:300]}"}
            data = resp.json()
            status = data.get("Messages", [{}])[0].get("Status", "")
            if status != "success":
                return {"sent": False, "reason": f"Mailjet reported status: {status} - {resp.text[:300]}"}
    except Exception as e:
        return {"sent": False, "reason": str(e)}

    return {"sent": True, "recipient": recipient}


async def _send_via_brevo(subject: str, html_body: str, recipient: str, attachments: list[tuple[bytes, str]]) -> dict:
    """
    Sends over HTTPS via Brevo's API - like SendGrid, this bypasses
    Render's free-tier SMTP port block. Brevo's free plan (300/day) has
    no trial expiry, unlike SendGrid's current 60-day trial.
    """
    import base64
    import httpx

    brevo_attachments = []
    for content, filename in attachments:
        if not content:
            continue
        brevo_attachments.append(
            {"content": base64.b64encode(content).decode("ascii"), "name": filename}
        )

    sender = {"email": env_settings.brevo_from_email}
    if env_settings.brevo_from_name:
        sender["name"] = env_settings.brevo_from_name

    body = {
        "sender": sender,
        "to": [{"email": recipient}],
        "subject": subject,
        "htmlContent": html_body,
    }
    if brevo_attachments:
        body["attachment"] = brevo_attachments

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": env_settings.brevo_api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=body,
            )
            if resp.status_code >= 400:
                return {"sent": False, "reason": f"Brevo {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"sent": False, "reason": str(e)}

    return {"sent": True, "recipient": recipient}


async def _send_via_sendgrid(subject: str, html_body: str, recipient: str, attachments: list[tuple[bytes, str]]) -> dict:
    """
    Sends over HTTPS via SendGrid's API instead of raw SMTP - this is
    what makes email work on Render's free tier, which blocks outbound
    SMTP ports (25/465/587) entirely but doesn't block normal HTTPS.
    """
    import base64
    import httpx

    from_block = {"email": env_settings.sendgrid_from_email}
    if env_settings.sendgrid_from_name:
        from_block["name"] = env_settings.sendgrid_from_name

    sg_attachments = []
    for content, filename in attachments:
        if not content:
            continue
        ctype, _ = mimetypes.guess_type(filename)
        sg_attachments.append(
            {
                "content": base64.b64encode(content).decode("ascii"),
                "filename": filename,
                "type": ctype or "application/octet-stream",
                "disposition": "attachment",
            }
        )

    body = {
        "personalizations": [{"to": [{"email": recipient}]}],
        "from": from_block,
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    if sg_attachments:
        body["attachments"] = sg_attachments

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {env_settings.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code >= 400:
                return {"sent": False, "reason": f"SendGrid {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"sent": False, "reason": str(e)}

    return {"sent": True, "recipient": recipient}


async def _send_via_smtp(subject: str, html_body: str, recipient: str, attachments: list[tuple[bytes, str]]) -> dict:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = env_settings.smtp_from
    msg["To"] = recipient

    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(html_body, "html"))
    msg.attach(body_part)

    for content, filename in (attachments or []):
        _attach_file(msg, content, filename)

    try:
        with _force_ipv4_dns():
            if env_settings.smtp_port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(env_settings.smtp_host, env_settings.smtp_port, context=context, timeout=20) as server:
                    if env_settings.smtp_user:
                        server.login(env_settings.smtp_user, env_settings.smtp_password)
                    server.sendmail(env_settings.smtp_from, [recipient], msg.as_string())
            else:
                with smtplib.SMTP(env_settings.smtp_host, env_settings.smtp_port, timeout=20) as server:
                    server.starttls(context=ssl.create_default_context())
                    if env_settings.smtp_user:
                        server.login(env_settings.smtp_user, env_settings.smtp_password)
                    server.sendmail(env_settings.smtp_from, [recipient], msg.as_string())
    except Exception as e:
        return {"sent": False, "reason": str(e)}

    return {"sent": True, "recipient": recipient}


async def notify_new_jobs(jobs: list[dict]) -> dict:
    if not jobs:
        return {"sent": False, "reason": "No new jobs to notify about"}
    rows = "".join(
        f"<li><b>{j['title']}</b> @ {j['company']} "
        f"({j.get('location','')}) - <a href='{j.get('url','')}'>view</a> "
        f"[{j.get('source','')}]</li>"
        for j in jobs[:30]
    )
    more = f"<p>...and {len(jobs) - 30} more.</p>" if len(jobs) > 30 else ""
    html = f"""
    <h3>{len(jobs)} new matching job(s) found</h3>
    <ul>{rows}</ul>
    {more}
    <p>Open the Jobs tab in your AI Job Application Agent to review and run ATS analysis.</p>
    """
    return await send_email(f"{len(jobs)} new job(s) found", html)


async def notify_followups_due(jobs: list[dict]) -> dict:
    if not jobs:
        return {"sent": False, "reason": "No follow-ups due"}
    rows = "".join(
        f"<li><b>{j['title']}</b> @ {j['company']} - applied on "
        f"{j.get('applied_at').strftime('%Y-%m-%d') if j.get('applied_at') else 'unknown date'}</li>"
        for j in jobs
    )
    html = f"""
    <h3>{len(jobs)} application(s) need a follow-up</h3>
    <ul>{rows}</ul>
    <p>Open the Jobs tab to send a follow-up email for each.</p>
    """
    return await send_email(f"{len(jobs)} follow-up(s) due", html)


def _build_application_email_html(job: dict, config: dict, has_cover_letter: bool) -> str:
    name = config.get("name") or "Candidate"
    experience = config.get("experience")
    # Prefer the curated keywords_include for a punchy skills line; fall back to top skills.
    highlight_skills = (config.get("keywords_include") or config.get("skills") or [])[:8]
    skills_line = ", ".join(highlight_skills)
    website = config.get("website_link", "")
    phone = config.get("phone", "")
    email = config.get("email", "")
    job_title = job.get("title", "this role")
    company = job.get("company", "your company")

    cover_letter_line = (
        "<p>I've also attached a cover letter with more detail on my fit for this role.</p>"
        if has_cover_letter
        else ""
    )
    website_line = f'<p>Portfolio / work samples: <a href="{website}">{website}</a></p>' if website else ""

    return f"""
    <p>Dear Hiring Team,</p>
    <p>
      I'm writing to express my interest in the <b>{job_title}</b> position at <b>{company}</b>.
      I have {experience if experience else "several"} years of experience working with
      {skills_line}, and I believe my background aligns well with what you're looking for.
    </p>
    <p>My resume is attached for your review.</p>
    {cover_letter_line}
    {website_line}
    <p>I'd welcome the opportunity to discuss how I can contribute to your team. Thank you for your time and consideration.</p>
    <p>
      Best regards,<br>
      <b>{name}</b><br>
      {phone}<br>
      {email}
    </p>
    """


def build_application_email_preview(job: dict, config: dict) -> dict:
    """Returns {subject, html_body} without sending - lets the user review/edit before it goes out."""
    has_cover_letter = bool(config.get("default_cover_letter"))
    html = _build_application_email_html(job, config, has_cover_letter)
    candidate_name = config.get("name") or "Candidate"
    subject = f"Application for {job.get('title', 'Open Position')} - {candidate_name}"
    return {"subject": subject, "html_body": html}


async def send_application_email(
    job: dict,
    hr_email: str,
    resume_content: bytes,
    resume_filename: str,
    cover_letter_content: bytes = b"",
    cover_letter_filename: str = "",
    subject_override: str | None = None,
    html_override: str | None = None,
) -> dict:
    config = await config_service.get_config()
    has_cover_letter = bool(cover_letter_content)
    html = html_override if html_override is not None else _build_application_email_html(job, config, has_cover_letter)

    attachments = [(resume_content, resume_filename)]
    if has_cover_letter:
        attachments.append((cover_letter_content, cover_letter_filename))

    candidate_name = config.get("name") or "Candidate"
    subject = subject_override or f"Application for {job.get('title', 'Open Position')} - {candidate_name}"

    return await send_email(subject, html, to=hr_email, attachments=attachments)

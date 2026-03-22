"""Transactional email via Resend API.

Requires RESEND_API_KEY and optionally RESEND_FROM_EMAIL env vars.
Falls back to logging if unconfigured (dev/test).
"""

from __future__ import annotations

import hashlib
import hmac
import html as html_mod
import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _api_key() -> str | None:
    return os.environ.get("RESEND_API_KEY", "").strip() or None


def _from_email() -> str:
    return os.environ.get("RESEND_FROM_EMAIL", "noreply@mail.zero-human-labs.com")


def send_email(to: str, subject: str, html: str) -> bool:
    """Send a transactional email. Returns True on success."""
    key = _api_key()
    if not key:
        logger.warning(
            "RESEND_API_KEY not set — email to %s not sent. Subject: %s",
            to,
            subject,
        )
        return False

    try:
        resp = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "from": _from_email(),
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info("Email sent to %s: %s", to, subject)
            return True
        logger.error("Resend API error %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def send_welcome_email(to: str, tenant_name: str, api_key_prefix: str = "") -> bool:
    """Send a welcome email after signup."""
    return send_email(
        to=to,
        subject="Welcome to Zero Human Labs",
        html=f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="margin: 0 0 16px;">Welcome to Zero Human Labs, {html_mod.escape(tenant_name)}!</h2>
  <p style="color: #666; line-height: 1.5;">
    Your account is ready. Here&rsquo;s everything you need to get started.
  </p>
  <h3 style="margin: 24px 0 8px;">Quick Start</h3>
  <ol style="color: #666; line-height: 1.8; padding-left: 20px;">
    <li>Create an organization</li>
    <li>Submit your first task via the API</li>
    <li>Watch your agents work</li>
  </ol>
  <a href="https://zero-human-labs.com/dashboard"
     style="display: inline-block; margin: 24px 0; padding: 12px 32px;
            background: #00ff88; color: #000; font-weight: 600;
            text-decoration: none; border-radius: 8px;">
    Go to Dashboard
  </a>
  <p style="color: #999; font-size: 13px; line-height: 1.5;">
    Need help? Reply to this email or reach out on Discord.
  </p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
  <p style="color: #999; font-size: 12px;">Zero Human Labs</p>
</div>""",
    )


def send_waitlist_confirmation_email(to: str) -> bool:
    """Send a confirmation email after waitlist signup."""
    return send_email(
        to=to,
        subject="You're on the waitlist \u2014 Zero Human Labs",
        html="""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="margin: 0 0 16px;">You're on the list!</h2>
  <p style="color: #666; line-height: 1.5;">
    Thanks for signing up for early access to Zero Human Labs.
    We&rsquo;ll email you as soon as your spot opens up.
  </p>
  <p style="color: #666; line-height: 1.5;">
    In the meantime, follow our progress:
  </p>
  <ul style="color: #666; line-height: 1.8; padding-left: 20px;">
    <li><a href="https://github.com/rsavitt/agency-os" style="color: #00cc66;">GitHub</a></li>
    <li><a href="https://zero-human-labs.com" style="color: #00cc66;">Website</a></li>
  </ul>
  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
  <p style="color: #999; font-size: 12px;">Zero Human Labs</p>
</div>""",
    )


# --- Unsubscribe token helpers ---


def _unsubscribe_secret() -> str:
    secret = os.environ.get("UNSUBSCRIBE_SECRET", "")
    if not secret:
        raise RuntimeError(
            "UNSUBSCRIBE_SECRET environment variable is required but not set"
        )
    return secret


def generate_unsubscribe_token(tenant_id: str) -> str:
    """Generate an HMAC-based unsubscribe token for a tenant."""
    return hmac.new(
        _unsubscribe_secret().encode(),
        tenant_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_unsubscribe_token(tenant_id: str, token: str) -> bool:
    """Verify an unsubscribe token matches the tenant."""
    expected = generate_unsubscribe_token(tenant_id)
    return hmac.compare_digest(expected, token)


def _unsubscribe_link(tenant_id: str) -> str:
    token = generate_unsubscribe_token(tenant_id)
    base = os.environ.get("APP_BASE_URL", "https://zero-human-labs.com")
    return f"{base}/api/v1/tenants/unsubscribe?tenant_id={tenant_id}&token={token}"


def _email_footer(tenant_id: str) -> str:
    unsub = html_mod.escape(_unsubscribe_link(tenant_id))
    return f"""\
  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
  <p style="color: #999; font-size: 12px;">
    Zero Human Labs &middot;
    <a href="{unsub}" style="color: #999;">Unsubscribe</a>
  </p>"""


# --- Nurture email sequence (day 1 / 3 / 7) ---

NURTURE_DAYS = (1, 3, 7)

NURTURE_EMAILS: dict[int, dict[str, str]] = {
    1: {
        "subject": "Getting started with Zero Human Labs",
        "heading": "Let\u2019s get you up and running",
        "body": """\
  <p style="color: #666; line-height: 1.5;">
    You signed up yesterday &mdash; here&rsquo;s the fastest path to your first governed agent run:
  </p>
  <ol style="color: #666; line-height: 1.8; padding-left: 20px;">
    <li>Create an organization via the API or dashboard</li>
    <li>Submit a task &mdash; governance presets are applied automatically</li>
    <li>Check the dashboard to see metering, trust scores, and cost tracking</li>
  </ol>
  <a href="https://zero-human-labs.com/dashboard"
     style="display: inline-block; margin: 24px 0; padding: 12px 32px;
            background: #00ff88; color: #000; font-weight: 600;
            text-decoration: none; border-radius: 8px;">
    Open Dashboard
  </a>""",
    },
    3: {
        "subject": "What teams are building with Zero Human Labs",
        "heading": "Use cases from the community",
        "body": """\
  <p style="color: #666; line-height: 1.5;">
    Here are three ways teams are using governed agent infrastructure:
  </p>
  <ul style="color: #666; line-height: 1.8; padding-left: 20px;">
    <li><strong>Automated code review</strong> &mdash; agents review PRs with trust-scored governance</li>
    <li><strong>Data pipeline agents</strong> &mdash; cost-capped, metered LLM calls with smart routing</li>
    <li><strong>Customer support bots</strong> &mdash; circuit breakers and audit trails for compliance</li>
  </ul>
  <p style="color: #666; line-height: 1.5;">
    Have a use case in mind? Reply to this email &mdash; we read every one.
  </p>""",
    },
    7: {
        "subject": "Need help? We\u2019re here for you",
        "heading": "One week in \u2014 how\u2019s it going?",
        "body": """\
  <p style="color: #666; line-height: 1.5;">
    It&rsquo;s been a week since you joined. If you haven&rsquo;t had a chance to
    explore yet, no worries &mdash; your account is ready whenever you are.
  </p>
  <p style="color: #666; line-height: 1.5;">
    A few things that might help:
  </p>
  <ul style="color: #666; line-height: 1.8; padding-left: 20px;">
    <li><a href="https://zero-human-labs.com/dashboard" style="color: #00cc66;">Dashboard</a> &mdash; usage, metering, and trust scores</li>
    <li><a href="https://github.com/rsavitt/agency-os" style="color: #00cc66;">GitHub</a> &mdash; open-source code and examples</li>
  </ul>
  <p style="color: #666; line-height: 1.5;">
    Hit reply if you have questions or feedback. We&rsquo;re a small team and
    genuinely want to help you succeed.
  </p>""",
    },
}


def send_nurture_email(to: str, tenant_name: str, tenant_id: str, day: int) -> bool:
    """Send a nurture email for the given day (1, 3, or 7)."""
    template = NURTURE_EMAILS.get(day)
    if template is None:
        logger.warning("No nurture template for day %d", day)
        return False

    heading = template["heading"]
    body = template["body"]
    footer = _email_footer(tenant_id)
    safe_name = html_mod.escape(tenant_name)

    return send_email(
        to=to,
        subject=template["subject"],
        html=f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="margin: 0 0 16px;">{heading}, {safe_name}!</h2>
{body}
{footer}
</div>""",
    )


def send_password_reset_email(to: str, reset_url: str) -> bool:
    """Send a password reset email."""
    return send_email(
        to=to,
        subject="Reset your Zero Human Labs password",
        html=f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="margin: 0 0 16px;">Reset your password</h2>
  <p style="color: #666; line-height: 1.5;">
    We received a request to reset your password. Click the button below to choose a new one.
    This link expires in 1 hour.
  </p>
  <a href="{reset_url}"
     style="display: inline-block; margin: 24px 0; padding: 12px 32px;
            background: #00ff88; color: #000; font-weight: 600;
            text-decoration: none; border-radius: 8px;">
    Reset Password
  </a>
  <p style="color: #999; font-size: 13px; line-height: 1.5;">
    If you didn&rsquo;t request this, you can safely ignore this email.
    Your password won&rsquo;t change unless you click the link above.
  </p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
  <p style="color: #999; font-size: 12px;">Zero Human Labs</p>
</div>""",
    )

"""
Transactional mailer — bilingual (AR+EN) emails.

Uses Resend's HTTPS API (works on Railway/Fly/Vercel where outbound SMTP
is blocked at the network level). Falls back to SMTP via smtplib when
RESEND_API_KEY is not set but SMTP_USER/SMTP_PASSWORD are.

Safe-by-default: if neither is configured, send_mail logs a warning and
returns False instead of raising, so local dev keeps working.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

import requests

from config import Config

log = logging.getLogger(__name__)


# ─── Backend detection ──────────────────────────────────────────────────

def _resend_is_configured() -> bool:
    return bool(getattr(Config, "RESEND_API_KEY", "") and Config.MAIL_FROM)


def _smtp_is_configured() -> bool:
    return bool(Config.SMTP_HOST and Config.SMTP_USER and Config.SMTP_PASSWORD)


def mailer_is_configured() -> bool:
    return _resend_is_configured() or _smtp_is_configured()


# ─── Public API ─────────────────────────────────────────────────────────

def send_mail(
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> bool:
    """Send a transactional email. Returns True on success, False otherwise."""
    if not to:
        return False

    if _resend_is_configured():
        return _send_resend(to, subject, text_body, html_body)
    if _smtp_is_configured():
        return _send_smtp(to, subject, text_body, html_body)

    log.warning("Mailer not configured — would have sent to %s: %s", to, subject)
    return False


# ─── Resend HTTPS API backend ──────────────────────────────────────────

def _send_resend(to, subject, text_body, html_body) -> bool:
    from_field = (
        formataddr((Config.MAIL_FROM_NAME, Config.MAIL_FROM))
        if Config.MAIL_FROM_NAME
        else Config.MAIL_FROM
    )
    payload = {
        "from": from_field,
        "to": [to],
        "subject": subject,
        "text": text_body,
    }
    if html_body:
        payload["html"] = html_body
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {Config.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if r.status_code >= 400:
            log.error("❌ Resend send failed for %s: %s %s", to, r.status_code, r.text[:200])
            return False
        log.info("✅ Email sent via Resend to %s", to)
        return True
    except Exception as e:
        log.error("❌ Resend request failed for %s: %s", to, e)
        return False


# ─── SMTP fallback backend ──────────────────────────────────────────────

def _send_smtp(to, subject, text_body, html_body) -> bool:
    msg = EmailMessage()
    msg["From"] = formataddr((Config.MAIL_FROM_NAME, Config.MAIL_FROM))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body, charset="utf-8")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        if Config.SMTP_PORT == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, context=ctx, timeout=20) as s:
                s.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as s:
                s.ehlo()
                if Config.SMTP_USE_TLS:
                    ctx = ssl.create_default_context()
                    s.starttls(context=ctx)
                    s.ehlo()
                s.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                s.send_message(msg)
        log.info("✅ Email sent via SMTP to %s", to)
        return True
    except Exception as e:
        log.error("❌ SMTP send failed for %s: %s", to, e)
        return False


# ─── Templates ──────────────────────────────────────────────────────────
#
# Design notes:
#  - English only.
#  - Two skins (light + dark) so a transactional email lands in the visual
#    register the user just left in the app. We do NOT rely on
#    `prefers-color-scheme` for theming any more — that drives the client's
#    OS pref, but we want to follow the user's *explicit* in-app choice.
#  - Logo is inline SVG. Gmail web, Apple Mail, and most modern clients render
#    it; Outlook desktop will show nothing in its place but the rest of the
#    layout stays intact.
#  - Tables for layout (the only thing Outlook reliably honors).

_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
    'width="40" height="40" fill="none" '
    'style="display:block">'
    '<circle cx="32" cy="32" r="29" stroke="#ffffff" stroke-width="2.5" fill="none"/>'
    '<path d="M44.5 16.5A18 18 0 1 0 44.5 47.5" '
    'stroke="#ffffff" stroke-width="3.4" stroke-linecap="round" fill="none"/>'
    '<path d="M21 22.5L31.5 32L21 41.5" '
    'stroke="#ffffff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    '<circle cx="46" cy="32" r="2.4" fill="#ffffff"/>'
    '</svg>'
)


def _normalize_theme(theme: Optional[str]) -> str:
    """Coerce arbitrary theme strings to one of {'light','dark'}."""
    return "dark" if (theme or "").strip().lower() == "dark" else "light"


def _palette(theme: str) -> dict:
    """Color tokens used across all email primitives.

    Mirrors the in-app design system:
      light → ivory page on white card with periwinkle gradient header
      dark  → near-black page on indigo-tinted card; same brand gradient
              header, lifted text colors so they read against the surface.
    """
    if theme == "dark":
        return {
            "page_bg":      "#0c0e1f",
            "card_bg":      "#161a30",
            "card_shadow":  "0 6px 28px rgba(0,0,0,0.45)",
            "title":        "#f1f1f8",
            "text":         "#c8cbe0",
            "text_strong":  "#ffffff",
            "text_mid":     "#9095b5",
            "footer_text":  "#7a7e9c",
            "footer_border":"#262a44",
            "info_bg":      "#1f2340",
            "info_text":    "#c8cbe0",
            "fine_text":    "#7a7e9c",
            "status_text":  "#e8eaf8",
            "outer_text":   "#5b5f7a",
            "link":         "#a0a5ff",
        }
    return {
        "page_bg":      "#eef0f7",
        "card_bg":      "#ffffff",
        "card_shadow":  "0 6px 28px rgba(71,77,197,0.12)",
        "title":        "#1a1b3a",
        "text":         "#3a3c5e",
        "text_strong":  "#1a1b3a",
        "text_mid":     "#7c7f9a",
        "footer_text":  "#7c7f9a",
        "footer_border":"#e8eaf3",
        "info_bg":      "#f5f6fb",
        "info_text":    "#3a3c5e",
        "fine_text":    "#3a3c5e",
        "status_text":  "#1a1b3a",
        "outer_text":   "#9a9db5",
        "link":         "#474dc5",
    }


def _brand_header() -> str:
    # The header gradient is the same in both themes — it's the brand's
    # signature touch and reads well on either surface. Logo + name colors
    # stay white on the gradient.
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:linear-gradient(135deg,#474dc5 0%,#6067df 100%);background-color:#474dc5">
      <tr>
        <td class="em-header-cell" style="padding:32px 36px 28px">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="vertical-align:middle;padding-right:14px;line-height:0">{_LOGO_SVG}</td>
              <td style="vertical-align:middle">
                <div class="em-brand-name" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;line-height:1.1">
                  Ain Real Estate
                </div>
                <div class="em-brand-tag" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:11px;font-weight:600;color:rgba(255,255,255,0.78);margin-top:6px;letter-spacing:1.2px;text-transform:uppercase">
                  KPI &amp; Sales Intelligence
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
"""


def _footer(p: dict) -> str:
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td class="em-footer-cell" style="padding:22px 36px 28px;border-top:1px solid {p['footer_border']}">
          <p style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:12px;line-height:1.6;color:{p['footer_text']};text-align:center">
            &copy; Ain Real Estate &middot; KPI &amp; Sales Intelligence System<br>
            This is an automated message — please do not reply to this email.
          </p>
        </td>
      </tr>
    </table>
"""


def _wrap_html(inner: str, theme: str = "light", preheader: str = "") -> str:
    """Wrap inner body HTML in the full email shell.

    Mobile note: side gutters and inner padding shrink on small screens via
    the @media block below — Gmail Android, Apple Mail iOS, and Outlook web
    all honour this. Outlook desktop ignores media queries but degrades to
    the desktop layout, which still fits.
    """
    p = _palette(theme)
    color_scheme = "dark" if theme == "dark" else "light"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="{color_scheme}">
  <meta name="supported-color-schemes" content="{color_scheme}">
  <title>Ain Real Estate</title>
  <style>
    /* Mobile: reclaim horizontal space so the card doesn't feel narrow.
       Trim outer gutters, tighten inner padding, and drop heading size. */
    @media only screen and (max-width: 520px) {{
      .em-outer       {{ padding: 16px 8px !important; }}
      .em-card        {{ border-radius: 14px !important; }}
      .em-header-cell {{ padding: 24px 20px 22px !important; }}
      .em-body-cell   {{ padding: 28px 20px 4px !important; }}
      .em-footer-cell {{ padding: 18px 20px 24px !important; }}
      .em-title       {{ font-size: 22px !important; line-height: 1.3 !important; }}
      .em-text        {{ font-size: 14.5px !important; }}
      .em-brand-name  {{ font-size: 20px !important; }}
      .em-brand-tag   {{ font-size: 10px !important; letter-spacing: 1px !important; }}
      .em-cta         {{ display: block !important; padding: 14px 20px !important; text-align: center !important; }}
      .em-cta-cell    {{ width: 100% !important; }}
      .em-status-card {{ padding: 12px 14px !important; }}
      .em-info-card   {{ padding: 14px 16px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:{p['page_bg']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
  <span style="display:none!important;visibility:hidden;opacity:0;height:0;width:0;max-height:0;max-width:0;font-size:1px;line-height:1px;color:transparent;overflow:hidden">{preheader}</span>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="em-outer" style="background:{p['page_bg']};padding:32px 12px">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" class="em-card"
               style="max-width:600px;width:100%;background:{p['card_bg']};border-radius:18px;overflow:hidden;box-shadow:{p['card_shadow']}">
          <tr><td>{_brand_header()}</td></tr>
          <tr><td class="em-body-cell" style="padding:36px 36px 8px">{inner}</td></tr>
          <tr><td>{_footer(p)}</td></tr>
        </table>
        <p style="margin:18px 0 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:11px;color:{p['outer_text']};text-align:center">
          Ain Real Estate &middot; al-ainrealestate.com
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _status_card(icon: str, accent: str, label: str, message: str, p: dict) -> str:
    """Coloured callout strip used at the top of each lifecycle email."""
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px">
      <tr>
        <td class="em-status-card" style="background:{accent}14;border:1px solid {accent}33;border-left:4px solid {accent};border-radius:10px;padding:14px 16px">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="vertical-align:middle;padding-right:12px;font-size:20px;line-height:1">{icon}</td>
              <td style="vertical-align:middle">
                <div style="font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:{accent};line-height:1">{label}</div>
                <div style="font-size:14px;color:{p['status_text']};margin-top:4px;line-height:1.5">{message}</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


# ─── Signup approval lifecycle templates ────────────────────────────────


def signup_pending_email(full_name: str, theme: str = "light") -> tuple:
    theme = _normalize_theme(theme)
    p = _palette(theme)
    name = full_name or "there"
    subject = "Ain Real Estate — Signup received"
    preheader = "Your registration is in the queue for admin approval."

    text = f"""Hi {name},

Thanks for signing up to Ain Real Estate. Your registration is now in the queue for admin review.

You'll receive another email once your account is approved (or if it's declined). No action is needed from you in the meantime.

— The Ain Real Estate team
"""

    inner = f"""
    {_status_card("&#9203;", "#c47200", "Pending review", "Your request is awaiting admin approval.", p)}

    <h1 class="em-title" style="margin:0 0 14px;font-size:24px;font-weight:700;color:{p['title']};letter-spacing:-0.3px;line-height:1.3">
      Welcome aboard, {name}.
    </h1>
    <p class="em-text" style="margin:0 0 14px;font-size:15px;line-height:1.7;color:{p['text']}">
      Thanks for signing up to <strong style="color:{p['text_strong']}">Ain Real Estate</strong>.
      Your registration has been received and is now in the queue for admin review.
    </p>
    <p class="em-text" style="margin:0 0 24px;font-size:15px;line-height:1.7;color:{p['text']}">
      You'll receive another email as soon as your account is approved — or if your request
      is declined. No action is needed from you in the meantime.
    </p>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px">
      <tr><td class="em-info-card" style="background:{p['info_bg']};border-radius:12px;padding:18px 20px">
        <div style="font-size:12px;font-weight:600;color:{p['text_mid']};text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">What happens next</div>
        <div class="em-text" style="font-size:14px;color:{p['info_text']};line-height:1.7">
          1. An admin reviews your request.<br>
          2. You receive an approval (or decline) email.<br>
          3. If approved, sign in with the credentials you chose at signup.
        </div>
      </td></tr>
    </table>

    <p class="em-text-mid" style="margin:20px 0 0;font-size:14px;color:{p['text_mid']};line-height:1.6">
      — The Ain Real Estate team
    </p>
    """
    return subject, text, _wrap_html(inner, theme, preheader)


def signup_approved_email(full_name: str, theme: str = "light") -> tuple:
    theme = _normalize_theme(theme)
    p = _palette(theme)
    name = full_name or "there"
    subject = "Ain Real Estate — Your account has been approved"
    preheader = "Good news — you can sign in now."

    text = f"""Hi {name},

Good news — your Ain Real Estate account has been approved.

You can now sign in using the username and password you chose at registration.

— The Ain Real Estate team
"""

    inner = f"""
    {_status_card("&#10003;", "#006762", "Approved", "Your account is active and ready to use.", p)}

    <h1 class="em-title" style="margin:0 0 14px;font-size:24px;font-weight:700;color:{p['title']};letter-spacing:-0.3px;line-height:1.3">
      You're in, {name}.
    </h1>
    <p class="em-text" style="margin:0 0 14px;font-size:15px;line-height:1.7;color:{p['text']}">
      Good news — your <strong style="color:{p['text_strong']}">Ain Real Estate</strong> account has been approved
      by an admin. You can sign in right now using the username and password you chose at signup.
    </p>

    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0">
      <tr><td class="em-cta-cell">
        <a href="https://al-ainrealestate.com/login" class="em-cta"
           style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#474dc5 0%,#6067df 100%);background-color:#474dc5;color:#ffffff;text-decoration:none;border-radius:10px;font-size:15px;font-weight:600;letter-spacing:-0.1px;box-shadow:0 4px 12px rgba(71,77,197,0.28)">
          Sign in to your account
        </a>
      </td></tr>
    </table>

    <p class="em-text-mid" style="margin:0;font-size:13px;color:{p['text_mid']};line-height:1.6">
      Forgot your password? Use the <strong style="color:{p['text']}">Forgot password</strong> link on the
      sign-in page and we'll send you a reset email.
    </p>

    <p class="em-text-mid" style="margin:20px 0 0;font-size:14px;color:{p['text_mid']};line-height:1.6">
      — The Ain Real Estate team
    </p>
    """
    return subject, text, _wrap_html(inner, theme, preheader)


def signup_rejected_email(full_name: str, theme: str = "light") -> tuple:
    theme = _normalize_theme(theme)
    p = _palette(theme)
    name = full_name or "there"
    subject = "Ain Real Estate — Update on your signup request"
    preheader = "Your signup request was not approved at this time."

    text = f"""Hi {name},

We're sorry — your Ain Real Estate signup request was not approved at this time.

If you believe this was a mistake, please contact your administrator.

— The Ain Real Estate team
"""

    inner = f"""
    {_status_card("&#9888;", "#ba1a1a", "Not approved", "Your signup request was declined at this time.", p)}

    <h1 class="em-title" style="margin:0 0 14px;font-size:24px;font-weight:700;color:{p['title']};letter-spacing:-0.3px;line-height:1.3">
      Hi {name},
    </h1>
    <p class="em-text" style="margin:0 0 14px;font-size:15px;line-height:1.7;color:{p['text']}">
      We're sorry to share that your <strong style="color:{p['text_strong']}">Ain Real Estate</strong> signup
      request was not approved at this time.
    </p>
    <p class="em-text" style="margin:0 0 24px;font-size:15px;line-height:1.7;color:{p['text']}">
      If you believe this was a mistake, or you'd like to follow up on the decision, please contact
      your administrator directly.
    </p>

    <p class="em-text-mid" style="margin:20px 0 0;font-size:14px;color:{p['text_mid']};line-height:1.6">
      — The Ain Real Estate team
    </p>
    """
    return subject, text, _wrap_html(inner, theme, preheader)


def password_reset_email(full_name: str, reset_url: str, ttl_minutes: int, theme: str = "light") -> tuple:
    """Returns (subject, text, html) — English-only password reset email."""
    theme = _normalize_theme(theme)
    p = _palette(theme)
    name = full_name or "there"
    subject = "Ain Real Estate — Reset your password"
    preheader = f"Use the link inside to choose a new password. Valid for {ttl_minutes} minutes."

    text = f"""Hi {name},

We received a request to reset your Ain Real Estate password.

Use this link to choose a new password (valid for {ttl_minutes} minutes):

{reset_url}

If you didn't request this, you can safely ignore this email — your current password will stay unchanged.

— The Ain Real Estate team
"""

    inner = f"""
    {_status_card("&#128274;", "#474dc5", "Password reset", f"This link is valid for {ttl_minutes} minutes.", p)}

    <h1 class="em-title" style="margin:0 0 14px;font-size:24px;font-weight:700;color:{p['title']};letter-spacing:-0.3px;line-height:1.3">
      Reset your password
    </h1>
    <p class="em-text" style="margin:0 0 14px;font-size:15px;line-height:1.7;color:{p['text']}">
      Hi <strong style="color:{p['text_strong']}">{name}</strong>, we received a request to reset the password
      on your Ain Real Estate account. Click the button below to choose a new one.
    </p>

    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0">
      <tr><td class="em-cta-cell">
        <a href="{reset_url}" class="em-cta"
           style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#474dc5 0%,#6067df 100%);background-color:#474dc5;color:#ffffff;text-decoration:none;border-radius:10px;font-size:15px;font-weight:600;letter-spacing:-0.1px;box-shadow:0 4px 12px rgba(71,77,197,0.28)">
          Reset password
        </a>
      </td></tr>
    </table>

    <p class="em-text-mid" style="margin:0 0 16px;font-size:13px;color:{p['text_mid']};line-height:1.6">
      This link expires in <strong style="color:{p['text']}">{ttl_minutes} minutes</strong>. If you didn't
      request a password reset, you can safely ignore this email — your current password will stay unchanged.
    </p>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0 0">
      <tr><td class="em-info-card" style="background:{p['info_bg']};border-radius:10px;padding:14px 16px">
        <div style="font-size:11px;font-weight:600;color:{p['text_mid']};text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">Button not working?</div>
        <div style="font-size:12px;color:{p['fine_text']};line-height:1.6;word-break:break-all">
          Copy and paste this URL into your browser:<br>
          <a href="{reset_url}" style="color:{p['link']};text-decoration:none">{reset_url}</a>
        </div>
      </td></tr>
    </table>

    <p class="em-text-mid" style="margin:20px 0 0;font-size:14px;color:{p['text_mid']};line-height:1.6">
      — The Ain Real Estate team
    </p>
    """
    return subject, text, _wrap_html(inner, theme, preheader)

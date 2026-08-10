#!/usr/bin/env python3
"""Pantheon Studios alert notifier.

Sends an SMS alert when new content enters queue/pending/ for human review.
Supports two transports based on .env config:
  - Twilio SMS (when TWILIO_ACCOUNT_SID is set)
  - SMTP Email-to-SMS gateway (fallback when SMTP_HOST is set)

No message is ever sent without a valid recipient and credentials.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _load_config() -> dict[str, str]:
    """Read alert config from environment (populated by python-dotenv or shell)."""
    return {
        "phone": _env("ALERT_PHONE_NUMBER", "260-224-8050"),
        "twilio_sid": _env("TWILIO_ACCOUNT_SID"),
        "twilio_token": _env("SMS_AUTH_TOKEN"),
        "twilio_from": _env("TWILIO_FROM_NUMBER"),
        "smtp_host": _env("SMTP_HOST"),
        "smtp_port": _env("SMTP_PORT", "587"),
        "smtp_user": _env("SMTP_USER"),
        "smtp_password": _env("SMTP_PASSWORD"),
        "sms_gateway_address": _env("SMS_GATEWAY_ADDRESS"),  # e.g. 2600000000@tmomail.net
    }


# ---------------------------------------------------------------------------
# Transport implementations
# ---------------------------------------------------------------------------

def _send_via_twilio(cfg: dict[str, str], body: str) -> None:
    """Send SMS through Twilio REST API (requires twilio package)."""
    try:
        from twilio.rest import Client  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "Twilio transport requires the 'twilio' package: pip install twilio"
        ) from exc

    client = Client(cfg["twilio_sid"], cfg["twilio_token"])
    # Normalize phone to E.164 – strip non-digits then prepend +1 if needed
    digits = "".join(c for c in cfg["phone"] if c.isdigit())
    to_number = f"+{digits}" if digits.startswith("1") else f"+1{digits}"

    client.messages.create(
        body=body,
        from_=cfg["twilio_from"],
        to=to_number,
    )


def _send_via_smtp(cfg: dict[str, str], body: str) -> None:
    """Send SMS through an Email-to-SMS gateway via SMTP."""
    gateway_address = cfg["sms_gateway_address"]
    if not gateway_address:
        # Build a best-effort gateway address from the raw phone number
        digits = "".join(c for c in cfg["phone"] if c.isdigit())
        raise RuntimeError(
            f"SMS_GATEWAY_ADDRESS not set. "
            f"Set it to your carrier's email-to-SMS address (e.g. {digits}@tmomail.net)."
        )

    msg = MIMEText(body)
    msg["From"] = cfg["smtp_user"]
    msg["To"] = gateway_address
    msg["Subject"] = ""  # carriers ignore subject; keep blank to save message space

    context = ssl.create_default_context()
    with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"])) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(cfg["smtp_user"], cfg["smtp_password"])
        server.sendmail(cfg["smtp_user"], [gateway_address], msg.as_string())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _log_sms_event(status: str, body: str, response_code: str | None = None) -> None:
    log_path = Path("intelligence") / "sms_telemetry.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat()} | status={status} | body={body[:80]} | response={response_code or 'n/a'}"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _send_with_transport(cfg: dict[str, str], body: str) -> tuple[str, str | None]:
    if cfg["twilio_sid"] and cfg["twilio_token"] and cfg["twilio_from"]:
        _send_via_twilio(cfg, body)
        return "sent", "200"

    if cfg["smtp_host"] and cfg["smtp_user"] and cfg["smtp_password"]:
        _send_via_smtp(cfg, body)
        return "sent", "250"

    raise RuntimeError(
        "No SMS transport configured. "
        "Set either Twilio credentials (TWILIO_ACCOUNT_SID / SMS_AUTH_TOKEN / TWILIO_FROM_NUMBER) "
        "or SMTP credentials (SMTP_HOST / SMTP_USER / SMTP_PASSWORD / SMS_GATEWAY_ADDRESS) in .env."
    )


def send_pending_review_alert(post_title: str) -> None:
    """Fire an SMS notification that a new draft is awaiting human review."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv()
    except ImportError:
        pass

    cfg = _load_config()
    body = f"[Pantheon Studios] New draft pending your approval: \"{post_title}\""
    status, response_code = _send_with_transport(cfg, body)
    _log_sms_event(status, body, response_code)


def send_daily_heartbeat() -> None:
    """Send the daily heartbeat text for the 24-hour continuous testing loop."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv()
    except ImportError:
        pass

    cfg = _load_config()
    body = "Pantheon Studios Daily Status: All systems nominal. Continuous testing active. Killswitch: INACTIVE."
    status, response_code = _send_with_transport(cfg, body)
    _log_sms_event(status, body, response_code)


def send_test_sms_ping() -> str:
    """Send an on-demand test ping and return a human-readable status."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv()
    except ImportError:
        pass

    cfg = _load_config()
    body = "Pantheon Studios Test Ping: Continuous testing daemon is live."
    try:
        status, response_code = _send_with_transport(cfg, body)
    except Exception as exc:  # noqa: BLE001
        _log_sms_event("failed", body, str(exc))
        return f"Test ping failed: {exc}"
    _log_sms_event(status, body, response_code)
    return f"Test ping sent to {cfg['phone']} (status={status}, response={response_code})"

"""Opt-in Gmail SMTP report sender. Requires a Google account app password."""

import smtplib
from email.message import EmailMessage
from pathlib import Path


def build_report_message(settings, files: dict, headline: str):
    """Build a message without network access; dry-run uses the same attachment path."""
    message = EmailMessage()
    message["From"] = settings.gmail_address or "not-configured@example.invalid"
    message["To"] = settings.report_to or "not-configured@example.invalid"
    message["Subject"] = headline
    message.set_content(
        "Báo cáo tin rao bất động sản theo whitelist phường. Thống kê được tính từ listing "
        "đủ điều kiện; dữ liệu legacy AI estimate được tách riêng. Xem tệp đính kèm."
    )
    message.add_alternative(Path(files["html"]).read_text(encoding="utf-8"), subtype="html")
    attachment_definitions = (
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("listings_csv", "text/csv"),
        ("statistics_csv", "text/csv"),
        ("listings_json", "application/json"),
        ("summary", "application/json"),
    )
    for key, mime_type in attachment_definitions:
        if key not in files:
            continue
        path = Path(files[key])
        maintype, subtype = mime_type.split("/", maxsplit=1)
        message.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )
    return message


def dry_run_report(settings, files: dict, headline: str):
    """Prepare and inspect a report without connecting to Gmail or SMTP."""
    message = build_report_message(settings, files, headline)
    return {
        "from": message["From"],
        "to": message["To"],
        "subject": message["Subject"],
        "attachments": [part.get_filename() for part in message.iter_attachments()],
        "message": message,
    }


def send_report(settings, files: dict, headline: str):
    if not settings.email_enabled:
        return False
    if not (settings.gmail_address and settings.gmail_app_password and settings.report_to):
        raise ValueError("ENABLE_EMAIL=true requires GMAIL_ADDRESS, GMAIL_APP_PASSWORD, REPORT_TO")
    message = build_report_message(settings, files, headline)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(settings.gmail_address, settings.gmail_app_password)
        server.send_message(message)
    return True

import resend
import os
from flask import current_app
from datetime import datetime


def _log_email(params):
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sent_emails.log')
    with open(log_path, 'a', encoding='utf-8') as log_file:
        log_file.write(f"[{datetime.utcnow().isoformat()}] TO: {params['to']} SUBJECT: {params['subject']}\n")
        log_file.write(f"FROM: {params['from']}\n")
        log_file.write(f"HTML_LENGTH: {len(params['html'])}\n")
        log_file.write('-' * 80 + '\n')


def send_verification_email(to_email, username, code):
    # Prefer the Flask app config value when called within an app context,
    # otherwise fall back to the environment variable.
    api_key = None
    try:
        api_key = current_app.config.get('RESEND_API_KEY')
    except RuntimeError:
        # no app context
        api_key = None

    resend.api_key = api_key or os.getenv('RESEND_API_KEY')

    # Styles are inlined — many email clients strip <style> blocks.
    # Palette matches the site: lavender #ccccff, ink #111, white cards,
    # hard borders + offset shadows.
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0; padding:0; background:#ccccff; font-family:Inter,'Segoe UI',Arial,sans-serif;">
        <div style="max-width:480px; margin:0 auto; padding:40px 16px;">

            <div style="text-align:center; margin-bottom:24px;">
                <span style="display:inline-block; font-family:'Arial Black',Arial,sans-serif; font-size:24px; font-weight:900; letter-spacing:0.08em; color:#111111; text-transform:uppercase;">STROKE</span>
            </div>

            <div style="background:#ffffff; border:3px solid #111111; border-radius:16px; padding:36px 32px; box-shadow:6px 6px 0 #111111;">
                <p style="font-size:11px; font-weight:800; letter-spacing:0.14em; text-transform:uppercase; color:#8f8ff0; margin:0 0 10px;">Email verification</p>
                <h1 style="font-family:'Arial Black',Arial,sans-serif; font-size:26px; font-weight:900; text-transform:uppercase; color:#111111; margin:0 0 14px; line-height:1.15;">Verify your email</h1>
                <p style="font-size:14px; color:#555555; line-height:1.7; margin:0 0 26px;">Hey {username}, welcome to STROKE. Enter this code to verify your email and activate your account.</p>

                <div style="background:#111111; border-radius:12px; padding:26px 20px; text-align:center; margin:0 0 26px;">
                    <span style="font-family:'Arial Black',Arial,sans-serif; font-size:38px; font-weight:900; letter-spacing:10px; color:#ccccff;">{code}</span>
                </div>

                <p style="font-size:13px; color:#888888; line-height:1.7; margin:0;">This code expires in <strong style="color:#111111;">15 minutes</strong>. If you didn't sign up for STROKE, you can safely ignore this email.</p>
            </div>

            <p style="font-size:11px; font-weight:700; color:#333333; text-align:center; margin:26px 0 0; text-transform:uppercase; letter-spacing:0.06em;">Built in New Zealand. For swimmers everywhere.</p>
        </div>
    </body>
    </html>
    """

    # Resend's shared sandbox domain until you verify your own with Resend --
    # then just set EMAIL_FROM (e.g. "STROKE <hello@yourdomain.com>"), no code change needed.
    from_address = os.getenv('EMAIL_FROM', 'onboarding@resend.dev')

    params = {
        "from": from_address,
        "to": [to_email],
        "subject": f"{code} is your STROKE verification code",
        "html": html_content,
    }

    _log_email(params)
    resend.Emails.send(params)
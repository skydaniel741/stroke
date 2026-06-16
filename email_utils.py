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

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Inter, sans-serif; background: #060f1c; color: #EAF5FF; margin: 0; padding: 0; }}
            .wrap {{ max-width: 480px; margin: 40px auto; padding: 40px; background: #0c1c30; border-radius: 14px; border: 0.5px solid rgba(160,221,255,0.1); }}
            .logo {{ font-size: 18px; font-weight: 500; letter-spacing: 0.16em; color: #A0DDFF; margin-bottom: 28px; }}
            h1 {{ font-size: 22px; font-weight: 400; color: #EAF5FF; margin-bottom: 12px; }}
            p {{ font-size: 14px; color: rgba(234,245,255,0.55); line-height: 1.7; margin-bottom: 24px; }}
            .code {{ font-size: 42px; font-weight: 300; letter-spacing: 8px; color: #A0DDFF; text-align: center; padding: 24px; background: rgba(160,221,255,0.06); border-radius: 10px; border: 0.5px solid rgba(160,221,255,0.15); margin: 24px 0; }}
            .footer {{ font-size: 12px; color: rgba(234,245,255,0.25); margin-top: 28px; }}
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="logo">STROKE</div>
            <h1>Verify your email</h1>
            <p>Hey {username}, welcome to STROKE. Enter this code to verify your email and activate your account.</p>
            <div class="code">{code}</div>
            <p>This code expires in 15 minutes. If you didn't sign up for STROKE, ignore this email.</p>
            <div class="footer">stroke.app · Built in New Zealand</div>
        </div>
    </body>
    </html>
    """

    params = {
        "from": "onboarding@resend.dev",
        "to": [to_email],
        "subject": f"{code} is your STROKE verification code",
        "html": html_content,
    }

    _log_email(params)
    resend.Emails.send(params)
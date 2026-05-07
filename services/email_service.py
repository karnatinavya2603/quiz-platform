import smtplib
import threading
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from config import SMTP_SENDER, SMTP_PASSWORD, ADMIN_EMAIL


def send_email_async(to, subject, body, pdf_path=None):
    def _send():
        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"]    = SMTP_SENDER
            msg["To"]      = to
            msg.attach(MIMEText(body, "html"))

            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f"attachment; filename=result_{to.split('@')[0]}.pdf")
                msg.attach(part)

            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls()
                s.login(SMTP_SENDER, SMTP_PASSWORD)
                s.send_message(msg)
            print(f"[EMAIL] Sent to {to}")
        except Exception as e:
            print(f"[EMAIL ERROR] {e}")
    threading.Thread(target=_send, daemon=True).start()


def notify_admin_login(username, email, role, time_str):
    body = f"""
    <div style="font-family:Arial;max-width:480px;margin:auto;border:1px solid #ddd;border-radius:10px;padding:24px;">
      <h3>Quiz Platform — Login Alert</h3>
      <p><b>User:</b> {username}</p>
      <p><b>Email:</b> {email}</p>
      <p><b>Role:</b> {role}</p>
      <p><b>Time:</b> {time_str}</p>
    </div>"""
    send_email_async(ADMIN_EMAIL, f"[Quiz] Login: {username}", body)


def notify_user_login(to_email, username):
    body = f"""
    <div style="font-family:Arial;max-width:480px;margin:auto;border:1px solid #ddd;border-radius:10px;padding:24px;">
      <h3>Welcome, {username}!</h3>
      <p>You have successfully logged in to the Quiz Platform.</p>
      <p>Good luck with your exam!</p>
    </div>"""
    send_email_async(to_email, "Quiz Platform — Login Successful", body)


def notify_admin_registration(username, email, role, token, base_url):
    approve_url = f"{base_url.rstrip('/')}/approve_token/{token}"
    body = f"""
    <div style="font-family:Arial;max-width:480px;margin:auto;border:1px solid #ddd;border-radius:10px;padding:24px;">
      <h3>New Registration — Approval Needed</h3>
      <p><b>Username:</b> {username}</p>
      <p><b>Email:</b> {email}</p>
      <p><b>Registered As:</b> {role.capitalize()}</p>
      <hr>
      <a href="{approve_url}"
         style="display:inline-block;padding:12px 28px;background:#28a745;color:#fff;
                text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold;">
        Approve {username}
      </a>
    </div>"""
    send_email_async(ADMIN_EMAIL, f"[Quiz] New Registration ({role}): {username}", body)


def send_approval_email(to_email, username, base_url):
    login_url = f"{base_url.rstrip('/')}/login"
    body = f"""
    <div style="font-family:Arial;max-width:480px;margin:auto;border:1px solid #ddd;border-radius:10px;padding:24px;">
      <h2 style="color:#28a745;">Account Approved!</h2>
      <p>Hello <b>{username}</b>,</p>
      <p>Your account has been approved. You can now login:</p>
      <a href="{login_url}"
         style="display:inline-block;padding:12px 28px;background:#007bff;color:#fff;
                text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold;">
        Login Now
      </a>
    </div>"""
    send_email_async(to_email, "Quiz Platform — Account Approved", body)


def send_result_email(to_email, username, mcq_score, mcq_total, coding_score, pdf_path):
    total = mcq_score + coding_score
    body = f"""
    <div style="font-family:Arial;max-width:500px;margin:auto;padding:24px;border:1px solid #ddd;border-radius:10px;">
      <h2 style="color:#28a745;">Exam Completed!</h2>
      <p>Hello <b>{username}</b>, your result PDF is attached.</p>
      <table style="width:100%;border-collapse:collapse;margin:12px 0;">
        <tr style="background:#1e2a3a;color:#fff;">
          <th style="padding:10px;text-align:left;">Section</th>
          <th style="padding:10px;text-align:left;">Score</th>
        </tr>
        <tr><td style="padding:8px;border:1px solid #ddd;">MCQ</td>
            <td style="padding:8px;border:1px solid #ddd;"><b>{mcq_score} / {mcq_total}</b></td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;">Coding</td>
            <td style="padding:8px;border:1px solid #ddd;"><b>{coding_score}</b></td></tr>
        <tr style="background:#d4edda;">
          <td style="padding:8px;border:1px solid #ddd;"><b>Total Score</b></td>
          <td style="padding:8px;border:1px solid #ddd;"><b>{total}</b></td>
        </tr>
      </table>
    </div>"""
    send_email_async(to_email, "Quiz Platform — Your Result (PDF Attached)", body, pdf_path)

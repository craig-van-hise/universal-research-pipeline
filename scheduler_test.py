#!/usr/bin/env python3
"""
Scholar-Alert Scheduler
Checks for new papers and sends email notifications.
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv
import argparse

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from alerts_db import (
    init_db, 
    get_active_subscriptions, 
    update_last_run,
    reset_dates_for_testing
)

# Load environment variables
load_dotenv(override=True)

def send_notification_email(to_email: str, query: str, papers_list: list):
    """
    Send email notification about new papers.
    
    Args:
        to_email: Recipient email address
        query: Search query that triggered the alert
        papers_list: List of paper dictionaries with 'title', 'doi', 'url', etc.
    """
    sender_email = os.getenv("GOOGLE_EMAIL") or os.getenv("SENDER_EMAIL")
    app_password = os.getenv("GOOGLE_APP_PASSWORD") or os.getenv("SENDER_APP_PASSWORD")
    
    if not sender_email or not app_password:
        print("❌ Error: GOOGLE_EMAIL and GOOGLE_APP_PASSWORD must be set in .env")
        return False
    
    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🔔 New Research Found: {query}"
    msg['From'] = sender_email
    msg['To'] = to_email
    
    # Create HTML body
    html_body = f"""
    <html>
      <head></head>
      <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #2c3e50;">📚 ScholarStack Alert</h2>
        <p>New papers found for your search: <strong>{query}</strong></p>
        <p>Found <strong>{len(papers_list)}</strong> new paper(s):</p>
        <hr style="border: 1px solid #ecf0f1;">
    """
    
    for i, paper in enumerate(papers_list, 1):
        title = paper.get('Title', 'Untitled')
        doi = paper.get('DOI', '')
        url = paper.get('Source_URL', '')
        authors = paper.get('Authors', 'Unknown')
        year = paper.get('Year', '')
        
        # Prefer DOI link, fallback to source URL
        link = f"https://doi.org/{doi}" if doi else url
        
        html_body += f"""
        <div style="margin-bottom: 20px; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #3498db;">
          <h3 style="margin-top: 0; color: #2c3e50;">{i}. {title}</h3>
          <p style="margin: 5px 0; color: #7f8c8d;">
            <strong>Authors:</strong> {authors[:100]}{'...' if len(str(authors)) > 100 else ''}<br>
            <strong>Year:</strong> {year}
          </p>
          <p style="margin: 10px 0;">
            <a href="{link}" style="color: #3498db; text-decoration: none;">📄 View Paper</a>
          </p>
        </div>
        """
    
    html_body += """
        <hr style="border: 1px solid #ecf0f1;">
        <p style="color: #95a5a6; font-size: 12px;">
          This is an automated alert from ScholarStack. 
          To manage your alerts, open the ScholarStack app.
        </p>
      </body>
    </html>
    """
    
    # Attach HTML
    msg.attach(MIMEText(html_body, 'html'))
    
    # Send email
    try:
        print(f"📧 Connecting to Gmail SMTP...")
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            print(f"🔐 Logging in as {sender_email}...")
            server.login(sender_email, app_password)
            print(f"📤 Sending email to {to_email}...")
            server.send_message(msg)
        
        print(f"✅ Email sent successfully to {to_email}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication Error: {e}")
        print("   Check that GOOGLE_APP_PASSWORD is correct (16-char app password, not regular password)")
        return False
    except Exception as e:
        print(f"❌ Email send error: {e}")
        return False

def check_alerts(test_mode=False):
    """
    Check all active subscriptions for new papers.
    
    Args:
        test_mode: If True, uses time travel to trigger alerts
    """
    print("\n" + "="*60)
    print("🔍 ScholarStack Alert Checker")
    print("="*60 + "\n")
    
    # Initialize database
    init_db()
    
    # Time travel for testing
    if test_mode:
        print("⏰ TEST MODE: Resetting dates to 30 days ago...")
        reset_dates_for_testing()
    
    # Get active subscriptions
    subscriptions = get_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions found.")
        return
    
    print(f"📬 Found {len(subscriptions)} active subscription(s)\n")
    
    for sub in subscriptions:
        sub_id = sub['id']
        email = sub['user_email']
        query = sub['search_query']
        source = sub['search_source']
        frequency = sub.get('frequency', 'daily')
        last_run = sub['last_run']
        
        print(f"🔎 Checking: '{query}' for {email}")
        print(f"   Frequency: {frequency}")
        print(f"   Last checked: {last_run}")
        
        # Check if alert should run based on frequency
        from alert_scheduler import should_run_alert
        
        if not should_run_alert(str(last_run), frequency):
            print(f"   ⏭️  Skipping (not time yet based on {frequency} schedule)\n")
            continue
        
        # TODO: Implement actual search logic using src/1_search_omni.py
        # For now, we'll simulate finding papers
        
        # Simulated new papers (in production, this would call the search API)
        new_papers = [
            {
                'Title': 'Example Paper on Spatial Audio',
                'Authors': 'Smith, J., Doe, A.',
                'Year': '2024',
                'DOI': '10.1234/example.2024',
                'Source_URL': 'https://example.com/paper1'
            }
        ]
        
        if new_papers:
            print(f"   ✨ Found {len(new_papers)} new paper(s)!")
            
            # Send notification
            success = send_notification_email(email, query, new_papers)
            
            if success:
                # Update last_run timestamp
                update_last_run(sub_id, datetime.now())
                print(f"   ✅ Notification sent and timestamp updated\n")
            else:
                print(f"   ❌ Failed to send notification\n")
        else:
            print(f"   📭 No new papers found\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ScholarStack Alert Scheduler")
    parser.add_argument('--test', action='store_true', help='Run in test mode (time travel enabled)')
    args = parser.parse_args()
    
    check_alerts(test_mode=args.test)

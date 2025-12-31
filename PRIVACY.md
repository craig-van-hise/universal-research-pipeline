# Privacy Policy for ScholarStack

**Last Updated:** December 30, 2024

## Overview

ScholarStack is a research paper discovery and management tool designed to help researchers find, organize, and manage academic papers. This privacy policy explains how we handle your data.

## Information We Collect

### Information You Provide
- **Google Account Information:** When you sign in with Google, we access:
  - Your name
  - Your email address
  - Your profile picture
- **Search Queries:** Topics and keywords you search for
- **Alert Subscriptions:** Email addresses and search queries for research alerts
- **Settings:** Your preferences for paper organization and search parameters

### Automatically Collected Information
- **Search History:** Locally stored record of your previous searches
- **Downloaded Papers:** Metadata about papers you've downloaded (titles, authors, DOIs, etc.)

## How We Use Your Information

We use the collected information to:
- **Authenticate Your Account:** Verify your identity via Google OAuth
- **Provide Core Functionality:** Search for papers, organize results, and manage your library
- **Send Research Alerts:** Email you when new papers matching your saved searches are found
- **Export to Google Drive:** Upload your research library to your Google Drive account (only when you explicitly request it)
- **Improve User Experience:** Remember your preferences and search history

## Data Storage

### Local Storage
- All data is stored **locally on your device**
- Search history, settings, and downloaded papers are stored in local files
- Alert subscriptions are stored in a local SQLite database (`data/alerts.db`)

### Google Services
- **Google OAuth:** Used only for authentication
- **Google Drive:** Used only when you explicitly click "Save to Drive" - uploads papers to a folder named `_Research_Assistant_Imports` in your Google Drive

### No Cloud Storage
- We do **not** store your data on any remote servers
- We do **not** share your data with third parties
- We do **not** sell your data

## Third-Party Services

ScholarStack integrates with the following third-party services:

1. **Google OAuth & Drive API**
   - Purpose: Authentication and optional file storage
   - Data shared: Name, email, profile picture (for OAuth); PDF files (for Drive export)
   - Privacy Policy: [Google Privacy Policy](https://policies.google.com/privacy)

2. **OpenAlex**
   - Purpose: Academic paper search
   - Data shared: Search queries
   - Privacy Policy: [OpenAlex Privacy](https://openalex.org/privacy)

3. **Unpaywall**
   - Purpose: Finding open-access versions of papers
   - Data shared: DOIs and search queries
   - Privacy Policy: [Unpaywall Privacy](https://unpaywall.org/legal)

4. **Gmail SMTP**
   - Purpose: Sending research alert emails
   - Data shared: Your email address and alert preferences
   - Privacy Policy: [Google Privacy Policy](https://policies.google.com/privacy)

## Data Security

- **OAuth Credentials:** Stored in session state (cleared when you sign out)
- **API Keys:** Stored in `.env` file (never committed to version control)
- **Local Files:** Protected by your device's file system permissions
- **Email Alerts:** Sent via encrypted SMTP (TLS)

## Your Rights

You have the right to:
- **Access Your Data:** All data is stored locally and accessible to you
- **Delete Your Data:** Delete local files, clear search history, or remove alert subscriptions at any time
- **Revoke Access:** Revoke ScholarStack's access to your Google account at [Google Account Permissions](https://myaccount.google.com/permissions)
- **Export Your Data:** Download your library as a ZIP file at any time

## Data Retention

- **Search History:** Retained locally until you clear it
- **Alert Subscriptions:** Retained until you delete them
- **Downloaded Papers:** Retained locally until you delete them
- **OAuth Tokens:** Cleared when you sign out or revoke access

## Children's Privacy

ScholarStack is not intended for use by children under 13. We do not knowingly collect personal information from children.

## Changes to This Policy

We may update this privacy policy from time to time. Changes will be reflected by updating the "Last Updated" date at the top of this policy.

## Open Source

ScholarStack is open-source software. You can review the code to verify our privacy practices at any time.

## Contact

For questions about this privacy policy or data practices, please contact the developer via the project repository.

## Consent

By using ScholarStack, you consent to this privacy policy.

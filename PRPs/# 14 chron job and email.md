
### **Feature Implementation: Local Alert System (Real Email Test)**

**Context:**
We are building the "Scholar-Alert" scheduler. We need a fully functional **local test rig** that checks for new papers and sends **REAL notification emails** to the user using Gmail SMTP.

**1. Database Schema (SQLite)**
Create/Update `alerts.db` using `sqlite3`. Ensure the `subscriptions` table exists:

* `id` (Primary Key)
* `user_email` (String) - *Target email address*
* `search_query` (String)
* `search_source` (String)
* `last_run` (Datetime)
* `active` (Boolean)

**2. Streamlit UI Updates (`app.py`)**
Add a "Manage Alerts" section to the Sidebar.

* **Input:** "Save current search as Alert."
* **Logic:** Insert the current search and the user's email into `alerts.db`.
* **Visual:** Show a list of active alerts.

**3. The Scheduler Script (`scheduler_test.py`)**
Create a script that performs the check and sends the email.

**A. The Search Logic**

* Connect to `alerts.db`.
* For every active subscription, run `search_papers()`.
* **Filter:** Keep only papers where `publication_date` > `last_run`.

**B. The Email Logic (Real SMTP)**

* **Library:** Use `smtplib` and `email.message`.
* **Credentials:** distinct variables `SENDER_EMAIL` and `SENDER_APP_PASSWORD` (load these from a `.env` file or constants at the top).
* **Function:** `send_notification_email(to_email, query, papers_list)`
* **Server:** `smtp.gmail.com`
* **Port:** `587` (TLS)
* **Logic:**
1. Login to SMTP server.
2. Construct a proper HTML email.
3. Subject: "New Research Found: [Query Name]"
4. Body: A clean list of the new papers found (Title + Link).
5. Send the email.




* **Error Handling:** Wrap the send logic in a `try/except` block. If the password is wrong or connection fails, print the specific error to the console so we can debug.

**4. The "Time Travel" Helper**
Include a function `reset_dates_for_testing()` in the script that forces all `last_run` dates in the database to **30 days ago**. This allows us to run the script immediately and trigger a "New Paper" condition to verify the email actually sends.

---

### **Crucial Setup Step for You (Before running the code)**

To make this work, you cannot use your normal Gmail login password (Google blocks scripts from doing that). You need an **App Password**:

1. Go to your **Google Account Settings** > **Security**.
2. Enable **2-Step Verification** (if not already on).
3. Search for **"App Passwords"** in the search bar.
4. Create a new one named "ScholarStack Test".
5. Google will give you a 16-character code (e.g., `abcd efgh ijkl mnop`). **This is the password** you will put in your script (or `.env` file).

Run the prompt, get the code, insert that App Password, and the email will arrive in your inbox for real.
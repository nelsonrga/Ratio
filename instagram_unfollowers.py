"""
Instagram Unfollower Checker
Logs into Instagram via Chrome and returns users you follow who don't follow you back.

Requirements:
    pip install selenium webdriver-manager
"""

import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

PROFILE_URL_RE = re.compile(r'https://www\.instagram\.com/([^/?#]+)/$')


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def wait_for_login(driver):
    driver.get("https://www.instagram.com/accounts/login/")
    log("  Chrome is open. Log in manually (including any 2FA).")
    log("  Waiting until you reach the home feed...")
    WebDriverWait(driver, 300).until(EC.url_to_be("https://www.instagram.com/"))
    time.sleep(2)


# ── Phase 1: Read counts from profile page ────────────────────────────────────

def get_profile_counts(driver, profile_url):
    """Return (followers_count, following_count) as shown on the profile page."""
    driver.get(profile_url)
    wait = WebDriverWait(driver, 15)
    time.sleep(2)

    followers_link = wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "followers")))
    following_link = wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "following")))

    def parse_count(text):
        m = re.search(r'[\d,]+', text)
        return int(m.group().replace(',', '')) if m else 0

    return parse_count(followers_link.text), parse_count(following_link.text)


# ── Phase 2: Scrape a followers/following dialog ───────────────────────────────

def find_scrollable(driver):
    """Use JS to find the first element inside the dialog with scrollable content."""
    return driver.execute_script("""
        var dialog = document.querySelector('div[role="dialog"]');
        if (!dialog) return null;
        var nodes = dialog.querySelectorAll('*');
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].scrollHeight > nodes[i].clientHeight + 10) {
                return nodes[i];
            }
        }
        return dialog;
    """)


def scrape_dialog(driver, profile_url, list_type, expected):
    """
    Click the followers/following link, scroll the dialog until all users are
    collected or no new users load. Returns (set_of_usernames, is_complete).
    """
    driver.get(profile_url)
    wait = WebDriverWait(driver, 15)
    time.sleep(2)

    link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, list_type)))
    link.click()
    time.sleep(2)

    wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(1)

    usernames = set()
    last_count = -1
    stall_rounds = 0

    while True:
        # Collect all visible profile links in the dialog
        anchors = driver.find_elements(By.XPATH, "//div[@role='dialog']//a[@href]")
        for a in anchors:
            href = a.get_attribute("href") or ""
            m = PROFILE_URL_RE.match(href)
            if m:
                usernames.add(m.group(1))

        print(f"\r  Collected {len(usernames)} / {expected} {list_type}...", end="", flush=True)

        if expected and len(usernames) >= expected:
            break

        if len(usernames) == last_count:
            stall_rounds += 1
            if stall_rounds >= 3:
                break  # Tried 3 times with no progress — give up
        else:
            stall_rounds = 0

        last_count = len(usernames)

        # Scroll the actual scrollable container inside the dialog
        container = find_scrollable(driver)
        if container:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", container)
        time.sleep(1.5)

    print()  # newline after progress line
    is_complete = expected is None or len(usernames) >= expected
    return usernames, is_complete


# ── Main ──────────────────────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# UI support and logging
# ---------------------------------------------------------------------------

log_widget = None  # will be set to a Text widget if GUI is used

def log(msg: str):
    """Print to console and append to the GUI text area if present."""
    print(msg)
    if log_widget is not None:
        try:
            log_widget.configure(state='normal')
            log_widget.insert('end', msg + "\n")
            log_widget.see('end')
            log_widget.configure(state='disabled')
        except Exception:
            pass


def run_check(username: str):
    """Perform the Instagram unfollower logic for a given username."""
    log(f"Starting check for @{username}")
    profile_url = f"https://www.instagram.com/{username}/"

    log("Opening browser...")
    driver = create_driver()

    try:
        # Login
        log("\nLogging in...")
        wait_for_login(driver)
        log("Logged in.\n")

        # ── Phase 1: Profile summary ──
        log("── Profile Summary ──────────────────────")
        total_followers, total_following = get_profile_counts(driver, profile_url)
        log(f"  Followers:  {total_followers}")
        log(f"  Following:  {total_following}\n")

        # ── Phase 2: Scrape followers ──
        log("── Scraping Followers ───────────────────")
        followers, followers_ok = scrape_dialog(driver, profile_url, "followers", total_followers)
        if not followers_ok:
            log(f"  WARNING: Could not verify all followers (got {len(followers)} / {total_followers})")
        else:
            log(f"  Verified: {len(followers)} followers collected")
        log("")

        # ── Phase 3: Scrape following ──
        log("── Scraping Following ───────────────────")
        following, following_ok = scrape_dialog(driver, profile_url, "following", total_following)
        if not following_ok:
            log(f"  WARNING: Could not verify all following (got {len(following)} / {total_following})")
        else:
            log(f"  Verified: {len(following)} following collected")
        log("")

        # ── Phase 4: Results ──
        log("── Results ──────────────────────────────")
        not_following_back = following - followers
        not_following_back.discard(username)

        if not followers_ok or not following_ok:
            log("  NOTE: Results may be incomplete — not all users could be verified.")
        log(f"  You follow:          {len(following)}")
        log(f"  Follow you back:     {len(following & followers)}")
        log(f"  Not following back:  {len(not_following_back)}")

        if not_following_back:
            log("\n  Users not following you back:")
            for user in sorted(not_following_back):
                log(f"    @{user}")

    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# GUI launcher
# ---------------------------------------------------------------------------

def gui_main():
    """Start a simple Tkinter GUI for getting input and showing progress."""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        # tkinter isn't installed/available, tell the user and fall back
        print("WARNING: tkinter not available; running in console mode.")
        username = input("Instagram username: ").strip()
        if username:
            try:
                run_check(username)
            except Exception as exc:
                print(f"Error: {exc}")
        return

    root = tk.Tk()
    root.title("Instagram Unfollower Checker")

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    tk.Label(frame, text="Instagram username:").grid(row=0, column=0, sticky='e')
    username_var = tk.StringVar()
    entry = tk.Entry(frame, textvariable=username_var, width=30)
    entry.grid(row=0, column=1, padx=(5, 0))

    start_btn = tk.Button(frame, text="Start")
    start_btn.grid(row=0, column=2, padx=(10, 0))

    log_text = tk.Text(root, state='disabled', width=80, height=20)
    log_text.pack(padx=10, pady=(0,10))

    global log_widget
    log_widget = log_text

    def start_check():
        user = username_var.get().strip()
        if not user:
            messagebox.showwarning("Input required", "Please enter a username")
            return
        entry.config(state='disabled')
        start_btn.config(state='disabled')
        thread = __import__('threading').Thread(target=lambda: _worker(user), daemon=True)
        thread.start()

    def _worker(user):
        try:
            run_check(user)
            messagebox.showinfo("Done", "Processing complete")
        except Exception as exc:
            err_msg = f"An unexpected error occurred:\n{exc}"
            log(err_msg)
            messagebox.showerror("Error", err_msg)

    start_btn.config(command=start_check)

    root.mainloop()


def main():
    # launch the GUI (gui_main handles a console fallback internally)
    gui_main()


if __name__ == "__main__":
    main()

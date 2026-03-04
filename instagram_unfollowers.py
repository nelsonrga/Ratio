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
    print("  Chrome is open. Log in manually (including any 2FA).")
    print("  Waiting until you reach the home feed...")
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

def main():
    username = input("Instagram username: ").strip()
    profile_url = f"https://www.instagram.com/{username}/"

    driver = create_driver()

    try:
        # Login
        print("\nLogging in...")
        wait_for_login(driver)
        print("Logged in.\n")

        # ── Phase 1: Profile summary ──
        print("── Profile Summary ──────────────────────")
        total_followers, total_following = get_profile_counts(driver, profile_url)
        print(f"  Followers:  {total_followers}")
        print(f"  Following:  {total_following}")
        print()

        # ── Phase 2: Scrape followers ──
        print("── Scraping Followers ───────────────────")
        followers, followers_ok = scrape_dialog(driver, profile_url, "followers", total_followers)
        if not followers_ok:
            print(f"  WARNING: Could not verify all followers (got {len(followers)} / {total_followers})")
        else:
            print(f"  Verified: {len(followers)} followers collected")
        print()

        # ── Phase 3: Scrape following ──
        print("── Scraping Following ───────────────────")
        following, following_ok = scrape_dialog(driver, profile_url, "following", total_following)
        if not following_ok:
            print(f"  WARNING: Could not verify all following (got {len(following)} / {total_following})")
        else:
            print(f"  Verified: {len(following)} following collected")
        print()

        # ── Phase 4: Results ──
        print("── Results ──────────────────────────────")
        not_following_back = following - followers
        not_following_back.discard(username)

        if not followers_ok or not following_ok:
            print("  NOTE: Results may be incomplete — not all users could be verified.")
        print(f"  You follow:          {len(following)}")
        print(f"  Follow you back:     {len(following & followers)}")
        print(f"  Not following back:  {len(not_following_back)}")

        if not_following_back:
            print("\n  Users not following you back:")
            for user in sorted(not_following_back):
                print(f"    @{user}")

    finally:
        input("\nPress Enter to close the browser...")
        driver.quit()


if __name__ == "__main__":
    main()

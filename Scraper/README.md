# Web Scraping Pipeline Documentations

This document describes the structure, functionality, and configuration of the hybrid web scraping script, designed to efficiently collect full text content from various URLs, including those protected by paywalls or sourced from data aggregators.

# 1. Overview and Key Features

The script implements a hybrid scraping strategy: it first attempts a fast, header-based request using requests and falls back to a full browser simulation using Selenium (Chrome/Chromedriver) if the initial attempt fails, encounters a 403 Forbidden error, or if the target is a data aggregator.

## Core Capabilities:

- **`Hybrid Fetching:`** Utilizes requests for speed and Selenium for dynamic content rendering and anti-bot mitigation.

- **`Aggregator Handling :`** Executes a two-step navigation process to find and scrape the original source article linked by aggregators .

- **`Obstacle Clearing:`** Automatically attempts to close common pop-ups (cookies, newsletters) and handles "press-and-hold" human verification challenges.

- **`Robust Error Handling:`**` Implements exponential backoff for server errors (5xx) and explicitly logs 404/paywall issues.

## 2. Prerequisites and Dependencies

This project requires Python 3.x and the following libraries, which must be installed in your environment:

## A. **`Python Libraries :`**

```bash
pip install -r requirements.txt
```

## B. **`Web Driver :`**

This script is designed to use Google Chrome and the ChromeDriver executable.

| Constant           | Description                                                                                                                                                                         | Your Current Value |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| CHROME_DRIVER_PATH | The absolute path of the chromedriver.exe executable same as the python code file url_scraper.py or save it into a directory that is already part of your system's PATH. (Critical) | chromedriver.exe   |

- ### **` Action Required by the User :`**

* **Download :** If the provided ChromeDriver is nor suitable download the correct version of ChromeDriver that matches your installed Chrome Browser version. You can find this on the official Chrome for Testing site or you can download it by clicking this link [https://developer.chrome.com/docs/chromedriver/downloads](URL "Chrome_driver")

* **Placement (On the System PATH) :** Place the downloaded chromedriver.exe (or just chromedriver on Linux/Mac) into a directory that is already part of your system's PATH.

* **Alternative :** If the you prefer not to modify your PATH, please ensure the value of CHROME_DRIVER_PATH path above is correct before running the script and that the driver is in the same folder as the code.

## 3. Configuration and Files

## **` A. File Structure Maintained :`**

| File/Folder               | Purpose                                           | Action                                                           |
| :------------------------ | :------------------------------------------------ | :--------------------------------------------------------------- |
| **`url_scraper.py`**      | The main Python code file.                        | submitted.                                                       |
| **`urls.csv`**            | The input file containing URLs to scrape.         | Must be provided in the same file.                               |
| `scraped_data_output.csv` | Output file.                                      | Generated upon successful run.                                   |
| **`chromedriver.exe`**    | The Chrome Driver same version as the your chrome | Downloaded and moved to the same folder as the main Python code. |

## **`B. Initial Variable Settings:`**

| Constant               | Description                                                                     | Default Value      |
| ---------------------- | ------------------------------------------------------------------------------- | ------------------ |
| **`CSV_FILE_PATH`**    | The input file containing the URLs to scrape.                                   | urls.csv           |
| **`TIMEOUT_SECONDS`**  | The maximum time (in seconds) to wait for an HTTP request to complete.          | 30                 |
| **`SLEEP_SECONDS`**    | Base time (in seconds) to pause between scraping individual pages.              | 3                  |
| **`MAX_RETRIES`**      | Maximum number of attempts for handling temporary server errors (5xx).          | 3                  |
| **`USER_AGENTS`**      | List of rotating user-agent strings to mimic different browsers.                | 4 standard strings |
| **`SOURCE_SELECTORS`** | List of CSS selectors used to locate external source links on aggregator pages. | Multiple selectors |

## 4. Run Instructions

#### Open Terminal/Command Prompt: Navigate to the folder containing url_scraper.py and urls.csv.

- **`Install Libraries`**

```bash
pip install -r requirements.txt
```

- **`Execute the Script :`** Run the main Python file :-

```bash
python url_scraper.py
```

- **`Review Output :`** The terminal will display success/failure logging for each URL, followed by a Scraping Summary.

- **`Check Results :`** A new file named scraped_data_output.csv will be generated with columns for url, status, error, and content_preview.

## 5. Design Decisions and Assumptions

### A. Paywall Bypass Logic (Key Design)

The scraper employs a fail-fast, tiered strategy to handle paywalls and dynamically rendered content:

- **`Tier 1 (Speed):`** Attempts to fetch the page using the requests library with a random User-Agent.

- **`Tier 2 (Bypass):`** If the request fails (e.g., 403 Forbidden) or detects paywall keywords (paywall, subscribe to read), it falls back to Selenium.

- **`Tier 3 (Referer Spoofing):`** Selenium spoofs the page's Referer header to Google [https://www.google.com/](URL "Google") and refreshes. This is the primary method for bypassing common news site paywalls.

- **`Tier 4 (Obstacle Clearing):`** Only if the paywall is cleared, the script proceeds to click common pop-ups (cookie banners, newsletters) and execute "press-and-hold" challenges before final scraping and cleaning secondary elements.

- **`Tier 5 (Aggregator Handling - Specialized Strategy):`** For URLs known to be data aggregators (e.g., Statista), the script forces a two-step navigation. It finds the original external source link on the aggregator page, navigates directly to that link, and scrapes the definitive source for maximum data accuracy and avoid complex paywall blockage.

# B. Key Assumptions

1.  **In Scraping :**

    - **Assumption:** Websites employ varying levels of anti-bot/anti-scraping defenses.
    - **Decision:** Implement a tiered scraping approach to prioritize efficiency while maximizing success:
      - **Tier 1 (Requests):** Fastest and simplest; used first. Assumes basic content is accessible without JS.
      - **Tier 2-5 (Selenium):** Used as a mandatory fallback for dynamic content, 403 blocks, or suspected soft paywalls. Assumes human-like behavior (JS execution, cookies) is necessary.

2.  **in Aggregator Handling :**

    - **Assumption:** Most target URLs are aggregator/summary pages and the goal is to reach the **original source**.
    - **Decision:** The scraper includes special two-step logic (`if "aggrigator_page.com" in url.lower():` in `scrape_page`): it finds the external link on the aggregator page using `find_and_get_source_url` and then navigates to that external source before scraping the final content.

3.  **In Anti-Detection and Obstacle Clearing:**

    - **Assumption:** Standard anti-bot measures check for User-Agent headers, traffic origin (referrer), and common interactive challenges.
    - **Decision:**
      - **User Agents:** Rotate a list of common desktop User-Agents.
      - **Referrer Spoofing:** Spoof the `document.referrer` to `https://www.google.com/` to appear as if traffic came from a search engine.
      - **Pop-up Handling:** `handle_selenium_obstacles` targets common cookie banners, newsletter modals, and specific "press-and-hold" human verification challenges.

4.  **In Validation and Fallbacks :**

    - **Assumption:** If requests fail or return content containing keywords like "paywall," "403 forbidden," "enable javascript," or if the cleaned text length is less than 100 characters, the scrape is considered a failure or a stub.
    - **Decision:** This validation logic is the _primary_ trigger for Selenium.

5.  **In Error Handling :**

    - **Assumption:** 5xx server errors are temporary, while 404s are permanent.
    - **Decision:** Exponential backoff and retries (up to `MAX_RETRIES`) are implemented for 5xx errors and connection issues in `handle_edge_cases`.

6.  **In Data Cleaning:**

    - **Assumption:** Elements commonly used for navigation, ads, footers, and known paywall overlays can be safely removed from the HTML using general CSS selectors before final text extraction.
    - **Decision:** The `clean_html` function decomposes elements matching selectors like `'aside', 'footer', 'nav', 'iframe', '.ad-banner',` and paywall-related classes.

7.  **In Input Data :**

    - **Assumption:** The input file is a standard CSV (`urls.csv`), and the target URLs are located in the **second column** (index 1) and the header contains names of the columns.
    - **Decision:** The code uses `df.columns[1]` to dynamically select the URL column, making it slightly more flexible than hardcoding a column name.

8.  **Driver Availability:** Assumes that the correct version of ChromeDriver is installed and correctly configured.

# 6. Usage Example

## Scraper Logic Flow and Expected Outcomes

| Input URL Type                                                                                                                      | Code Block Engaged                                                                                                                | Expected Behavior                                                                                                                           | Output Status |
| :---------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------ | :------------ |
| **[https://www.webwire.com/ViewPressRel.asp?aId=340305]()**                                                                         | `handle_edge_cases()` (Tier 1)                                                                                                    | `requests` successfully retrieves full HTML quickly.                                                                                        | **SUCCESS**   |
| **[https://www.reutersagency.com/en/reutersbest/article/volkswagen-india-unit-faces-1-4-billion-tax-evasion-notice/]()**            | `handle_edge_cases()` (Tier 1)                                                                                                    | `requests` gets a 404 status code.                                                                                                          | **FAILURE**   |
| **[https://www.investing.com/analysis/paypal-beats-and-raises-outlook-but-stock-slips-as-investors-watch-key-support-200664504]()** | `handle_edge_cases()` (Tier 1) fails (content too short/stubby).Then page detects POPUP handeled by `handle_selenium_obstacles()` | Selenium runs $\rightarrow$ No paywall found $\rightarrow$ `handle_selenium_obstacles` runs $\rightarrow$ Content scraped after JS renders. | **SUCCESS**   |

## 7. Aggregator Site Handling

| Section            | Recommended Text                                                                                                                                                                                                                                                                                                                                                                                                            |     |
| :----------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :-- |
| **Objective**      | The scraper is designed to prioritize **original data sources** over secondary aggregators.The primary goal is to retrieve the content from the final, linked source.                                                                                                                                                                                                                                                       |
| **Implementation** | When a URL contains aggregator patterns, the scraper executes a **two-step navigation**: <br><br>1. Load the initial aggregator URL. <br>2. Use specific selectors (`.source-list__item a` etc.) to extract the **external source URL** (`target_url`). <br>3. The scraper then navigates directly to the `target_url`, using the aggregator page as the **HTTP Referer** to potentially bypass source access restrictions. |
| **Data Scope**     | The final content retrieved is strictly the page source from the **linked external source (`target_url`)**, after successful navigation and obstacle clearing. **Content from the initial aggregator page is discarded.**                                                                                                                                                                                                   |
| **Fallback**       | If a reliable external source link cannot be found on the aggregator page, the scraper logs a warning and proceeds to scrape the aggregator page itself, acknowledging that the resulting content will be a summary.                                                                                                                                                                                                        |

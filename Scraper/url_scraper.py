from bs4 import BeautifulSoup
import csv
import logging
import os
import pandas as pd 
import random
import requests
from requests.exceptions import RequestException
from selenium import webdriver 
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By 
from selenium.common.exceptions import TimeoutException , NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
import time 


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CSV_FILE_PATH = 'urls.csv'
CHROME_DRIVER_PATH = 'chromedriver.exe' 
TIMEOUT_SECONDS = 30 
SLEEP_SECONDS = 3
MAX_RETRIES = 3
USER_AGENTS = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/114.0.1823.58',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0']

    
TRUSTED_AGGREGATOR_DOMAINS = [
    "statista.com",
    "fivethirtyeight.com",
    "kff.org"
]

# Selectors to find the source link on the aggregator page
SOURCE_SELECTORS = [
    ".source-list__item a",
    ".source-box a", 
    "section#statisticHeader[data-url]",  
    "a[href*='org/']", 
    "a[href*='gov/']", 
    "a[title*='source']"
]

def find_and_get_source_url(driver, aggregator_url):
    """
    Attempts to find the external original source link on the current page 
    and returns the target URL.
    """

    LINK_ATTRIBUTES = ['href', 'data-url', 'data-link', 'source-url']
    logger.info(f"Attempting to find original source link on: {aggregator_url}")
    time.sleep(random.uniform(1.5, 3)) 

    for selector in SOURCE_SELECTORS:
        try:
            source_element = WebDriverWait(driver, 15).until( 
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            
            original_url = None
            

            for attr in LINK_ATTRIBUTES:
                attr_value = source_element.get_attribute(attr)
                if attr_value:
                    original_url = attr_value
                    break  # Found the URL, stop checking attributes
               
            
            if original_url:
                # Here Cleaning the URL 
                original_url = original_url.split('?')[0].split('#')[0]
                
                # Here Preventing Loop
                if original_url != driver.current_url:
                    # 3. Handle aggregator case (Ensure it's a different trusted domain)
                    if any(aggregator in aggregator_url.lower() for aggregator in  TRUSTED_AGGREGATOR_DOMAINS):
                        # If we find ANY non-identical URL, return it immediately for the second step.
                        logger.info(f"Aggregator source found using selector '{selector}': {original_url}")
                        return original_url
                    
                    # 4. Handle non-aggregator case (Ensure it's truly external)
                    else:
                        # Simple domain check to filter out non-aggregators linking to themselves
                        current_domain = driver.current_url.split('/')[2] if driver.current_url.startswith('http') else ""
                        
                        if current_domain not in original_url:
                             logger.info(f"External source found using selector '{selector}': {original_url}")
                             return original_url
            
        except TimeoutException:
            logger.debug(f"Selector '{selector}' timed out finding element.")
            continue 
        except NoSuchElementException:
            logger.debug(f"Selector '{selector}' not found.")
            continue
            
    logger.warning("Could not find a reliable external source link.")
    return None

def handle_edge_cases(url): #Access & Validation
    """
    Attempts to fetch a URL using requests (one attempt only).
    Flags 403 and paywalls for Selenium fallback.
    Returns: (html_content, error_message)
    """
    for attempt in range(MAX_RETRIES):
        try:
            random_agent = random.choice(USER_AGENTS)
            HEADERS = {'User-Agent': random_agent}
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)

            # 1. Handle Successful Response
            if response.status_code == 200:
                return response.text, None 
            
            # 2. Handle 404 (Permanent Failure)
            elif response.status_code == 404:
                logger.error(f"Page not found (404): {url}")
                return None, "404 Not Found"

            # 3. Handle 5xx Errors (Temporary Server Issues - RETRY)
            elif 500 <= response.status_code < 600:
                if attempt < MAX_RETRIES - 1:
                    wait_time = 2**(attempt + 1) # Wait 2s, 4s, 8s...
                    logger.warning(f"Server Error {response.status_code} for {url}. Retrying in {wait_time}s... (Attempt {attempt+1}/{MAX_RETRIES})")
                    time.sleep(wait_time) 
                    continue # Go to the next attempt
                else:
                    logger.error(f"Max retries failed for 5xx error: {url}")
                    return None, f"Max retries failed due to {response.status_code} error"
            
            # 4. Handle 403 (Flag for Selenium Fallback) 
            elif response.status_code == 403:
                # Return the content (which is usually a stub/error message)
                logger.warning(f"403 Forbidden detected. Flagging for Selenium fallback: {url}")
                return response.text, None 
            
            # 5. Handle Other Non-200 Failures (Exit immediately)
            else:
                logger.error(f"Failed to load page (status code {response.status_code}): {url}")
                return None, f"Failed to load, status code {response.status_code}" 

        except RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = 2**(attempt + 1)
                logger.warning(f"Request error for {url}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time + random.uniform(1, 2))
                continue
            logger.error(f"Request error after max retries: {e}")
            return None, str(e)
            
    return None, "Max retries reached due to unhandled request errors."

def handle_selenium_obstacles(driver, url):

    """
    Conditionally handles general pop-ups and press-and-hold challenges.
    """

    # this are common popup keywords not just specific to any site
    POPUP_KEYWORDS = ["cookie-banner", "modal-backdrop", 
                      "overlay-container", "subscription-modal",
                        "newsletter-popup", "ccpa"]   
        
    
     # common selectors ()for pop-up close buttons
    POPUP_CLOSE_SELECTORS = [
    (By.CSS_SELECTOR, 'button[aria-label="Close"]'),
    (By.CLASS_NAME, 'modal-close'),
    (By.XPATH, '//button[contains(text(), "No Thanks")]'),
    (By.XPATH, '//button[contains(text(), "Skip")]'),
        ]                                                 

    HOLD_BUTTON_LOCATOR = (By.ID, 'confirm-human-button') 
    HOLD_TIME_SECONDS = 3

    # 1. Get page source for pop-up check
    try:
        page_source = driver.page_source
    except Exception as e:
        logger.error(f"Failed to get page source for obstacle check: {e}")
        return 

    # --- A. CONDITIONAL POP-UP CLOSING ---
    is_popup_likely = any(keyword in page_source.lower() for keyword in POPUP_KEYWORDS)
    
    if is_popup_likely:
        logger.info(f"Pop-up keywords detected for {url}. Attempting to close.")
        
        for selector_type, selector_value in POPUP_CLOSE_SELECTORS:
            try:
                close_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                close_button.click()
                logger.info(f"Successfully closed pop-up using selector: {selector_value}")
                break
            except Exception:
                continue 

      #- B. CONDITIONAL LONG-PRESS ACTION ---
    try:
        # Check specifically for the long-press button
        hold_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(HOLD_BUTTON_LOCATOR)
        )
        
        logger.info(f"Press-and-hold button detected. Executing ActionChains for {HOLD_TIME_SECONDS}s.")
        
        actions = ActionChains(driver)
        actions.click_and_hold(hold_button).perform()
        time.sleep(HOLD_TIME_SECONDS)
        actions.release(hold_button).perform()
        
        logger.info("Successfully executed press-and-hold action.")

    except TimeoutException:
        logger.debug("Press-and-hold challenge not detected/skipped.")
        pass
    except Exception as e:
        logger.warning(f"Failed during long press action: {e}")
        pass

def clean_html(html_content):  # Preparation of text for final use
    """
    Parses HTML content and removes common irrelevant elements (ads, navigation, etc.).
    Returns: cleaned text content.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, 'html.parser')

   
    irrelevant_selectors = [
        'aside', 'footer', 'header', 'nav', 'iframe',
        '.ad-banner', '.advertisement', '#sidebar',
        '[class*="ad-"]', '[id*="ad-"]',
        '[class*="paywall-"]', '[id*="paywall-"]'
    ]

    for selector in irrelevant_selectors:
        for element in soup.select(selector):
            element.decompose()

    # Return the clean, concatenated text
    return soup.get_text(separator=' ', strip=True)
    

def scrape_page(url, driver): # makes decisions and calls other functions
    """
    Scrapes a single URL, using requests first and falling back to Selenium if needed.
    Returns: (scraped_text_or_none, error_message_or_none)
    """

    paywall_indicators = ["paywall", "subscribe to read"]
    
    # 1. Try fetching with requests (Tier 1 and Error Handling)
    html_content, error = handle_edge_cases(url)
    
    if error:
        return None, error 

    PLACEHOLDER_INDICATORS = [
        "please enable javascript", "load full story", "continue reading", 
        "login to read this story", "javascript is required","paywall","subscribe to read",
        "403 forbidden", "access denied", "client blocked", "sorry, you have been blocked" 
    ]
    is_stub = any(indicator in html_content.lower() for indicator in PLACEHOLDER_INDICATORS)
    
    # --- Check for Selenium Fallback or aggregator Requirement (Tier 2 : Selenium Fallback ) ---
    if is_stub or len(clean_html(html_content)) < 100 or any(aggregator in url.lower() for aggregator in  TRUSTED_AGGREGATOR_DOMAINS):
        logger.info(f"Initial HTML appears blocked OR URL is aggregator. Falling back to Selenium for {url}.")
        
        try:
            # Tier 3: Referer Spoofing
            driver.execute_script("Object.defineProperty(document, 'referrer', {get : function(){ return 'https://www.google.com/'; }});")
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            time.sleep(random.uniform(4, 5)) # Random wait
            
            # --- START: AGGREGATOR SPECIAL HANDLING (Tier 5) ---
            if any(aggregator in url.lower() for aggregator in  TRUSTED_AGGREGATOR_DOMAINS) :
                logger.info(f"URL is an aggregator: {url}. Attempting two-step navigation to source.")
                
                # Get the external target URL while staying on the aggregator page
                target_url = find_and_get_source_url(driver, url)

                if target_url:
                    # Navigate to the external source
                    driver.get(target_url) 
                    logger.info("Successfully performed two-step navigation to final source.")
                    
                    # Wait for the FINAL page to load
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
                    time.sleep(random.uniform(1, 2))
                else:
                    logger.warning(f"Could not find external source. Scraping aggregator directly: {url}")
            
            # Tier 4: Obstacle Clearing
            handle_selenium_obstacles(driver, driver.current_url)
            
            html_content = driver.page_source
            cleaned_text = clean_html(html_content)

            # Check after Tier 5 (Selenium/Referer/Obstacle Clearing)
            if any(indicator in cleaned_text.lower() for indicator in paywall_indicators):
                logger.warning("Paywall text detected in CLEANED content after all Selenium tiers.")
                
           
            if len(cleaned_text) < 100:
                return None, "Scraped page contained insufficient content after Selenium."
            
            return cleaned_text, None 
            
        except Exception as e:
            logger.error(f"Selenium error for {url} (current URL: {driver.current_url}): {e}")
            return None, f"Selenium error: {str(e)}"
        
   
    cleaned_text = clean_html(html_content)
    return cleaned_text, None

def run_scraper(csv_file_path=CSV_FILE_PATH, driver_path=CHROME_DRIVER_PATH, headless=True):
    """
    Main function to read URLs from a CSV, scrape them, and report results.
    """
    if not os.path.exists(driver_path):
        logger.error(f"ChromeDriver not found at path: {driver_path}. Please update CHROME_DRIVER_PATH.")
        return []

    # Initialize WebDriver
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless=new') 
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
    

    driver = webdriver.Chrome(service=Service(driver_path), options=chrome_options)
    driver.set_page_load_timeout(30)

    # Initialize counters and results
    success_count = 0
    failure_count = 0
    total_urls = 0
    results = []
    
    try:


            df = pd.read_csv(csv_file_path) 
            URL_COLUMN_HEADER = df.columns[1]  
            df_unique = df.drop_duplicates(subset=[URL_COLUMN_HEADER])
            urls_to_scrape = df_unique[URL_COLUMN_HEADER].tolist()
            
            
            for url in urls_to_scrape:
                if not url or not url.strip():
                    continue # Skip empty rows
                total_urls += 1
                
                # --- SCRAPING AND COUNTING LOGIC ---
                scraped_text, error_message = scrape_page(url, driver)

                if error_message: 
                    logger.info(f"FAILURE: {url} - {error_message}")
                    failure_count += 1
                    results.append({'url': url, 'status': 'FAILURE', 'error': error_message, 'content_preview': ''})
                    
                else:
                    logger.info(f"SUCCESS: {url} - Content length {len(scraped_text)}")
                    success_count += 1
                    # Append result for later use (e.g., saving to DB/CSV)
                    results.append({'url': url, 'status': 'SUCCESS', 'error': None, 'content_preview': scraped_text[:1000]})
                
    except Exception as e:
        logger.critical(f"A critical error occurred: {e}", exc_info=True)

    finally:
        driver.quit() # Always close the driver
        
       
        print("\n" + "="*50)
        print("SCRAPING SUMMARY")
        print(f"Total URLs processed: {total_urls}")
        if total_urls > 0:
            success_rate = (success_count / total_urls) * 100
            failure_rate = (failure_count / total_urls) * 100
            print("-" * 50)
            print(f"SUCCESS COUNT:      {success_count}")
            print(f"FAILURE COUNT:      {failure_count}")
            print(f"SUCCESS RATE:      {success_rate:.2f}%")
            print(f"FAILURE RATE:      {failure_rate:.2f}%")
        else:
            print("No URLs were processed.")

        print("="*50)

        return results
      

if __name__ == '__main__':
    final_results = run_scraper()
    if final_results:
        try:
            df = pd.DataFrame(final_results)
            output_filename = 'scraped_data_output.csv' # NOTE: you can update this path if needed
            df.to_csv(output_filename, index=False, encoding='utf-8', quoting=csv.QUOTE_ALL, quotechar='"')
            
        except NameError:
            print("\nERROR: Pandas is not imported. Please add 'import pandas as pd' at the top.")
        except Exception as e:
            print(f"\nCRITICAL ERROR during data saving: {e}")
    else:
        print("\nSCRAPING FINISHED: No records were collected to save.")  
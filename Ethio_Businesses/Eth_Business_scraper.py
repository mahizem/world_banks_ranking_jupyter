from bs4 import BeautifulSoup
import logging
import pandas as pd
from selenium import webdriver
import random
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
from sqlalchemy import create_engine
from itertools import zip_longest
from urllib.parse import quote_plus 

# Configuration and Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

url = 'https://www.ethyp.com/'

# Selectors
# Initial Selector (before 'See all' click)
INITIAL_CATEGORY_SELECTOR = (By.CSS_SELECTOR, "a.lazy-img.lazy-bg.entered.lazy-done") 
# Expanded Selector (after 'See all' click, based on user feedback)
EXPANDED_CATEGORY_SELECTOR = (By.CSS_SELECTOR, "ul.icats > li > a") 
# Guess for the 'See all' button/link
SEE_ALL_LOCATOR = (By.XPATH, "//a[contains(translate(text(), 'SEE ALL', 'see all'), 'see all') or contains(translate(text(), 'VIEW ALL', 'view all'), 'view all')]")

DB_CONFIG = {
    'host': 'localhost',
    'database': 'postgres',
    'user': 'postgres',
    'password': 'ilovemum21%406', # *** IMPORTANT: Replace 'your_secure_password' with your actual password ***
    'port': '5432'
}
TABLE_NAME = 'business_listings' 

# Inner Loop: Scrape all pages for a single category found
def scrape_category_pages(driver, category_name): 
    """
    Scrapes all paginated listings for the CURRENTLY LOADED category page.
    """
    scraped_data = [] 
    current_page = 1
    
    # Wait for the first business listing on the new category page
    try:
        # Wait for the listing page to load its primary element
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.company_header')))
        time.sleep(random.uniform(2, 4))
        logger.info(f"Successfully landed on listings page for: {category_name}")
    except Exception as e:
        logger.critical(f"Failed to confirm listing page load for {category_name}: {e}")
        return scraped_data

    # --- PAGINATION LOOP: Scrape and move to next page ---
    while True:
        logger.info(f"--- Starting scrape for {category_name} - Page {current_page} ---")
        
        try:
            # 2a. Find listing elements for the staleness check later
            listing_elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.company_header'))
            )

            # 2b. SCAPE THE DATA using BeautifulSoup on the current page source
            html_content = driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')

            # Selectors targeting data points
            business_name_els = soup.select('.company_header h3')
            address_els = soup.select('.address')
            # Selector for phone number: <span> immediately following the phone icon
            contact_info_els = soup.select('.fa-phone + span')
            ratings_els = soup.select('.company_reviews.rate')

            all_listings = zip_longest(business_name_els, address_els, contact_info_els, ratings_els, fillvalue=None)
            num_listings_scraped = 0

            for name_el, address_el, contact_el, rating_el in all_listings:
                business_name = name_el.get_text(strip=True) if name_el else None
                address = address_el.get_text(strip=True) if address_el else None
                contact_info = contact_el.get_text(strip=True) if contact_el else None
                ratings = rating_el.get_text(strip=True) if rating_el else None

                if business_name and address and contact_info:
                    scraped_data.append({
                        'category': category_name, 
                        'bussiness_name': business_name, 
                        'address': address,
                        'contact_info': contact_info,
                        'ratings': ratings
                    })
                    num_listings_scraped += 1
            
            logger.info(f"Scraped {num_listings_scraped} records from Page {current_page}.")
            
            # 2c. ADVANCE TO NEXT PAGE
            next_page_num = current_page + 1
            NEXT_PAGE_LOCATOR = (By.XPATH, f"//a[text()='{next_page_num}']")
            
            try:
                next_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(NEXT_PAGE_LOCATOR)
                )
                
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                time.sleep(random.uniform(0.5, 1.5))
                next_button.click()
                
                current_page = next_page_num
                logger.info(f"Clicked page {current_page}. Waiting for new data to load...")
                
                # Wait for the old listing to become stale, confirming the page reloaded
                if listing_elements:
                     WebDriverWait(driver, 10).until(EC.staleness_of(listing_elements[0]))
                
            except TimeoutException:
                logger.info("Next page link not found. Pagination finished for this category.")
                break # Exit the inner while loop
            
        except Exception as e:
            logger.critical(f"A critical error occurred in the pagination loop (Page {current_page}): {e}")
            break 
            
    return scraped_data
    
# Function to store data
def append_and_store_data(scraped_data):
    if not scraped_data:
        logger.warning("Scraped data list is empty. Skipping database save.")
        return
    logger.info("Organizing data with Pandas...")

    df = pd.DataFrame(scraped_data)
    try:
        # Construct DB_URL securely using quote_plus for the password
        password_encoded = quote_plus(DB_CONFIG['password'])
        safe_db_url = (
            f"postgresql+psycopg2://{DB_CONFIG['user']}:{password_encoded}@"
            f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
        )

        engine = create_engine(safe_db_url)
        logger.info(f"Connecting to database and loading {len(df)} records into table '{TABLE_NAME}'...")
        
        df.to_sql(
            TABLE_NAME, 
            engine, 
            if_exists='append', 
            index=False, 
            chunksize=500
        )
        logger.info(f"Successfully saved {len(df)} records to PostgreSQL.")
    except Exception as e:
        logger.critical(f"Failed to save data to PostgreSQL. Check your DB_CONFIG and table structure: {e}")


# Main execution logic
if __name__ == '__main__':
    
    # 1. Setup Driver
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/114.0.1823.58',
        'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0'
    ]
    random_agent = random.choice(USER_AGENTS)
    service = Service(ChromeDriverManager().install())
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument(f'user-agent={random_agent}')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    all_scraped_results = []
    
    try:
        # --- PHASE 1: Determine the correct Category Selector and List Size ---
        
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        
        # Start by assuming the initial selector
        active_category_selector = INITIAL_CATEGORY_SELECTOR
        
        logger.info("PHASE 1: Checking for 'See all' button to expand categories.")
        
        try:
            # 1. Find and click the 'See all' button
            see_all_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(SEE_ALL_LOCATOR)
            )
            
            driver.execute_script("arguments[0].scrollIntoView(true);", see_all_button)
            time.sleep(random.uniform(0.5, 1.5))
            driver.execute_script("arguments[0].click();", see_all_button)
            
            logger.info("Successfully clicked 'See all'. Structure is now expected to change.")
            time.sleep(random.uniform(3, 5)) # Give it time for the new structure to load

            # 2. Update the active selector to the one confirmed to work for the expanded view
            active_category_selector = EXPANDED_CATEGORY_SELECTOR
            
        except TimeoutException:
            logger.warning("'See all' button not found. Scraping initial list using original selector.")
        except Exception as e:
             logger.critical(f"Error during 'See all' click. Falling back to original selector: {e}")
        
        
        # --- PHASE 2: Loop over the final, expanded (or initial) list ---
        
        # 1. Get the final count of categories to loop through
        # We must reload here if the click navigated away, but assuming it was an inline expansion:
        final_categories = driver.find_elements(*active_category_selector)
        total_category_links_count = len(final_categories)

        if total_category_links_count == 0:
            logger.error("No category links found with the final selector. Exiting.")
            driver.quit()
            exit()

        logger.info(f"PHASE 2: Starting to scrape all {total_category_links_count} categories using selector: {active_category_selector[1]}")

        for i in range(total_category_links_count):
            
            # CRITICAL RE-LOAD: We must reload the homepage for every category because 
            # scrape_category_pages navigates away to the listings page.
            driver.get(url) 
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

            # If we successfully clicked 'See all', we must click it again on reload 
            # to re-expand the list to access the later elements in the loop.
            if active_category_selector == EXPANDED_CATEGORY_SELECTOR:
                try:
                    see_all_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable(SEE_ALL_LOCATOR)
                    )
                    driver.execute_script("arguments[0].click();", see_all_button)
                    time.sleep(random.uniform(1, 2))
                except Exception as e:
                    logger.warning(f"Failed to re-expand list at index {i}. May miss later categories: {e}")


            # 2. Re-find the entire list using the determined active selector
            try:
                re_found_categories = WebDriverWait(driver, 15).until(
                    EC.presence_of_all_elements_located(active_category_selector)
                )
            except Exception as e:
                logger.error(f"Failed to re-find category links on reload at index {i}: {e}. Stopping.")
                break

            if i >= len(re_found_categories):
                logger.error(f"Category index {i} out of range after re-finding. Stopping.")
                break
            
            current_category_link_element = re_found_categories[i]
            
            # --- CATEGORY NAME EXTRACTION (using JavaScript for robust innerText) ---
            category_title = current_category_link_element.get_attribute('title')
            
            if not category_title:
                 title_from_js = driver.execute_script(
                    "return arguments[0].innerText;", current_category_link_element
                 )
                 category_title = title_from_js.strip() if title_from_js else f"Category Index {i}"
            
            logger.info(f"\n--- Starting to process Category {i+1}/{total_category_links_count}: {category_title} ---")
            
            try:
                # 3. Click and Scrape
                driver.execute_script("arguments[0].click();", current_category_link_element)
                
                results = scrape_category_pages(driver, category_title)
                all_scraped_results.extend(results)
                
            except StaleElementReferenceException:
                logger.error(f"StaleElementReferenceException during click for {category_title}. Skipping this category.")
            except Exception as e:
                logger.critical(f"Error processing category {category_title}: {e}")
            
        # --- END OUTER LOOP ---
        
        logger.info(f"Finished scraping all categories. Total records collected: {len(all_scraped_results)}")
        
        if all_scraped_results:
            append_and_store_data(all_scraped_results)
        
    except Exception as e:
        logger.critical(f"A critical error occurred in the main process: {e}")

    finally:
        driver.quit() 
        logger.info("Web driver closed.")
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
url = 'https://www.ethyp.com/'
TIMEOUT_SECONDS = random.uniform(5, 10)
# Selector for the main category links on the homepage
CATEGORY_SELECTOR = (By.CSS_SELECTOR, " a.lazy-img.lazy-bg.entered.lazy-done") 
SEE_ALL_LOCATOR = (By.XPATH, "//li/a.text('See All')")
# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'postgres',
    'user': 'postgres',
    'password': 'ilovemum21%406',
    'port': '5432'
}
TABLE_NAME = 'business_listings' 

DB_URL = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
    f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)
# --- END CONFIGURATION ---

# --- HELPER FUNCTIONS ---

def get_category_elements(driver, url, SELECTOR):
    """
    Navigates to the homepage, clicks 'See All' if available, 
    and returns the full list of category links.
    """
    driver.get(url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    logger.info("Loaded homepage to retrieve categories.")
    
    try:
        # 1. Attempt to find and click the 'See All' button
        try:
            see_all_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(SEE_ALL_LOCATOR)
            )
            logger.info("Clicking 'See All' button to reveal all categories.")
            see_all_button.click()
            # Wait briefly for the new elements to render
            time.sleep(random.uniform(1, 2)) 
        except TimeoutException:
            # If 'See All' isn't found (maybe all are visible already), log and proceed.
            logger.info("'See All' button not found or not needed. Proceeding.")

        # 2. Retrieve the *now fully expanded* list of category elements
        category_elements = WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located(SELECTOR)
        )
        logger.info(f"Retrieved {len(category_elements)} total categories.")
        return category_elements
        
    except TimeoutException:
        logger.error("Timed out waiting for category elements after loading.")
        return []

def scrape_and_paginate(driver,category_name): 
    """Scrapes data from the current listings page and handles pagination."""
    scraped_data = []     
    current_page = 1
    
    # Selector for a listing element (used for the staleness check)
    LISTING_ELEMENT_LOCATOR = (By.CSS_SELECTOR, '.company_header')

    while True:
        logger.info(f"--- Starting scrape for Page {current_page} ---")
        
        try:
            # 1. Get the list of ALL listings on the current page for staleness check
            # Use a short timeout since the page should already be loaded after the click.
            listing_elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located(LISTING_ELEMENT_LOCATOR)
            )

            # 2. SCAPE THE DATA from the current page HTML
            html_content = driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')

            # Selectors targeting data points (uses h3 inside .company_header as requested)
            business_name_els = soup.select('.company_header h3')
            address_els = soup.select('.address')
            contact_info_els = soup.select('.cont .s')
            ratings_els = soup.select('.tagline')

            all_listings = zip_longest(business_name_els, address_els, contact_info_els, ratings_els, fillvalue=None)
            num_listings_scraped = 0
            num_listings_skipped = 0
            
            for name_el, address_el, contact_el, rating_el in all_listings:
                
                business_name = name_el.get_text(strip=True) if name_el else None
                address = address_el.get_text(strip=True) if address_el else None
                contact_info = contact_el.get_text(strip=True) if contact_el else None
                ratings = rating_el.get_text(strip=True) if rating_el else None

                # Filter: Only store if ALL fields are present (not None/empty string)
                if business_name:
                    scraped_data.append({
                        'bussiness_name': business_name, 
                        'address': address,
                        'contact_info': contact_info,
                        'ratings': ratings,
                        'category_name': category_name
                    })
                    num_listings_scraped += 1
                else:
                    num_listings_skipped += 1
                    logger.debug(f"Skipped record: Name={business_name}, Address={address}, Contact={contact_info}")
                
            logger.info(f"Scraped {num_listings_scraped} valid records from Page {current_page}. Skipped: {num_listings_skipped}")
            
            
            # 3. ADVANCE TO NEXT PAGE
            next_page_num = current_page + 1
            NEXT_PAGE_LOCATOR = (By.XPATH, f"//a[text()='{next_page_num}']")
            
            try:
                # Wait for the next page link to be clickable
                next_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(NEXT_PAGE_LOCATOR)
                )
                
                # Scroll to and click the button
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                time.sleep(random.uniform(0.5, 1.5))
                next_button.click()
                
                current_page = next_page_num
                logger.info(f"Clicked page {current_page}. Waiting for new data to load...")
                
                # Check for staleness to confirm the page reloaded
                if listing_elements:
                     WebDriverWait(driver, 10).until(
                         EC.staleness_of(listing_elements[0])
                     )
                
            except TimeoutException:
                logger.info("Next page link not found. Pagination finished for this category.")
                break # Exit the while loop
            
        except Exception as e:
            logger.critical(f"A critical error occurred in the pagination loop (Page {current_page}): {e}")
            break # Exit on critical error
            
    return scraped_data 

def append_and_store_data(scraped_data):
    """Stores the collected data into the PostgreSQL database."""
    if not scraped_data:
        logger.warning("Scraped data list is empty. Skipping database save.")
        return
    logger.info("Organizing data with Pandas...")

    df = pd.DataFrame(scraped_data)
    
    # Ensure all column names match what the DB expects
    # Example: df.rename(columns={'bussiness_name': 'business_name'}, inplace=True)

    try:
        engine = create_engine(DB_URL)
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

# --- MAIN EXECUTION ---

if __name__ == '__main__':

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/114.0.1823.58',
    ]
    random_agent = random.choice(USER_AGENTS)
    service = Service(ChromeDriverManager().install())
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument(f'user-agent={random_agent}')
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        total_results = []
        
        # 1. Get ALL category elements
        initial_categories = get_category_elements(driver, url, CATEGORY_SELECTOR)
        category_elements_count = len(initial_categories)
        if category_elements_count == 0:
            logger.critical("No categories found on the homepage. Shutting down.")
        
        # 2. Loop through the categories by INDEX
        for i in range(category_elements_count):
            
            try:
                # A. Return to the homepage and re-find all elements (CRITICAL for avoiding StaleElementReferenceException)
                fresh_categories = get_category_elements(driver, url, CATEGORY_SELECTOR)
                
                # Check if the number of elements changed or index is valid
                if i >= len(fresh_categories):
                    logger.warning(f"Category index {i+1} is out of range. Stopping category loop.")
                    break
                
                # B. Prepare for the click
                category_link = fresh_categories[i]
                
                try:
                    category_link_text = category_link.get_attribute("title") or category_link.text or f"Category #{i+1}"
                except:
                    category_link_text = f"Category #{i+1}"

                logger.info(f"\n==================== STARTING {category_link_text} ({i+1}/{category_elements_count}) ====================")

                # C. Click the category link (this navigates away from the home page)
                category_link.click()
                
                # D. Wait for the list page to load (use a known element on the listings page)
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.company_header')))
                time.sleep(random.uniform(2, 4))
                
                # E. Run the scraping and pagination loop
                category_results = scrape_and_paginate(driver, category_link_text) # <-- Pass the text
                total_results.extend(category_results)
                
                logger.info(f"Finished {category_link_text}. Scraped {len(category_results)} total listings.")
                
            except Exception as e:
                logger.error(f"Error processing Category #{i+1} ({category_link_text}): {e}. Skipping to next category.")
            
            # F. CRITICAL STEP: Always return to the homepage to reset for the next category click
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

        # 3. Store the total scraped data once all categories are done
        if total_results:
            append_and_store_data(total_results)
            
    except Exception as e:
        logger.critical(f"A critical error occurred in the main process: {e}")

    finally:
        driver.quit()
        logger.info("Driver successfully closed.")
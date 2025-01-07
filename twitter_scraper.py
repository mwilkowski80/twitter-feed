from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager
import time
import argparse
from datetime import datetime, timedelta
import re
from sqlalchemy import create_engine, Column, String, DateTime, Integer, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

# Database setup
Base = declarative_base()
engine = create_engine('sqlite:///tweets.db')
Session = sessionmaker(bind=engine)

class Tweet(Base):
    __tablename__ = 'tweets'
    
    id = Column(Integer, primary_key=True)
    tweet_id = Column(String, unique=True)
    handle = Column(String)
    text = Column(String)
    tweet_original_timestamp = Column(String)
    timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Add unique constraint for handle + text combination
    __table_args__ = (
        UniqueConstraint('handle', 'text', name='uix_handle_text'),
    )

# Only create tables if they don't exist
Base.metadata.create_all(engine)

class TwitterScraper:
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = self._setup_driver()
        self.session = Session()

    def _setup_driver(self):
        chrome_options = Options()
        
        # Add stealth options
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Add headless mode if requested
        if self.headless:
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
        
        # Initialize Chrome with options only
        driver = webdriver.Chrome(options=chrome_options)
        
        stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        
        return driver

    def _parse_timestamp(self, timestamp_str):
        """Parse Twitter's relative timestamp into a datetime object."""
        now = datetime.now()
        
        try:
            # Handle "Xh" format (e.g., "2h")
            if 'h' in timestamp_str:
                hours = int(timestamp_str.replace('h', ''))
                return now - timedelta(hours=hours)
            
            # Handle "Xm" format (e.g., "45m")
            elif 'm' in timestamp_str:
                minutes = int(timestamp_str.replace('m', ''))
                return now - timedelta(minutes=minutes)
            
            # Handle "Xs" format (e.g., "30s")
            elif 's' in timestamp_str:
                seconds = int(timestamp_str.replace('s', ''))
                return now - timedelta(seconds=seconds)
            
            # Handle dates with year (e.g., "Feb 2, 2020" or "January 27, 2018")
            elif ',' in timestamp_str and re.search(r'\d{4}', timestamp_str):
                try:
                    # Try standard format first
                    return datetime.strptime(timestamp_str, '%b %d, %Y')
                except ValueError:
                    # Try full month name format
                    return datetime.strptime(timestamp_str, '%B %d, %Y')
            
            # Handle "Month Day" format (e.g., "Mar 21")
            elif re.match(r'[A-Za-z]{3,9} \d{1,2}', timestamp_str):
                try:
                    # Try abbreviated month format
                    date_str = f"{timestamp_str} {now.year}"
                    return datetime.strptime(date_str, '%b %d %Y')
                except ValueError:
                    # Try full month format
                    return datetime.strptime(date_str, '%B %d %Y')
            
            return None
            
        except Exception as e:
            print(f"Error parsing timestamp '{timestamp_str}': {e}")
            return None

    def scrape_handle(self, handle):
        try:
            # Navigate to user's profile
            self.driver.get(f'https://twitter.com/{handle}')
            wait = WebDriverWait(self.driver, 10)
            
            # Wait for tweets to load
            tweets = wait.until(EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, '[data-testid="tweet"]')))
            
            for tweet in tweets:
                try:
                    # Extract tweet information
                    tweet_id = tweet.get_attribute('data-tweet-id')
                    text = tweet.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]').text
                    original_timestamp = tweet.find_element(By.CSS_SELECTOR, 'time').text
                    
                    # Try to extract link from tweet card if present
                    try:
                        card = tweet.find_element(By.CSS_SELECTOR, '[data-testid="card.wrapper"] a')
                        card_link = card.get_attribute('href')
                        if card_link:
                            text = f"{text}\n{card_link}"
                    except:
                        pass  # No card link present
                    
                    # Parse the timestamp
                    parsed_timestamp = self._parse_timestamp(original_timestamp)
                    
                    # Create tweet object
                    tweet_obj = Tweet(
                        tweet_id=tweet_id,
                        handle=handle,
                        text=text,
                        tweet_original_timestamp=original_timestamp,
                        timestamp=parsed_timestamp
                    )
                    
                    # Save to database
                    self.session.add(tweet_obj)
                    try:
                        self.session.commit()
                        print(f"Saved tweet from {handle}: {text[:50]}...")
                        print(f"Timestamp: {original_timestamp} -> {parsed_timestamp}")
                    except IntegrityError as e:
                        self.session.rollback()
                        if "UNIQUE constraint failed" in str(e):
                            print(f"Note: Tweet from {handle} already exists in database, skipping...")
                        else:
                            print(f"Database error: {e}")
                        
                except Exception as e:
                    print(f"Error processing tweet: {e}")
                    continue
            
            time.sleep(2)  # Prevent rate limiting
            
        except Exception as e:
            print(f"Error scraping handle {handle}: {e}")

    def scrape_handles(self, handles):
        try:
            for handle in handles:
                print(f"\nScraping tweets for @{handle}")
                self.scrape_handle(handle.strip())
        finally:
            self.driver.quit()
            self.session.close()

def main():
    parser = argparse.ArgumentParser(description='Scrape tweets from specified Twitter handles')
    parser.add_argument('--handles', type=str, required=True,
                      help='Comma-separated list of Twitter handles to scrape')
    parser.add_argument('--headless', action='store_true',
                      help='Run Chrome in headless mode')
    
    args = parser.parse_args()
    handles = args.handles.split(',')
    
    scraper = TwitterScraper(headless=args.headless)
    scraper.scrape_handles(handles)

if __name__ == "__main__":
    main() 


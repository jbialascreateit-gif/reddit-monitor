import feedparser
import requests
import time
import os
import logging
import json
from logging.handlers import RotatingFileHandler
from typing import Set, List, Optional, Dict, Any
import google.genai as genai
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

# ==============================================================================
# SETUP & LOGGING
# ==============================================================================

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create handlers
# Rotating file handler
rfh = RotatingFileHandler("monitor.log", maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
rfh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

# Console handler
sh = logging.StreamHandler()
sh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

# Add handlers to the logger
logger.addHandler(rfh)
logger.addHandler(sh)

# Load environment variables from .env file
dotenv_path = find_dotenv()
if dotenv_path:
    logger.info(f"Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path, override=True, encoding='utf-8')
else:
    logger.warning(".env file not found. Relying on system environment variables.")

# ==============================================================================
# MAIN CONFIGURATION
# ==============================================================================

# Try to load from environment, fallback to hardcoded (Not recommended for production)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Diagnostic check for environment variables
if GEMINI_API_KEY:
    logger.info("Successfully loaded GEMINI_API_KEY from .env file.")
else:
    logger.warning("Could not find GEMINI_API_KEY in .env file. AI features will be disabled.")

if DISCORD_WEBHOOK_URL:
    logger.info("Successfully loaded DISCORD_WEBHOOK_URL from .env file.")
else:
    logger.warning("Could not find DISCORD_WEBHOOK_URL in .env file. Discord notifications will be disabled.")

# Configuration placeholders
SUBREDDITS: List[str] = []
KEYWORDS: List[str] = []
SLEEP_TIME: int = 3600
AI_DELAY: int = 30

HISTORY_FILE = "historia_postow.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


# ==============================================================================

# ==============================================================================
# AI & PROMPT CONFIGURATION
# ==============================================================================

# AI Client Configuration
AI_CLIENT = None
if GEMINI_API_KEY and "AIza" in GEMINI_API_KEY:
    try:
        # The new google.genai client is expected to automatically use the
        # GOOGLE_API_KEY environment variable.
        if 'GOOGLE_API_KEY' not in os.environ:
            os.environ['GOOGLE_API_KEY'] = GEMINI_API_KEY
        AI_CLIENT = genai.Client()
        logger.info("Gemini AI client initialized.")
    except Exception as e:
        logger.error(f"AI Configuration Error: {e}")
        AI_CLIENT = None

AI_PROMPT = """
You are a Casino Security Analyst. Your task is to evaluate if the following Reddit post describes a GENUINE technical issue, system error, or a specific scam.

Criteria for 'YES':
1. Reports a technical bug, site freeze, or error code (e.g., "error 500", "game crashed").
2. Describes a specific withdrawal/deposit failure (e.g., "money disappeared", "transaction stuck for 5 days").
3. Provides specific evidence of fraud or rigged games.

Criteria for 'NO':
1. General complaining about losing money or "bad luck".
2. Asking general questions about bonuses or strategies.
3. Low-quality "shitposting" or insults without technical details.

Post Content:
"{text}"

Answer ONLY with 'YES' or 'NO'.
"""

# ==============================================================================

seen_links: Set[str] = set()


def load_history() -> Set[str]:
    """Loads post history from the history file and performs self-cleaning."""
    if not os.path.exists(HISTORY_FILE):
        return set()
    
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        
        # SELF-CLEANING SYSTEM: If history exceeds 5000, keep the 1000 most recent.
        if len(lines) > 5000:
            logger.info(f"Clearing history... (Old entries: {len(lines)})")
            lines = lines[-1000:]
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            logger.info("History refreshed, retaining the 1000 most recent entries.")

        return set(lines)
    except Exception as e:
        logger.error(f"Failed to load or clean history file: {e}")
        return set()

def save_to_history(link: str) -> None:
    """Appends a new link to the history file."""
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(link + "\n")
    except IOError as e:
        logger.error(f"Error saving to history file: {e}")

def analyze_with_ai_lvl100(text: str) -> bool:
    """
    Analyzes text using the Gemini AI model with a backoff mechanism for rate limits.
    """
    if not AI_CLIENT:
        logger.warning("AI Client not initialized. Skipping analysis (Defaulting to True).")
        return True 

    prompt = AI_PROMPT.format(text=text)
    
    backoff_time = 60
    max_retries = 5
    retries = 0

    while retries < max_retries:
        try:
            response = AI_CLIENT.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt
            )
            
            # We clean the answer of any spaces and periods.
            answer = response.text.strip().upper()
            
            if "YES" in answer:
                logger.info("      AI Rating: IMPORTANT")
                return True
            else:
                logger.info("      AI Rating: TRASH (Ignore)")
                return False
                
        except Exception as e:
            error_msg = str(e)
            
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                retries += 1
                logger.warning(f"      API rate limit exceeded (429). Activating Backoff. Retry {retries}/{max_retries}.")
                logger.info(f"      Waiting {backoff_time} seconds...")
                time.sleep(backoff_time)
                backoff_time *= 2  # Exponential backoff
                if backoff_time > 900: backoff_time = 900
                logger.info("      Retrying...")
                continue
            else:
                logger.error(f"      AI Error: {e}. Defaulting to True as a precaution.")
                return True
    
    logger.error("      AI analysis failed after multiple retries. Defaulting to True.")
    return True

def send_discord_alert(title: str, link: str, keyword: str, subreddit: str) -> None:
    # Checks if the URL is empty, starts with http
    if not DISCORD_WEBHOOK_URL or not DISCORD_WEBHOOK_URL.startswith("http"):
        logger.warning("Discord Webhook URL is invalid or missing. Cannot send alert.")
        return

    data = {
        "content": f"**POTENTIAL ISSUE DETECTED: {keyword.upper()}**",
        "embeds": [{
            "title": title,
            "url": link,
            "description": f"Source: r/{subreddit}\nKeyword: **{keyword}**\nVerified by Gemini AI",
            "color": 16711680, # Red
            "footer": {
                "text": f"Casino Monitor v13 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes
        logger.info(f"   └── Notification sent for: {title[:30]}...")
    except requests.exceptions.RequestException as e:
        logger.error(f"   └── Discord notification error: {e}")

def check_feed():
    current_time = datetime.now().strftime('%H:%M:%S')
    print(f"\nSCANNING ({current_time}) + SYSTEM ANTI-429")
    print("-" * 50)
    
    # 1. FIRST, WE JUST COLLECT IT INTO A BAG (QUEUEING)
    candidate_queue = []

    for sub in SUBREDDITS:
        print(f"r/{sub:<15} ... ", end='')
        target_url = f"https://www.reddit.com/r/{sub}/new/.rss"
        
        try:
            response = requests.get(target_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
                
            feed = feedparser.parse(response.content)
            if not feed.entries:
                print("Empty")
                continue
            
            print(f"OK ({len(feed.entries)})")
            
            for entry in feed.entries:
                if entry.link in seen_links:
                    continue
                
                seen_links.add(entry.link)
                save_to_history(entry.link)
                
                full_text = (entry.title + " " + entry.get("summary", "")).lower()
                
                keyword_found = None
                for word in KEYWORDS:
                    if word.lower() in full_text:
                        keyword_found = word
                        break
                
                # If a word is found, we add it to the queue.
                if keyword_found:
                    candidate_queue.append({
                        "entry": entry,
                        "keyword": keyword_found,
                        "sub": sub
                    })

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error for r/{sub}: {e}")
        except Exception as e:
            logger.error(f"Feed Error for r/{sub}: {e}")
            
        time.sleep(2) # Increased sleep to be safer with Reddit's rate limits

    # 2. WE ARE NOW PROCESSING THE QUEUE WITH A CONFIGURED DELAY
    if not candidate_queue:
        print("-" * 50)
        print("No new posts matching keywords found.")
    else:
        print("-" * 50)
        print(f"Analysis Queue: {len(candidate_queue)} post(s) to check.")
        print(f"Safe mode: Analyzing 1 post every {AI_DELAY} seconds to avoid API rate limits.")
        
        for i, item in enumerate(candidate_queue, 1):
            entry = item["entry"]
            keyword = item["keyword"]
            sub = item["sub"]
            
            print(f"\n   [{i}/{len(candidate_queue)}] Analyzing: '{entry.title[:40]}...' (Keyword: {keyword})")
            
            # We call the AI Level 100 function
            full_post_text = entry.title + "\n" + entry.get("summary", "")
            is_valid = analyze_with_ai_lvl100(full_post_text)
            
            if is_valid:
                send_discord_alert(entry.title, entry.link, keyword, sub)
            
            # --- Configurable Delay ---
            # Only if it is not the last post in the queue
            if i < len(candidate_queue): 
                print(f"      Cooling down for {AI_DELAY}s before next analysis...")
                time.sleep(AI_DELAY)

    print("-" * 50)
    print("Scan cycle complete.")

def load_config():
    """Loads configuration from config.json."""
    global SUBREDDITS, KEYWORDS, SLEEP_TIME, AI_DELAY
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            # Ensure loaded keywords are lowercase for case-insensitive matching
            SUBREDDITS = config.get("subreddits", [])
            KEYWORDS = [k.lower() for k in config.get("keywords", [])]
            SLEEP_TIME = config.get("sleep_time", 3600)
            AI_DELAY = config.get("ai_delay", 60) # Default to 60s from config
            logger.info("Configuration loaded successfully from config.json")
    except FileNotFoundError:
        logger.error("FATAL: config.json not found! Please create it based on the example.")
        exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"FATAL: Invalid JSON in config.json! Details: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"FATAL: An unexpected error occurred while loading config: {e}")
        exit(1)

def main():
    """Main function to run the monitor."""
    print("================================================")
    print("   CASINO MONITOR v13.1 (STABLE)            ")
    
    load_config()

    print(f"   Scan interval: {SLEEP_TIME / 60:.0f} minutes")
    print(f"   AI analysis delay: {AI_DELAY} seconds")
    print("================================================")

    if not GEMINI_API_KEY or not AI_CLIENT:
        logger.warning("WARNING: Gemini API key is missing, invalid, or model failed to initialize. AI analysis will be skipped.")

    print("\nStarting initial scan in 3 seconds...")
    time.sleep(3)

    while True:
        global seen_links
        seen_links = load_history() # Refresh seen links from file at the start of each cycle
        logger.info(f"Loaded {len(seen_links)} links from history.")
        
        try:
            check_feed()
            print(f"\nNext scan in {SLEEP_TIME / 60:.0f} minutes...")
            time.sleep(SLEEP_TIME)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.critical(f"A critical error occurred in the main loop: {e}", exc_info=True)
            logger.info("Restarting scan cycle in 60 seconds to recover.")
            time.sleep(60)

if __name__ == "__main__":
    main()
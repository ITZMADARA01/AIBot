#!/usr/bin/env python3
import os
import sys
import logging
import asyncio
import time
import signal
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Configure logging with file output for 24/7 operation
log_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_directory, exist_ok=True)

log_file = os.path.join(log_directory, f'slayer_bot_{datetime.now().strftime("%Y%m%d")}.log')

# Set up rotating file handler to avoid large log files
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()  # Output to console as well
    ]
)
logger = logging.getLogger(__name__)

# Global variables for tracking bot state
restart_count = 0
last_crash_time = None
consecutive_rapid_crashes = 0
MAX_CONSECUTIVE_CRASHES = 5  # Maximum number of consecutive rapid crashes before cooldown
RAPID_CRASH_WINDOW = 60  # Time in seconds that defines a "rapid" crash
RESTART_COOLDOWN = 300  # Cooldown period in seconds after too many rapid crashes

# Load environment variables
load_dotenv()

# Make sure the required environment variables are set
required_vars = [
    "TELEGRAM_BOT_TOKEN", 
    "API_ID", 
    "API_HASH", 
    "DATABASE_URL"
]

# Check for optional but recommended variables
recommended_vars = [
    "OPENAI_API_KEY"
]

# Signal handler for clean shutdown
def signal_handler(sig, frame):
    logger.info("Received termination signal. Shutting down gracefully...")
    # Set a flag to indicate shutdown
    global shutdown_requested
    shutdown_requested = True

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Global shutdown flag
shutdown_requested = False

missing_recommended = [var for var in recommended_vars if not os.environ.get(var)]
if missing_recommended:
    logger.warning(f"Missing recommended environment variables: {', '.join(missing_recommended)}")
    logger.warning("AI features may be limited or unavailable without these variables.")
    
    # Specifically handle OpenAI API key missing
    if "OPENAI_API_KEY" in missing_recommended:
        logger.warning("OPENAI_API_KEY not found. AI conversation features will be disabled.")
        os.environ["AI_ENABLED"] = "false"

missing_vars = [var for var in required_vars if not os.environ.get(var)]
if missing_vars:
    logger.error(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
    logger.error("Please set these variables in your .env file or environment.")
    sys.exit(1)

# Required for importing app and bot modules
sys.path.append('.')

# Try to integrate with Slack for notifications if available
try:
    from slack_integration import post_notification
    slack_available = True
except Exception:
    slack_available = False
    logger.warning("Slack integration not available, notifications will not be sent")

def notify(title, message, level="info"):
    """Send notification through available channels"""
    try:
        if slack_available:
            post_notification(title, message, level)
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

def setup_db():
    """Set up the database before starting the bot"""
    # Skip MongoDB connection completely
    os.environ['SKIP_MONGODB'] = '1'
    logger.info("Setting SKIP_MONGODB=1 to bypass MongoDB connection entirely")
    
    try:
        from app import app, db
        
        with app.app_context():
            import models
            db.create_all()
            logger.info("Database initialized successfully (PostgreSQL)")
            return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        logger.error(traceback.format_exc())
        notify("Database Error", f"Failed to initialize database: {str(e)}", "error")
        return False

async def run_bot_with_retries():
    """Run the bot with automatic restarts on failures"""
    global restart_count, last_crash_time, consecutive_rapid_crashes
    
    # Initialize last_crash_time if it's None
    if last_crash_time is None:
        last_crash_time = time.time() - RAPID_CRASH_WINDOW - 1  # Ensure first failure is not considered rapid
    
    max_retries = 10  # Maximum number of retries before giving up
    retry_count = 0
    
    while not shutdown_requested and retry_count < max_retries:
        try:
            # Check if we need a cooldown due to too many rapid crashes
            if consecutive_rapid_crashes >= MAX_CONSECUTIVE_CRASHES:
                cooldown_time = RESTART_COOLDOWN
                logger.warning(f"Too many consecutive rapid crashes. Entering cooldown for {cooldown_time} seconds")
                notify("Bot Cooldown", f"Bot entered cooldown for {cooldown_time} seconds due to multiple crashes", "warning")
                
                # Wait for cooldown period, checking for shutdown request periodically
                for _ in range(cooldown_time):
                    if shutdown_requested:
                        logger.info("Shutdown requested during cooldown. Exiting...")
                        return
                    await asyncio.sleep(1)
                
                # Reset crash counter after cooldown
                consecutive_rapid_crashes = 0
                logger.info("Cooldown complete, resuming bot...")
            
            # Run the bot
            await run_bot()
            
            # If we get here without an exception, the bot was stopped gracefully
            if shutdown_requested:
                logger.info("Bot stopped gracefully due to shutdown request")
                break
            else:
                logger.warning("Bot exited without an exception. Restarting...")
                restart_count += 1
                
        except Exception as e:
            # Calculate if this is a rapid crash
            current_time = time.time()
            time_since_last_crash = current_time - last_crash_time
            
            retry_count += 1
            restart_count += 1
            
            # Log the exception with full traceback
            logger.error(f"Bot crashed with exception: {e}")
            logger.error(traceback.format_exc())
            
            # Update crash tracking
            if time_since_last_crash < RAPID_CRASH_WINDOW:
                consecutive_rapid_crashes += 1
                logger.warning(f"Rapid crash detected! {consecutive_rapid_crashes}/{MAX_CONSECUTIVE_CRASHES} consecutive rapid crashes")
            else:
                # Reset counter if this wasn't a rapid crash
                consecutive_rapid_crashes = 1
            
            last_crash_time = current_time
            
            # Send notification about the crash
            error_message = f"Exception: {str(e)}\nRestart count: {restart_count}\nRetry attempt: {retry_count}/{max_retries}"
            notify("Bot Crash", error_message, "error")
            
            # Exponential backoff for retry delay
            if retry_count < max_retries:
                delay = min(60, 2 ** retry_count)  # Cap at 60 seconds
                logger.info(f"Restarting bot in {delay} seconds... (Attempt {retry_count}/{max_retries})")
                
                # Wait for delay, but check for shutdown requests
                for _ in range(delay):
                    if shutdown_requested:
                        logger.info("Shutdown requested during retry delay. Exiting...")
                        return
                    await asyncio.sleep(1)
    
    if retry_count >= max_retries and not shutdown_requested:
        logger.critical(f"Bot failed after {max_retries} restart attempts. Giving up.")
        notify("Bot Failed", f"Bot failed after {max_retries} restart attempts and will not automatically restart.", "critical")

async def run_bot():
    """Run the Telegram bot directly using asyncio"""
    # Import the initialize_bot function with production_mode parameter
    from bot.slayer_bot import initialize_bot, get_bot_status, stop_bot
    
    # Get the bot token
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        sys.exit(1)
    
    logger.info(f"Starting Telegram bot in PRODUCTION mode with token: {token[:5]}...{token[-5:]}")
    
    # Initialize the bot with production_mode=True
    success = initialize_bot(production_mode=True)
    
    if not success:
        status = get_bot_status()
        error_msg = status.get("error", "Unknown error") if status else "Unknown error"
        logger.error(f"Failed to initialize bot: {error_msg}")
        raise Exception(f"Bot initialization failed: {error_msg}")
        
    logger.info("Bot is now running in production mode!")
    
    # If this is a restart, send notification
    global restart_count
    if restart_count > 0:
        notify("Bot Restarted", f"Bot has been restarted successfully (restart #{restart_count})", "info")
    else:
        notify("Bot Started", "Bot has been started successfully", "info")
    
    # Keep the script running and monitor bot status
    try:
        while not shutdown_requested:
            # Check bot status periodically
            status = get_bot_status()
            if not status:
                logger.error("Failed to get bot status")
                raise Exception("Failed to get bot status")
                
            if not status.get("running", False):
                error_msg = status.get("error", "Unknown error")
                logger.error(f"Bot stopped running: {error_msg}")
                raise Exception(f"Bot stopped running: {error_msg}")
                
            # Log stats periodically
            if restart_count == 0 or restart_count % 5 == 0:
                stats = status.get("stats", {})
                commands = stats.get("commands_processed", 0)
                messages = stats.get("messages_processed", 0)
                uptime = status.get("uptime", "unknown")
                logger.info(f"Bot status: Running for {uptime}, {commands} commands and {messages} messages processed")
                
            await asyncio.sleep(60)  # Check every minute
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot is shutting down due to user request...")
    finally:
        try:
            stop_bot()
            logger.info("Bot has been stopped")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

async def main():
    """Main function to run the bot with database setup"""
    logger.info("Starting Slayer Bot in 24/7 mode")
    
    # Set up the database
    db_success = setup_db()
    if not db_success:
        logger.error("Database setup failed. Cannot continue without database.")
        sys.exit(1)
    
    logger.info("Database setup completed successfully")
    
    # Run the bot with automatic restart on failure
    try:
        await run_bot_with_retries()
    except Exception as e:
        logger.critical(f"Unhandled exception in main loop: {e}")
        logger.critical(traceback.format_exc())
        
    logger.info("Slayer Bot has shut down")

if __name__ == "__main__":
    try:
        # Print banner
        print("\n" + "=" * 50)
        print("     SLAYER BOT - 24/7 PRODUCTION MODE")
        print("=" * 50)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Logs: {log_file}")
        print("=" * 50 + "\n")
        
        # Start the main loop
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user. Exiting...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        logger.critical(traceback.format_exc())
        sys.exit(1)

import os
import json
import logging
import re
import random
from telegram import Update
from telegram.ext import MessageHandler, filters, ContextTypes

# Configure logging
logger = logging.getLogger(__name__)

# This will be set from slayer_bot.py to avoid circular imports
increment_stats = None

# Load settings from environment variables
AUTO_RESPONSES_ENABLED = os.environ.get("AUTO_RESPONSES_ENABLED", "true").lower() == "true"
AUTO_REACTIONS_ENABLED = os.environ.get("AUTO_REACTIONS_ENABLED", "true").lower() == "true"

# Load auto-response patterns
def load_responses():
    """Load auto-response patterns from config file."""
    try:
        if os.path.exists('config/responses.json'):
            with open('config/responses.json', 'r') as f:
                return json.load(f)
        else:
            # Create default responses if file doesn't exist
            default_responses = {
                "greeting": {
                    "patterns": ["hello", "hi", "hey", "greetings", "sup", "what's up"],
                    "responses": [
                        "Hello there! How can I help you today?",
                        "Hi! Feel free to ask me anything or play some music!",
                        "Hey! What would you like to listen to today?",
                        "Greetings! How's your day going?"
                    ],
                    "case_sensitive": False
                },
                "thanks": {
                    "patterns": ["thank you", "thanks", "thx", "thank", "appreciate it"],
                    "responses": [
                        "You're welcome!",
                        "No problem!",
                        "Happy to help!",
                        "My pleasure!"
                    ],
                    "case_sensitive": False
                },
                "goodbye": {
                    "patterns": ["bye", "goodbye", "see you", "cya", "gotta go", "gtg"],
                    "responses": [
                        "Goodbye! Come back soon!",
                        "See you later!",
                        "Take care!",
                        "Bye! Let me know if you need anything else!"
                    ],
                    "case_sensitive": False
                },
                "music": {
                    "patterns": ["play music", "song", "play song", "some music", "some tunes"],
                    "responses": [
                        "I'd be happy to play music for you! Try using the /play command followed by a song name.",
                        "Ready for some tunes! Use /play followed by a song name to start playing.",
                        "Want to listen to music? Use /search to find your favorite songs.",
                        "I can play music for you! Just use the /play command followed by what you want to hear."
                    ],
                    "case_sensitive": False
                }
            }
            
            # Ensure config directory exists
            os.makedirs('config', exist_ok=True)
            
            # Write default responses to file
            with open('config/responses.json', 'w') as f:
                json.dump(default_responses, f, indent=2)
            
            return default_responses
    except Exception as e:
        logger.error(f"Error loading responses: {e}")
        return {}

# Load auto-reaction patterns
def load_reactions():
    """Load auto-reaction patterns from config file."""
    try:
        if os.path.exists('config/reactions.json'):
            with open('config/reactions.json', 'r') as f:
                return json.load(f)
        else:
            # Create default reactions if file doesn't exist
            default_reactions = {
                "like": {
                    "patterns": ["great", "awesome", "amazing", "excellent", "fantastic", "love"],
                    "reactions": ["👍", "❤️", "🔥", "⭐"],
                    "case_sensitive": False
                },
                "laugh": {
                    "patterns": ["haha", "lol", "funny", "lmao", "joke", "hilarious"],
                    "reactions": ["😂", "😆", "🤣", "😹"],
                    "case_sensitive": False
                },
                "sad": {
                    "patterns": ["sad", "unhappy", "depressed", "miserable", "disappointed"],
                    "reactions": ["😢", "😔", "😞", "💔"],
                    "case_sensitive": False
                },
                "music": {
                    "patterns": ["music", "song", "sing", "playlist", "album", "artist"],
                    "reactions": ["🎵", "🎶", "🎸", "🎧", "🎤"],
                    "case_sensitive": False
                }
            }
            
            # Ensure config directory exists
            os.makedirs('config', exist_ok=True)
            
            # Write default reactions to file
            with open('config/reactions.json', 'w') as f:
                json.dump(default_reactions, f, indent=2)
            
            return default_reactions
    except Exception as e:
        logger.error(f"Error loading reactions: {e}")
        return {}

# Global variables to store patterns
responses = load_responses()
reactions = load_reactions()

async def handle_auto_responses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle auto-responses based on message patterns."""
    # Check if auto-responses are enabled
    if not AUTO_RESPONSES_ENABLED and not AUTO_REACTIONS_ENABLED:
        return
        
    # Ignore non-text messages, commands, and messages already handled by AI conversation
    if not update.message or not update.message.text or update.message.text.startswith('/'):
        return
    
    # Get message text
    message_text = update.message.text
    chat_id = update.effective_chat.id
    bot_username = context.bot.username
    
    # Check if the message is not directed to the bot specifically
    is_private_chat = update.effective_chat.type == "private"
    is_mentioned = f"@{bot_username}" in message_text
    is_replied_to = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
    
    # If directed to the bot, let the AI conversation handler handle it
    if is_private_chat or is_mentioned or is_replied_to:
        return
    
    # Check for auto-response matches
    matched_response = None
    
    for category, data in responses.items():
        patterns = data.get("patterns", [])
        response_list = data.get("responses", [])
        case_sensitive = data.get("case_sensitive", False)
        
        if not case_sensitive:
            message_text_lower = message_text.lower()
            patterns = [p.lower() for p in patterns]
            
            for pattern in patterns:
                # Check for word boundaries
                if re.search(r'\b' + re.escape(pattern) + r'\b', message_text_lower):
                    matched_response = random.choice(response_list)
                    break
        else:
            for pattern in patterns:
                if re.search(r'\b' + re.escape(pattern) + r'\b', message_text):
                    matched_response = random.choice(response_list)
                    break
        
        if matched_response:
            break
    
    # Send auto-response if matched and enabled
    if matched_response and AUTO_RESPONSES_ENABLED:
        await update.message.reply_text(matched_response)
        increment_stats("messages_processed")
    
    # Skip reaction check if disabled
    if not AUTO_REACTIONS_ENABLED:
        return
        
    # Check for auto-reaction matches
    matched_reaction = None
    
    for category, data in reactions.items():
        patterns = data.get("patterns", [])
        reaction_list = data.get("reactions", [])
        case_sensitive = data.get("case_sensitive", False)
        
        if not case_sensitive:
            message_text_lower = message_text.lower()
            patterns = [p.lower() for p in patterns]
            
            for pattern in patterns:
                if re.search(r'\b' + re.escape(pattern) + r'\b', message_text_lower):
                    matched_reaction = random.choice(reaction_list)
                    break
        else:
            for pattern in patterns:
                if re.search(r'\b' + re.escape(pattern) + r'\b', message_text):
                    matched_reaction = random.choice(reaction_list)
                    break
        
        if matched_reaction:
            break
    
    # Add reaction if matched
    if matched_reaction:
        # In PTB v13+, reactions are done properly, but for now we'll simulate 
        # reactions by sending the emoji as a reply
        await update.message.reply_text(matched_reaction)
        increment_stats("messages_processed")

def setup_auto_responses(application):
    """Set up handlers for auto-responses."""
    # Add message handler for auto-responses with lower priority than AI
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_auto_responses), group=2)

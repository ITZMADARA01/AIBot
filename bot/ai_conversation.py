import os
import logging
import json
import time
from datetime import datetime
import asyncio
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Configure logging
logger = logging.getLogger(__name__)

# This will be set from slayer_bot.py to avoid circular imports
increment_stats = None

# Initialize OpenAI client
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
AI_ENABLED = os.environ.get("AI_ENABLED", "true").lower() == "true"
AI_RESPONSE_TEMPERATURE = float(os.environ.get("AI_RESPONSE_TEMPERATURE", "0.7"))
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "1000"))
AI_PRESENCE_PROBABILITY = float(os.environ.get("AI_PRESENCE_PROBABILITY", "0.4"))

if AI_ENABLED and not OPENAI_API_KEY:
    logger.warning("AI is enabled but OPENAI_API_KEY is not set. AI features will not work properly.")
    
openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Store chat histories for different users/chats
chat_histories = {}  # {chat_id: {user_id: [messages]}}
MAX_HISTORY = 10  # Maximum number of messages to keep in history per user

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /ask command to ask the AI a question."""
    if not context.args and not (update.message.reply_to_message and update.message.reply_to_message.text):
        await update.message.reply_text(
            "Please provide a question after the /ask command.\n"
            "Example: /ask What's the weather like today?"
        )
        return
    
    # Get the question
    if context.args:
        question = ' '.join(context.args)
    else:
        question = update.message.reply_to_message.text
    
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    
    # Send typing action to indicate the bot is processing
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # Get AI response
        response = await generate_ai_response(chat_id, user_id, question)
        
        # Save conversation to database
        await asyncio.to_thread(
            save_conversation_to_db,
            user_id=user_id,
            chat_id=chat_id,
            message=question,
            response=response["content"]
        )
        
        # Send response
        await update.message.reply_text(response["content"])
        
        # Update stats
        increment_stats("commands_processed")
        increment_stats("ai_conversations")
    
    except Exception as e:
        logger.error(f"Error in ask command: {str(e)}")
        await update.message.reply_text(f"❌ Error generating response: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular messages that might be directed to the AI."""
    # Check if AI is enabled
    if not AI_ENABLED:
        return
        
    # Ignore non-text messages and commands
    if not update.message or not update.message.text or update.message.text.startswith('/'):
        return
    
    message_text = update.message.text
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    bot_username = context.bot.username
    
    # Check if the message is directed to the bot (mentioned or in private chat)
    is_private_chat = update.effective_chat.type == "private"
    is_mentioned = f"@{bot_username}" in message_text
    is_replied_to = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
    
    # For random messages, use the presence probability
    if not (is_private_chat or is_mentioned or is_replied_to):
        import random
        if random.random() > AI_PRESENCE_PROBABILITY:
            return
    
    if is_private_chat or is_mentioned or is_replied_to or True:  # The 'or True' ensures we proceed with random messages that passed the probability check
        # Remove the bot's username from the message if it's mentioned
        if is_mentioned:
            message_text = message_text.replace(f"@{bot_username}", "").strip()
        
        # Send typing action
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        try:
            # Get AI response
            response = await generate_ai_response(chat_id, user_id, message_text)
            
            if response and "content" in response:
                # Save conversation to database
                try:
                    await asyncio.to_thread(
                        save_conversation_to_db,
                        user_id=user_id,
                        chat_id=chat_id,
                        message=message_text,
                        response=response["content"]
                    )
                except Exception as db_error:
                    # If database saving fails, just log it but continue
                    logger.error(f"Failed to save conversation to database: {str(db_error)}")
                
                # Send response
                await update.message.reply_text(response["content"])
                
                # Update stats
                if increment_stats:
                    increment_stats("messages_processed")
                    increment_stats("ai_conversations")
            else:
                logger.error("Invalid response format from AI")
                await update.message.reply_text("Sorry, I couldn't process that request.")
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error handling message: {error_msg}")
            
            # Send a user-friendly error message
            if "quota" in error_msg.lower() or "insufficient_quota" in error_msg:
                await update.message.reply_text("Sorry, I can't use AI responses right now due to API quota limits.")
            elif "rate limit" in error_msg.lower():
                await update.message.reply_text("I'm receiving too many requests right now. Please try again in a moment.")
            else:
                await update.message.reply_text("Sorry, I encountered an error while processing your message.")

async def generate_ai_response(chat_id, user_id, message):
    """Generate a response using the OpenAI API with context from chat history."""
    # Initialize chat history for this user if it doesn't exist
    if chat_id not in chat_histories:
        chat_histories[chat_id] = {}
    if user_id not in chat_histories[chat_id]:
        chat_histories[chat_id][user_id] = []
    
    # Get chat history for context
    history = chat_histories[chat_id][user_id]
    
    # Prepare messages for API call
    messages = [
        {
            "role": "system",
            "content": (
                "You are Slayer, an AI-powered Telegram music bot with advanced conversation capabilities. "
                "You're helpful, friendly, and knowledgeable. You can discuss music, answer questions, and engage in casual conversation. "
                "You can play music, manage queues, and perform various music-related tasks, but you're responding in a conversation now, "
                "not executing commands. If users want to play music, remind them to use commands like /play instead of just asking in conversation. "
                "Keep responses concise but friendly."
            )
        }
    ]
    
    # Add history for context
    for entry in history:
        messages.append({"role": "user", "content": entry["user"]})
        messages.append({"role": "assistant", "content": entry["assistant"]})
    
    # Add the current message
    messages.append({"role": "user", "content": message})
    
    # Check if AI is enabled
    if not AI_ENABLED:
        return {"content": "AI responses are currently disabled. Please contact the bot administrator."}
    
    # Check if OpenAI client is available
    if not openai:
        logger.error("OpenAI client not initialized - missing API key")
        return {"content": "Sorry, I'm unable to generate a response at the moment due to configuration issues."}
    
    try:
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=AI_MAX_TOKENS,
            temperature=AI_RESPONSE_TEMPERATURE,
        )
        
        # Extract response content
        content = response.choices[0].message.content
        
        # Update chat history
        history.append({"user": message, "assistant": content})
        
        # Limit history size
        if len(history) > MAX_HISTORY:
            history.pop(0)
        
        return {"content": content}
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error generating AI response: {error_msg}")
        
        # Handle specific error types
        if "quota" in error_msg.lower() or "insufficient_quota" in error_msg:
            return {"content": "Sorry, I can't use AI responses right now due to API quota limits. Please try again later or contact the bot administrator."}
        elif "rate limit" in error_msg.lower():
            return {"content": "I'm receiving too many requests right now. Please try again in a moment."}
        else:
            return {"content": "Sorry, I encountered an error while generating a response. Please try again later."}

def save_conversation_to_db(user_id, chat_id, message, response):
    """Save conversation to the database."""
    try:
        from app import db
        from models import ConversationLog
        
        with db.app.app_context():
            # Create new conversation log entry
            log_entry = ConversationLog(
                user_id=user_id,
                chat_id=chat_id,
                message=message,
                response=response,
                timestamp=datetime.utcnow()
            )
            
            db.session.add(log_entry)
            db.session.commit()
    
    except Exception as e:
        logger.error(f"Error saving conversation to database: {str(e)}")

def setup_ai_handlers(application):
    """Set up handlers for AI-related commands and messages."""
    # Add command handler for explicit AI questions
    application.add_handler(CommandHandler("ask", ask_command))
    
    # Add message handler for implicit conversations
    # Make sure this has lower priority than other handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message), group=1)

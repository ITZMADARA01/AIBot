import os
import logging
from telegram import Update, BotCommand
from telegram.ext import CommandHandler, ContextTypes
from bot.sudo_auth import is_sudo_user

# Configure logging
logger = logging.getLogger(__name__)

# This will be set from slayer_bot.py to avoid circular imports
increment_stats = None

async def setup_bot_commands(application):
    """Set up the bot commands menu."""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help information"),
        BotCommand("play", "Play a song by name or URL"),
        BotCommand("pause", "Pause the current playback"),
        BotCommand("resume", "Resume the playback"),
        BotCommand("skip", "Skip to the next song"),
        BotCommand("stop", "Stop playback and clear queue"),
        BotCommand("queue", "Show the current music queue"),
        BotCommand("current", "Show the currently playing song"),
        BotCommand("search", "Search for songs"),
        BotCommand("ask", "Ask the AI a question"),
        BotCommand("ping", "Check if the bot is responsive"),
        BotCommand("about", "About this bot"),
        BotCommand("addsudo", "Add a sudo user (admin only)"),
        BotCommand("delsudo", "Remove a sudo user (admin only)"),
        BotCommand("sudolist", "List all sudo users (sudo only)"),
        BotCommand("ban", "Ban a user from the chat"),
        BotCommand("unban", "Unban a user from the chat"),
        BotCommand("kick", "Kick a user from the chat"),
        BotCommand("mute", "Mute a user in the chat"),
        BotCommand("unmute", "Unmute a user in the chat"),
        BotCommand("gban", "Globally ban a user from all groups (sudo only)"),
        BotCommand("ungban", "Remove a global ban (sudo only)"),
        BotCommand("gbanlist", "List all globally banned users (sudo only)")
    ]
    
    await application.bot.set_my_commands(commands)

async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user from using the bot."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to ban.\n"
            "Example: /ban 123456789 Spamming"
        )
        return
    
    target_id = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    try:
        # Ban user in database
        from app import db
        from models import TelegramUser
        
        with db.app.app_context():
            user = TelegramUser.query.filter_by(telegram_id=target_id).first()
            
            if user:
                user.is_banned = True
                user.ban_reason = reason
                db.session.commit()
                await update.message.reply_text(f"✅ User {target_id} has been banned.\nReason: {reason}")
            else:
                # Create a new banned user entry
                new_user = TelegramUser(
                    telegram_id=target_id,
                    is_banned=True,
                    ban_reason=reason
                )
                db.session.add(new_user)
                db.session.commit()
                await update.message.reply_text(f"✅ User {target_id} has been added to the ban list.\nReason: {reason}")
        
        increment_stats("commands_processed")
    
    except Exception as e:
        logger.error(f"Error banning user: {str(e)}")
        await update.message.reply_text(f"❌ Error banning user: {str(e)}")

async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban a user."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to unban.\n"
            "Example: /unban 123456789"
        )
        return
    
    target_id = context.args[0]
    
    try:
        # Unban user in database
        from app import db
        from models import TelegramUser
        
        with db.app.app_context():
            user = TelegramUser.query.filter_by(telegram_id=target_id).first()
            
            if user and user.is_banned:
                user.is_banned = False
                user.ban_reason = None
                db.session.commit()
                await update.message.reply_text(f"✅ User {target_id} has been unbanned.")
            else:
                await update.message.reply_text(f"⚠️ User {target_id} is not banned or not found in the database.")
        
        increment_stats("commands_processed")
    
    except Exception as e:
        logger.error(f"Error unbanning user: {str(e)}")
        await update.message.reply_text(f"❌ Error unbanning user: {str(e)}")

async def ban_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a chat (group, channel) from using the bot."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a chat ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a chat ID to ban.\n"
            "Example: /banchat -1001234567890 Spam group"
        )
        return
    
    target_id = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    try:
        # Ban chat in database
        from app import db
        from models import TelegramChat
        
        with db.app.app_context():
            chat = TelegramChat.query.filter_by(chat_id=target_id).first()
            
            if chat:
                chat.is_banned = True
                chat.ban_reason = reason
                db.session.commit()
                await update.message.reply_text(f"✅ Chat {target_id} has been banned.\nReason: {reason}")
            else:
                # Create a new banned chat entry
                new_chat = TelegramChat(
                    chat_id=target_id,
                    is_banned=True,
                    ban_reason=reason
                )
                db.session.add(new_chat)
                db.session.commit()
                await update.message.reply_text(f"✅ Chat {target_id} has been added to the ban list.\nReason: {reason}")
            
            # Try to leave the chat if the bot is in it
            try:
                await context.bot.leave_chat(target_id)
                await update.message.reply_text(f"✅ Bot has left the banned chat {target_id}.")
            except Exception as leave_err:
                await update.message.reply_text(f"ℹ️ Bot could not leave chat {target_id}: {leave_err}")
        
        increment_stats("commands_processed")
    
    except Exception as e:
        logger.error(f"Error banning chat: {str(e)}")
        await update.message.reply_text(f"❌ Error banning chat: {str(e)}")

async def unban_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban a chat."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a chat ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a chat ID to unban.\n"
            "Example: /unbanchat -1001234567890"
        )
        return
    
    target_id = context.args[0]
    
    try:
        # Unban chat in database
        from app import db
        from models import TelegramChat
        
        with db.app.app_context():
            chat = TelegramChat.query.filter_by(chat_id=target_id).first()
            
            if chat and chat.is_banned:
                chat.is_banned = False
                chat.ban_reason = None
                db.session.commit()
                await update.message.reply_text(f"✅ Chat {target_id} has been unbanned.")
            else:
                await update.message.reply_text(f"⚠️ Chat {target_id} is not banned or not found in the database.")
        
        increment_stats("commands_processed")
    
    except Exception as e:
        logger.error(f"Error unbanning chat: {str(e)}")
        await update.message.reply_text(f"❌ Error unbanning chat: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    try:
        from app import db
        from models import TelegramUser, TelegramChat, MusicTrack, ConversationLog
        from bot.slayer_bot import get_bot_status
        
        with db.app.app_context():
            user_count = TelegramUser.query.count()
            banned_users = TelegramUser.query.filter_by(is_banned=True).count()
            chat_count = TelegramChat.query.count()
            banned_chats = TelegramChat.query.filter_by(is_banned=True).count()
            track_count = MusicTrack.query.count()
            conversation_count = ConversationLog.query.count()
            
            # Get most played tracks
            top_tracks = MusicTrack.query.order_by(MusicTrack.play_count.desc()).limit(5).all()
            
            status = get_bot_status()
            
            stats_text = (
                "📊 *Bot Statistics* 📊\n\n"
                f"👥 *Users:* {user_count} (Banned: {banned_users})\n"
                f"💬 *Chats:* {chat_count} (Banned: {banned_chats})\n"
                f"🎵 *Tracks in database:* {track_count}\n"
                f"🧠 *AI Conversations:* {conversation_count}\n\n"
                f"*Commands processed:* {status['commands_processed']}\n"
                f"*Messages handled:* {status['messages_processed']}\n"
                f"*Songs played:* {status['songs_played']}\n"
                f"*Running since:* {status['start_time']}\n\n"
                "*Top Tracks:*\n"
            )
            
            for i, track in enumerate(top_tracks, 1):
                stats_text += f"{i}. {track.title} - Played {track.play_count} times\n"
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
        increment_stats("commands_processed")
    
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        await update.message.reply_text(f"❌ Error getting stats: {str(e)}")

def setup_commands(application):
    """Set up command handlers for the bot."""
    # Set up bot commands menu
    application.create_task(setup_bot_commands(application))
    
    # Add admin command handlers
    application.add_handler(CommandHandler("ban", ban_user_command))
    application.add_handler(CommandHandler("unban", unban_user_command))
    application.add_handler(CommandHandler("banchat", ban_chat_command))
    application.add_handler(CommandHandler("unbanchat", unban_chat_command))
    application.add_handler(CommandHandler("stats", stats_command))

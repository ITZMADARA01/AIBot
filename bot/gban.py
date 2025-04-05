
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from bot.sudo_auth import is_sudo_user

# Configure logging
logger = logging.getLogger(__name__)

# This will be set from slayer_bot.py to avoid circular imports
increment_stats = None
db = None  # Will be set from slayer_bot.py

async def gban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Globally ban a user from all groups where the bot is admin."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to globally ban.\n"
            "Example: /gban 123456789 Spammer across multiple groups"
        )
        return
    
    # Extract user and reason
    target = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    try:
        # Try to get user ID
        try:
            target_user_id = int(target)
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
            return
        
        # Add user to global ban list in database
        if db and db.app:
            from models import TelegramUser, GlobalBan
            with db.app.app_context():
                # Update or create user record
                user = TelegramUser.query.filter_by(telegram_id=str(target_user_id)).first()
                if not user:
                    user = TelegramUser(
                        telegram_id=str(target_user_id),
                        is_banned=True,
                        ban_reason=f"Global Ban: {reason}"
                    )
                    db.session.add(user)
                else:
                    user.is_banned = True
                    user.ban_reason = f"Global Ban: {reason}"
                
                # Create global ban record
                gban = GlobalBan(
                    user_id=str(target_user_id),
                    banned_by=str(update.effective_user.id),
                    reason=reason
                )
                db.session.add(gban)
                db.session.commit()
        
        # Get a list of all groups the bot is in
        status_message = await update.message.reply_text(
            f"🔄 Processing global ban for user {target_user_id}. This may take a moment..."
        )
        
        if db and db.app:
            from models import TelegramChat
            with db.app.app_context():
                # Get all active group chats
                chats = TelegramChat.query.filter(
                    TelegramChat.is_banned.isnot(True),
                    TelegramChat.chat_type.in_(['group', 'supergroup'])
                ).all()
                
                # Ban the user from each chat
                success_count = 0
                fail_count = 0
                
                for chat in chats:
                    try:
                        await context.bot.ban_chat_member(chat.chat_id, target_user_id)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to ban user {target_user_id} from chat {chat.chat_id}: {str(e)}")
                        fail_count += 1
                
                # Update status message
                await status_message.edit_text(
                    f"✅ User {target_user_id} has been globally banned.\n"
                    f"Reason: {reason}\n\n"
                    f"✅ Successfully banned from {success_count} chats.\n"
                    f"❌ Failed to ban from {fail_count} chats."
                )
        else:
            await status_message.edit_text(
                f"✅ User {target_user_id} has been added to the global ban list.\n"
                f"Reason: {reason}\n\n"
                f"⚠️ Database not available, user will be banned from new chats when they join."
            )
        
        # Increment stats
        if increment_stats:
            increment_stats("global_bans")
    
    except Exception as e:
        logger.error(f"Error in global ban: {str(e)}")
        await update.message.reply_text(f"❌ Error processing global ban: {str(e)}")

async def ungban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a user from the global ban list."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to remove from global ban.\n"
            "Example: /ungban 123456789"
        )
        return
    
    # Extract user ID
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
        return
    
    try:
        # Remove user from global ban list in database
        gban_exists = False
        
        if db and db.app:
            from models import TelegramUser, GlobalBan
            with db.app.app_context():
                # Check if user is globally banned
                gban = GlobalBan.query.filter_by(
                    user_id=str(target_user_id),
                    unbanned_at=None
                ).first()
                
                if gban:
                    gban_exists = True
                    gban.unbanned_by = str(update.effective_user.id)
                    gban.unbanned_at = db.func.now()
                    
                    # Update user record
                    user = TelegramUser.query.filter_by(telegram_id=str(target_user_id)).first()
                    if user:
                        user.is_banned = False
                        user.ban_reason = None
                    
                    db.session.commit()
        
        if not gban_exists:
            await update.message.reply_text(f"⚠️ User {target_user_id} is not in the global ban list.")
            return
        
        # Get a list of all groups the bot is in
        status_message = await update.message.reply_text(
            f"🔄 Processing global unban for user {target_user_id}. This may take a moment..."
        )
        
        if db and db.app:
            from models import TelegramChat
            with db.app.app_context():
                # Get all active group chats
                chats = TelegramChat.query.filter(
                    TelegramChat.is_banned.isnot(True),
                    TelegramChat.chat_type.in_(['group', 'supergroup'])
                ).all()
                
                # Unban the user from each chat
                success_count = 0
                fail_count = 0
                
                for chat in chats:
                    try:
                        await context.bot.unban_chat_member(chat.chat_id, target_user_id)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to unban user {target_user_id} from chat {chat.chat_id}: {str(e)}")
                        fail_count += 1
                
                # Update status message
                await status_message.edit_text(
                    f"✅ User {target_user_id} has been removed from the global ban list.\n\n"
                    f"✅ Successfully unbanned from {success_count} chats.\n"
                    f"❌ Failed to unban from {fail_count} chats."
                )
        else:
            await status_message.edit_text(
                f"✅ User {target_user_id} has been removed from the global ban list.\n\n"
                f"⚠️ Database not available, the user may still be banned in some chats."
            )
    
    except Exception as e:
        logger.error(f"Error in global unban: {str(e)}")
        await update.message.reply_text(f"❌ Error processing global unban: {str(e)}")

async def gban_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all globally banned users."""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    try:
        if db and db.app:
            from models import GlobalBan
            with db.app.app_context():
                # Get all active global bans
                gbans = GlobalBan.query.filter_by(unbanned_at=None).all()
                
                if not gbans:
                    await update.message.reply_text("📝 The global ban list is empty.")
                    return
                
                # Format the list
                gban_text = "📝 *Global Ban List:*\n\n"
                
                for i, gban in enumerate(gbans, 1):
                    gban_text += (
                        f"{i}. User ID: `{gban.user_id}`\n"
                        f"   Reason: {gban.reason}\n"
                        f"   Banned by: `{gban.banned_by}`\n"
                        f"   Date: {gban.banned_at.strftime('%Y-%m-%d %H:%M UTC') if gban.banned_at else 'Unknown'}\n\n"
                    )
                
                # Split into multiple messages if too long
                if len(gban_text) > 4000:
                    parts = [gban_text[i:i+4000] for i in range(0, len(gban_text), 4000)]
                    for i, part in enumerate(parts):
                        if i == 0:
                            await update.message.reply_text(part, parse_mode="Markdown")
                        else:
                            await context.bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=part,
                                parse_mode="Markdown"
                            )
                else:
                    await update.message.reply_text(gban_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Database not available, cannot retrieve global ban list.")
    
    except Exception as e:
        logger.error(f"Error getting global ban list: {str(e)}")
        await update.message.reply_text(f"❌ Error retrieving global ban list: {str(e)}")

async def check_global_ban(user_id):
    """Check if a user is globally banned."""
    try:
        if db and db.app:
            from models import GlobalBan
            with db.app.app_context():
                gban = GlobalBan.query.filter_by(
                    user_id=str(user_id),
                    unbanned_at=None
                ).first()
                
                return gban is not None, gban.reason if gban else None
        
        return False, None
    
    except Exception as e:
        logger.error(f"Error checking global ban status: {str(e)}")
        return False, None

async def on_new_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if new chat members are globally banned."""
    if not update.message or not update.message.new_chat_members:
        return
    
    chat = update.effective_chat
    
    # Check if the bot has ban permissions
    bot_member = await chat.get_member(context.bot.id)
    if not bot_member.can_restrict_members:
        return
    
    # Check each new member
    for member in update.message.new_chat_members:
        is_banned, reason = await check_global_ban(member.id)
        
        if is_banned:
            try:
                # Ban the user from this chat
                await chat.ban_member(member.id)
                
                # Send notification
                await update.message.reply_text(
                    f"⚠️ User {member.id} is on the global ban list and has been banned from this chat.\n"
                    f"Reason: {reason}"
                )
            
            except Exception as e:
                logger.error(f"Error enforcing global ban for user {member.id} in chat {chat.id}: {str(e)}")

def setup_gban_handlers(application):
    """Set up handlers for global ban commands and events."""
    from telegram.ext import CommandHandler, MessageHandler, filters
    
    application.add_handler(CommandHandler("gban", gban_user))
    application.add_handler(CommandHandler("ungban", ungban_user))
    application.add_handler(CommandHandler("gbanlist", gban_list))
    
    # Add handler for new chat members to enforce global bans
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_member))

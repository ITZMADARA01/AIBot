
import logging
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from bot.sudo_auth import is_sudo_user

# Configure logging
logger = logging.getLogger(__name__)

# This will be set from slayer_bot.py to avoid circular imports
increment_stats = None
db = None  # Will be set from slayer_bot.py

async def ban_user_from_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user from the current chat."""
    # Check if command was issued by an admin or sudo user
    if not await is_sudo_user(update.effective_user.id) and not await is_chat_admin(update):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID or username was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID or username to ban.\n"
            "Example: /ban @username Spamming"
        )
        return
    
    # Extract user and reason
    target = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    # Check if bot has ban permissions
    chat = update.effective_chat
    bot_member = await chat.get_member(context.bot.id)
    
    if not bot_member.can_restrict_members:
        await update.message.reply_text("❌ I don't have permission to ban users in this chat.")
        return
    
    try:
        # Try to get user ID from mention or ID
        target_user = None
        if target.startswith('@'):
            # It's a username
            username = target[1:]  # Remove the @ symbol
            # We need to search for this user in the database or get from chat members
            # For now, we'll respond that we need a user ID
            await update.message.reply_text(
                "❌ Please use a user ID instead of a username. You can forward a message from the user to identify them."
            )
            return
        else:
            try:
                # Try to interpret as a user ID
                target_user_id = int(target)
                
                # Ban the user
                await chat.ban_member(target_user_id)
                
                # Log the ban in the database
                if db and db.app:
                    from models import TelegramUser, BanRecord
                    with db.app.app_context():
                        # Update or create user record
                        user = TelegramUser.query.filter_by(telegram_id=str(target_user_id)).first()
                        if not user:
                            user = TelegramUser(
                                telegram_id=str(target_user_id),
                                is_banned=True,
                                ban_reason=reason
                            )
                            db.session.add(user)
                        else:
                            user.is_banned = True
                            user.ban_reason = reason
                        
                        # Create ban record
                        ban_record = BanRecord(
                            user_id=str(target_user_id),
                            chat_id=str(chat.id),
                            banned_by=str(update.effective_user.id),
                            reason=reason
                        )
                        db.session.add(ban_record)
                        db.session.commit()
                
                # Increment stats
                if increment_stats:
                    increment_stats("users_banned")
                
                await update.message.reply_text(
                    f"✅ User {target_user_id} has been banned from this chat.\n"
                    f"Reason: {reason}"
                )
                
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID. Please provide a valid user ID.")
                return
    
    except BadRequest as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    except TelegramError as e:
        logger.error(f"Error banning user: {str(e)}")
        await update.message.reply_text(f"❌ Failed to ban user: {str(e)}")

async def unban_user_from_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban a user from the current chat."""
    # Check if command was issued by an admin or sudo user
    if not await is_sudo_user(update.effective_user.id) and not await is_chat_admin(update):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to unban.\n"
            "Example: /unban 123456789"
        )
        return
    
    # Extract user ID
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
        return
    
    # Check if bot has ban permissions
    chat = update.effective_chat
    bot_member = await chat.get_member(context.bot.id)
    
    if not bot_member.can_restrict_members:
        await update.message.reply_text("❌ I don't have permission to unban users in this chat.")
        return
    
    try:
        # Unban the user
        await chat.unban_member(target_user_id)
        
        # Log the unban in the database
        if db and db.app:
            from models import BanRecord
            with db.app.app_context():
                # Update ban records
                ban_records = BanRecord.query.filter_by(
                    user_id=str(target_user_id),
                    chat_id=str(chat.id),
                    unbanned_at=None
                ).all()
                
                for record in ban_records:
                    record.unbanned_by = str(update.effective_user.id)
                    record.unbanned_at = db.func.now()
                
                db.session.commit()
        
        await update.message.reply_text(f"✅ User {target_user_id} has been unbanned from this chat.")
    
    except BadRequest as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    except TelegramError as e:
        logger.error(f"Error unbanning user: {str(e)}")
        await update.message.reply_text(f"❌ Failed to unban user: {str(e)}")

async def kick_user_from_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kick a user from the current chat (ban and then unban)."""
    # Check if command was issued by an admin or sudo user
    if not await is_sudo_user(update.effective_user.id) and not await is_chat_admin(update):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to kick.\n"
            "Example: /kick 123456789 Disrupting conversation"
        )
        return
    
    # Extract user and reason
    target = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    # Check if bot has ban permissions
    chat = update.effective_chat
    bot_member = await chat.get_member(context.bot.id)
    
    if not bot_member.can_restrict_members:
        await update.message.reply_text("❌ I don't have permission to kick users in this chat.")
        return
    
    try:
        # Try to get user ID
        try:
            target_user_id = int(target)
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
            return
        
        # Kick the user (ban and then immediately unban)
        await chat.ban_member(target_user_id)
        await chat.unban_member(target_user_id)
        
        # Log the kick in the database
        if db and db.app:
            from models import BanRecord
            with db.app.app_context():
                # Create kick record
                kick_record = BanRecord(
                    user_id=str(target_user_id),
                    chat_id=str(chat.id),
                    banned_by=str(update.effective_user.id),
                    reason=f"Kicked: {reason}",
                    unbanned_by=str(update.effective_user.id),
                    unbanned_at=db.func.now(),
                    is_kick=True
                )
                db.session.add(kick_record)
                db.session.commit()
        
        await update.message.reply_text(
            f"✅ User {target_user_id} has been kicked from this chat.\n"
            f"Reason: {reason}"
        )
    
    except BadRequest as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    except TelegramError as e:
        logger.error(f"Error kicking user: {str(e)}")
        await update.message.reply_text(f"❌ Failed to kick user: {str(e)}")

async def mute_user_in_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mute a user in the current chat."""
    # Check if command was issued by an admin or sudo user
    if not await is_sudo_user(update.effective_user.id) and not await is_chat_admin(update):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to mute.\n"
            "Example: /mute 123456789 Spamming"
        )
        return
    
    # Extract user and reason
    target = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    # Check if bot has restriction permissions
    chat = update.effective_chat
    bot_member = await chat.get_member(context.bot.id)
    
    if not bot_member.can_restrict_members:
        await update.message.reply_text("❌ I don't have permission to mute users in this chat.")
        return
    
    try:
        # Try to get user ID
        try:
            target_user_id = int(target)
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
            return
        
        # Mute the user by removing send message permissions
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
        
        await chat.restrict_member(target_user_id, permissions)
        
        # Log the mute in the database
        if db and db.app:
            from models import MuteRecord
            with db.app.app_context():
                # Create mute record
                mute_record = MuteRecord(
                    user_id=str(target_user_id),
                    chat_id=str(chat.id),
                    muted_by=str(update.effective_user.id),
                    reason=reason
                )
                db.session.add(mute_record)
                db.session.commit()
        
        await update.message.reply_text(
            f"✅ User {target_user_id} has been muted in this chat.\n"
            f"Reason: {reason}"
        )
    
    except BadRequest as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    except TelegramError as e:
        logger.error(f"Error muting user: {str(e)}")
        await update.message.reply_text(f"❌ Failed to mute user: {str(e)}")

async def unmute_user_in_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute a user in the current chat."""
    # Check if command was issued by an admin or sudo user
    if not await is_sudo_user(update.effective_user.id) and not await is_chat_admin(update):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to unmute.\n"
            "Example: /unmute 123456789"
        )
        return
    
    # Extract user ID
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
        return
    
    # Check if bot has restriction permissions
    chat = update.effective_chat
    bot_member = await chat.get_member(context.bot.id)
    
    if not bot_member.can_restrict_members:
        await update.message.reply_text("❌ I don't have permission to unmute users in this chat.")
        return
    
    try:
        # Unmute the user by restoring permissions
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        
        await chat.restrict_member(target_user_id, permissions)
        
        # Log the unmute in the database
        if db and db.app:
            from models import MuteRecord
            with db.app.app_context():
                # Update mute records
                mute_records = MuteRecord.query.filter_by(
                    user_id=str(target_user_id),
                    chat_id=str(chat.id),
                    unmuted_at=None
                ).all()
                
                for record in mute_records:
                    record.unmuted_by = str(update.effective_user.id)
                    record.unmuted_at = db.func.now()
                
                db.session.commit()
        
        await update.message.reply_text(f"✅ User {target_user_id} has been unmuted in this chat.")
    
    except BadRequest as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    except TelegramError as e:
        logger.error(f"Error unmuting user: {str(e)}")
        await update.message.reply_text(f"❌ Failed to unmute user: {str(e)}")

async def is_chat_admin(update: Update) -> bool:
    """Check if the user is an admin in the chat."""
    if not update.effective_chat:
        return False
    
    try:
        chat_member = await update.effective_chat.get_member(update.effective_user.id)
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking admin status: {str(e)}")
        return False

def setup_ban_handlers(application):
    """Set up handlers for ban-related commands."""
    from telegram.ext import CommandHandler
    
    application.add_handler(CommandHandler("ban", ban_user_from_chat))
    application.add_handler(CommandHandler("unban", unban_user_from_chat))
    application.add_handler(CommandHandler("kick", kick_user_from_chat))
    application.add_handler(CommandHandler("mute", mute_user_in_chat))
    application.add_handler(CommandHandler("unmute", unmute_user_in_chat))

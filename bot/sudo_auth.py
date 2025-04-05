import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

# Configure logging
logger = logging.getLogger(__name__)

# This will be set from slayer_bot.py to avoid circular imports
increment_stats = None
db = None  # Will be set from slayer_bot.py


async def is_sudo_user(user_id):
    """Check if a user is a sudo user"""
    # Check environment variable first for owner/admin
    owner_id = os.environ.get("6586095302", "True")
    admin_ids = os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")

    if str(user_id) == owner_id or str(user_id) in admin_ids:
        return True

    # Check database for sudo users
    try:
        if db and db.app:
            from models import SudoUser
            with db.app.app_context():
                sudo_user = SudoUser.query.filter_by(telegram_id=str(user_id),
                                                     is_active=True).first()
                return sudo_user is not None
        return False
    except Exception as e:
        logger.error(f"Error checking sudo user: {str(e)}")
        return False


async def addsudo_command(update: Update,
                          context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a user to sudo users"""
    # Check if command was issued by an admin or owner
    admin_ids = os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    owner_id = os.environ.get("6586095302", "True")
    user_id = str(update.effective_user.id)

    if user_id not in admin_ids and user_id != owner_id:
        await update.message.reply_text(
            "❌ You don't have permission to use this command.")
        return

    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to add as sudo.\n"
            "Example: /addsudo 123456789")
        return

    target_id = context.args[0]

    try:
        # Add sudo user to database
        if db and db.app:
            from models import SudoUser
            with db.app.app_context():
                existing_sudo = SudoUser.query.filter_by(
                    telegram_id=target_id).first()

                if existing_sudo:
                    if existing_sudo.is_active:
                        await update.message.reply_text(
                            f"⚠️ User {target_id} is already a sudo user.")
                    else:
                        existing_sudo.is_active = True
                        existing_sudo.added_by = user_id
                        existing_sudo.added_at = datetime.utcnow()
                        db.session.commit()
                        await update.message.reply_text(
                            f"✅ User {target_id} has been restored as a sudo user."
                        )
                else:
                    # Create a new sudo user
                    new_sudo = SudoUser(telegram_id=target_id,
                                        added_by=user_id,
                                        is_active=True)
                    db.session.add(new_sudo)
                    db.session.commit()
                    await update.message.reply_text(
                        f"✅ User {target_id} has been added as a sudo user.")

        increment_stats("commands_processed")

    except Exception as e:
        logger.error(f"Error adding sudo user: {str(e)}")
        await update.message.reply_text(f"❌ Error adding sudo user: {str(e)}")


async def delsudo_command(update: Update,
                          context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a user from sudo users"""
    # Check if command was issued by an admin or owner
    admin_ids = os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    owner_id = os.environ.get("OWNER_ID", "")
    user_id = str(update.effective_user.id)

    if user_id not in admin_ids and user_id != owner_id:
        await update.message.reply_text(
            "❌ You don't have permission to use this command.")
        return

    # Check if a user ID was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a user ID to remove from sudo.\n"
            "Example: /delsudo 123456789")
        return

    target_id = context.args[0]

    # Cannot remove the owner
    if target_id == owner_id:
        await update.message.reply_text(
            "❌ Cannot remove the owner from sudo users.")
        return

    try:
        # Remove sudo user from database
        if db and db.app:
            from models import SudoUser
            with db.app.app_context():
                sudo_user = SudoUser.query.filter_by(telegram_id=target_id,
                                                     is_active=True).first()

                if sudo_user:
                    sudo_user.is_active = False
                    sudo_user.removed_by = user_id
                    sudo_user.removed_at = datetime.utcnow()
                    db.session.commit()
                    await update.message.reply_text(
                        f"✅ User {target_id} has been removed from sudo users."
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ User {target_id} is not a sudo user.")

        increment_stats("commands_processed")

    except Exception as e:
        logger.error(f"Error removing sudo user: {str(e)}")
        await update.message.reply_text(f"❌ Error removing sudo user: {str(e)}"
                                        )


async def sudolist_command(update: Update,
                           context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all sudo users"""
    # Check if command was issued by a sudo user
    if not await is_sudo_user(update.effective_user.id):
        await update.message.reply_text(
            "❌ You don't have permission to use this command.")
        return

    try:
        # Get sudo users from database
        if db and db.app:
            from models import SudoUser
            with db.app.app_context():
                sudo_users = SudoUser.query.filter_by(is_active=True).all()

                if sudo_users:
                    sudo_list = "📜 *Sudo Users:*\n\n"
                    for i, sudo in enumerate(sudo_users, 1):
                        sudo_list += f"{i}. `{sudo.telegram_id}`\n"

                    # Include owner for completeness
                    owner_id = os.environ.get("OWNER_ID", "True")
                    if owner_id:
                        sudo_list += f"\n👑 *Owner:* `{owner_id}`\n"

                    await update.message.reply_text(sudo_list,
                                                    parse_mode="Markdown")
                else:
                    await update.message.reply_text(
                        "No sudo users found in database.")

        increment_stats("commands_processed")

    except Exception as e:
        logger.error(f"Error listing sudo users: {str(e)}")
        await update.message.reply_text(f"❌ Error listing sudo users: {str(e)}"
                                        )


def setup_sudo_handlers(application):
    """Set up sudo user command handlers"""
    application.add_handler(CommandHandler("addsudo", addsudo_command))
    application.add_handler(CommandHandler("delsudo", delsudo_command))
    application.add_handler(CommandHandler("sudolist", sudolist_command))

import os
import logging
import asyncio
import threading
import json
import time
from datetime import datetime
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from collections import defaultdict

# Configure logging
logger = logging.getLogger(__name__)

# This will be set from slayer_bot.py to avoid circular imports
increment_stats = None

# Global variables to track music playback
music_queues = defaultdict(list)  # chat_id -> list of tracks
current_track = {}  # chat_id -> current track info
is_playing = {}  # chat_id -> boolean

# Configure yt-dlp options for audio extraction
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True
}

def create_download_dir():
    """Create the downloads directory if it doesn't exist."""
    os.makedirs('downloads', exist_ok=True)

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /play command to play music."""
    chat_id = update.effective_chat.id
    
    # Check if there's a query
    if not context.args and not (update.message.reply_to_message and update.message.reply_to_message.text):
        await update.message.reply_text(
            "Please provide a song name or URL after the /play command.\n"
            "Example: /play Bohemian Rhapsody"
        )
        return
    
    # Get the search query
    if context.args:
        query = ' '.join(context.args)
    else:
        query = update.message.reply_to_message.text
    
    await update.message.reply_text(f"🔍 Searching for: {query}")
    
    # Search for the song
    try:
        song_info = await asyncio.to_thread(search_song, query)
        if not song_info:
            await update.message.reply_text("❌ Sorry, I couldn't find any matching songs.")
            return
        
        # Add song to queue
        music_queues[chat_id].append(song_info)
        
        # Save track to database
        await asyncio.to_thread(save_track_to_db, song_info)
        
        # Check if already playing, if not start playback
        if chat_id not in is_playing or not is_playing[chat_id]:
            await update.message.reply_text(
                f"🎵 Added to queue and starting playback: {song_info['title']}"
            )
            asyncio.create_task(play_next(chat_id, context))
        else:
            position = len(music_queues[chat_id])
            await update.message.reply_text(
                f"🎵 Added to queue (position {position}): {song_info['title']}"
            )
        
        increment_stats("commands_processed")
        
    except Exception as e:
        logger.error(f"Error in play command: {str(e)}")
        await update.message.reply_text(f"❌ Error playing song: {str(e)}")

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause music playback."""
    chat_id = update.effective_chat.id
    
    if chat_id in is_playing and is_playing[chat_id]:
        is_playing[chat_id] = False
        await update.message.reply_text("⏸️ Music playback paused.")
    else:
        await update.message.reply_text("❌ No music is currently playing.")
    
    increment_stats("commands_processed")

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume music playback."""
    chat_id = update.effective_chat.id
    
    if chat_id in current_track and current_track[chat_id]:
        if not is_playing[chat_id]:
            is_playing[chat_id] = True
            await update.message.reply_text("▶️ Music playback resumed.")
            asyncio.create_task(play_next(chat_id, context))
        else:
            await update.message.reply_text("❓ Music is already playing.")
    else:
        await update.message.reply_text("❌ No music in queue. Use /play to add songs.")
    
    increment_stats("commands_processed")

async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Skip to the next song in the queue."""
    chat_id = update.effective_chat.id
    
    if chat_id in is_playing and is_playing[chat_id]:
        await update.message.reply_text("⏭️ Skipping to the next song...")
        is_playing[chat_id] = False  # This will trigger the next song to play
    else:
        await update.message.reply_text("❌ No music is currently playing.")
    
    increment_stats("commands_processed")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop playback and clear the queue."""
    chat_id = update.effective_chat.id
    
    if chat_id in music_queues:
        music_queues[chat_id].clear()
    
    if chat_id in is_playing:
        is_playing[chat_id] = False
    
    if chat_id in current_track:
        current_track[chat_id] = None
    
    await update.message.reply_text("⏹️ Music playback stopped and queue cleared.")
    increment_stats("commands_processed")

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the current music queue."""
    chat_id = update.effective_chat.id
    
    if chat_id not in music_queues or not music_queues[chat_id]:
        await update.message.reply_text("📋 The music queue is empty. Use /play to add songs.")
        return
    
    queue_text = "📋 *Music Queue:*\n\n"
    
    # Add current track if there is one
    if chat_id in current_track and current_track[chat_id]:
        queue_text += f"*Now Playing:* {current_track[chat_id]['title']}\n\n"
    
    # Add upcoming tracks
    if music_queues[chat_id]:
        queue_text += "*Up Next:*\n"
        for i, track in enumerate(music_queues[chat_id], 1):
            duration_str = format_duration(track.get('duration', 0))
            queue_text += f"{i}. {track['title']} ({duration_str})\n"
    
    await update.message.reply_text(queue_text, parse_mode="Markdown")
    increment_stats("commands_processed")

async def current_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show currently playing track."""
    chat_id = update.effective_chat.id
    
    if chat_id in current_track and current_track[chat_id]:
        track = current_track[chat_id]
        duration_str = format_duration(track.get('duration', 0))
        
        # Create keyboard with YouTube link
        keyboard = [
            [InlineKeyboardButton("🔗 Watch on YouTube", url=f"https://www.youtube.com/watch?v={track['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎵 *Now Playing:*\n"
            f"*Title:* {track['title']}\n"
            f"*Duration:* {duration_str}\n",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ No music is currently playing.")
    
    increment_stats("commands_processed")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for songs and display results."""
    if not context.args:
        await update.message.reply_text(
            "Please provide a search query after the /search command.\n"
            "Example: /search Bohemian Rhapsody"
        )
        return
    
    query = ' '.join(context.args)
    await update.message.reply_text(f"🔍 Searching for: {query}")
    
    try:
        results = await asyncio.to_thread(search_multiple_songs, query, limit=5)
        if not results:
            await update.message.reply_text("❌ No results found for your search.")
            return
        
        # Create inline keyboard with search results
        keyboard = []
        for i, result in enumerate(results):
            duration_str = format_duration(result.get('duration', 0))
            button_text = f"{i+1}. {result['title']} ({duration_str})"
            callback_data = f"play:{result['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔍 *Search Results:*\nClick on a song to play it.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    except Exception as e:
        logger.error(f"Error in search command: {str(e)}")
        await update.message.reply_text(f"❌ Error searching for songs: {str(e)}")
    
    increment_stats("commands_processed")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks from inline keyboards."""
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    data = query.data
    
    if data.startswith("play:"):
        video_id = data.split(":")[1]
        try:
            # Get song info from video id
            song_info = await asyncio.to_thread(get_song_info, video_id)
            if not song_info:
                await query.edit_message_text("❌ Sorry, I couldn't fetch information for this song.")
                return
            
            # Add song to queue
            music_queues[chat_id].append(song_info)
            
            # Save track to database
            await asyncio.to_thread(save_track_to_db, song_info)
            
            # Check if already playing, if not start playback
            if chat_id not in is_playing or not is_playing[chat_id]:
                await query.edit_message_text(
                    f"🎵 Added to queue and starting playback: {song_info['title']}"
                )
                asyncio.create_task(play_next(chat_id, context))
            else:
                position = len(music_queues[chat_id])
                await query.edit_message_text(
                    f"🎵 Added to queue (position {position}): {song_info['title']}"
                )
        
        except Exception as e:
            logger.error(f"Error in button callback: {str(e)}")
            await query.edit_message_text(f"❌ Error playing song: {str(e)}")

async def play_next(chat_id, context):
    """Play the next song in the queue."""
    try:
        bot = context.bot
        
        # If paused or stopped, don't continue
        if chat_id in is_playing and not is_playing[chat_id]:
            return
        
        # Check if there are songs in the queue
        if not music_queues[chat_id]:
            await bot.send_message(chat_id, "📋 Music queue is now empty.")
            is_playing[chat_id] = False
            current_track[chat_id] = None
            return
        
        # Get the next song from the queue
        song = music_queues[chat_id].pop(0)
        current_track[chat_id] = song
        is_playing[chat_id] = True
        
        # Mark song as playing in the database
        await asyncio.to_thread(update_track_play_count, song['id'])
        
        # Send now playing message
        duration_str = format_duration(song.get('duration', 0))
        
        # Create keyboard with YouTube link
        keyboard = [
            [InlineKeyboardButton("🔗 Watch on YouTube", url=f"https://www.youtube.com/watch?v={song['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await bot.send_message(
            chat_id,
            f"🎵 *Now Playing:*\n"
            f"*Title:* {song['title']}\n"
            f"*Duration:* {duration_str}\n",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
        # Update stats
        increment_stats("songs_played")
        
        # Simulate playback by waiting the duration of the song
        # In a real implementation, this would be streaming audio
        await asyncio.sleep(song.get('duration', 180))
        
        # After the song finishes, play the next one
        if chat_id in is_playing and is_playing[chat_id]:
            await play_next(chat_id, context)
    
    except Exception as e:
        logger.error(f"Error playing next song: {str(e)}")
        await bot.send_message(chat_id, f"❌ Error during playback: {str(e)}")
        # Try to continue with the next song
        is_playing[chat_id] = False
        await asyncio.sleep(2)
        is_playing[chat_id] = True
        await play_next(chat_id, context)

def search_song(query):
    """Search for a song using yt-dlp and return the first result."""
    create_download_dir()
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if query.startswith('http'):
                # If it's a URL, just extract info
                info = ydl.extract_info(query, download=False)
            else:
                # Otherwise, search for it
                info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            
            return {
                'id': info['id'],
                'title': info['title'],
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'url': f"https://www.youtube.com/watch?v={info['id']}"
            }
    except Exception as e:
        logger.error(f"Error searching for song: {str(e)}")
        return None

def search_multiple_songs(query, limit=5):
    """Search for multiple songs and return a list of results."""
    create_download_dir()
    
    try:
        ydl_opts_search = ydl_opts.copy()
        with yt_dlp.YoutubeDL(ydl_opts_search) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            
            results = []
            for entry in info['entries']:
                if entry:
                    results.append({
                        'id': entry['id'],
                        'title': entry['title'],
                        'duration': entry.get('duration', 0),
                        'thumbnail': entry.get('thumbnail', ''),
                        'url': f"https://www.youtube.com/watch?v={entry['id']}"
                    })
            
            return results
    except Exception as e:
        logger.error(f"Error searching for multiple songs: {str(e)}")
        return []

def get_song_info(video_id):
    """Get information about a specific YouTube video."""
    create_download_dir()
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            
            return {
                'id': info['id'],
                'title': info['title'],
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'url': f"https://www.youtube.com/watch?v={info['id']}"
            }
    except Exception as e:
        logger.error(f"Error getting song info: {str(e)}")
        return None

def format_duration(seconds):
    """Format duration in seconds to MM:SS format."""
    if not seconds:
        return "Unknown"
    
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def save_track_to_db(track_info):
    """Save track information to the database."""
    try:
        from app import db
        from models import MusicTrack
        
        with db.app.app_context():
            # Check if track already exists
            existing_track = MusicTrack.query.filter_by(youtube_id=track_info['id']).first()
            
            if existing_track:
                # Track exists, no need to create a new one
                return existing_track
            
            # Create new track
            new_track = MusicTrack(
                youtube_id=track_info['id'],
                title=track_info['title'],
                duration=track_info.get('duration', 0),
                thumbnail_url=track_info.get('thumbnail', ''),
                added_at=datetime.utcnow()
            )
            
            db.session.add(new_track)
            db.session.commit()
            
            return new_track
    
    except Exception as e:
        logger.error(f"Error saving track to database: {str(e)}")
        return None

def update_track_play_count(youtube_id):
    """Update play count and last played time for a track."""
    try:
        from app import db
        from models import MusicTrack
        
        with db.app.app_context():
            track = MusicTrack.query.filter_by(youtube_id=youtube_id).first()
            
            if track:
                track.play_count += 1
                track.last_played = datetime.utcnow()
                db.session.commit()
    
    except Exception as e:
        logger.error(f"Error updating track play count: {str(e)}")

def setup_music_handlers(application):
    """Set up handlers for music-related commands."""
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("skip", skip_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("current", current_command))
    application.add_handler(CommandHandler("search", search_command))
    
    # Add callback query handler for inline keyboard buttons
    application.add_handler(CallbackQueryHandler(button_callback))

from app import db
from flask_login import UserMixin
from datetime import datetime
import json

class User(UserMixin, db.Model):
    """User model representing bot administrators"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

class TelegramUser(db.Model):
    """Model for tracking Telegram users who interact with the bot"""
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(64), unique=True, nullable=False)
    username = db.Column(db.String(64))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.String(256))
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    interaction_count = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'telegram_id': self.telegram_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_banned': self.is_banned,
            'ban_reason': self.ban_reason,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'interaction_count': self.interaction_count
        }

class TelegramChat(db.Model):
    """Model for tracking Telegram chats where the bot is active"""
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(64), unique=True, nullable=False)
    chat_type = db.Column(db.String(20))  # group, supergroup, private, channel
    title = db.Column(db.String(128))
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.String(256))
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'chat_type': self.chat_type,
            'title': self.title,
            'is_banned': self.is_banned,
            'ban_reason': self.ban_reason,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None
        }

class MusicTrack(db.Model):
    """Model for storing information about music tracks played by the bot"""
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(256), nullable=False)
    duration = db.Column(db.Integer)  # Duration in seconds
    thumbnail_url = db.Column(db.String(256))
    play_count = db.Column(db.Integer, default=0)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_played = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'youtube_id': self.youtube_id,
            'title': self.title,
            'duration': self.duration,
            'thumbnail_url': self.thumbnail_url,
            'play_count': self.play_count,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'last_played': self.last_played.isoformat() if self.last_played else None
        }

class PlaybackHistory(db.Model):
    """Model for tracking music playback history"""
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey('music_track.id'), nullable=False)
    chat_id = db.Column(db.String(64), nullable=False)
    requested_by = db.Column(db.String(64))
    played_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    
    track = db.relationship('MusicTrack', backref='playback_history')

class BanRecord(db.Model):
    """Model for tracking user bans in chats"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=False)
    chat_id = db.Column(db.String(64), nullable=False)
    banned_by = db.Column(db.String(64), nullable=False)
    banned_at = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.String(256))
    unbanned_by = db.Column(db.String(64))
    unbanned_at = db.Column(db.DateTime)
    is_kick = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'banned_by': self.banned_by,
            'banned_at': self.banned_at.isoformat() if self.banned_at else None,
            'reason': self.reason,
            'unbanned_by': self.unbanned_by,
            'unbanned_at': self.unbanned_at.isoformat() if self.unbanned_at else None,
            'is_kick': self.is_kick
        }

class MuteRecord(db.Model):
    """Model for tracking user mutes in chats"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=False)
    chat_id = db.Column(db.String(64), nullable=False)
    muted_by = db.Column(db.String(64), nullable=False)
    muted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.String(256))
    unmuted_by = db.Column(db.String(64))
    unmuted_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'muted_by': self.muted_by,
            'muted_at': self.muted_at.isoformat() if self.muted_at else None,
            'reason': self.reason,
            'unmuted_by': self.unmuted_by,
            'unmuted_at': self.unmuted_at.isoformat() if self.unmuted_at else None
        }

class GlobalBan(db.Model):
    """Model for tracking globally banned users"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=False)
    banned_by = db.Column(db.String(64), nullable=False)
    banned_at = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.String(256))
    unbanned_by = db.Column(db.String(64))
    unbanned_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'banned_by': self.banned_by,
            'banned_at': self.banned_at.isoformat() if self.banned_at else None,
            'reason': self.reason,
            'unbanned_by': self.unbanned_by,
            'unbanned_at': self.unbanned_at.isoformat() if self.unbanned_at else None
        }

    """Model for tracking music playback history"""
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey('music_track.id'), nullable=False)
    chat_id = db.Column(db.String(64), nullable=False)
    requested_by = db.Column(db.String(64))
    played_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    
    track = db.relationship('MusicTrack', backref='playback_history')

class ConversationLog(db.Model):
    """Model for logging AI conversations with the bot"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=False)
    chat_id = db.Column(db.String(64), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    tokens_used = db.Column(db.Integer)

class Setting(db.Model):
    """Model for storing bot configuration settings"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(256))
    
    @property
    def value_parsed(self):
        """Parse the setting value based on its content"""
        try:
            return json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return self.value

class SudoUser(db.Model):
    """Model for storing sudo users who have elevated permissions"""
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(64), unique=True, nullable=False)
    added_by = db.Column(db.String(64))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    removed_by = db.Column(db.String(64))
    removed_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'telegram_id': self.telegram_id,
            'added_by': self.added_by,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'is_active': self.is_active,
            'removed_by': self.removed_by,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None
        }

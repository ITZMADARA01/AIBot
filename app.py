import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from bot.slayer_bot import initialize_bot, get_bot_status

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Initialize SQLAlchemy
db = SQLAlchemy(model_class=Base)

# MongoDB connection (optional)
mongo_client = None
mongo_db = None

# Check if SKIP_MONGODB environment variable is set
if os.environ.get('SKIP_MONGODB') == '1':
    logger.info("SKIP_MONGODB=1 is set, skipping MongoDB connection")
    mongo_client = None
    mongo_db = None
else:
    # Get MongoDB URI from environment variables
    mongo_uri = os.environ.get("MONGO_DB_URI")
    
    if not mongo_uri:
        logger.warning("MONGO_DB_URI not found in environment variables. MongoDB features will be disabled.")
        mongo_client = None
        mongo_db = None
    else:
        try:
            from pymongo import MongoClient
            import re
            
            logger.info("Attempting MongoDB connection...")
            
            # Extract database name from URI using a more flexible pattern
            # Pattern matches mongodb://user:pass@host:port/dbname?options or mongodb+srv://user:pass@host/dbname?options
            uri_pattern = r'mongodb(?:\+srv)?:\/\/[^\/]+(?:\/([^\?]+))?'
            db_name_match = re.search(uri_pattern, mongo_uri)
            
            # Default database name is 'admin' if not specified in URI
            db_name = "admin"
            if db_name_match and db_name_match.group(1):
                db_name = db_name_match.group(1)
            
            logger.info(f"Connecting to MongoDB database: {db_name}")
            
            # Set a shorter timeout to avoid hanging
            mongodb_timeout = int(os.environ.get('MONGODB_TIMEOUT', '5000'))
            logger.info(f"Using MongoDB timeout: {mongodb_timeout}ms")
            
            mongo_client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=mongodb_timeout,
                connectTimeoutMS=mongodb_timeout,
                socketTimeoutMS=mongodb_timeout,
                appname="SlayerBot"
            )
            
            # Check if connection is successful with ping
            mongo_client.admin.command('ping')
            
            # Get the database
            mongo_db = mongo_client[db_name]
            logger.info(f"MongoDB connected successfully: {db_name}")
        except Exception as e:
            logger.error(f"MongoDB connection error: {str(e)}")
            logger.warning("Continuing without MongoDB support. Set SKIP_MONGODB=1 to disable this warning.")
            mongo_client = None
            mongo_db = None

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# Verify critical environment variables
if not os.environ.get("TELEGRAM_BOT_TOKEN"):
    logger.warning("TELEGRAM_BOT_TOKEN is not set in environment variables. Bot will run in demo mode only.")
    
if not os.environ.get("OPENAI_API_KEY"):
    logger.warning("OPENAI_API_KEY is not set in environment variables. AI features will be disabled.")

# Add template context processor for datetime
@app.context_processor
def inject_now():
    return {'now': datetime.now}

# Configure the database
# Use PostgreSQL database URL if available, otherwise fall back to SQLite
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    # Heroku-style URL correction for SQLAlchemy 1.4+
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///slayer_bot.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Log the database connection for debugging
logger.info(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")

# Initialize the database
db.init_app(app)

# Import routes after initializing db to avoid circular imports
with app.app_context():
    import models
    db.create_all()

    # Initialize the Telegram bot
    initialize_bot()

@app.route('/')
def index():
    """Homepage route"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard route to show bot status and activity"""
    status = get_bot_status()
    return render_template('dashboard.html', status=status)

@app.route('/settings')
def settings():
    """Settings page for bot configuration"""
    from models import Setting
    settings = Setting.query.all()
    return render_template('settings.html', settings=settings)

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """API endpoint to update bot settings"""
    from models import Setting
    data = request.json
    
    for key, value in data.items():
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            db.session.add(setting)
    
    db.session.commit()
    flash('Settings updated successfully', 'success')
    return jsonify({"status": "success"})

@app.route('/api/bot/status')
def bot_status():
    """API endpoint to get bot status"""
    status = get_bot_status()
    return jsonify(status)

@app.route('/api/bot/restart', methods=['POST'])
def restart_bot():
    """API endpoint to restart the bot"""
    try:
        initialize_bot(restart=True)
        return jsonify({"status": "success", "message": "Bot restarted successfully"})
    except Exception as e:
        logger.error(f"Failed to restart bot: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/db/status')
def db_status():
    """API endpoint to check database connectivity"""
    response_data = {"status": "error"}
    
    try:
        # Check SQL database connection
        from sqlalchemy import text
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                # Get the database info
                if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
                    db_info = conn.execute(text("SELECT version()")).fetchone()[0]
                    db_type = "PostgreSQL"
                else:
                    db_info = "SQLite"
                    db_type = "SQLite"
                
                # Count tables in the database
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                table_count = len(inspector.get_table_names())
                
                response_data = {
                    "status": "connected", 
                    "database": db_type,
                    "info": db_info,
                    "tables": table_count
                }
                
                # Add MongoDB status if configured
                if mongo_db:
                    try:
                        # Ping MongoDB to verify connection
                        mongo_client.admin.command('ping')
                        
                        # Get MongoDB server info
                        server_info = mongo_client.server_info()
                        mongo_version = server_info.get('version', 'Unknown')
                        
                        # Get collection count
                        collection_count = len(mongo_db.list_collection_names())
                        
                        response_data["mongodb_status"] = "connected"
                        response_data["mongodb_info"] = f"MongoDB {mongo_version}"
                        response_data["mongodb_database"] = mongo_db.name
                        response_data["mongodb_collections"] = collection_count
                    except Exception as mongo_error:
                        logger.error(f"MongoDB status check error: {str(mongo_error)}")
                        response_data["mongodb_status"] = "error"
                        response_data["mongodb_error"] = str(mongo_error)
                else:
                    response_data["mongodb_status"] = "not_configured"
                
                return jsonify(response_data)
            else:
                return jsonify({"status": "error", "message": "Database query returned unexpected result"})
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    logger.error(f"Server error: {str(e)}")
    return render_template('500.html'), 500

@app.route('/recommendations')
def recommendations():
    """Song recommendations page with carousel"""
    return render_template('recommendations.html')

@app.route('/deployment')
def deployment():
    """Deployment guide page"""
    return render_template('deployment.html')

@app.route('/api/recommendations')
def get_recommendations():
    """API endpoint to get song recommendations"""
    try:
        # In a real implementation, this would retrieve actual recommendations
        # based on user history, preferences, or external APIs
        recommendations = [
            {
                "id": "1",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
                "thumbnail": "https://i.scdn.co/image/ab67616d0000b273e8b066f70c206551210d902b",
                "year": "1975",
                "genre": "Rock"
            },
            {
                "id": "2",
                "title": "Hotel California",
                "artist": "Eagles",
                "album": "Hotel California",
                "thumbnail": "https://i.scdn.co/image/ab67616d0000b273a9f494126e8f466f8e0d1d1f",
                "year": "1976",
                "genre": "Rock"
            },
            {
                "id": "3",
                "title": "Sweet Child O' Mine",
                "artist": "Guns N' Roses",
                "album": "Appetite for Destruction",
                "thumbnail": "https://i.scdn.co/image/ab67616d0000b273bdba586f726b84a5451d0789",
                "year": "1987",
                "genre": "Hard Rock"
            },
            {
                "id": "4",
                "title": "Billie Jean",
                "artist": "Michael Jackson",
                "album": "Thriller",
                "thumbnail": "https://i.scdn.co/image/ab67616d0000b273de437d960dda1ac0a3586d97",
                "year": "1982",
                "genre": "Pop"
            },
            {
                "id": "5",
                "title": "Smells Like Teen Spirit",
                "artist": "Nirvana",
                "album": "Nevermind",
                "thumbnail": "https://i.scdn.co/image/ab67616d0000b273fbc71c99f9c1296c56dd8409",
                "year": "1991",
                "genre": "Grunge"
            },
            {
                "id": "6",
                "title": "Stairway to Heaven",
                "artist": "Led Zeppelin",
                "album": "Led Zeppelin IV",
                "thumbnail": "https://i.scdn.co/image/ab67616d0000b273cd9d8bc9ef04014b6e90e389",
                "year": "1971",
                "genre": "Rock"
            }
        ]
        return jsonify({"recommendations": recommendations})
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Cấu hình bot"""
    
    # Discord
    DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    PREFIX = os.getenv('BOT_PREFIX', '!')
    
    # API Keys
    RIOT_API_KEY = os.getenv('RIOT_API_KEY', '')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    
    # Database
    DB_FILE = os.getenv('DB_FILE', 'tft_tracker.db')
    BACKUP_DIR = os.getenv('BACKUP_DIR', 'backups')
    
    # Settings
    AUTO_CHECK_INTERVAL = int(os.getenv('AUTO_CHECK_INTERVAL', '5'))  # minutes
    VERIFICATION_TIMEOUT = int(os.getenv('VERIFICATION_TIMEOUT', '30'))  # minutes
    
    # Regions
    SUPPORTED_REGIONS = {
        'vn': 'Vietnam',
        'na': 'North America',
        'euw': 'Europe West',
        'eune': 'Europe Nordic & East',
        'kr': 'Korea',
        'jp': 'Japan',
        'br': 'Brazil',
        'lan': 'Latin America North',
        'las': 'Latin America South',
        'oce': 'Oceania',
        'ru': 'Russia',
        'tr': 'Turkey'
    }
    
    @classmethod
    def validate(cls):
        """Kiểm tra config"""
        errors = []
        
        if not cls.DISCORD_TOKEN:
            errors.append("DISCORD_TOKEN is required")
        
        if not cls.RIOT_API_KEY:
            print("⚠️ RIOT_API_KEY không có, một số tính năng sẽ bị giới hạn")
        
        if not cls.GEMINI_API_KEY:
            print("⚠️ GEMINI_API_KEY không có, phân tích AI sẽ không khả dụng")
        
        return errors

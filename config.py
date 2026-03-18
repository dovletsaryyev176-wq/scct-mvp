import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-key-for-dev')
    PERMANENT_SESSION_LIFETIME = int(os.getenv('PERMANENT_SESSION_LIFETIME', 604800))
    SESSION_REFRESH_EACH_REQUEST = os.getenv('SESSION_REFRESH_EACH_REQUEST', 'True') == 'True'
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # DB credentials
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '19121987')
    DB_NAME = os.getenv('DB_NAME', 'sarwan')
    DB_MAXCONNECTIONS = int(os.getenv('DB_MAXCONNECTIONS', 20))
import os

class Config:
    DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cambiar-en-produccion')
    
    # Absolute path for the database based on the app's root path
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'database.db'))

import os

class Config:
    SECRET_KEY = '9f1c8a07ae9cde11abcdef0123456789abcdef0011223344'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///library.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'covers')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
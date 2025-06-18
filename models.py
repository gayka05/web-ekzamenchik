from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()



class Role(db.Model):
    __tablename__ = 'roles'  
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    users = db.relationship('User', backref='role', lazy=True)

class User(db.Model, UserMixin):
    __tablename__ = 'users' 
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(50), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    reviews = db.relationship('Review', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Cover(db.Model):
    __tablename__ = 'covers' 
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    mime_type = db.Column(db.String(50), nullable=False)
    md5_hash = db.Column(db.String(32), nullable=False)
    book = db.relationship('Book', back_populates='cover', uselist=False)

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    publisher = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    pages = db.Column(db.Integer, nullable=False)
    cover_id = db.Column(db.Integer, db.ForeignKey('covers.id', ondelete='CASCADE'), nullable=False, unique=True)  # Add ondelete
    cover = db.relationship('Cover', back_populates='book', uselist=False, cascade="all, delete-orphan", single_parent=True) # Add single_parent
    genres = db.relationship('Genre', secondary='book_genres', back_populates='books')
    reviews = db.relationship('Review', backref='book', lazy=True, cascade="all, delete-orphan")

class BookView(db.Model):
    __tablename__ = 'book_views'  

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    session_id = db.Column(db.String(128), nullable=True)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    book = db.relationship('Book', backref='views')
    user = db.relationship('User', backref='book_views')

class Genre(db.Model):
    __tablename__ = 'genres' 
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    books = db.relationship('Book', secondary='book_genres', back_populates='genres')

book_genres = db.Table('book_genres',
    db.Column('book_id', db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genres.id', ondelete='CASCADE'), primary_key=True)
)

class Review(db.Model):
    __tablename__ = 'reviews'  
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())


from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import os
import hashlib
from models import db, User, Role, Book, Cover, Genre, Review, BookView
import bleach
from config import Config
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy import func
import uuid
from flask_migrate import Migrate

app = Flask(__name__)
app.config.from_object(Config)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

db.init_app(app)

migrate = Migrate(app, db)

with app.app_context():
    db.create_all()
    # Удаляем старых пользователей (кроме admin и moderator1, если нужно)
    User.query.filter(User.login.notin_(['admin', 'moderator1'])).delete()
    db.session.commit()

    existing_roles = {role.name for role in Role.query.all()}
    roles_to_add = [
        Role(name='admin', description='Администратор (полный доступ)'),
        Role(name='moderator', description='Модератор (редактирование книг и рецензий)'),
        Role(name='user', description='Пользователь (может оставлять рецензии)')
    ]
    new_roles = [role for role in roles_to_add if role.name not in existing_roles]
    if new_roles:
        db.session.add_all(new_roles)
        db.session.commit()  # Сохраняем роли, чтобы получить их id

    # Создаем администратора, если нет
    if not User.query.filter_by(login='admin').first():
        admin = User(
            login='admin',
            last_name='Admin',
            first_name='System',
            role_id=Role.query.filter_by(name='admin').first().id
        )
        admin.set_password('adminpassword')
        db.session.add(admin)

    # Создаем модератора, если нет
    if not User.query.filter_by(login='moderator1').first():
        moderator1 = User(
            login='moderator1',
            last_name='Moder',
            first_name='System',
            role_id=Role.query.filter_by(name='moderator').first().id
        )
        moderator1.set_password('moderpassword')
        db.session.add(moderator1)

    # Создаем трёх пользователей, если нет
    users_data = [
        {'login': 'user1', 'last_name': 'Manukyan', 'first_name': 'Gaya', 'password': 'userpass1'},
        {'login': 'user2', 'last_name': 'Davtyan', 'first_name': 'Avik', 'password': 'userpass2'},
        {'login': 'user3', 'last_name': 'Kirtanov', 'first_name': 'Maks', 'password': 'userpass3'}
    ]

    for udata in users_data:
        if not User.query.filter_by(login=udata['login']).first():
            user = User(
                login=udata['login'],
                last_name=udata['last_name'],
                first_name=udata['first_name'],
                role_id=Role.query.filter_by(name='user').first().id
            )
            user.set_password(udata['password'])
            db.session.add(user)

    db.session.commit()


    existing_genres = {genre.name for genre in Genre.query.all()}
    genres_to_add = [
        'Фантастика', 'Детектив', 'Роман', 'Поэзия', 'Научная литература',
        'Исторический роман', 'Приключения', 'Триллер', 'Фэнтези', 'Биография',
        'Психология', 'Эссе', 'Документальная литература', 'Юмор', 'Драма',
        'Мистика', 'Классическая литература', 'Публицистика', 'Комиксы', 'Детская литература'
    ]
    new_genres = [Genre(name=name) for name in genres_to_add if name not in existing_genres]
    if new_genres:
        db.session.add_all(new_genres)

    db.session.commit()

def role_required(*required_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Для выполнения данного действия необходимо пройти процедуру аутентификации', 'warning')
                return redirect(url_for('login'))

            if current_user.role.name not in required_roles:
                flash('У вас недостаточно прав для выполнения данного действия', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_cover_file(file_storage):
    filename = secure_filename(file_storage.filename)
    if '.' not in filename:
        raise ValueError('Файл обложки должен иметь расширение')
    ext = filename.rsplit('.', 1)[1].lower()

    if not allowed_file(filename):
        raise ValueError('Недопустимый формат файла обложки')

    file_bytes = file_storage.read()
    md5_hash = hashlib.md5(file_bytes).hexdigest()
    file_storage.seek(0)

    cover = Cover.query.filter_by(md5_hash=md5_hash).first()
    if cover:
        return cover

    cover = Cover(filename='', mime_type=file_storage.mimetype, md5_hash=md5_hash)
    db.session.add(cover)
    db.session.flush()

    cover.filename = f"{cover.id}.{ext}"

    covers_dir = os.path.join(app.static_folder, 'covers')
    os.makedirs(covers_dir, exist_ok=True)
    save_path = os.path.join(covers_dir, cover.filename)

    try:
        file_storage.save(save_path)
    except Exception as e:
        db.session.rollback()
        raise IOError(f"Ошибка при сохранении файла обложки: {e}")
    return cover

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    # Генерация visitor_id для неаутентифицированных пользователей (если нужно)
    if not current_user.is_authenticated:
        if 'visitor_id' not in session:
            session['visitor_id'] = str(uuid.uuid4())

    page = request.args.get('page', 1, type=int)

    # Получаем параметры поиска из query string
    title = request.args.get('title', '', type=str).strip()
    author = request.args.get('author', '', type=str).strip()
    genre_ids = request.args.getlist('genre', type=int)
    year_list = request.args.getlist('year', type=int)
    pages_from = request.args.get('pages_from', type=int)
    pages_to = request.args.get('pages_to', type=int)

    # Начинаем запрос с фильтрацией
    query = Book.query

    if title:
        query = query.filter(Book.title.ilike(f'%{title}%'))
    if author:
        query = query.filter(Book.author.ilike(f'%{author}%'))
    if genre_ids:
        query = query.join(Book.genres).filter(Genre.id.in_(genre_ids))
    if year_list:
        query = query.filter(Book.year.in_(year_list))
    if pages_from is not None:
        query = query.filter(Book.pages >= pages_from)
    if pages_to is not None:
        query = query.filter(Book.pages <= pages_to)

    # Сортировка по году по убыванию
    query = query.order_by(Book.year.desc())

    # Пагинация
    books = query.paginate(page=page, per_page=10, error_out=False)

    # Вычисляем количество отзывов и средний рейтинг для каждой книги
    for book in books.items:
        book.review_count = len(book.reviews)
        if book.review_count > 0:
            book.avg_rating = sum(review.rating for review in book.reviews) / book.review_count
        else:
            book.avg_rating = 0

    # Получаем все жанры и годы для формы (нужно для заполнения мультиселектов)
    genres = Genre.query.order_by(Genre.name).all()
    years = [y[0] for y in db.session.query(Book.year).distinct().order_by(Book.year).all()]

    # Передаём параметры поиска для заполнения формы и пагинации
    search_params = {
        'title': title,
        'author': author,
        'genre_ids': genre_ids,
        'year_list': year_list,
        'pages_from': pages_from,
        'pages_to': pages_to
    }

    return render_template('index.html',
                           books=books,
                           genres=genres,
                           years=years,
                           search_params=search_params)
@app.route('/books/<int:book_id>')
def view_book(book_id):
    book = Book.query.get_or_404(book_id)
    reviews = Review.query.filter_by(book_id=book.id, status='approved').order_by(Review.created_at.desc()).all()
    user_review = None
    can_write_review = False

    if current_user.is_authenticated:
        user_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
        can_write_review = user_review is None
    else:
        can_write_review = False

    return render_template('view_book.html', book=book, reviews=reviews, user_review=user_review, can_write_review=can_write_review)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        remember = True if request.form.get('remember') else False
        user = User.query.filter_by(login=login).first()

        if not user or not user.check_password(password):
            flash('Невозможно аутентифицироваться с указанными логином и паролем', 'error')
            return redirect(url_for('login'))

        login_user(user, remember=remember)
        next_page = request.args.get('next')
        return redirect(next_page or url_for('index'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/books/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def new_book():
    genres = Genre.query.all()
    now = datetime.now()

    if request.method == 'POST':
        try:
            title = request.form['title'].strip()
            author = request.form['author'].strip()
            year = int(request.form['year'])
            publisher = request.form['publisher'].strip()
            pages = int(request.form['pages'])
            description_raw = request.form['description']
            genres_ids = request.form.getlist('genres[]')

            allowed_tags = bleach.sanitizer.ALLOWED_TAGS.union({'p', 'br', 'ul', 'li', 'strong', 'em', 'a'})
            description = bleach.clean(description_raw, tags=allowed_tags, strip=True)

            if 'cover' not in request.files:
                flash('Файл обложки обязателен', 'danger')
                raise ValueError('Файл обложки обязателен')
            cover_file = request.files['cover']
            if cover_file.filename == '':
                flash('Файл обложки обязателен', 'danger')
                raise ValueError('Файл обложки обязателен')

            cover = save_cover_file(cover_file)
            db.session.add(cover)
            db.session.flush()

            book = Book(title=title, author=author, year=year, publisher=publisher, pages=pages,
                        description=description, cover=cover)

            db.session.add(book)

            with db.session.no_autoflush:
                selected_genres = Genre.query.filter(Genre.id.in_(genres_ids)).all()
                book.genres = selected_genres

            db.session.commit()
            flash('Книга успешно добавлена', 'success')
            return redirect(url_for('view_book', book_id=book.id))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Ошибка при добавлении книги: {e}", exc_info=True)
            flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.', 'danger')
            return render_template('book_form.html', book=None, genres=genres, now=now)

    return render_template('book_form.html', book=None, genres=genres, now=now)

@app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'moderator')
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    genres = Genre.query.all()
    now = datetime.now()

    if request.method == 'POST':
        try:
            book.title = request.form['title'].strip()
            book.author = request.form['author'].strip()
            book.year = int(request.form['year'])
            book.publisher = request.form['publisher'].strip()
            book.pages = int(request.form['pages'])
            description_raw = request.form['description']
            book.description = bleach.clean(
                description_raw,
                tags=bleach.sanitizer.ALLOWED_TAGS.union({'p', 'br', 'ul', 'li', 'strong', 'em', 'a'}),
                strip=True
            )
            # Use the same name as in the new_book route
            genres_ids = request.form.getlist('genres[]')
            selected_genres = Genre.query.filter(Genre.id.in_(genres_ids)).all()
            book.genres = selected_genres

            db.session.commit()
            flash('Книга успешно обновлена', 'success')
            return redirect(url_for('view_book', book_id=book.id))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Ошибка при редактировании книги: {e}")
            flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.', 'danger')
            return render_template('book_form.html', book=book, genres=genres, now=now)

    return render_template('book_form.html', book=book, genres=genres, now=now)

@app.route('/books/<int:book_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)

    # Затем удаляем обложку (если она существует)
    cover = book.cover  # Получаем обложку после удаления книги из сессии
    cover_path = os.path.join(app.static_folder, 'covers', cover.filename)
    if os.path.exists(cover_path):
        os.remove(cover_path)
        app.logger.debug(f"Файл обложки: {cover_path} успешно удален.")

    db.session.delete(book)
    app.logger.debug(f"Обложка с ID: {cover.id} удалена из сессии.")
    db.session.commit()
    app.logger.debug("Транзакция успешно зафиксирована.")

    flash(f'Книга "{book.title}" успешно удалена.', 'success')
    return redirect(url_for('index'))

@app.route('/books/<int:book_id>/review/new', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    book = Book.query.get_or_404(book_id)

    if current_user.role.name not in ('user', 'moderator', 'admin'):
        flash('У вас недостаточно прав для добавления рецензии', 'danger')
        return redirect(url_for('view_book', book_id=book_id))

    existing_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    if existing_review:
        flash('Вы уже оставили рецензию на эту книгу', 'warning')
        return redirect(url_for('view_book', book_id=book_id))

    if request.method == 'POST':
        try:
            rating = int(request.form['rating'])
            text_raw = request.form['text']
            allowed_tags = bleach.sanitizer.ALLOWED_TAGS.union({'p', 'br', 'ul', 'ol', 'li', 'strong', 'em', 'a', 'blockquote'})
            text_clean = bleach.clean(text_raw, tags=allowed_tags, strip=True)
            review = Review(
                book_id=book_id,
                user_id=current_user.id,
                rating=rating,
                text=text_clean,
                status='pending'
            )
            db.session.add(review)
            db.session.commit()

            flash('Рецензия успешно добавлена', 'success')
            return redirect(url_for('view_book', book_id=book_id))
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при сохранении рецензии. Проверьте корректность введённых данных.', 'danger')

    return render_template('add_review.html', book=book)

@app.route('/reviews/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)

    if review.user_id != current_user.id and current_user.role.name not in ['admin', 'moderator']:
        flash('У вас недостаточно прав для выполнения данного действия', 'error')
        return redirect(url_for('view_book', book_id=review.book_id))

    try:
        book_id = review.book_id
        db.session.delete(review)
        db.session.commit()
        flash('Рецензия успешно удалена', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Ошибка при удалении рецензии: {str(e)}')
        flash('При удалении рецензии возникла ошибка', 'error')

    return redirect(url_for('view_book', book_id=book_id))

@app.route('/reviews/moder')
@login_required
@role_required('admin', 'moderator')
def review_moderation():
    reviews = Review.query.filter_by(status='pending').order_by(Review.created_at.desc()).all()
    return render_template('review_moder.html', reviews=reviews)

@app.route('/reviews/<int:review_id>/approve', methods=['POST'])
@login_required
@role_required('admin', 'moderator')
def approve_review(review_id):
    review = Review.query.get_or_404(review_id)
    review.status = 'approved'
    db.session.commit()
    flash('Рецензия одобрена', 'success')
    return redirect(url_for('review_moderation'))

@app.route('/reviews/<int:review_id>/reject', methods=['POST'])
@login_required
@role_required('admin', 'moderator')
def reject_review(review_id):
    review = Review.query.get_or_404(review_id)
    review.status = 'rejected'
    db.session.commit()
    flash('Рецензия отклонена', 'warning')
    return redirect(url_for('review_moderation'))



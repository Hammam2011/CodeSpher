import sqlite3
import os
from flask import Flask, request, redirect, url_for, render_template, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
CORS(app)

def init_db():
    conn = sqlite3.connect('database/database.db')
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')

    try:
        cursor.execute('ALTER TABLE users ADD COLUMN birthdate TEXT;')
        cursor.execute('ALTER TABLE users ADD COLUMN phone TEXT;')
        cursor.execute('ALTER TABLE users ADD COLUMN country TEXT;')
        cursor.execute('ALTER TABLE users ADD COLUMN about TEXT;')
    except sqlite3.OperationalError:
        pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        content TEXT,
        media TEXT,
        type TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS user_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        label TEXT,
        url TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        search_query TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
    )''')

    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('database/database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user is None:
            flash('اسم المستخدم غير موجود.')
        elif check_password_hash(user['password'], password):
            session['username'] = username
            return redirect(session.pop('previous_url', url_for('home')))
        else:
            flash('كلمة المرور غير صحيحة.')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()

        try:
            hashed_password = generate_password_hash(password)
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            flash('تم تسجيل الحساب بنجاح.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('اسم المستخدم موجود بالفعل.')
        finally:
            conn.close()

    return render_template('signup.html')

@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    conn = get_db_connection()

    user = conn.execute('SELECT profile_image FROM users WHERE username = ?', (username,)).fetchone()
    profile_image = user['profile_image'] if user else None

    # تعديل استعلام posts لجلب الحقول المفقودة
    posts = conn.execute('''
        SELECT posts.*, users.profile_image, users.about, users.phone, users.country, users.birthdate 
        FROM posts 
        JOIN users ON posts.username = users.username 
        ORDER BY posts.timestamp DESC
    ''').fetchall()

    comments = conn.execute('''
        SELECT comments.*, users.profile_image 
        FROM comments 
        JOIN users ON comments.username = users.username 
        ORDER BY comments.timestamp DESC
    ''').fetchall()

    conn.close()

    return render_template('home.html', posts=posts, comments=comments, username=username, profile_image=profile_image)

@app.route('/create_post', methods=['GET', 'POST'])
def create_post():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = session['username']
        content = request.form['post_content']
        media = request.files.get('media')
        media_filename = ''

        if media:
            media_filename = media.filename
            media.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))

        post_type = 'text'
        if media_filename:
            if media_filename.endswith(('.png', '.jpg', '.jpeg', '.svg')):
                post_type = 'image'
            elif media_filename.endswith(('.mp4', '.mov')):
                post_type = 'video'

        conn = get_db_connection()
        conn.execute('INSERT INTO posts (username, content, media, type) VALUES (?, ?, ?, ?)',
                     (username, content, media_filename, post_type))
        conn.commit()
        conn.close()

        return redirect(session.pop('previous_url', url_for('home')))

    return render_template('create_post.html')

@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()

    if request.method == 'POST':
        content = request.form.get('post_content', None)
        media = request.files.get('media', None)

        if content is None:
            return redirect(url_for('edit_post', post_id=post_id))

        media_filename = post['media']

        if media:
            media_filename = media.filename
            media.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))

        post_type = 'text'
        if media_filename:
            if media_filename.endswith(('.png', '.jpg', '.jpeg', '.svg')):
                post_type = 'image'
            elif media_filename.endswith(('.mp4', '.mov')):
                post_type = 'video'

        conn.execute('UPDATE posts SET content = ?, media = ?, type = ? WHERE id = ?',
                     (content, media_filename, post_type, post_id))
        conn.commit()
        conn.close()
        return redirect(session.pop('previous_url', url_for('home')))

    conn.close()
    return render_template('edit_post.html', post=post)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    return redirect(session.pop('previous_url', url_for('home')))

@app.route('/add_comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    content = request.form['comment_content']
    username = session['username']
    
    if not content.strip():
        return redirect(session.pop('previous_url', url_for('home')))

    conn = get_db_connection()
    conn.execute('INSERT INTO comments (post_id, username, content) VALUES (?, ?, ?)', (post_id, username, content))
    conn.commit()
    conn.close()

    return redirect(session.pop('previous_url', url_for('home')))

@app.route('/user/<username>', methods=['GET'])
def view_user(username):
    conn = get_db_connection()
    
    # جلب معلومات المستخدم
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    
    # جلب المنشورات
    posts = conn.execute('SELECT * FROM posts WHERE username = ?', (username,)).fetchall()
    
    # جلب روابط المستخدم
    user_links = conn.execute('SELECT * FROM user_links WHERE username = ?', (username,)).fetchall()

    conn.close()

    if user:
        return render_template('user.html', 
                               username=user['username'], 
                               profile_image=user['profile_image'],
                               phone=user['phone'], 
                               country=user['country'], 
                               birthdate=user['birthdate'], 
                               about=user['about'], 
                               posts=posts,
                               user_links=user_links)  # أضف الروابط هنا
    else:
        return render_template('user_not_found.html')

@app.route('/edit_comment/<int:comment_id>', methods=['GET', 'POST'])
def edit_comment(comment_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    comment = conn.execute('SELECT * FROM comments WHERE id = ?', (comment_id,)).fetchone()

    if request.method == 'POST':
        content = request.form['comment_content']
        conn.execute('UPDATE comments SET content = ? WHERE id = ?', (content, comment_id))
        conn.commit()
        conn.close()
        return redirect(session.pop('previous_url', url_for('home')))

    conn.close()
    return render_template('edit_comment.html', comment=comment)

@app.route('/post/<int:post_id>')
def view_post(post_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    conn = get_db_connection()

    user = conn.execute('SELECT profile_image FROM users WHERE username = ?', (username,)).fetchone()
    profile_image = user['profile_image'] if user else None
    
    # اسم المستخدم من الجلسة
    viewer_username = session['username']
    conn = get_db_connection()

    # جلب بيانات المنشور
    post = conn.execute(
        '''
        SELECT posts.*, users.profile_image, users.about, users.phone, users.country, users.birthdate 
        FROM posts 
        JOIN users ON posts.username = users.username 
        WHERE posts.id = ?
        ''',
        (post_id,)
    ).fetchone()

    # التحقق من وجود المنشور
    if post is None:
        conn.close()
        return "المنشور غير موجود", 404

    # جلب التعليقات الخاصة بالمنشور
    comments = conn.execute(
        '''
        SELECT comments.*, users.profile_image 
        FROM comments 
        JOIN users ON comments.username = users.username 
        WHERE post_id = ? 
        ORDER BY comments.timestamp ASC
        ''',
        (post_id,)
    ).fetchall()

    # جلب بيانات المستخدم الذي يشاهد المنشور
    viewer_info = conn.execute(
        '''
        SELECT username, profile_image, about, phone, country, birthdate 
        FROM users 
        WHERE username = ?
        ''',
        (viewer_username,)
    ).fetchone()

    conn.close()

    # عرض البيانات في القالب
    return render_template('view_post.html', post=post, comments=comments, viewer_info=viewer_info, profile_image=profile_image, username=username)

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    conn.commit()
    conn.close()
    return redirect(session.pop('previous_url', url_for('home')))

UPLOAD_FOLDER = 'static/profile_images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/profile', methods=['GET'])
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    
    # استرجاع الروابط المرتبطة بالمستخدم
    user_links = conn.execute('SELECT * FROM user_links WHERE username = ?', (username,)).fetchall()
    conn.close()

    if user:
        profile_image = user['profile_image']
        return render_template('profile.html', user=user, profile_image=profile_image, user_links=user_links) 
    else:
        return "المستخدم غير موجود", 404

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    conn = get_db_connection()
    
    # Get form data
    new_username = request.form['username']
    phone = request.form['phone']
    country = request.form['country']
    birthdate = request.form['birthdate']
    about = request.form['about']

    # Handle profile image upload
    profile_image = request.files.get('profile_image')
    profile_image_path = None
    
    if profile_image:
        filename = secure_filename(profile_image.filename)
        profile_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        profile_image.save(profile_image_path)
        profile_image_path = filename  # Save filename to store in the database

    try:
        # Update user information in the database
        if profile_image_path:
            conn.execute(
                '''UPDATE users SET username = ?, phone = ?, country = ?, birthdate = ?, about = ?, profile_image = ? WHERE username = ?''',
                (new_username, phone, country, birthdate, about, profile_image_path, username)
            )
        else:
            conn.execute(
                '''UPDATE users SET username = ?, phone = ?, country = ?, birthdate = ?, about = ? WHERE username = ?''',
                (new_username, phone, country, birthdate, about, username)
            )
        conn.commit()
        session['username'] = new_username  # Update session username if changed

    finally:
        conn.close()
    
    return redirect(url_for('profile'))

@app.route('/search_friends', methods=['GET'])
def search_friends():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    conn = get_db_connection()
    
    current_user = conn.execute('SELECT profile_image FROM users WHERE username = ?', (username,)).fetchone()
    profile_image = current_user['profile_image'] if current_user else None

    query = request.args.get('query')

    if query:
        friends = conn.execute('SELECT username, profile_image FROM users WHERE username LIKE ?', ('%' + query + '%',)).fetchall()

        # تحقق مما إذا كان الاستعلام موجودًا في تاريخ البحث
        existing_search = conn.execute('SELECT 1 FROM search_history WHERE username = ? AND search_query = ?', 
                                       (username, query)).fetchone()

        # إدخال الاستعلام في السجل فقط إذا لم يكن موجودًا مسبقًا
        if not existing_search:
            conn.execute('INSERT INTO search_history (username, search_query) VALUES (?, ?)', (username, query))
            conn.commit()
    else:
        friends = conn.execute('SELECT username, profile_image FROM users').fetchall()

    # الحصول على تاريخ البحث
    search_history = conn.execute('SELECT search_query FROM search_history WHERE username = ? ORDER BY timestamp DESC LIMIT 10', 
                                  (username,)).fetchall()

    conn.close()

    return render_template('search_friends.html', friends=friends, query=query, profile_image=profile_image, search_history=search_history)

@app.route('/delete_search', methods=['POST'])
def delete_search():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    search_query = request.args.get('search_query')

    conn = get_db_connection()

    conn.execute('DELETE FROM search_history WHERE username = ? AND search_query = ?', (username, search_query))
    conn.commit()

    conn.close()

    return redirect(url_for('search_friends'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)

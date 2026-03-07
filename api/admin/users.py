from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db
from werkzeug.security import generate_password_hash


@admin_bp.route('/users', methods=['GET'])
def get_users():
    role_param = request.args.get('role')
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            if role_param:
                cursor.execute("SELECT id, full_name, username, phone, role, is_active FROM users WHERE role=%s", (role_param,))
            else:
                cursor.execute("SELECT id, full_name, username, phone, role, is_active FROM users")
            users = cursor.fetchall()
        return jsonify(users), 200
    finally:
        conn.close()


@admin_bp.route('/users', methods=['POST'])
@roles_required('admin')
def add_user():
    data = request.get_json()
    required = ['full_name', 'phone', 'username', 'password', 'role']
    if not all(k in data for k in required):
        return jsonify({"error": "Заполните все поля"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT id FROM users WHERE username=%s OR phone=%s", (data['username'], data['phone']))
            if cursor.fetchone():
                return jsonify({"error": "Пользователь с таким логином или телефоном уже есть"}), 400

            hashed_pw = generate_password_hash(data['password'])
            cursor.execute(
                "INSERT INTO users (full_name, username, phone, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
                (data['full_name'], data['username'], data['phone'], hashed_pw, data['role'])
            )
            conn.commit()
            user_id = cursor.lastrowid

            # Если courier - создаем location
            if data['role'] == 'courier':
                cursor.execute(
                    "INSERT INTO locations (name, type, user_id) VALUES (%s, %s, %s)",
                    (data['full_name'], 'courier', user_id)
                )
                conn.commit()

            cursor.execute("SELECT id, full_name, username, phone, role, is_active FROM users WHERE id=%s", (user_id,))
            new_user = cursor.fetchone()
        return jsonify(new_user), 201
    finally:
        conn.close()


from flask import jsonify, request
from werkzeug.security import generate_password_hash
from . import admin_bp
from decorators import roles_required
from db import Db


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@roles_required('admin')
def update_user(user_id):
    data = request.get_json()
    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "SELECT id, username, role, full_name FROM users WHERE id=%s",
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({"error": "Пользователь не найден"}), 404

            new_username = data.get('username')
            if new_username and new_username != user['username']:
                cursor.execute(
                    "SELECT id FROM users WHERE username=%s AND id!=%s",
                    (new_username, user_id)
                )
                if cursor.fetchone():
                    return jsonify({"error": "Это имя пользователя уже занято"}), 400

            fields = []
            values = []

            for field in ['full_name', 'username', 'phone']:
                if field in data:
                    fields.append(f"{field}=%s")
                    values.append(data[field])

            if 'role' in data:
                if user['role'] == 'courier' and data['role'] != 'courier':
                    return jsonify({"error": "Нельзя менять роль пользователя courier"}), 400

                fields.append("role=%s")
                values.append(data['role'])

            if 'password' in data:
                fields.append("password_hash=%s")
                values.append(generate_password_hash(data['password']))

            if fields:
                sql = f"UPDATE users SET {', '.join(fields)} WHERE id=%s"
                values.append(user_id)
                cursor.execute(sql, tuple(values))

            #  Если это courier и изменился full_name — обновляем locations
            if user['role'] == 'courier' and 'full_name' in data:
                cursor.execute(
                    """
                    UPDATE locations 
                    SET name=%s 
                    WHERE user_id=%s AND type='courier'
                    """,
                    (data['full_name'], user_id)
                )

            conn.commit()

            cursor.execute(
                "SELECT id, full_name, username, phone, role, is_active FROM users WHERE id=%s",
                (user_id,)
            )
            updated_user = cursor.fetchone()

        return jsonify(updated_user), 200

    finally:
        conn.close()


@admin_bp.route('/users/<int:user_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_user(user_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (user_id,))
            conn.commit()
            cursor.execute("SELECT id, full_name, username, phone, role, is_active FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
        return jsonify({"message": f"Пользователь {user['username']} заблокирован", "user": user}), 200
    finally:
        conn.close()


@admin_bp.route('/users/<int:user_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_user(user_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET is_active=TRUE WHERE id=%s", (user_id,))
            conn.commit()
            cursor.execute("SELECT id, full_name, username, phone, role, is_active FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
        return jsonify({"message": f"Пользователь {user['username']} разблокирован", "user": user}), 200
    finally:
        conn.close()
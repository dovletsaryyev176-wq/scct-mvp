from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import check_password_hash
from db import Db
import jwt

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Введите логин и пароль"}), 400

    connection = Db.get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM users WHERE username = %s AND is_active = 1",
                (username,)
            )
            user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session.permanent = True
            session['user_id'] = user['id']
            session['role'] = user['role']

            token = jwt.encode(
                {
                    'user_id': user['id'],
                    'role': user['role']
                },
                current_app.config['SECRET_KEY'],
                algorithm="HS256"
            )

            return jsonify({
                "status": "success",
                "token": token,
                "user": {
                    "id": user['id'],
                    "username": user['username'],
                    "role": user['role'],
                    "full_name": user['full_name']
                }
            }), 200

        return jsonify({"error": "Неверный логин или пароль"}), 401

    finally:
        connection.close()


@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')
    role = session.get('role')

    if not user_id or not role:
        return jsonify({"authenticated": False}), 401

    connection = Db.get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, role, full_name FROM users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()

        if not user:
            session.clear()
            return jsonify({"authenticated": False}), 401

        return jsonify({
            "authenticated": True,
            "user": {
                "id": user['id'],
                "username": user['username'],
                "role": user['role'],
                "full_name": user['full_name']
            }
        }), 200

    finally:
        connection.close()


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    response = jsonify({
        "status": "success",
        "message": "Вышли из системы"
    })
    response.set_cookie('session', '', expires=0)
    return response, 200
from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db


@admin_bp.route('/cities', methods=['GET'])
def get_cities():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, is_active FROM cities")
            cities = cursor.fetchall()
        return jsonify(cities), 200
    finally:
        conn.close()


@admin_bp.route('/cities', methods=['POST'])
@roles_required('admin')
def add_city():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({"error": "Укажите название"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM cities WHERE name=%s", (name,))
            if cursor.fetchone():
                return jsonify({"error": "Город с таким названием уже существует"}), 400

            cursor.execute("INSERT INTO cities (name) VALUES (%s)", (name,))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM cities WHERE id=%s", (cursor.lastrowid,))
            new_city = cursor.fetchone() 
        return jsonify(new_city), 201
    finally:
        conn.close()


@admin_bp.route('/cities/<int:city_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_city(city_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE cities SET is_active=0 WHERE id=%s", (city_id,))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM cities WHERE id=%s", (city_id,))
            city = cursor.fetchone()
        if not city:
            return jsonify({"error": "Город не найден"}), 404
        return jsonify({"message": "Город заблокирован", "city": city}), 200
    finally:
        conn.close()


@admin_bp.route('/cities/<int:city_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_city(city_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE cities SET is_active=1 WHERE id=%s", (city_id,))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM cities WHERE id=%s", (city_id,))
            city = cursor.fetchone()
        if not city:
            return jsonify({"error": "Город не найден"}), 404
        return jsonify({
            "message": f"Город '{city['name']}' успешно разблокирован",
            "city": city
        }), 200
    finally:
        conn.close()


@admin_bp.route('/cities/<int:city_id>', methods=['PUT'])
@roles_required('admin')
def update_city(city_id):
    data = request.get_json()
    new_name = data.get('name')
    if not new_name:
        return jsonify({"error": "Название не может быть пустым"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM cities WHERE name=%s AND id!=%s", (new_name, city_id))
            if cursor.fetchone():
                return jsonify({"error": "Город с таким названием уже существует"}), 400

            cursor.execute("UPDATE cities SET name=%s WHERE id=%s", (new_name, city_id))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM cities WHERE id=%s", (city_id,))
            city = cursor.fetchone()
        if not city:
            return jsonify({"error": "Город не найден"}), 404
        return jsonify({"message": "Город обновлен", "city": city}), 200
    finally:
        conn.close()


@admin_bp.route('/cities/full-list', methods=['GET'])
def get_cities_full_list():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    c.id,
                    c.name,
                    c.is_active,
                    COUNT(DISTINCT d.id) AS districts_count,
                    COUNT(DISTINCT cd.courier_id) AS couriers_count
                FROM cities c
                LEFT JOIN districts d ON d.city_id = c.id
                LEFT JOIN courier_districts cd ON cd.district_id = d.id
                GROUP BY c.id
            """)
            result = cursor.fetchall() 
        return jsonify(result), 200
    finally:
        conn.close()

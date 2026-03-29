from flask import jsonify, request
from . import admin_bp
from db import Db
from decorators import roles_required


@admin_bp.route('/streets', methods=['GET'])
def get_streets():
    city_id = request.args.get('city_id')
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            if city_id:
                cursor.execute(
                    "SELECT id, name, city_id, is_active FROM streets WHERE city_id=%s",
                    (city_id,)
                )
            else:
                cursor.execute("SELECT id, name, city_id, is_active FROM streets")
            streets = cursor.fetchall()
        return jsonify(streets), 200
    finally:
        conn.close()


@admin_bp.route('/streets', methods=['POST'])
@roles_required('admin')
def add_street():
    data = request.get_json()
    name = data.get('name')
    city_id = data.get('city_id')
    if not name or not city_id:
        return jsonify({"error": "Нужны name и city_id"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO streets (name, city_id) VALUES (%s, %s)",
                (name, city_id)
            )
            conn.commit()
            cursor.execute(
                "SELECT id, name, city_id, is_active FROM streets WHERE id=%s",
                (cursor.lastrowid,)
            )
            new_street = cursor.fetchone()
        return jsonify(new_street), 201
    finally:
        conn.close()


@admin_bp.route('/streets/<int:s_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_street(s_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE streets SET is_active=0 WHERE id=%s", (s_id,))
            conn.commit()
            cursor.execute("SELECT id, name, city_id, is_active FROM streets WHERE id=%s", (s_id,))
            street = cursor.fetchone()
        if not street:
            return jsonify({"error": "Улица не найдена"}), 404
        return jsonify({"message": "Улица заблокирована", "street": street}), 200
    finally:
        conn.close()


@admin_bp.route('/streets/<int:s_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_street(s_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE streets SET is_active=1 WHERE id=%s", (s_id,))
            conn.commit()
            cursor.execute("SELECT id, name, city_id, is_active FROM streets WHERE id=%s", (s_id,))
            street = cursor.fetchone()
        if not street:
            return jsonify({"error": "Улица не найдена"}), 404
        return jsonify({"message": f"Улица '{street['name']}' разблокирована", "street": street}), 200
    finally:
        conn.close()


@admin_bp.route('/streets/<int:s_id>', methods=['PUT'])
@roles_required('admin')
def update_street(s_id):
    data = request.get_json()
    new_name = data.get('name')
    new_city_id = data.get('city_id')

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            if new_city_id:
                cursor.execute("SELECT id FROM cities WHERE id=%s", (new_city_id,))
                if not cursor.fetchone():
                    return jsonify({"error": "Указанный город не существует"}), 404

            updates = []
            params = []

            if new_name:
                updates.append("name=%s")
                params.append(new_name)
            if new_city_id:
                updates.append("city_id=%s")
                params.append(new_city_id)

            if updates:
                params.append(s_id)
                cursor.execute(f"UPDATE streets SET {', '.join(updates)} WHERE id=%s", params)
                conn.commit()

            cursor.execute("SELECT id, name, city_id, is_active FROM streets WHERE id=%s", (s_id,))
            street = cursor.fetchone()
        if not street:
            return jsonify({"error": "Улица не найдена"}), 404
        return jsonify({"message": "Улица обновлена", "street": street}), 200
    finally:
        conn.close()

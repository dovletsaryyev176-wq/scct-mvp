from flask import jsonify, request
from . import admin_bp
from db import Db
from decorators import roles_required


@admin_bp.route('/districts', methods=['GET'])
def get_districts():
    city_id = request.args.get('city_id')
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            if city_id:
                cursor.execute(
                    "SELECT id, name, city_id, is_active FROM districts WHERE city_id=%s",
                    (city_id,)
                )
            else:
                cursor.execute("SELECT id, name, city_id, is_active FROM districts")
            districts = cursor.fetchall()
        return jsonify(districts), 200
    finally:
        conn.close()


@admin_bp.route('/districts', methods=['POST'])
@roles_required('admin')
def add_district():
    data = request.get_json()
    name = data.get('name')
    city_id = data.get('city_id')
    if not name or not city_id:
        return jsonify({"error": "Нужны name и city_id"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO districts (name, city_id) VALUES (%s, %s)",
                (name, city_id)
            )
            conn.commit()
            cursor.execute(
                "SELECT id, name, city_id, is_active FROM districts WHERE id=%s",
                (cursor.lastrowid,)
            )
            new_district = cursor.fetchone()
        return jsonify(new_district), 201
    finally:
        conn.close()


@admin_bp.route('/districts/<int:d_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_district(d_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE districts SET is_active=0 WHERE id=%s", (d_id,))
            conn.commit()
            cursor.execute("SELECT id, name, city_id, is_active FROM districts WHERE id=%s", (d_id,))
            district = cursor.fetchone()
        if not district:
            return jsonify({"error": "Район не найден"}), 404
        return jsonify({"message": "Район заблокирован", "district": district}), 200
    finally:
        conn.close()


@admin_bp.route('/districts/<int:d_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_district(d_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE districts SET is_active=1 WHERE id=%s", (d_id,))
            conn.commit()
            cursor.execute("SELECT id, name, city_id, is_active FROM districts WHERE id=%s", (d_id,))
            district = cursor.fetchone()
        if not district:
            return jsonify({"error": "Район не найден"}), 404
        return jsonify({"message": f"Район '{district['name']}' разблокирован", "district": district}), 200
    finally:
        conn.close()


@admin_bp.route('/districts/<int:d_id>', methods=['PUT'])
@roles_required('admin')
def update_district(d_id):
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
                params.append(d_id)
                cursor.execute(f"UPDATE districts SET {', '.join(updates)} WHERE id=%s", params)
                conn.commit()

            cursor.execute("SELECT id, name, city_id, is_active FROM districts WHERE id=%s", (d_id,))
            district = cursor.fetchone()
        if not district:
            return jsonify({"error": "Район не найден"}), 404
        return jsonify({"message": "Район обновлен", "district": district}), 200
    finally:
        conn.close()


@admin_bp.route('/districts/stats', methods=['GET'])
def get_districts_stats():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    d.id AS dist_id,
                    d.name AS dist_name,
                    c.name AS city_name,
                    COALESCE(cd.couriers_count, 0) AS couriers_count,
                    COALESCE(ca.clients_count, 0) AS clients_count
                FROM districts d
                JOIN cities c ON d.city_id = c.id
                LEFT JOIN (
                    SELECT district_id, COUNT(DISTINCT courier_id) AS couriers_count
                    FROM courier_districts
                    GROUP BY district_id
                ) cd ON cd.district_id = d.id
                LEFT JOIN (
                    SELECT district_id, COUNT(DISTINCT client_id) AS clients_count
                    FROM client_addresses
                    GROUP BY district_id
                ) ca ON ca.district_id = d.id
                ORDER BY c.name, d.name
            """)
            stats = cursor.fetchall()
        return jsonify(stats), 200
    finally:
        conn.close()
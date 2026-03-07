from flask import jsonify, request
from . import admin_bp
from db import Db
from decorators import roles_required


@admin_bp.route('/price-types', methods=['GET', 'POST'])
def handle_price_types():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'POST':
                data = request.get_json()
                name = data.get('name')
                if not name:
                    return jsonify({"error": "Имя обязательно"}), 400

                cursor.execute("SELECT id FROM price_types WHERE name=%s", (name,))
                if cursor.fetchone():
                    return jsonify({"error": "Тип с таким именем уже существует"}), 400

                cursor.execute("INSERT INTO price_types (name) VALUES (%s)", (name,))
                conn.commit()
                cursor.execute("SELECT id, name, is_active FROM price_types WHERE id=%s", (cursor.lastrowid,))
                new_pt = cursor.fetchone()
                return jsonify(new_pt), 201


            cursor.execute("SELECT id, name, is_active FROM price_types")
            pts = cursor.fetchall()
        return jsonify(pts), 200
    finally:
        conn.close()


@admin_bp.route('/price-types/<int:pt_id>', methods=['PUT'])
@roles_required('admin')
def update_price_type(pt_id):
    data = request.get_json()
    new_name = data.get('name')
    if not new_name:
        return jsonify({"error": "Имя обязательно"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM price_types WHERE id=%s", (pt_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Тип не найден"}), 404

  
            cursor.execute("SELECT id FROM price_types WHERE name=%s AND id!=%s", (new_name, pt_id))
            if cursor.fetchone():
                return jsonify({"error": "Тип с таким именем уже существует"}), 400

            cursor.execute("UPDATE price_types SET name=%s WHERE id=%s", (new_name, pt_id))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM price_types WHERE id=%s", (pt_id,))
            updated_pt = cursor.fetchone()
        return jsonify(updated_pt), 200
    finally:
        conn.close()


@admin_bp.route('/price-types/<int:pt_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_price_type(pt_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE price_types SET is_active=0 WHERE id=%s", (pt_id,))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM price_types WHERE id=%s", (pt_id,))
            pt = cursor.fetchone()
        if not pt:
            return jsonify({"error": "Тип не найден"}), 404
        return jsonify(pt), 200
    finally:
        conn.close()


@admin_bp.route('/price-types/<int:pt_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_price_type(pt_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE price_types SET is_active=1 WHERE id=%s", (pt_id,))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM price_types WHERE id=%s", (pt_id,))
            pt = cursor.fetchone()
        if not pt:
            return jsonify({"error": "Тип не найден"}), 404
        return jsonify(pt), 200
    finally:
        conn.close()
from flask import jsonify, request
from decorators import roles_required
from . import admin_bp
from db import Db


@admin_bp.route('/brands', methods=['GET', 'POST'])
def handle_brands():
    conn = Db.get_connection()
    try:
        if request.method == 'POST':
            data = request.get_json()
            name = data.get('name')
            if not name:
                return jsonify({"error": "Имя обязательно"}), 400

            with conn.cursor() as cursor:
                sql = "INSERT INTO brands (name) VALUES (%s)"
                cursor.execute(sql, (name,))
                conn.commit()
                brand_id = cursor.lastrowid
                
                cursor.execute("SELECT id, name, is_active FROM brands WHERE id = %s", (brand_id,))
                brand = cursor.fetchone()
            return jsonify(brand), 201

        
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, is_active FROM brands")
            brands = cursor.fetchall()
        return jsonify(brands), 200

    finally:
        conn.close()


@admin_bp.route('/brands/<int:brand_id>', methods=['PUT'])
@roles_required('admin')
def update_brand(brand_id):
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({"error": "Имя обязательно"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверяем существует ли бренд
            cursor.execute("SELECT id, name, is_active FROM brands WHERE id = %s", (brand_id,))
            brand = cursor.fetchone()
            if not brand:
                return jsonify({"error": "Бренд не найден"}), 404

            cursor.execute("UPDATE brands SET name = %s WHERE id = %s", (name, brand_id))
            conn.commit()

            cursor.execute("SELECT id, name, is_active FROM brands WHERE id = %s", (brand_id,))
            updated_brand = cursor.fetchone()
        return jsonify(updated_brand), 200
    finally:
        conn.close()


@admin_bp.route('/brands/<int:brand_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_brand(brand_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, is_active FROM brands WHERE id = %s", (brand_id,))
            brand = cursor.fetchone()
            if not brand:
                return jsonify({"error": "Бренд не найден"}), 404

            cursor.execute("UPDATE brands SET is_active = FALSE WHERE id = %s", (brand_id,))
            conn.commit()

            cursor.execute("SELECT id, name, is_active FROM brands WHERE id = %s", (brand_id,))
            updated_brand = cursor.fetchone()
        return jsonify(updated_brand), 200
    finally:
        conn.close()


@admin_bp.route('/brands/<int:brand_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_brand(brand_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, is_active FROM brands WHERE id = %s", (brand_id,))
            brand = cursor.fetchone()
            if not brand:
                return jsonify({"error": "Бренд не найден"}), 404

            cursor.execute("UPDATE brands SET is_active = TRUE WHERE id = %s", (brand_id,))
            conn.commit()

            cursor.execute("SELECT id, name, is_active FROM brands WHERE id = %s", (brand_id,))
            updated_brand = cursor.fetchone()
        return jsonify(updated_brand), 200
    finally:
        conn.close()
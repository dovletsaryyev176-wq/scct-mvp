from flask import jsonify, request
from . import admin_bp
from db import Db
from decorators import roles_required


@admin_bp.route('/product-types', methods=['POST'])
@roles_required('admin')
def create_product_type():

    data = request.get_json()
    name = data.get('name')

    if not name:
        return jsonify({"error": "Имя обязательно"}), 400

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO product_types (name) VALUES (%s)",
                    (name,)
                )
                conn.commit()

            except Exception as e:
                conn.rollback()
                if "Duplicate entry" in str(e):
                    return jsonify({"error": "Тип продукта уже существует"}), 400
                return jsonify({"error": "Ошибка базы данных"}), 500

            cursor.execute(
                "SELECT id, name, is_active FROM product_types WHERE id=%s",
                (cursor.lastrowid,)
            )
            new_pt = cursor.fetchone()

        return jsonify(new_pt), 201

    finally:
        conn.close()


@admin_bp.route('/product-types', methods=['GET'])
def get_product_types():

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, is_active FROM product_types"
            )
            pts = cursor.fetchall()

        return jsonify(pts), 200

    finally:
        conn.close()


@admin_bp.route('/product-types/<int:pt_id>', methods=['PUT'])
@roles_required('admin')
def update_product_type(pt_id):

    data = request.get_json()
    name = data.get('name')

    if not name:
        return jsonify({"error": "Имя обязательно"}), 400

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "SELECT id FROM product_types WHERE id=%s",
                (pt_id,)
            )
            if not cursor.fetchone():
                return jsonify({"error": "Тип продукта не найден"}), 404

            try:
                cursor.execute(
                    "UPDATE product_types SET name=%s WHERE id=%s",
                    (name, pt_id)
                )
                conn.commit()

            except Exception as e:
                conn.rollback()
                if "Duplicate entry" in str(e):
                    return jsonify({"error": "Тип продукта с таким именем уже существует"}), 400
                return jsonify({"error": "Ошибка базы данных"}), 500

            cursor.execute(
                "SELECT id, name, is_active FROM product_types WHERE id=%s",
                (pt_id,)
            )
            updated_pt = cursor.fetchone()

        return jsonify(updated_pt), 200

    finally:
        conn.close()

@admin_bp.route('/product-types/<int:pt_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_product_type(pt_id):

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "UPDATE product_types SET is_active = FALSE WHERE id=%s",
                (pt_id,)
            )

            if cursor.rowcount == 0:
                return jsonify({"error": "Тип продукта не найден"}), 404

            conn.commit()

            cursor.execute(
                "SELECT id, name, is_active FROM product_types WHERE id=%s",
                (pt_id,)
            )
            pt = cursor.fetchone()

        return jsonify(pt), 200

    finally:
        conn.close()

@admin_bp.route('/product-types/<int:pt_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_product_type(pt_id):

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "UPDATE product_types SET is_active = TRUE WHERE id=%s",
                (pt_id,)
            )

            if cursor.rowcount == 0:
                return jsonify({"error": "Тип продукта не найден"}), 404

            conn.commit()

            cursor.execute(
                "SELECT id, name, is_active FROM product_types WHERE id=%s",
                (pt_id,)
            )
            pt = cursor.fetchone()

        return jsonify(pt), 200

    finally:
        conn.close()
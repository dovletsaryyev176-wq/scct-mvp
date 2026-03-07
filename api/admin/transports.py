from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db


@admin_bp.route('/transports', methods=['GET', 'POST'])
def handle_transports():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'POST':
                data = request.get_json()
                number = data.get('number')
                capacity = data.get('capacity')

                if not number or not capacity:
                    return jsonify({"error": "Номер и вместимость обязательны"}), 400

                cursor.execute(
                    "INSERT INTO transports (number, capacity) VALUES (%s, %s)",
                    (number, int(capacity))
                )
                conn.commit()
                t_id = cursor.lastrowid
                cursor.execute(
                    "SELECT id, number, capacity, is_active FROM transports WHERE id=%s",
                    (t_id,)
                )
                new_t = cursor.fetchone()
                return jsonify(new_t), 201

            cursor.execute("SELECT id, number, capacity, is_active FROM transports")
            transports = cursor.fetchall()
        return jsonify(transports), 200
    finally:
        conn.close()



@admin_bp.route('/transports/<int:t_id>', methods=['PUT'])
@roles_required('admin')
def update_transport(t_id):
    data = request.get_json()
    number = data.get('number')
    capacity = data.get('capacity')

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM transports WHERE id=%s", (t_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Транспорт не найден"}), 404

            cursor.execute(
                "UPDATE transports SET number=%s, capacity=COALESCE(%s, capacity) WHERE id=%s",
                (number, int(capacity) if capacity else None, t_id)
            )
            conn.commit()

            cursor.execute("SELECT id, number, capacity, is_active FROM transports WHERE id=%s", (t_id,))
            t = cursor.fetchone()
        return jsonify(t), 200
    finally:
        conn.close()



@admin_bp.route('/transports/<int:t_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_transport(t_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE transports SET is_active=FALSE WHERE id=%s", (t_id,))
            conn.commit()
            cursor.execute("SELECT id, number, capacity, is_active FROM transports WHERE id=%s", (t_id,))
            t = cursor.fetchone()
        return jsonify(t), 200
    finally:
        conn.close()


@admin_bp.route('/transports/<int:t_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_transport(t_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE transports SET is_active=TRUE WHERE id=%s", (t_id,))
            conn.commit()
            cursor.execute("SELECT id, number, capacity, is_active FROM transports WHERE id=%s", (t_id,))
            t = cursor.fetchone()
        return jsonify(t), 200
    finally:
        conn.close()
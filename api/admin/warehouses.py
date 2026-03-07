from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db

@admin_bp.route('/warehouses', methods=['GET'])
def get_warehouses():
    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT 
                    w.id,
                    w.name,
                    w.is_active,
                    l.id AS location_id,
                    l.name AS location_name
                FROM warehouses w
                LEFT JOIN locations l
                    ON l.warehouse_id = w.id
                    AND l.type = 'warehouse'
            """)

            warehouses = cursor.fetchall()

            result = []

            for w in warehouses:

                cursor.execute(
                    "SELECT address_line FROM warehouse_addresses WHERE warehouse_id=%s",
                    (w['id'],)
                )
                addresses = [a['address_line'] for a in cursor.fetchall()]

                cursor.execute(
                    "SELECT phone FROM warehouse_phones WHERE warehouse_id=%s",
                    (w['id'],)
                )
                phones = [p['phone'] for p in cursor.fetchall()]

                result.append({
                    "id": w["id"],
                    "name": w["name"],
                    "is_active": w["is_active"],
                    "location": {
                        "id": w["location_id"],
                        "name": w["location_name"]
                    } if w["location_id"] else None,
                    "addresses": addresses,
                    "phones": phones
                })

        return jsonify(result), 200

    finally:
        conn.close()


@admin_bp.route('/warehouses', methods=['POST'])
@roles_required('admin')
def create_warehouse():

    data = request.get_json()

    name = data.get('name')
    if not name:
        return jsonify({"error": "Имя обязательно"}), 400

    addresses = data.get('addresses', [])
    phones = data.get('phones', [])

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "INSERT INTO warehouses (name) VALUES (%s)",
                (name,)
            )
            warehouse_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO locations (name, type, warehouse_id)
                VALUES (%s, 'warehouse', %s)
            """, (name, warehouse_id))

            for addr in addresses:
                cursor.execute("""
                    INSERT INTO warehouse_addresses (warehouse_id, address_line)
                    VALUES (%s, %s)
                """, (warehouse_id, addr))

            for ph in phones:
                cursor.execute("""
                    INSERT INTO warehouse_phones (warehouse_id, phone)
                    VALUES (%s, %s)
                """, (warehouse_id, ph))

            conn.commit()

            cursor.execute("""
                SELECT 
                    w.id,
                    w.name,
                    w.is_active,
                    l.id AS location_id,
                    l.name AS location_name
                FROM warehouses w
                LEFT JOIN locations l
                    ON l.warehouse_id = w.id
                    AND l.type = 'warehouse'
                WHERE w.id = %s
            """, (warehouse_id,))

            w = cursor.fetchone()

            result = {
                "id": w["id"],
                "name": w["name"],
                "is_active": w["is_active"],
                "location": {
                    "id": w["location_id"],
                    "name": w["location_name"]
                },
                "addresses": addresses,
                "phones": phones
            }

        return jsonify(result), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()


@admin_bp.route('/warehouses/<int:w_id>', methods=['PUT'])
@roles_required('admin','operator','courier','warehouse')
def update_warehouse(w_id):

    data = request.get_json()

    name = data.get('name')
    addresses = data.get('addresses', None)
    phones = data.get('phones', None)

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM warehouses WHERE id=%s", (w_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Склад не найден"}), 404

            if name:
                cursor.execute(
                    "UPDATE warehouses SET name=%s WHERE id=%s",
                    (name, w_id)
                )

                cursor.execute("""
                    UPDATE locations
                    SET name=%s
                    WHERE warehouse_id=%s AND type='warehouse'
                """, (name, w_id))

            if addresses is not None:
                cursor.execute(
                    "DELETE FROM warehouse_addresses WHERE warehouse_id=%s",
                    (w_id,)
                )

                for addr in addresses:
                    cursor.execute("""
                        INSERT INTO warehouse_addresses (warehouse_id, address_line)
                        VALUES (%s, %s)
                    """, (w_id, addr))

            if phones is not None:
                cursor.execute(
                    "DELETE FROM warehouse_phones WHERE warehouse_id=%s",
                    (w_id,)
                )

                for ph in phones:
                    cursor.execute("""
                        INSERT INTO warehouse_phones (warehouse_id, phone)
                        VALUES (%s, %s)
                    """, (w_id, ph))

            conn.commit()

            cursor.execute("""
                SELECT 
                    w.id,
                    w.name,
                    w.is_active,
                    l.id AS location_id,
                    l.name AS location_name
                FROM warehouses w
                LEFT JOIN locations l
                    ON l.warehouse_id = w.id
                    AND l.type = 'warehouse'
                WHERE w.id = %s
            """, (w_id,))

            w = cursor.fetchone()

            cursor.execute(
                "SELECT address_line FROM warehouse_addresses WHERE warehouse_id=%s",
                (w_id,)
            )
            addr_list = [a['address_line'] for a in cursor.fetchall()]

            cursor.execute(
                "SELECT phone FROM warehouse_phones WHERE warehouse_id=%s",
                (w_id,)
            )
            phone_list = [p['phone'] for p in cursor.fetchall()]

            result = {
                "id": w["id"],
                "name": w["name"],
                "is_active": w["is_active"],
                "location": {
                    "id": w["location_id"],
                    "name": w["location_name"]
                } if w["location_id"] else None,
                "addresses": addr_list,
                "phones": phone_list
            }

        return jsonify(result), 200

    finally:
        conn.close()


@admin_bp.route('/warehouses/<int:w_id>/block', methods=['PATCH'])
@roles_required('admin','operator','courier','warehouse')
def block_warehouse(w_id):

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "UPDATE warehouses SET is_active=FALSE WHERE id=%s",
                (w_id,)
            )

            conn.commit()

            cursor.execute(
                "SELECT id, name, is_active FROM warehouses WHERE id=%s",
                (w_id,)
            )

            warehouse = cursor.fetchone()

        return jsonify(warehouse), 200

    finally:
        conn.close()


@admin_bp.route('/warehouses/<int:w_id>/unblock', methods=['PATCH'])
@roles_required('admin','operator','courier','warehouse')
def unblock_warehouse(w_id):

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "UPDATE warehouses SET is_active=TRUE WHERE id=%s",
                (w_id,)
            )

            conn.commit()

            cursor.execute(
                "SELECT id, name, is_active FROM warehouses WHERE id=%s",
                (w_id,)
            )

            warehouse = cursor.fetchone()

        return jsonify(warehouse), 200

    finally:
        conn.close()


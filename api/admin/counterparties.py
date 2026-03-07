from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db


@admin_bp.route('/counterparties', methods=['POST'])
@roles_required('admin')
def create_counterparty():
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
                "INSERT INTO counterparties (name) VALUES (%s)",
                (name,)
            )
            counterparty_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO locations (name, type, counterparty_id)
                VALUES (%s, 'counterparty', %s)
                """,
                (name, counterparty_id)
            )

            for addr in addresses:
                cursor.execute(
                    """
                    INSERT INTO counterparty_addresses (counterparty_id, address_line)
                    VALUES (%s, %s)
                    """,
                    (counterparty_id, addr)
                )

            for ph in phones:
                cursor.execute(
                    """
                    INSERT INTO counterparty_phones (counterparty_id, phone)
                    VALUES (%s, %s)
                    """,
                    (counterparty_id, ph)
                )

            conn.commit()

            cursor.execute("""
                SELECT 
                    c.id,
                    c.name,
                    c.is_active,
                    l.id AS location_id,
                    l.name AS location_name
                FROM counterparties c
                LEFT JOIN locations l 
                    ON l.counterparty_id = c.id 
                    AND l.type = 'counterparty'
                WHERE c.id = %s
            """, (counterparty_id,))

            cp = cursor.fetchone()

            cursor.execute(
                "SELECT address_line FROM counterparty_addresses WHERE counterparty_id = %s",
                (counterparty_id,)
            )
            addr_list = [a['address_line'] for a in cursor.fetchall()]

            cursor.execute(
                "SELECT phone FROM counterparty_phones WHERE counterparty_id = %s",
                (counterparty_id,)
            )
            phone_list = [p['phone'] for p in cursor.fetchall()]

            result = {
                "id": cp["id"],
                "name": cp["name"],
                "is_active": cp["is_active"],
                "location": {
                    "id": cp["location_id"],
                    "name": cp["location_name"]
                } if cp["location_id"] else None,
                "addresses": addr_list,
                "phones": phone_list
            }

        return jsonify(result), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()


@admin_bp.route('/counterparties', methods=['GET'])
def get_counterparties():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    c.id,
                    c.name,
                    c.is_active,
                    l.id AS location_id,
                    l.name AS location_name,
                    a.address_line,
                    p.phone
                FROM counterparties c
                LEFT JOIN locations l 
                    ON l.counterparty_id = c.id 
                    AND l.type = 'counterparty'
                LEFT JOIN counterparty_addresses a 
                    ON a.counterparty_id = c.id
                LEFT JOIN counterparty_phones p 
                    ON p.counterparty_id = c.id
                ORDER BY c.id
            """)

            rows = cursor.fetchall()

        counterparties = {}

        for row in rows:
            c_id = row["id"]

            if c_id not in counterparties:
                counterparties[c_id] = {
                    "id": c_id,
                    "name": row["name"],
                    "is_active": row["is_active"],
                    "location": {
                        "id": row["location_id"],
                        "name": row["location_name"]
                    } if row["location_id"] else None,
                    "addresses": set(),
                    "phones": set()
                }

            if row["address_line"]:
                counterparties[c_id]["addresses"].add(row["address_line"])

            if row["phone"]:
                counterparties[c_id]["phones"].add(row["phone"])

        result = []
        for cp in counterparties.values():
            cp["addresses"] = list(cp["addresses"])
            cp["phones"] = list(cp["phones"])
            result.append(cp)

        return jsonify(result), 200

    finally:
        conn.close()


@admin_bp.route('/counterparties/<int:c_id>/block', methods=['PATCH'])
@roles_required('admin')
def block_counterparty(c_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE counterparties SET is_active = FALSE WHERE id = %s", (c_id,))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM counterparties WHERE id = %s", (c_id,))
            counterparty = cursor.fetchone()
        return jsonify(counterparty), 200
    finally:
        conn.close()


@admin_bp.route('/counterparties/<int:c_id>/unblock', methods=['PATCH'])
@roles_required('admin')
def unblock_counterparty(c_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE counterparties SET is_active = TRUE WHERE id = %s", (c_id,))
            conn.commit()
            cursor.execute("SELECT id, name, is_active FROM counterparties WHERE id = %s", (c_id,))
            counterparty = cursor.fetchone()
        return jsonify(counterparty), 200
    finally:
        conn.close()


@admin_bp.route('/counterparties/<int:c_id>', methods=['PUT'])
@roles_required('admin')
def update_counterparty(c_id):
    data = request.get_json()
    name = data.get('name')
    addresses = data.get('addresses', None)
    phones = data.get('phones', None)

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "SELECT id FROM counterparties WHERE id = %s",
                (c_id,)
            )
            if not cursor.fetchone():
                return jsonify({"error": "Контрагент не найден"}), 404

            if name:

                cursor.execute(
                    "UPDATE counterparties SET name = %s WHERE id = %s",
                    (name, c_id)
                )

                cursor.execute(
                    """
                    UPDATE locations 
                    SET name = %s
                    WHERE counterparty_id = %s 
                    AND type = 'counterparty'
                    """,
                    (name, c_id)
                )

            if addresses is not None:
                cursor.execute(
                    "DELETE FROM counterparty_addresses WHERE counterparty_id = %s",
                    (c_id,)
                )
                for addr in addresses:
                    cursor.execute(
                        """
                        INSERT INTO counterparty_addresses (counterparty_id, address_line)
                        VALUES (%s, %s)
                        """,
                        (c_id, addr)
                    )

            if phones is not None:
                cursor.execute(
                    "DELETE FROM counterparty_phones WHERE counterparty_id = %s",
                    (c_id,)
                )
                for ph in phones:
                    cursor.execute(
                        """
                        INSERT INTO counterparty_phones (counterparty_id, phone)
                        VALUES (%s, %s)
                        """,
                        (c_id, ph)
                    )

            conn.commit()

            cursor.execute("""
                SELECT 
                    c.id,
                    c.name,
                    c.is_active,
                    l.id AS location_id,
                    l.name AS location_name
                FROM counterparties c
                LEFT JOIN locations l 
                    ON l.counterparty_id = c.id 
                    AND l.type = 'counterparty'
                WHERE c.id = %s
            """, (c_id,))

            cp = cursor.fetchone()

        return jsonify(cp), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()



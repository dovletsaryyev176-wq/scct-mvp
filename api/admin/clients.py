from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db
import math


#Взять информацию об всех клиентах
@admin_bp.route('/clients', methods=['GET'])
def get_all_clients():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    is_active = request.args.get('is_active', type=str)
    price_type_id = request.args.get('price_type_id', type=int)
    city_id = request.args.get('city_id', type=int)
    district_id = request.args.get('district_id', type=int)
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            where_clauses = []
            params = []
            
            if is_active is not None:
                where_clauses.append("c.is_active = %s")
                params.append(is_active.lower() == 'true')
                
            if price_type_id is not None:
                where_clauses.append("c.price_type_id = %s")
                params.append(price_type_id)
                
            if city_id is not None:
                where_clauses.append("EXISTS (SELECT 1 FROM client_addresses ca WHERE ca.client_id = c.id AND ca.city_id = %s)")
                params.append(city_id)
                
            if district_id is not None:
                where_clauses.append("EXISTS (SELECT 1 FROM client_addresses ca WHERE ca.client_id = c.id AND ca.district_id = %s)")
                params.append(district_id)

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            
            count_query = f"SELECT COUNT(c.id) as total FROM clients c {where_sql}"
            cursor.execute(count_query, tuple(params))
            total_items = cursor.fetchone()['total']

            total_pages = math.ceil(total_items / per_page) if total_items > 0 else 0
            offset = (page - 1) * per_page

            
            query = f"""
                SELECT c.id, c.full_name, c.is_active, c.created_at, c.price_type_id, pt.name as price_type_name
                FROM clients c
                LEFT JOIN price_types pt ON c.price_type_id = pt.id
                {where_sql}
                ORDER BY c.id DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(query, tuple(params + [per_page, offset]))
            clients_raw = cursor.fetchall()

            if not clients_raw:
                return jsonify({
                    "data": [],
                    "pagination": {"page": page, "per_page": per_page, "total": 0, "pages": 0}
                }), 200

            
            client_ids = [c['id'] for c in clients_raw]
            format_strings = ','.join(['%s'] * len(client_ids))

            
            cursor.execute(f"SELECT id, client_id, phone FROM client_phones WHERE client_id IN ({format_strings})", tuple(client_ids))
            phones_raw = cursor.fetchall()
            phones_map = {}
            for p in phones_raw:
                phones_map.setdefault(p['client_id'], []).append({"id": p['id'], "phone": p['phone']})

            
            cursor.execute(f"""
                SELECT ca.id, ca.client_id, ca.city_id, ca.district_id, ca.address_line,
                       ct.name as city_name, d.name as district_name
                FROM client_addresses ca
                LEFT JOIN cities ct ON ca.city_id = ct.id
                LEFT JOIN districts d ON ca.district_id = d.id
                WHERE ca.client_id IN ({format_strings})
            """, tuple(client_ids))
            addresses_raw = cursor.fetchall()
            addresses_map = {}
            for a in addresses_raw:
                addresses_map.setdefault(a['client_id'], []).append({
                    "id": a['id'],
                    "city_id": a['city_id'],
                    "city_name": a['city_name'],
                    "district_id": a['district_id'],
                    "district_name": a['district_name'],
                    "address_line": a['address_line']
                })

            
            clients_data = []
            for c in clients_raw:
                cid = c['id']
                created_at_iso = c['created_at'].isoformat() if c['created_at'] else None
                clients_data.append({
                    "id": cid,
                    "full_name": c['full_name'],
                    "is_active": c['is_active'],
                    "created_at": created_at_iso,
                    "price_type_id": c['price_type_id'],
                    "price_type_name": c['price_type_name'],
                    "phones": phones_map.get(cid, []),
                    "addresses": addresses_map.get(cid, [])
                })

        return jsonify({
            "data": clients_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_items,
                "pages": total_pages
            }
        }), 200
    finally:
        conn.close()


#Создание нового клиента
@admin_bp.route('/clients', methods=['POST'])
@roles_required('admin','operator')
def create_client():
    data = request.get_json()
    price_type_id = data.get('price_type_id')
    full_name = data.get('full_name')
    
    if not price_type_id:
        return jsonify({"error": "Нужно выбрать тип цены"}), 400
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "INSERT INTO clients (full_name, price_type_id) VALUES (%s, %s)",
                (full_name, price_type_id)
            )
            client_id = cursor.lastrowid
            

            cursor.execute(
                "INSERT INTO locations (name, type, client_id) VALUES (%s, %s, %s)",
                (full_name, 'client', client_id)
            )
            
            conn.commit()
            return jsonify({"message": "Клиент создан", "id": client_id}), 201
    finally:
        conn.close()

#Взять информацию о конкретном клиенте
@admin_bp.route('/clients/<int:client_id>', methods=['GET'])
def get_client(client_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT c.id, c.full_name, c.is_active, c.created_at, c.price_type_id, 
                       pt.name as price_type_name, l.id as location_id
                FROM clients c
                LEFT JOIN price_types pt ON c.price_type_id = pt.id
                LEFT JOIN locations l ON c.id = l.client_id AND l.type = 'client'
                WHERE c.id = %s
            """, (client_id,))
            client = cursor.fetchone()
            
            if not client:
                return jsonify({"error": "Клиент не найден"}), 404


            cursor.execute("SELECT id, phone FROM client_phones WHERE client_id = %s", (client_id,))
            phones = cursor.fetchall()


            cursor.execute("""
                SELECT ca.id, ca.city_id, ca.district_id, ca.address_line,
                       ct.name as city_name, d.name as district_name
                FROM client_addresses ca
                LEFT JOIN cities ct ON ca.city_id = ct.id
                LEFT JOIN districts d ON ca.district_id = d.id
                WHERE ca.client_id = %s
            """, (client_id,))
            addresses = cursor.fetchall()


            cursor.execute("""
                SELECT credit_limit, used_credit 
                FROM client_credits WHERE client_id = %s AND is_active = TRUE
            """, (client_id,))
            credit_raw = cursor.fetchone()
            
            credit_info = None
            if credit_raw:
                c_limit = float(credit_raw['credit_limit'])
                c_used = float(credit_raw['used_credit'])
                credit_info = {
                    "credit_limit": c_limit,
                    "used_credit": c_used,
                    "available_credit": c_limit - c_used
                }


            total_items = 0
            if client['location_id']:
                cursor.execute("""
                    SELECT SUM(quantity) as total 
                    FROM stocks WHERE location_id = %s
                """, (client['location_id'],))
                stock_res = cursor.fetchone()
                if stock_res and stock_res['total'] is not None:
                    total_items = float(stock_res['total'])

            created_at_iso = client['created_at'].isoformat() if client['created_at'] else None

            client_data = {
                "id": client['id'],
                "full_name": client['full_name'],
                "is_active": bool(client['is_active']),
                "created_at": created_at_iso,
                "price_type_id": client['price_type_id'],
                "price_type_name": client['price_type_name'],
                "location_id": client['location_id'],
                "phones": [{"id": p['id'], "phone": p['phone']} for p in phones],
                "addresses": [
                    {
                        "id": a['id'],
                        "city_id": a['city_id'],
                        "city_name": a['city_name'],
                        "district_id": a['district_id'],
                        "district_name": a['district_name'],
                        "address_line": a['address_line']
                    } for a in addresses
                ],
                "credit": credit_info,
                "total_items_in_location": total_items
            }
            
        return jsonify(client_data), 200
    finally:
        conn.close()

#Изменить статус клиента(активный или заблокирован)
@admin_bp.route('/clients/<int:client_id>/toggle-active', methods=['POST'])
@roles_required('admin')
def toggle_client_active(client_id):
    data = request.get_json() or {}
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT is_active FROM clients WHERE id = %s", (client_id,))
            client = cursor.fetchone()
            
            if not client:
                return jsonify({"error": "Клиент не найден"}), 404

            current_status = bool(client['is_active'])
            target_status = data.get('is_active')
            
            if target_status is None:
                target_status = not current_status


            if current_status and not target_status:
                reason_text = data.get('reason')
                if not reason_text or not str(reason_text).strip():
                    return jsonify({"error": "При блокировке необходимо указать причину"}), 400
                
                cursor.execute(
                    "INSERT INTO client_block_reasons (client_id, reason) VALUES (%s, %s)",
                    (client_id, str(reason_text).strip())
                )


            cursor.execute("UPDATE clients SET is_active = %s WHERE id = %s", (target_status, client_id))
            conn.commit()
            
            return jsonify({
                "message": "Статус успешно обновлен", 
                "is_active": target_status
            }), 200
    finally:
        conn.close()

#Взять информацию о причинах блокировки клиентов
@admin_bp.route('/clients/<int:client_id>/block-reasons', methods=['GET'])
def get_client_block_reasons(client_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Клиент не найден"}), 404

            cursor.execute("""
                SELECT id, reason, created_at 
                FROM client_block_reasons 
                WHERE client_id = %s 
                ORDER BY created_at DESC
            """, (client_id,))
            
            reasons_list = [
                {
                    "id": r['id'],
                    "reason": r['reason'],
                    "created_at": r['created_at'].isoformat() if r['created_at'] else None
                }
                for r in cursor.fetchall()
            ]
            
        return jsonify(reasons_list), 200
    finally:
        conn.close()


#Добавить телефонный номер клиенту
@admin_bp.route('/clients/<int:client_id>/phones', methods=['POST'])
@roles_required('admin','operator')
def add_phone(client_id):
    data = request.get_json()
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Телефон не указан"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO client_phones (client_id, phone) VALUES (%s, %s)", (client_id, phone))
            phone_id = cursor.lastrowid
            conn.commit()
            
        return jsonify({"id": phone_id, "message": "Телефон добавлен"}), 201
    finally:
        conn.close()


#Взять телефонные номера клиента
@admin_bp.route('/clients/<int:client_id>/phones', methods=['GET'])
def get_client_phones(client_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Клиент не найден"}), 404

            cursor.execute("SELECT id, phone FROM client_phones WHERE client_id = %s", (client_id,))
            phones = cursor.fetchall()
            
        return jsonify([{"id": p['id'], "phone": p['phone']} for p in phones]), 200
    finally:
        conn.close()


#Удаление информации о номере телефона клиента
@admin_bp.route('/clients/phones/<int:phone_id>', methods=['DELETE'])
@roles_required('admin','operator')
def remove_phone(phone_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM client_phones WHERE id = %s", (phone_id,))
            if cursor.rowcount == 0:
                return jsonify({"error": "Телефон не найден"}), 404
            conn.commit()
            
        return jsonify({"message": "Телефон удален"}), 200
    finally:
        conn.close()


#Добавить адрес клиенту
@admin_bp.route('/clients/<int:client_id>/addresses', methods=['POST'])
@roles_required('admin','operator')
def add_address(client_id):
    data = request.get_json()
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO client_addresses (client_id, city_id, district_id, address_line) 
                VALUES (%s, %s, %s, %s)
            """, (
                client_id, 
                data.get('city_id'), 
                data.get('district_id'), 
                data.get('address_line')
            ))
            address_id = cursor.lastrowid
            conn.commit()
            
        return jsonify({"id": address_id, "message": "Адрес добавлен"}), 201
    finally:
        conn.close()


#Удалит адрес клиента
@admin_bp.route('/clients/addresses/<int:address_id>', methods=['DELETE'])
@roles_required('admin','operator')
def remove_address(address_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM client_addresses WHERE id = %s", (address_id,))
            if cursor.rowcount == 0:
                return jsonify({"error": "Адрес не найден"}), 404
            conn.commit()
            
        return jsonify({"message": "Адрес удален"}), 200
    finally:
        conn.close()


#Взять адреса клиента
@admin_bp.route('/clients/<int:client_id>/addresses', methods=['GET'])
def get_client_addresses(client_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Клиент не найден"}), 404

            cursor.execute("""
                SELECT ca.id, ca.city_id, ca.district_id, ca.address_line,
                       ct.name as city_name, d.name as district_name
                FROM client_addresses ca
                LEFT JOIN cities ct ON ca.city_id = ct.id
                LEFT JOIN districts d ON ca.district_id = d.id
                WHERE ca.client_id = %s
            """, (client_id,))
            addresses = cursor.fetchall()
            
            addresses_list = [
                {
                    "id": a['id'],
                    "city_id": a['city_id'],
                    "city_name": a['city_name'] or "Неизвестно",
                    "district_id": a['district_id'],
                    "district_name": a['district_name'] or "Неизвестно",
                    "address_line": a['address_line']
                } for a in addresses
            ]
            
        return jsonify(addresses_list), 200
    finally:
        conn.close()


#Изменить информацию об клиенте
@admin_bp.route('/clients/<int:client_id>', methods=['PATCH'])
@roles_required('admin','operator')
def update_client(client_id):
    data = request.get_json()
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Клиент не найден"}), 404

            updates = []
            params = []
            
            if 'full_name' in data:
                updates.append("full_name = %s")
                params.append(data['full_name'])
                
            if 'price_type_id' in data:
                updates.append("price_type_id = %s")
                params.append(data['price_type_id'])
                
            if updates:

                params.append(client_id)
                update_sql = f"UPDATE clients SET {', '.join(updates)} WHERE id = %s"
                cursor.execute(update_sql, tuple(params))
                

                if 'full_name' in data:
                    cursor.execute(
                        "UPDATE locations SET name = %s WHERE client_id = %s AND type = 'client'",
                        (data['full_name'], client_id)
                    )
                

                conn.commit()
                
        return jsonify({"message": "Данные обновлены"}), 200
    finally:
        conn.close()


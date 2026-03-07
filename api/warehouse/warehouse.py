from flask import jsonify, request, session
from . import warehouse_bp
from db import Db
from decorators import roles_required
from all_types_description import TransactionTypes
from datetime import datetime
import math


#Прием с завода на склад
@warehouse_bp.route('/stocks/receive_from_counterparty', methods=['POST'])
@roles_required('admin','warehouse')
def receive_stock_from_counterparty():
    data = request.get_json() or {}
    required = ['from_location_id', 'to_location_id', 'product_id', 'product_state_id', 'quantity']
    if not all(k in data for k in required):
        return jsonify({'error': 'Отсутствуют обязательные поля'}), 400

    try:
        from_loc_id = int(data['from_location_id'])
        to_loc_id = int(data['to_location_id'])
        product_id = int(data['product_id'])
        product_state_id = int(data['product_state_id'])
        quantity = float(data['quantity'])
    except (ValueError, TypeError):
        return jsonify({'error': 'Неверные типы данных в полях'}), 400

    if quantity <= 0:
        return jsonify({'error': 'Количество должно быть больше нуля'}), 400

    if from_loc_id == to_loc_id:
        return jsonify({'error': 'from_location и to_location не могут быть одинаковыми'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
         
            cursor.execute(
                "SELECT id, name, type FROM locations WHERE id IN (%s, %s)",
                (from_loc_id, to_loc_id)
            )
            locs = cursor.fetchall()
            if len(locs) != 2:
                return jsonify({'error': 'Одна или обе локации не найдены'}), 404

            loc_map = {l['id']: l for l in locs}
            from_loc = loc_map.get(from_loc_id)
            to_loc = loc_map.get(to_loc_id)

            if from_loc['type'] != 'counterparty':
                return jsonify({'error': 'from_location должен быть типа "counterparty"'}), 400
            if to_loc['type'] != 'warehouse':
                return jsonify({'error': 'to_location должен быть типа "warehouse"'}), 400

        
            cursor.execute("SELECT id, name FROM products WHERE id=%s", (product_id,))
            product = cursor.fetchone()
            if not product:
                return jsonify({'error': 'Товар не найден'}), 404

            cursor.execute("SELECT id, name FROM product_states WHERE id=%s", (product_state_id,))
            product_state = cursor.fetchone()
            if not product_state:
                return jsonify({'error': 'Состояние товара не найдено'}), 404

            
            user_id = session.get('user_id')

            
            conn.begin()

            
            cursor.execute(
                """
                INSERT INTO transactions
                (operation_type, from_location_id, to_location_id, product_id, product_state_id, quantity, user_id, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (TransactionTypes.INVENTORY_IN, from_loc_id, to_loc_id, product_id, product_state_id, quantity, user_id, data.get('note'))
            )
            transaction_id = cursor.lastrowid

            
            cursor.execute(
                """
                SELECT id, quantity FROM stocks
                WHERE location_id=%s AND product_id=%s AND product_state_id=%s
                """,
                (to_loc_id, product_id, product_state_id)
            )
            stock = cursor.fetchone()
            if stock:
                cursor.execute(
                    "UPDATE stocks SET quantity = quantity + %s WHERE id=%s",
                    (quantity, stock['id'])
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO stocks (location_id, product_id, product_state_id, quantity)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (to_loc_id, product_id, product_state_id, quantity)
                )

            conn.commit()

            
            result = {
                "id": transaction_id,
                "operation_type": TransactionTypes.INVENTORY_IN,
                "from_location": {"id": from_loc['id'], "name": from_loc['name']},
                "to_location": {"id": to_loc['id'], "name": to_loc['name']},
                "product": {"id": product['id'], "name": product['name']},
                "product_state": {"id": product_state['id'], "name": product_state['name']},
                "quantity": quantity,
                "user_id": user_id,
                "note": data.get('note')
            }

        return jsonify(result), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при сохранении транзакции', 'detail': str(e)}), 500
    finally:
        conn.close()

#Узнаем текущий остаток на складе
@warehouse_bp.route('/stocks', methods=['GET'])
def get_warehouse_stocks():
    location_type = request.args.get('location_type', type=str, default=None)

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT 
                    l.id AS location_id,
                    l.name AS location_name,
                    l.type AS location_type,
                    p.id AS product_id,
                    p.name AS product_name,
                    pt.name AS product_type_name,
                    b.name AS brand_name,
                    ps.name AS product_state_name,
                    s.quantity
                FROM stocks s
                JOIN locations l ON s.location_id = l.id
                JOIN products p ON s.product_id = p.id
                JOIN product_types pt ON p.product_type_id = pt.id
                JOIN brands b ON p.brand_id = b.id
                JOIN product_states ps ON s.product_state_id = ps.id
            """
            params = ()
            if location_type:
                query += " WHERE l.type = %s"
                params = (location_type,)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            result = [
                {
                    "location_id": r['location_id'],
                    "location_name": r['location_name'],
                    "location_type": r['location_type'],
                    "product_id": r['product_id'],
                    "product_name": r['product_name'],
                    "product_type_name": r['product_type_name'],
                    "brand_name": r['brand_name'],
                    "product_state_name": r['product_state_name'],
                    "quantity": float(r['quantity'])
                }
                for r in rows
            ]

        return jsonify(result), 200
    finally:
        conn.close()


# Показывает транзакции по приемке с завода на склад
@warehouse_bp.route('/transactions_from_counterparties', methods=['GET'])
@roles_required('admin','operator','courier','warehouse')
def list_incoming_transactions_from_counterparties():
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    
    where_clauses = ["t.operation_type = %s"]
    params = [TransactionTypes.INVENTORY_IN]

    if start:
        try:
            dt_start = datetime.fromisoformat(start)
            where_clauses.append("t.created_at >= %s")
            params.append(dt_start)
        except ValueError:
            return jsonify({'error': 'Неверный формат start_date'}), 400
            
    if end:
        try:
            dt_end = datetime.fromisoformat(end)
            where_clauses.append("t.created_at <= %s")
            params.append(dt_end)
        except ValueError:
            return jsonify({'error': 'Неверный формат end_date'}), 400

    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        return jsonify({'error': 'page и per_page должны быть числами'}), 400

    where_sql = " WHERE " + " AND ".join(where_clauses)
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            count_query = f"SELECT COUNT(*) as total FROM transactions t {where_sql}"
            cursor.execute(count_query, tuple(params))
            total = cursor.fetchone()['total']
            pages = math.ceil(total / per_page) if total > 0 else 0

            
            offset = (page - 1) * per_page
            data_query = f"""
                SELECT 
                    t.id, t.created_at, t.operation_type, 
                    t.from_location_id, lf.name as from_location_name,
                    t.to_location_id, lt.name as to_location_name,
                    t.product_id, p.name as product_name,
                    t.product_state_id, ps.name as product_state_name,
                    t.quantity, t.user_id, u.full_name as user_name, t.note
                FROM transactions t
                LEFT JOIN locations lf ON t.from_location_id = lf.id
                LEFT JOIN locations lt ON t.to_location_id = lt.id
                LEFT JOIN products p ON t.product_id = p.id
                LEFT JOIN product_states ps ON t.product_state_id = ps.id
                LEFT JOIN users u ON t.user_id = u.id
                {where_sql}
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(data_query, tuple(params + [per_page, offset]))
            rows = cursor.fetchall()

            items = []
            for r in rows:
                items.append({
                    'id': r['id'],
                    'created_at': r['created_at'].isoformat() if r['created_at'] else None,
                    'operation_type': r['operation_type'],
                    'from_location_id': r['from_location_id'],
                    'from_location_name': r['from_location_name'],
                    'to_location_id': r['to_location_id'],
                    'to_location_name': r['to_location_name'],
                    'product_id': r['product_id'],
                    'product_name': r['product_name'],
                    'product_state_id': r['product_state_id'],
                    'product_state_name': r['product_state_name'],
                    'quantity': float(r['quantity']),
                    'user_id': r['user_id'],
                    'user_name': r['user_name'],
                    'note': r['note']
                })

        return jsonify({
            'transactions': items,
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages
        }), 200
    finally:
        conn.close()



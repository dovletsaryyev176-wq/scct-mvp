from flask import request, jsonify, session
from datetime import datetime
from . import courier_bp
from db import Db
from decorators import roles_required
from all_types_description import TransactionTypes

#Увидеть остатки в машине
@courier_bp.route('/stocks', methods=['GET'])
@roles_required('courier')
def get_courier_stocks():
    user_id = session.get('user_id')
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user or user['role'] != 'courier':
                return jsonify({'error': 'Unauthorized'}), 403
            
            query = """
                SELECT 
                    l.name AS location_name,
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
                WHERE l.type = 'courier' AND l.user_id = %s AND s.quantity > 0
            """
            cursor.execute(query, (user_id,))
            stocks = cursor.fetchall()

            result = [
                {
                    'location_name': stock['location_name'],
                    'product_name': stock['product_name'],
                    'product_type_name': stock['product_type_name'],
                    'brand_name': stock['brand_name'],
                    'product_state_name': stock['product_state_name'],
                    'quantity': float(stock['quantity'])
                }
                for stock in stocks
            ]

        return jsonify(result), 200
    finally:
        conn.close()


#Увидеть перемещения за дату
@courier_bp.route('/transactions', methods=['GET'])
@roles_required('courier')
def get_courier_transactions():
    user_id = session.get('user_id')
    
    lang = request.args.get('lang', 'ru')
    if lang not in ['ru', 'tm']:
        lang = 'ru'

    date_str = request.args.get('date', type=str)
    if not date_str:
        return jsonify({'error': 'Date parameter is required (format: YYYY-MM-DD)'}), 400
    
    try:
        transaction_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM locations WHERE user_id = %s AND type = 'courier'", (user_id,))
            location_res = cursor.fetchone()
            
            if not location_res:
                return jsonify({'error': 'Локация курьера не найдена'}), 404
            
            courier_location_id = location_res['id']
            
            query = """
                SELECT 
                    t.id, t.created_at, t.operation_type, t.quantity, t.note,
                    p.name AS product_name,
                    ps.name AS product_state_name,
                    lf.name AS from_location_name,
                    lt.name AS to_location_name
                FROM transactions t
                JOIN products p ON t.product_id = p.id
                JOIN product_states ps ON t.product_state_id = ps.id
                LEFT JOIN locations lf ON t.from_location_id = lf.id
                LEFT JOIN locations lt ON t.to_location_id = lt.id
                WHERE (t.from_location_id = %s OR t.to_location_id = %s) 
                  AND DATE(t.created_at) = %s
                ORDER BY t.created_at DESC
            """
            cursor.execute(query, (courier_location_id, courier_location_id, transaction_date))
            transactions = cursor.fetchall()
            
            result = []
            for t in transactions:
                op_type = t['operation_type']
                
                op_name = TransactionTypes.LABELS.get(op_type, {}).get(lang, op_type)

                result.append({
                    'id': t['id'],
                    'created_at': t['created_at'].isoformat() if t['created_at'] else None,
                    'operation_type': op_type,
                    'operation_type_name': op_name,
                    'product_name': t['product_name'],
                    'product_state_name': t['product_state_name'],
                    'from_location_name': t['from_location_name'],
                    'to_location_name': t['to_location_name'],
                    'quantity': float(t['quantity']),
                    'note': t['note']
                })
            
        return jsonify(result), 200
    finally:
        conn.close()


#Перемещение между курьерами
@courier_bp.route('/transactions', methods=['POST'])
@roles_required('courier')
def create_courier_to_courier_transaction():
    user_id = session.get('user_id')
    
    data = request.get_json() or {}
    required = ['to_user_id', 'product_id', 'product_state_id', 'quantity']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        to_user_id = int(data['to_user_id'])
        product_id = int(data['product_id'])
        product_state_id = int(data['product_state_id'])
        quantity = float(data['quantity'])
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid data types'}), 400
    
    if quantity <= 0:
        return jsonify({'error': 'Quantity must be greater than zero'}), 400
    
    if user_id == to_user_id:
        return jsonify({'error': 'Cannot transfer products to yourself'}), 400

    conn = Db.get_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            cursor.execute("SELECT role FROM users WHERE id = %s", (to_user_id,))
            target_user = cursor.fetchone()
            if not target_user or target_user['role'] != 'courier':
                conn.rollback()
                return jsonify({'error': 'Target user not found or is not a courier'}), 404
            
            cursor.execute("SELECT id FROM locations WHERE user_id = %s AND type = 'courier'", (user_id,))
            from_loc = cursor.fetchone()
            
            cursor.execute("SELECT id FROM locations WHERE user_id = %s AND type = 'courier'", (to_user_id,))
            to_loc = cursor.fetchone()

            if not from_loc or not to_loc:
                conn.rollback()
                return jsonify({'error': 'One of the courier locations not found in locations table'}), 404
                
            from_loc_id = from_loc['id']
            to_loc_id = to_loc['id']

            cursor.execute("""
                SELECT id, quantity FROM stocks 
                WHERE location_id = %s AND product_id = %s AND product_state_id = %s 
                FOR UPDATE
            """, (from_loc_id, product_id, product_state_id))
            from_stock = cursor.fetchone()
            
            if not from_stock or from_stock['quantity'] < quantity:
                conn.rollback()
                return jsonify({'error': 'Insufficient stock'}), 400
                
            cursor.execute("UPDATE stocks SET quantity = quantity - %s WHERE id = %s", (quantity, from_stock['id']))

            cursor.execute("""
                INSERT INTO stocks (location_id, product_id, product_state_id, quantity) 
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)
            """, (to_loc_id, product_id, product_state_id, quantity))

            operation_type = TransactionTypes.COURIER_TRANSFER
            note = data.get('note')
            
            cursor.execute("""
                INSERT INTO transactions 
                (operation_type, from_location_id, to_location_id, product_id, product_state_id, quantity, user_id, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (operation_type, from_loc_id, to_loc_id, product_id, product_state_id, quantity, user_id, note))
            
            new_txn_id = cursor.lastrowid

        conn.commit()
        
        return jsonify({
            'message': 'Транзакция успешна',
            'transaction_id': new_txn_id,
            'quantity': quantity,
            'to_user_id': to_user_id
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        conn.close()


# Получить информацию о конкретной транзакции по ID
@courier_bp.route('/transactions/<int:transaction_id>', methods=['GET'])
@roles_required('courier')
def get_transaction_by_id(transaction_id):
    user_id = session.get('user_id')
    
    lang = request.args.get('lang', 'ru')
    if lang not in ['ru', 'tm']:
        lang = 'ru'

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM locations WHERE user_id = %s AND type = 'courier'", (user_id,))
            location_res = cursor.fetchone()
            
            if not location_res:
                return jsonify({'error': 'Локация курьера не найдена'}), 404
            
            courier_location_id = location_res['id']
            

            query = """
                SELECT 
                    t.id, t.created_at, t.operation_type, t.quantity, t.note,
                    p.name AS product_name,
                    ps.name AS product_state_name,
                    lf.name AS from_location_name,
                    lt.name AS to_location_name
                FROM transactions t
                JOIN products p ON t.product_id = p.id
                JOIN product_states ps ON t.product_state_id = ps.id
                LEFT JOIN locations lf ON t.from_location_id = lf.id
                LEFT JOIN locations lt ON t.to_location_id = lt.id
                WHERE t.id = %s AND (t.from_location_id = %s OR t.to_location_id = %s)
            """
            cursor.execute(query, (transaction_id, courier_location_id, courier_location_id))
            t = cursor.fetchone()
            
            if not t:
                return jsonify({'error': 'Транзакция не найдена или доступ запрещен'}), 404
            
            op_type = t['operation_type']
            op_name = TransactionTypes.LABELS.get(op_type, {}).get(lang, op_type)

            result = {
                'id': t['id'],
                'created_at': t['created_at'].isoformat() if t['created_at'] else None,
                'operation_type': op_type,
                'operation_type_name': op_name,
                'product_name': t['product_name'],
                'product_state_name': t['product_state_name'],
                'from_location_name': t['from_location_name'],
                'to_location_name': t['to_location_name'],
                'quantity': float(t['quantity']),
                'note': t['note']
            }
            
        return jsonify(result), 200
    finally:
        conn.close()
from flask import jsonify, request, session
from . import warehouse_bp
from db import Db
from decorators import roles_required
from datetime import datetime
import math
from all_types_description import TransactionTypes


# Создать транзакцию (перемещение товара между локациями)
@warehouse_bp.route('/transaction', methods=['POST'])
@roles_required('admin','warehouse')
def create_transaction():
    data = request.get_json() or {}
    required = ['from_location_id', 'to_location_id', 'product_id', 'product_state_id', 'quantity', 'operation_type']
    if not all(k in data for k in required):
        return jsonify({'error': 'Отсутствуют обязательные поля'}), 400

    try:
        from_loc_id = int(data['from_location_id'])
        to_loc_id = int(data['to_location_id'])
        product_id = int(data['product_id'])
        product_state_id = int(data['product_state_id'])
        quantity = float(data['quantity'])
        operation_type = str(data['operation_type'])
    except (ValueError, TypeError):
        return jsonify({'error': 'Неверные типы данных в полях'}), 400

    if quantity <= 0:
        return jsonify({'error': 'Количество должно быть больше нуля'}), 400

    user_id = session.get('user_id')
    
    conn = Db.get_connection()
    try:
        
        conn.begin()
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT id FROM locations WHERE id IN (%s, %s)", (from_loc_id, to_loc_id))
            if cursor.rowcount < 2:
                conn.rollback()
                return jsonify({'error': 'Одна или обе локации не найдены'}), 404

            
            cursor.execute("SELECT id FROM products WHERE id = %s", (product_id,))
            if not cursor.fetchone():
                conn.rollback()
                return jsonify({'error': 'Товар не найден'}), 404
                
            cursor.execute("SELECT id FROM product_states WHERE id = %s", (product_state_id,))
            if not cursor.fetchone():
                conn.rollback()
                return jsonify({'error': 'Состояние товара не найдено'}), 404

            
            cursor.execute("""
                SELECT id, quantity FROM stocks 
                WHERE location_id = %s AND product_id = %s AND product_state_id = %s 
                FOR UPDATE
            """, (from_loc_id, product_id, product_state_id))
            from_stock = cursor.fetchone()
            
            if not from_stock:
                conn.rollback()
                return jsonify({'error': 'Товар не найден на исходной локации'}), 404
            if from_stock['quantity'] < quantity:
                conn.rollback()
                return jsonify({'error': 'Недостаточно товара на исходной локации'}), 400

            cursor.execute("UPDATE stocks SET quantity = quantity - %s WHERE id = %s", (quantity, from_stock['id']))

            
            cursor.execute("""
                SELECT id FROM stocks 
                WHERE location_id = %s AND product_id = %s AND product_state_id = %s 
                FOR UPDATE
            """, (to_loc_id, product_id, product_state_id))
            to_stock = cursor.fetchone()

            if to_stock:
                cursor.execute("UPDATE stocks SET quantity = quantity + %s WHERE id = %s", (quantity, to_stock['id']))
            else:
                cursor.execute("""
                    INSERT INTO stocks (location_id, product_id, product_state_id, quantity) 
                    VALUES (%s, %s, %s, %s)
                """, (to_loc_id, product_id, product_state_id, quantity))

            
            insert_txn_query = """
                INSERT INTO transactions 
                (operation_type, from_location_id, to_location_id, product_id, product_state_id, quantity, user_id, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_txn_query, (
                operation_type, from_loc_id, to_loc_id, product_id, product_state_id, quantity, user_id, data.get('note')
            ))
            
            
            new_txn_id = cursor.lastrowid

        conn.commit()
        return jsonify({
            'id': new_txn_id,
            'operation_type': operation_type,
            'from_location_id': from_loc_id,
            'to_location_id': to_loc_id,
            'product_id': product_id,
            'product_state_id': product_state_id,
            'quantity': quantity,
            'user_id': user_id,
            'note': data.get('note')
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при сохранении транзакции', 'detail': str(e)}), 500
    finally:
        conn.close()

#Получить все транзакции
@warehouse_bp.route('/transactions', methods=['GET'])
def list_transactions():
    lang = request.args.get('lang', 'ru')
    if lang not in ['ru', 'tm']:
        lang = 'ru'

    where_clauses = []
    params = []

    start = request.args.get('start_date')
    if start:
        try:
            dt_start = datetime.fromisoformat(start)
            where_clauses.append("t.created_at >= %s")
            params.append(dt_start)
        except ValueError:
            return jsonify({'error': 'Неверный формат start_date'}), 400
            
    end = request.args.get('end_date')
    if end:
        try:
            dt_end = datetime.fromisoformat(end)
            where_clauses.append("t.created_at <= %s")
            params.append(dt_end)
        except ValueError:
            return jsonify({'error': 'Неверный формат end_date'}), 400

    user_id = request.args.get('user_id')
    if user_id:
        try:
            uid = int(user_id)
            where_clauses.append("t.user_id = %s")
            params.append(uid)
        except ValueError:
            return jsonify({'error': 'user_id должен быть числом'}), 400

    operation_type = request.args.get('operation_type')
    if operation_type:
        where_clauses.append("t.operation_type = %s")
        params.append(operation_type)

    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        return jsonify({'error': 'page и per_page должны быть числами'}), 400

    where_sql = ""
    if where_clauses:
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
                op_type = r['operation_type']
                op_label = TransactionTypes.LABELS.get(op_type, {}).get(lang, op_type)

                items.append({
                    'id': r['id'],
                    'created_at': r['created_at'].isoformat() if r['created_at'] else None,
                    'operation_type': op_type,
                    'operation_type_label': op_label,
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


# Удалить транзакцию (отмена перемещения товара между локациями)
@warehouse_bp.route('/transaction/<int:transaction_id>', methods=['DELETE'])
@roles_required('admin','operator','courier','warehouse')
def delete_transaction(transaction_id):
    conn = Db.get_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT * FROM transactions WHERE id = %s FOR UPDATE", (transaction_id,))
            transaction = cursor.fetchone()
            
            if not transaction:
                conn.rollback()
                return jsonify({'error': 'Транзакция не найдена'}), 404

            from_loc_id = transaction['from_location_id']
            to_loc_id = transaction['to_location_id']
            product_id = transaction['product_id']
            product_state_id = transaction['product_state_id']
            quantity = transaction['quantity']

            
            cursor.execute("""
                SELECT id, quantity FROM stocks 
                WHERE location_id = %s AND product_id = %s AND product_state_id = %s 
                FOR UPDATE
            """, (to_loc_id, product_id, product_state_id))
            to_stock = cursor.fetchone()

            if not to_stock:
                conn.rollback()
                return jsonify({'error': 'Товар не найден на локации получателя'}), 404
            if to_stock['quantity'] < quantity:
                conn.rollback()
                return jsonify({'error': 'Недостаточно товара для отмены транзакции'}), 400

            cursor.execute("UPDATE stocks SET quantity = quantity - %s WHERE id = %s", (quantity, to_stock['id']))

            
            cursor.execute("""
                SELECT id FROM stocks 
                WHERE location_id = %s AND product_id = %s AND product_state_id = %s 
                FOR UPDATE
            """, (from_loc_id, product_id, product_state_id))
            from_stock = cursor.fetchone()

            if from_stock:
                cursor.execute("UPDATE stocks SET quantity = quantity + %s WHERE id = %s", (quantity, from_stock['id']))
            else:
                cursor.execute("""
                    INSERT INTO stocks (location_id, product_id, product_state_id, quantity) 
                    VALUES (%s, %s, %s, %s)
                """, (from_loc_id, product_id, product_state_id, quantity))

            
            cursor.execute("DELETE FROM transactions WHERE id = %s", (transaction_id,))
            
        conn.commit()
        return jsonify({'message': 'Транзакция успешно отменена'}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при отмене транзакции', 'detail': str(e)}), 500
    finally:
        conn.close()

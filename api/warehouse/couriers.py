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

    # Убираем динамическую фильтрацию по operation_type и жестко задаем два типа
    where_clauses.append("t.operation_type IN (%s, %s)")
    params.extend([TransactionTypes.COURIER_ISSUE, TransactionTypes.COURIER_RETURN])

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

# -------------------------------------------------------------
# 1. Отчет по остаткам в машине каждого курьера на данную дату
# -------------------------------------------------------------
@warehouse_bp.route('/couriers/stocks', methods=['GET'])
@roles_required('admin', 'operator', 'warehouse')
def get_all_couriers_stocks():
    from datetime import date, datetime
    date_str = request.args.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Неверный формат даты. Используйте YYYY-MM-DD'}), 400
    else:
        target_date = date.today()

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Если дата - сегодня, просто берем текущие остатки
            if target_date == date.today():
                query = """
                    SELECT 
                        u.id AS courier_id,
                        u.full_name AS courier_name,
                        p.name AS product_name,
                        pt.name AS product_type_name,
                        b.name AS brand_name,
                        ps.name AS product_state_name,
                        s.quantity
                    FROM stocks s
                    JOIN locations l ON s.location_id = l.id
                    JOIN users u ON l.user_id = u.id
                    JOIN products p ON s.product_id = p.id
                    JOIN product_types pt ON p.product_type_id = pt.id
                    JOIN brands b ON p.brand_id = b.id
                    JOIN product_states ps ON s.product_state_id = ps.id
                    WHERE l.type = 'courier' AND s.quantity > 0
                    ORDER BY u.full_name, p.name
                """
                cursor.execute(query)
            else:
                # Если дата в прошлом, высчитываем исторические остатки по транзакциям
                query = """
                    SELECT 
                        u.id AS courier_id,
                        u.full_name AS courier_name,
                        p.name AS product_name,
                        pt.name AS product_type_name,
                        b.name AS brand_name,
                        ps.name AS product_state_name,
                        SUM(CASE WHEN t.to_location_id = l.id THEN t.quantity ELSE 0 END) -
                        SUM(CASE WHEN t.from_location_id = l.id THEN t.quantity ELSE 0 END) AS quantity
                    FROM locations l
                    JOIN users u ON l.user_id = u.id
                    JOIN transactions t ON (t.to_location_id = l.id OR t.from_location_id = l.id)
                    JOIN products p ON t.product_id = p.id
                    JOIN product_types pt ON p.product_type_id = pt.id
                    JOIN brands b ON p.brand_id = b.id
                    JOIN product_states ps ON t.product_state_id = ps.id
                    WHERE l.type = 'courier' AND DATE(t.created_at) <= %s
                    GROUP BY u.id, u.full_name, p.name, pt.name, b.name, ps.name
                    HAVING quantity > 0
                    ORDER BY u.full_name, p.name
                """
                cursor.execute(query, (target_date,))
                
            stocks = cursor.fetchall()
            
            result = []
            for stock in stocks:
                result.append({
                    'courier_id': stock['courier_id'],
                    'courier_name': stock['courier_name'],
                    'product_name': stock['product_name'],
                    'product_type_name': stock['product_type_name'],
                    'brand_name': stock['brand_name'],
                    'product_state_name': stock['product_state_name'],
                    'quantity': float(stock['quantity'])
                })
                
        return jsonify({
            'date': target_date.isoformat(),
            'stocks': result
        }), 200
    finally:
        conn.close()

# -------------------------------------------------------------
# 2. Возврат всех остатков курьера на заданный склад
# -------------------------------------------------------------
@warehouse_bp.route('/couriers/<int:courier_id>/return-stocks', methods=['POST'])
@roles_required('admin', 'operator', 'warehouse')
def return_courier_stocks(courier_id):
    data = request.get_json() or {}
    to_warehouse_id = data.get('warehouse_id')
    user_id = session.get('user_id')
    note = data.get('note', 'Возврат всех остатков курьера на склад')
    
    if not to_warehouse_id:
        return jsonify({'error': 'Необходим warehouse_id'}), 400

    conn = Db.get_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            # Ищем локацию курьера
            cursor.execute("SELECT id FROM locations WHERE user_id = %s AND type = 'courier'", (courier_id,))
            courier_loc = cursor.fetchone()
            if not courier_loc:
                conn.rollback()
                return jsonify({'error': 'Локация курьера не найдена'}), 404
            from_loc_id = courier_loc['id']

            # Ищем локацию склада (по warehouse_id)
            cursor.execute("SELECT id FROM locations WHERE warehouse_id = %s AND type = 'warehouse'", (to_warehouse_id,))
            warehouse_loc = cursor.fetchone()
            if not warehouse_loc:
                conn.rollback()
                return jsonify({'error': 'Локация склада не найдена'}), 404
            to_loc_id = warehouse_loc['id']

            # Получаем все остатки курьера > 0
            cursor.execute("""
                SELECT id, product_id, product_state_id, quantity 
                FROM stocks 
                WHERE location_id = %s AND quantity > 0
                FOR UPDATE
            """, (from_loc_id,))
            courier_stocks = cursor.fetchall()

            if not courier_stocks:
                conn.rollback()
                return jsonify({'message': 'У курьера нет остатков для возврата'}), 200

            returned_items = []
            
            for stock in courier_stocks:
                prod_id = stock['product_id']
                state_id = stock['product_state_id']
                qty = stock['quantity']

                # Списываем у курьера
                cursor.execute("UPDATE stocks SET quantity = 0 WHERE id = %s", (stock['id'],))

                # Зачисляем на склад
                cursor.execute("""
                    SELECT id FROM stocks 
                    WHERE location_id = %s AND product_id = %s AND product_state_id = %s 
                    FOR UPDATE
                """, (to_loc_id, prod_id, state_id))
                to_stock = cursor.fetchone()

                if to_stock:
                    cursor.execute("UPDATE stocks SET quantity = quantity + %s WHERE id = %s", (qty, to_stock['id']))
                else:
                    cursor.execute("""
                        INSERT INTO stocks (location_id, product_id, product_state_id, quantity) 
                        VALUES (%s, %s, %s, %s)
                    """, (to_loc_id, prod_id, state_id, qty))

                # Пишем транзакцию
                cursor.execute("""
                    INSERT INTO transactions 
                    (operation_type, from_location_id, to_location_id, product_id, product_state_id, quantity, user_id, note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (TransactionTypes.COURIER_RETURN, from_loc_id, to_loc_id, prod_id, state_id, qty, user_id, note))
                
                returned_items.append({
                    'product_id': prod_id,
                    'product_state_id': state_id,
                    'quantity': float(qty)
                })

        conn.commit()
        return jsonify({
            'message': 'Все остатки успешно возвращены на склад',
            'returned_items': returned_items
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при возврате остатков', 'detail': str(e)}), 500
    finally:
        conn.close()


# -------------------------------------------------------------
# 3. Получить список всех складов с их локациями
# -------------------------------------------------------------
@warehouse_bp.route('/warehouses/list', methods=['GET'])
@roles_required('admin', 'operator', 'warehouse')
def list_warehouses_for_return():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT w.id AS warehouse_id, w.name AS warehouse_name, l.id AS location_id
                FROM warehouses w
                JOIN locations l ON l.warehouse_id = w.id
                WHERE w.is_active = 1 AND l.type = 'warehouse'
            """)
            warehouses = cursor.fetchall()

            return jsonify(warehouses), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


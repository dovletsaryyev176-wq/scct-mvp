from flask import jsonify, request, session
from datetime import date
from decimal import Decimal
from db import Db
from . import courier_bp
from decorators import roles_required
from all_types_description import OrderStatuses, TransactionTypes

# -------------------------------------------------------------
# 1. Сводка по заказам курьера на сегодня
# -------------------------------------------------------------
@courier_bp.route('/orders/summary', methods=['GET'])
@roles_required('admin', 'operator', 'courier')
def get_courier_orders_summary():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Необходима авторизация'}), 401

    today = date.today()

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Считаем все заказы и доставленные заказы курьера на сегодня
            sql = """
                SELECT 
                    COUNT(id) as total_orders,
                    SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as completed_orders
                FROM orders 
                WHERE courier_id = %s AND delivery_date = %s
            """
            cursor.execute(sql, (OrderStatuses.DELIVERED, user_id, today))
            result = cursor.fetchone()
            
            total = result['total_orders'] or 0
            completed = result['completed_orders'] or 0

            return jsonify({
                'date': today.isoformat(),
                'total_orders': int(total),
                'completed_orders': int(completed)
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 2. Информация о таре у курьера (Остатки и Выданное сегодня)
# -------------------------------------------------------------
@courier_bp.route('/inventory', methods=['GET'])
@roles_required('admin', 'operator', 'courier')
def get_courier_inventory():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Необходима авторизация'}), 401

    today = date.today()

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Находим location_id курьера
            cursor.execute("SELECT id FROM locations WHERE user_id = %s AND type = 'courier'", (user_id,))
            loc_row = cursor.fetchone()
            
            if not loc_row:
                return jsonify({'error': 'Локация курьера не найдена'}), 404
                
            courier_location_id = loc_row['id']

            # 2.1 Текущее количество (сумма всех quantity в stocks для данной локации)
            stocks_sql = """
                SELECT SUM(quantity) as current_tare 
                FROM stocks 
                WHERE location_id = %s
            """
            cursor.execute(stocks_sql, (courier_location_id,))
            stock_res = cursor.fetchone()
            current_tare = stock_res['current_tare'] or 0.0

            # 2.2 Выдано сегодня (сумма транзакций типа COURIER_ISSUE на эту локацию сегодня)
            trans_sql = """
                SELECT SUM(quantity) as issued_today 
                FROM transactions 
                WHERE to_location_id = %s 
                  AND operation_type = %s 
                  AND DATE(created_at) = %s
            """
            cursor.execute(trans_sql, (courier_location_id, TransactionTypes.COURIER_ISSUE, today))
            trans_res = cursor.fetchone()
            issued_today = trans_res['issued_today'] or 0.0

            return jsonify({
                'date': today.isoformat(),
                'current_tare': float(current_tare),
                'issued_today': float(issued_today)
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 3. Смена статуса заказа курьером (КРОМЕ DELIVERED)
# -------------------------------------------------------------
@courier_bp.route('/orders/<int:order_id>/status', methods=['PUT'])
@roles_required('admin', 'operator', 'courier')
def update_courier_order_status(order_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Необходима авторизация'}), 401

    data = request.get_json()
    new_status = data.get('status')

    if not new_status:
        return jsonify({'error': 'Статус (status) не передан'}), 400

    if new_status not in OrderStatuses.CHOICES:
        return jsonify({'error': f"Недопустимый статус. Допустимые: {', '.join(OrderStatuses.CHOICES)}"}), 400

    if new_status == OrderStatuses.DELIVERED:
        return jsonify({'error': 'Курьер не может самостоятельно переводить заказ в статус Доставлено (DELIVERED)'}), 403

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверяем, что заказ существует и принадлежит этому курьеру
            cursor.execute("SELECT courier_id, status FROM orders WHERE id = %s", (order_id,))
            order_row = cursor.fetchone()

            if not order_row:
                return jsonify({'error': 'Заказ не найден'}), 404
                
            # Если это курьер, проверяем привязку
            cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            user_role = cursor.fetchone()['role']
            
            if user_role == 'courier' and order_row['courier_id'] != user_id:
                return jsonify({'error': 'Этот заказ не назначен вам'}), 403

            # Обновляем статус
            cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, order_id))
            conn.commit()

            return jsonify({
                'message': 'Статус заказа успешно обновлен',
                'order_id': order_id,
                'old_status': order_row['status'],
                'new_status': new_status
            }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 4. Список всех заказов курьера на сегодня
# -------------------------------------------------------------
@courier_bp.route('/orders', methods=['GET'])
@roles_required('admin', 'operator', 'courier')
def get_courier_todays_orders():
    user_id = session.get('user_id')
    
    # Можно передать courier_id через query params, если вызывает админ/оператор 
    target_courier_id = request.args.get('courier_id', default=user_id, type=int)

    # Проверка прав: курьер может смотреть только свои заказы
    cursor = None
    conn = Db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        role_row = cursor.fetchone()
        
        if role_row and role_row['role'] == 'courier' and target_courier_id != user_id:
            return jsonify({'error': 'У вас нет прав на просмотр заказов других курьеров'}), 403

        today = date.today()
        
        sql = """
            SELECT 
                o.id,
                o.client_id,
                c.full_name as client_name,
                cp.phone as client_phone,
                ca.address_line as client_address,
                city.name as city_name,
                dist.name as district_name,
                o.delivery_time_type,
                o.delivery_time,
                o.payment_type,
                o.status,
                o.total_amount,
                o.cash_amount,
                o.card_amount,
                o.note
            FROM orders o
            LEFT JOIN clients c ON o.client_id = c.id
            LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
            LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
            LEFT JOIN cities city ON ca.city_id = city.id
            LEFT JOIN districts dist ON ca.district_id = dist.id
            WHERE o.courier_id = %s AND o.delivery_date = %s
            ORDER BY o.delivery_time ASC, o.created_at ASC
        """
        cursor.execute(sql, (target_courier_id, today))
        orders = cursor.fetchall()
        
        # Получаем items для каждого заказа
        order_ids = [order['id'] for order in orders]
        items_by_order = {}
        
        if order_ids:
            placeholders = ', '.join(['%s'] * len(order_ids))
            items_sql = f"""
                SELECT oi.order_id, oi.service_id, s.name as service_name, oi.quantity, oi.price, oi.total_price
                FROM order_items oi
                JOIN services s ON oi.service_id = s.id
                WHERE oi.order_id IN ({placeholders})
            """
            cursor.execute(items_sql, tuple(order_ids))
            items = cursor.fetchall()
            
            for item in items:
                o_id = item['order_id']
                if o_id not in items_by_order:
                    items_by_order[o_id] = []
                # Format decimals
                if item.get('price') is not None: item['price'] = float(item['price'])
                if item.get('total_price') is not None: item['total_price'] = float(item['total_price'])
                item['quantity'] = float(item['quantity'])
                items_by_order[o_id].append(item)

        # Форматируем ответ
        for order in orders:
            if order.get('delivery_time') and hasattr(order['delivery_time'], 'seconds'):
                hours, remainder = divmod(order['delivery_time'].seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                
            order['total_amount'] = float(order['total_amount'])
            if order.get('cash_amount') is not None: order['cash_amount'] = float(order['cash_amount'])
            if order.get('card_amount') is not None: order['card_amount'] = float(order['card_amount'])

            order['items'] = items_by_order.get(order['id'], [])

        return jsonify({
            'date': today.isoformat(),
            'courier_id': target_courier_id,
            'orders': orders,
            'total_count': len(orders)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

# -------------------------------------------------------------
# 5. Детальная информация по одному заказу курьера
# -------------------------------------------------------------
@courier_bp.route('/orders/<int:order_id>', methods=['GET'])
@roles_required('admin', 'operator', 'courier')
def get_courier_single_order(order_id):
    user_id = session.get('user_id')
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверки прав доступа
            cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            user_role = cursor.fetchone()['role']

            sql = """
                SELECT 
                    o.id,
                    o.client_id,
                    o.courier_id,
                    c.full_name as client_name,
                    cp.phone as client_phone,
                    ca.address_line as client_address,
                    city.name as city_name,
                    dist.name as district_name,
                    o.delivery_date,
                    o.delivery_time_type,
                    o.delivery_time,
                    o.payment_type,
                    o.status,
                    o.total_amount,
                    o.cash_amount,
                    o.card_amount,
                    o.note,
                    o.created_at
                FROM orders o
                LEFT JOIN clients c ON o.client_id = c.id
                LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
                LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
                LEFT JOIN cities city ON ca.city_id = city.id
                LEFT JOIN districts dist ON ca.district_id = dist.id
                WHERE o.id = %s
            """
            cursor.execute(sql, (order_id,))
            order = cursor.fetchone()
            
            if not order:
                return jsonify({'error': 'Заказ не найден'}), 404
                
            if user_role == 'courier' and order['courier_id'] != user_id:
                return jsonify({'error': 'Этот заказ не назначен вам'}), 403

            # Получаем items
            items_sql = """
                SELECT oi.service_id, s.name as service_name, oi.quantity, oi.price, oi.total_price
                FROM order_items oi
                JOIN services s ON oi.service_id = s.id
                WHERE oi.order_id = %s
            """
            cursor.execute(items_sql, (order_id,))
            items = cursor.fetchall()
            
            for item in items:
                if item.get('price') is not None: item['price'] = float(item['price'])
                if item.get('total_price') is not None: item['total_price'] = float(item['total_price'])
                item['quantity'] = float(item['quantity'])

            # Получаем discounts
            d_sql = """
                SELECT d.name as discount_name, d.discount_type, od.discount_amount
                FROM order_discounts od
                JOIN discounts d ON od.discount_id = d.id
                WHERE od.order_id = %s
            """
            cursor.execute(d_sql, (order_id,))
            discounts = cursor.fetchall()

            for d in discounts:
                d['discount_amount'] = float(d['discount_amount'])

            # Форматирование
            if order.get('delivery_date'): order['delivery_date'] = order['delivery_date'].isoformat()
            if order.get('created_at'): order['created_at'] = order['created_at'].isoformat()
            if order.get('delivery_time') and hasattr(order['delivery_time'], 'seconds'):
                hours, remainder = divmod(order['delivery_time'].seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                
            order['total_amount'] = float(order['total_amount'])
            if order.get('cash_amount') is not None: order['cash_amount'] = float(order['cash_amount'])
            if order.get('card_amount') is not None: order['card_amount'] = float(order['card_amount'])

            order['items'] = items
            order['discounts'] = discounts

            return jsonify(order), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 6. Добавление заметки к заказу курьером
# -------------------------------------------------------------
@courier_bp.route('/orders/<int:order_id>/notes', methods=['POST'])
@roles_required('admin', 'operator', 'courier')
def add_courier_order_note(order_id):
    user_id = session.get('user_id')
    
    data = request.get_json()
    new_note_text = data.get('note')

    if not new_note_text:
        return jsonify({'error': 'Текст заметки (note) не может быть пустым'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверки прав доступа
            cursor.execute("SELECT courier_id, note FROM orders WHERE id = %s", (order_id,))
            order_row = cursor.fetchone()

            if not order_row:
                return jsonify({'error': 'Заказ не найден'}), 404

            cursor.execute("SELECT role, full_name FROM users WHERE id = %s", (user_id,))
            user_info = cursor.fetchone()
            
            if user_info['role'] == 'courier' and order_row['courier_id'] != user_id:
                return jsonify({'error': 'Этот заказ не назначен вам'}), 403

            # Формируем новую заметку с указанием времени и автора
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            author_tag = f"[{user_info['full_name']} ({timestamp})]"
            
            existing_notes = order_row['note'] or ""
            
            if existing_notes.strip():
                updated_note = f"{existing_notes}\n{author_tag}: {new_note_text}"
            else:
                updated_note = f"{author_tag}: {new_note_text}"

            # Сохраняем обратно в таблицу
            cursor.execute("UPDATE orders SET note = %s WHERE id = %s", (updated_note, order_id))
            conn.commit()

            return jsonify({
                'message': 'Заметка успешно добавлена',
                'order_id': order_id,
                'note': updated_note
            }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 7. Получение всех заметок заказа
# -------------------------------------------------------------
@courier_bp.route('/orders/<int:order_id>/notes', methods=['GET'])
@roles_required('admin', 'operator', 'courier')
def get_courier_order_notes(order_id):
    user_id = session.get('user_id')
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверки прав доступа
            cursor.execute("SELECT courier_id, note FROM orders WHERE id = %s", (order_id,))
            order_row = cursor.fetchone()

            if not order_row:
                return jsonify({'error': 'Заказ не найден'}), 404

            cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            user_role = cursor.fetchone()['role']
            
            if user_role == 'courier' and order_row['courier_id'] != user_id:
                return jsonify({'error': 'Этот заказ не назначен вам'}), 403

            notes_text = order_row['note'] or ""

            return jsonify({
                'order_id': order_id,
                'notes': notes_text
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


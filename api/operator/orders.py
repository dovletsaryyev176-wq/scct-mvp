from flask import Blueprint, jsonify, request, session
from datetime import datetime, date, timedelta
from decimal import Decimal
from extensions import db  # Оставляем временно для совместимости (если другие части еще юзают)
from db import Db
from . import operator_bp
from decorators import roles_required
from all_types_description import PaymentTypes, DeliveryTimes, OrderStatuses

# -------------------------------------------------------------
# Поиск клиентов по телефону
# -------------------------------------------------------------
@operator_bp.route('/clients/search', methods=['GET'])
@roles_required('operator')
def search_clients_by_phone():
    phone_query = request.args.get('phone', type=str)
    
    if not phone_query:
        return jsonify({'error': 'Phone parameter is required'}), 400
        
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT c.id, c.full_name, cp.phone
                FROM clients c
                JOIN client_phones cp ON c.id = cp.client_id
                WHERE cp.phone LIKE %s
            """
            cursor.execute(sql, (f'%{phone_query}%',))
            clients = cursor.fetchall()
            
        return jsonify(clients), 200
    finally:
        conn.close()

# -------------------------------------------------------------
# Типы оплат 
# -------------------------------------------------------------
@operator_bp.route('/payment-types', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def get_payment_types():
    payment_types = [
        {
            'value': choice,
            'label_ru': PaymentTypes.LABELS[choice].get('ru'),
            'label_tm': PaymentTypes.LABELS[choice].get('tm'),
        }
        for choice in PaymentTypes.CHOICES
    ]
    return jsonify({'payment_types': payment_types}), 200

# -------------------------------------------------------------
# Варианты времени доставки
# -------------------------------------------------------------
@operator_bp.route('/delivery-times', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def get_delivery_times():
    delivery_times = [
        {
            'value': choice,
            'label_ru': DeliveryTimes.LABELS[choice].get('ru'),
            'label_tm': DeliveryTimes.LABELS[choice].get('tm'),
        }
        for choice in DeliveryTimes.CHOICES
    ]
    return jsonify({'delivery_times': delivery_times}), 200

# -------------------------------------------------------------
# Статусы заказов
# -------------------------------------------------------------
@operator_bp.route('/order-statuses', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def get_order_statuses():
    statuses = [
        {
            'value': choice,
            'label_ru': OrderStatuses.LABELS[choice].get('ru'),
            'label_tm': OrderStatuses.LABELS[choice].get('tm'),
        }
        for choice in OrderStatuses.CHOICES
    ]
    return jsonify({'order_statuses': statuses}), 200

# -------------------------------------------------------------
# Получение всех заказов с пагинацией и фильтрами
# -------------------------------------------------------------
@operator_bp.route('/orders', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def get_all_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    offset = (page - 1) * per_page
    
    client_id = request.args.get('client_id', type=int)
    courier_id = request.args.get('courier_id', type=int)
    status = request.args.get('status', type=str)
    payment_type = request.args.get('payment_type', type=str)
    delivery_date = request.args.get('delivery_date', type=str)
    
    conditions = []
    params = []
    
    if client_id:
        conditions.append("o.client_id = %s")
        params.append(client_id)
    if courier_id:
        conditions.append("o.courier_id = %s")
        params.append(courier_id)
    if status:
        conditions.append("o.status = %s")
        params.append(status)
    if payment_type:
        conditions.append("o.payment_type = %s")
        params.append(payment_type)
    if delivery_date:
        try:
            delivery_date_obj = datetime.strptime(delivery_date, '%Y-%m-%d').date()
            conditions.append("o.delivery_date = %s")
            params.append(delivery_date_obj)
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты доставки. Используйте YYYY-MM-DD'}), 400
            
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Подсчет общего количества
            count_sql = f"SELECT COUNT(*) as total FROM orders o {where_clause}"
            cursor.execute(count_sql, tuple(params))
            total = cursor.fetchone()['total']
            
            # Получение заказов
            sql = f"""
                SELECT 
                    o.*,
                    c.full_name as client_name,
                    cp.phone as client_phone,
                    ca.address_line as client_address
                FROM orders o
                LEFT JOIN clients c ON o.client_id = c.id
                LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
                LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
                {where_clause}
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """
            
            query_params = params + [per_page, offset]
            cursor.execute(sql, tuple(query_params))
            orders = cursor.fetchall()
            
            # Если нужно приводить даты к строке для JSON
            for order in orders:
                if order.get('delivery_date'):
                    order['delivery_date'] = order['delivery_date'].isoformat()
                if order.get('created_at'):
                    order['created_at'] = order['created_at'].isoformat()
                if order.get('delivery_time') and hasattr(order['delivery_time'], 'strftime'):
                     # timedelta, как возвращает pymysql для TIME
                     hours, remainder = divmod(order['delivery_time'].seconds, 3600)
                     minutes, seconds = divmod(remainder, 60)
                     order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
            
        pages = (total + per_page - 1) // per_page if total > 0 else 1
            
        return jsonify({
            'orders': orders,
            'total': total,
            'pages': pages,
            'current_page': page,
        }), 200
    finally:
        conn.close()

# -------------------------------------------------------------
# Получение конкретного заказа (и его items)
# -------------------------------------------------------------
@operator_bp.route('/orders/<int:order_id>', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def get_order(order_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    o.*,
                    c.full_name as client_name,
                    cp.phone as client_phone,
                    ca.address_line as client_address
                FROM orders o
                LEFT JOIN clients c ON o.client_id = c.id
                LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
                LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
                WHERE o.id = %s
            """
            cursor.execute(sql, (order_id,))
            order = cursor.fetchone()
            
            if not order:
                return jsonify({'error': 'Заказ не найден'}), 404
                
            # Обработка дат для JSON
            if order.get('delivery_date'):
                order['delivery_date'] = order['delivery_date'].isoformat()
            if order.get('created_at'):
                order['created_at'] = order['created_at'].isoformat()
            if order.get('delivery_time') and hasattr(order['delivery_time'], 'seconds'):
                hours, remainder = divmod(order['delivery_time'].seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                
            # Получение items заказа
            cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
            order['items'] = cursor.fetchall()
            
            for item in order['items']:
                if item.get('created_at'):
                    item['created_at'] = item['created_at'].isoformat()
            
        return jsonify(order), 200
    finally:
        conn.close()

# -------------------------------------------------------------
# Получение заказов конкретного клиента
# -------------------------------------------------------------
@operator_bp.route('/clients/<int:client_id>/orders', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def get_client_orders(client_id):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    offset = (page - 1) * per_page
    
    status = request.args.get('status', type=str)
    courier_id = request.args.get('courier_id', type=int)
    delivery_date = request.args.get('delivery_date', type=str)
    
    conditions = ["o.client_id = %s"]
    params = [client_id]
    
    if status:
        conditions.append("o.status = %s")
        params.append(status)
    if courier_id:
        conditions.append("o.courier_id = %s")
        params.append(courier_id)
    if delivery_date:
        try:
            delivery_date_obj = datetime.strptime(delivery_date, '%Y-%m-%d').date()
            conditions.append("o.delivery_date = %s")
            params.append(delivery_date_obj)
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты доставки. Используйте YYYY-MM-DD'}), 400
            
    where_clause = "WHERE " + " AND ".join(conditions)
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверка клиента
            cursor.execute("SELECT full_name FROM clients WHERE id = %s", (client_id,))
            client = cursor.fetchone()
            if not client:
                return jsonify({'error': 'Клиент не найден'}), 404
                
            # Подсчет количества
            count_sql = f"SELECT COUNT(*) as total FROM orders o {where_clause}"
            cursor.execute(count_sql, tuple(params))
            total = cursor.fetchone()['total']
            
            # Выборка заказов
            sql = f"""
                SELECT o.* 
                FROM orders o 
                {where_clause} 
                ORDER BY o.created_at DESC 
                LIMIT %s OFFSET %s
            """
            query_params = params + [per_page, offset]
            cursor.execute(sql, tuple(query_params))
            orders = cursor.fetchall()
            
            for order in orders:
                if order.get('delivery_date'):
                    order['delivery_date'] = order['delivery_date'].isoformat()
                if order.get('created_at'):
                    order['created_at'] = order['created_at'].isoformat()
                if order.get('delivery_time') and hasattr(order['delivery_time'], 'seconds'):
                    hours, remainder = divmod(order['delivery_time'].seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
            
        pages = (total + per_page - 1) // per_page if total > 0 else 1
            
        return jsonify({
            'client_id': client_id,
            'client_name': client['full_name'],
            'orders': orders,
            'total': total,
            'pages': pages,
            'current_page': page,
        }), 200
    finally:
        conn.close()

# -------------------------------------------------------------
# Создание заказа
# -------------------------------------------------------------
@operator_bp.route('/orders', methods=['POST'])
@roles_required('admin', 'operator')
def create_order():
    data = request.get_json()
    
    required_fields = ['client_id', 'client_address_id', 'client_phone_id', 
                       'delivery_date', 'delivery_time_type', 'payment_type', 'items']
    
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Не все обязательные поля заполнены'}), 400
        
    if not data['items'] or len(data['items']) == 0:
        return jsonify({'error': 'Order must contain at least one service'}), 400
        
    try:
        delivery_date = datetime.strptime(data['delivery_date'], '%Y-%m-%d').date()
        today = date.today()
        if delivery_date not in [today, today + timedelta(days=1)]:
            return jsonify({'error': 'Delivery date must be today or tomorrow'}), 400
            
        delivery_time = None
        if data['delivery_time_type'] == 'specific_time':
            if not data.get('delivery_time'):
                return jsonify({'error': 'Delivery time required for specific_time type'}), 400
            delivery_time = datetime.strptime(data['delivery_time'], '%H:%M:%S').time()
    except ValueError as e:
        return jsonify({'error': f'Invalid date or time format: {str(e)}'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Валидация клиента, адреса, телефона
            cursor.execute("SELECT price_type_id FROM clients WHERE id = %s", (data['client_id'],))
            client = cursor.fetchone()
            if not client:
                return jsonify({'error': 'Client not found'}), 404
                
            cursor.execute("SELECT city_id FROM client_addresses WHERE id = %s AND client_id = %s", 
                          (data['client_address_id'], data['client_id']))
            address_info = cursor.fetchone()
            if not address_info:
                return jsonify({'error': 'Client address not found or does not belong to client'}), 404
            client_city_id = address_info['city_id']
                
            cursor.execute("SELECT id FROM client_phones WHERE id = %s AND client_id = %s", 
                          (data['client_phone_id'], data['client_id']))
            if not cursor.fetchone():
                return jsonify({'error': 'Client phone not found or does not belong to client'}), 404
                
            # Проверка курьера
            if data.get('courier_id'):
                cursor.execute("SELECT user_id FROM courier_profiles WHERE user_id = %s", (data['courier_id'],))
                if not cursor.fetchone():
                    return jsonify({'error': 'Courier not found'}), 404

            # 2. Создание заголовка заказа
            sql_order = """
                INSERT INTO orders (client_id, client_address_id, client_phone_id, courier_id, 
                                  user_id, note, delivery_date, delivery_time_type, 
                                  delivery_time, payment_type, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            user_id = session.get('user_id', 1)  # Дефолт 1 если нет сессии (для тестов)
            order_params = (
                data['client_id'], data['client_address_id'], data['client_phone_id'], 
                data.get('courier_id'), user_id, data.get('note'), 
                delivery_date, data['delivery_time_type'], delivery_time, 
                data['payment_type'], data.get('status', 'pending')
            )
            cursor.execute(sql_order, order_params)
            order_id = cursor.lastrowid
            
            total_order_price = Decimal('0.0')
            items_for_insert = []
            service_ids = []
            
            # 3. Подготовка и вставка позиций заказа
            price_type_id = client['price_type_id']
            
            for item in data['items']:
                if 'service_id' not in item or 'quantity' not in item:
                    conn.rollback()
                    return jsonify({'error': 'Each item must have service_id and quantity'}), 400
                    
                service_id = item['service_id']
                quantity = Decimal(str(item['quantity']))
                service_ids.append(service_id)
                
                # Поиск цены
                cursor.execute("""
                    SELECT price FROM service_prices 
                    WHERE service_id = %s AND city_id = %s AND price_type_id = %s
                """, (service_id, client_city_id, price_type_id))
                price_row = cursor.fetchone()
                
                price = None
                total_price = None
                
                if price_row and price_row['price'] is not None:
                    price = Decimal(str(price_row['price']))
                    total_price = price * quantity
                    total_order_price = total_order_price + total_price
                    
                items_for_insert.append((order_id, service_id, quantity, price, total_price))
            
            sql_items = """
                INSERT INTO order_items (order_id, service_id, quantity, price, total_price)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.executemany(sql_items, items_for_insert)
            
            # 4. Система скидок на чистом SQL
            if total_order_price > 0:
                current_date = datetime.now().date()
                current_time = datetime.now().time()
                
                # Получаем все активные скидки, подходящие по датам и лимитам
                discount_sql = """
                    SELECT d.* 
                    FROM discounts d
                    WHERE d.is_active = 1
                      AND (d.start_date IS NULL OR d.start_date <= %s)
                      AND (d.end_date IS NULL OR d.end_date >= %s)
                      AND (d.start_time IS NULL OR d.start_time <= %s)
                      AND (d.end_time IS NULL OR d.end_time >= %s)
                      AND (d.limit_count IS NULL OR d.usage_count < d.limit_count)
                """
                cursor.execute(discount_sql, (current_date, current_date, current_time, current_time))
                potential_discounts = cursor.fetchall()
                
                best_discount_id = None
                max_discount_amount = Decimal('0.0')
                
                for discount in potential_discounts:
                    d_id = discount['id']
                    
                    # Проверка городов
                    cursor.execute("SELECT city_id FROM discount_cities WHERE discount_id = %s", (d_id,))
                    d_cities = [r['city_id'] for r in cursor.fetchall()]
                    if d_cities and client_city_id not in d_cities:
                        continue
                        
                    # Проверка услуг
                    cursor.execute("SELECT service_id FROM discount_services WHERE discount_id = %s", (d_id,))
                    d_services = [r['service_id'] for r in cursor.fetchall()]
                    if d_services and not any(sid in d_services for sid in service_ids):
                        continue
                        
                    # Расчет суммы скидки
                    amount = Decimal('0.0')
                    d_type = discount['discount_type']
                    d_val = Decimal(str(discount['value'])) if discount['value'] is not None else Decimal('0.0')
                    
                    if d_type == 'fixed_amount':
                        amount = d_val
                        if amount > total_order_price:
                            amount = total_order_price
                            
                    elif d_type == 'percentage':
                        amount = (total_order_price * d_val) / Decimal('100.0')
                        
                    elif d_type == 'fixed_price':
                        if total_order_price > d_val:
                            amount = total_order_price - d_val
                            
                    elif d_type == 'free_n_th_order':
                        nth = discount['nth_order']
                        if nth and nth > 0:
                            cursor.execute("SELECT COUNT(*) as count FROM orders WHERE client_id = %s", (data['client_id'],))
                            orders_count = cursor.fetchone()['count']
                            if (orders_count + 1) % nth == 0:
                                amount = total_order_price
                    
                    if amount > max_discount_amount:
                        max_discount_amount = amount
                        best_discount_id = d_id
                
                # Применяем скидку
                if best_discount_id and max_discount_amount > 0:
                    cursor.execute("UPDATE discounts SET usage_count = usage_count + 1 WHERE id = %s", (best_discount_id,))
                    cursor.execute("""
                        UPDATE orders 
                        SET applied_discount_id = %s, discount_amount = %s 
                        WHERE id = %s
                    """, (best_discount_id, max_discount_amount, order_id))

            # 5. Обработка кредита
            if data['payment_type'] == 'credit' and data.get('order_amount'):
                order_amount = Decimal(str(data['order_amount']))
                
                cursor.execute("SELECT id, available_credit, used_credit FROM client_credits WHERE client_id = %s FOR UPDATE", 
                              (data['client_id'],))
                credit_row = cursor.fetchone()
                
                if not credit_row:
                    # Создание кредитной линии с нулевым лимитом
                    cursor.execute("INSERT INTO client_credits (client_id, credit_limit, used_credit) VALUES (%s, %s, %s)",
                                  (data['client_id'], 0, 0))
                    credit_id = cursor.lastrowid
                    available = Decimal('0')
                    used = Decimal('0')
                else:
                    credit_id = credit_row['id']
                    
                    # ПРИМЕЧАНИЕ: в schema.sql нет поля available_credit.
                    # Обычно available = credit_limit - used_credit
                    # Вычисляем:
                    limit = Decimal(str(credit_row.get('credit_limit', 0) or 0)) 
                    used = Decimal(str(credit_row.get('used_credit', 0) or 0))
                    available = limit - used
                    
                if available < order_amount:
                    conn.rollback()
                    return jsonify({
                        'error': 'Insufficient credit',
                        'available_credit': float(available)
                    }), 400
                    
                new_used = used + order_amount
                cursor.execute("UPDATE client_credits SET used_credit = %s WHERE id = %s", (new_used, credit_id))
                
                cursor.execute("""
                    INSERT INTO credit_payments (client_credit_id, order_id, payment_type, amount, description)
                    VALUES (%s, %s, %s, %s, %s)
                """, (credit_id, order_id, 'charge', order_amount, f'Charge for order #{order_id}'))

            conn.commit()
            
            # Возвращаем созданный заказ
            cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            new_order = cursor.fetchone()
            if new_order.get('delivery_date'): new_order['delivery_date'] = new_order['delivery_date'].isoformat()
            if new_order.get('created_at'): new_order['created_at'] = new_order['created_at'].isoformat()
            if new_order.get('delivery_time') and hasattr(new_order['delivery_time'], 'seconds'):
                hours, remainder = divmod(new_order['delivery_time'].seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                new_order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                
            return jsonify(new_order), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# Обновление заказа
# -------------------------------------------------------------
@operator_bp.route('/orders/<int:order_id>', methods=['PUT'])
@roles_required('admin', 'operator')
def update_order(order_id):
    data = request.get_json()
    conn = Db.get_connection()
    
    try:
        with conn.cursor() as cursor:
            # Проверка существования заказа
            cursor.execute("""
                SELECT o.*, c.price_type_id, ca.city_id 
                FROM orders o 
                JOIN clients c ON o.client_id = c.id
                JOIN client_addresses ca ON o.client_address_id = ca.id
                WHERE o.id = %s FOR UPDATE
            """, (order_id,))
            order = cursor.fetchone()
            
            if not order:
                return jsonify({'error': 'Order not found'}), 404
                
            updates = []
            params = []
            
            if 'courier_id' in data:
                if data['courier_id']:
                    cursor.execute("SELECT user_id FROM courier_profiles WHERE user_id = %s", (data['courier_id'],))
                    if not cursor.fetchone():
                        return jsonify({'error': 'Courier not found'}), 404
                updates.append("courier_id = %s")
                params.append(data['courier_id'])
                
            if 'note' in data:
                updates.append("note = %s")
                params.append(data['note'])
                
            if 'status' in data:
                updates.append("status = %s")
                params.append(data['status'])
                order['status'] = data['status']  # Для возврата
                
            if 'payment_type' in data:
                updates.append("payment_type = %s")
                params.append(data['payment_type'])
                
            if 'delivery_time_type' in data:
                updates.append("delivery_time_type = %s")
                params.append(data['delivery_time_type'])
                
                if data['delivery_time_type'] == 'specific_time':
                    if not data.get('delivery_time'):
                        return jsonify({'error': 'Delivery time required for specific_time type'}), 400
                    try:
                        delivery_time = datetime.strptime(data['delivery_time'], '%H:%M:%S').time()
                        updates.append("delivery_time = %s")
                        params.append(delivery_time)
                    except ValueError:
                        return jsonify({'error': 'Invalid delivery_time format. Use HH:MM:SS'}), 400
                else:
                    updates.append("delivery_time = NULL")

            if updates:
                sql = f"UPDATE orders SET {', '.join(updates)} WHERE id = %s"
                cursor.execute(sql, tuple(params + [order_id]))
                
            # Обновление товаров/услуг
            if 'items' in data:
                # Удаляем старые
                cursor.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
                
                # Добавляем новые
                if data['items'] and len(data['items']) > 0:
                    items_for_insert = []
                    city_id = order['city_id']
                    price_type_id = order['price_type_id']
                    
                    for item in data['items']:
                        if 'service_id' not in item or 'quantity' not in item:
                            conn.rollback()
                            return jsonify({'error': 'Each item must have service_id and quantity'}), 400
                            
                        cursor.execute("SELECT id FROM services WHERE id = %s", (item['service_id'],))
                        if not cursor.fetchone():
                            conn.rollback()
                            return jsonify({'error': f"Service {item['service_id']} not found"}), 404
                            
                        quantity = Decimal(str(item['quantity']))
                        
                        cursor.execute("""
                            SELECT price FROM service_prices 
                            WHERE service_id = %s AND city_id = %s AND price_type_id = %s
                        """, (item['service_id'], city_id, price_type_id))
                        price_row = cursor.fetchone()
                        
                        price = None
                        total_price = None
                        
                        if price_row and price_row['price'] is not None:
                            price = Decimal(str(price_row['price']))
                            total_price = price * quantity
                            
                        items_for_insert.append((order_id, item['service_id'], quantity, price, total_price))
                        
                    if items_for_insert:
                        sql_items = """
                            INSERT INTO order_items (order_id, service_id, quantity, price, total_price)
                            VALUES (%s, %s, %s, %s, %s)
                        """
                        cursor.executemany(sql_items, items_for_insert)

            conn.commit()
            
            # Возвращаем обновленный заказ
            cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            updated = cursor.fetchone()
            if updated.get('delivery_date'): updated['delivery_date'] = updated['delivery_date'].isoformat()
            if updated.get('created_at'): updated['created_at'] = updated['created_at'].isoformat()
            if updated.get('delivery_time') and hasattr(updated['delivery_time'], 'seconds'):
                hours, remainder = divmod(updated['delivery_time'].seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                updated['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                
            return jsonify(updated), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# Удаление заказа
# -------------------------------------------------------------
@operator_bp.route('/orders/<int:order_id>', methods=['DELETE'])
@roles_required('admin')
def delete_order(order_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM orders WHERE id = %s", (order_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Order not found'}), 404
                
            # Каскадное удаление order_items сработает благодаря FK (ON DELETE CASCADE)
            cursor.execute("DELETE FROM orders WHERE id = %s", (order_id,))
            conn.commit()
            
        return jsonify({'message': 'Order deleted successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

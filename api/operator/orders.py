from flask import Blueprint, jsonify, request, session
from datetime import datetime, date, timedelta
from decimal import Decimal
from db import Db
from . import operator_bp
from decorators import roles_required
from all_types_description import PaymentTypes, DeliveryTimes, OrderStatuses

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
        return jsonify({'error': 'Заказ должен содержать хотя бы одну услугу'}), 400

    if data['payment_type'] not in PaymentTypes.CHOICES:
        return jsonify({'error': f"Недопустимый тип оплаты. Допустимые: {', '.join(PaymentTypes.CHOICES)}"}), 400
        
    if data['delivery_time_type'] not in DeliveryTimes.CHOICES:
        return jsonify({'error': f"Недопустимый тип времени доставки. Допустимые: {', '.join(DeliveryTimes.CHOICES)}"}), 400
        
    try:
        delivery_date = datetime.strptime(data['delivery_date'], '%Y-%m-%d').date()
        today = date.today()
        if delivery_date < today:
            return jsonify({'error': 'Дата доставки не может быть в прошлом'}), 400
            
        delivery_time = None
        if data['delivery_time_type'] == DeliveryTimes.SPECIFIC_TIME:
            if not data.get('delivery_time'):
                return jsonify({'error': 'Для указанного типа времени доставки требуется точное время (delivery_time)'}), 400
            delivery_time = datetime.strptime(data['delivery_time'], '%H:%M:%S').time()
    except ValueError as e:
        return jsonify({'error': f'Неправильный формат даты или времени: {str(e)}'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Загрузка данных клиента, проверка адреса, телефона
            cursor.execute("SELECT price_type_id FROM clients WHERE id = %s AND is_active = 1", (data['client_id'],))
            client = cursor.fetchone()
            if not client:
                return jsonify({'error': 'Активный клиент не найден'}), 404
            client_price_type_id = client['price_type_id']
                
            cursor.execute("""
                SELECT city_id FROM client_addresses 
                WHERE id = %s AND client_id = %s
            """, (data['client_address_id'], data['client_id']))
            address_info = cursor.fetchone()
            if not address_info:
                return jsonify({'error': 'Адрес клиента не найден или не принадлежит указанному клиенту'}), 404
            client_city_id = address_info['city_id']
                
            cursor.execute("""
                SELECT id FROM client_phones 
                WHERE id = %s AND client_id = %s
            """, (data['client_phone_id'], data['client_id']))
            if not cursor.fetchone():
                return jsonify({'error': 'Телефон клиента не найден или не принадлежит указанному клиенту'}), 404
                
            # Проверка курьера (если передан)
            if data.get('courier_id'):
                cursor.execute("SELECT user_id FROM courier_profiles WHERE user_id = %s", (data['courier_id'],))
                if not cursor.fetchone():
                    return jsonify({'error': 'Профиль курьера не найден'}), 404

            # 2. Создание заголовка заказа (создаем пустой total_amount=0, потом обновим)
            sql_order = """
                INSERT INTO orders (client_id, client_address_id, client_phone_id, courier_id, 
                                  user_id, note, delivery_date, delivery_time_type, 
                                  delivery_time, payment_type, cash_amount, card_amount, status, total_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            user_id = session.get('user_id', 1)  # Дефолт 1 
            order_params = (
                data['client_id'], data['client_address_id'], data['client_phone_id'], 
                data.get('courier_id'), user_id, data.get('note'), 
                delivery_date, data['delivery_time_type'], delivery_time, 
                data['payment_type'], data.get('cash_amount'), data.get('card_amount'), OrderStatuses.PENDING, 0.00
            )
            cursor.execute(sql_order, order_params)
            order_id = cursor.lastrowid
            
            # 3. Добавление услуг (items) и расчет суммы
            total_order_price = Decimal('0.0')
            items_for_insert = []
            
            # Вспомогательный массив для расчета скидок
            order_items_calculated = []

            for item in data['items']:
                if 'service_id' not in item or 'quantity' not in item:
                    conn.rollback()
                    return jsonify({'error': 'Каждая позиция (item) должна содержать service_id и quantity'}), 400
                    
                service_id = item['service_id']
                quantity = Decimal(str(item['quantity']))
                
                # Поиск цены для данной услуги в данном городе по данному типу прайса клиента
                cursor.execute("""
                    SELECT price FROM service_prices 
                    WHERE service_id = %s AND city_id = %s AND price_type_id = %s
                """, (service_id, client_city_id, client_price_type_id))
                price_row = cursor.fetchone()
                
                price = None
                total_item_price = None
                
                if price_row and price_row['price'] is not None:
                    price = Decimal(str(price_row['price']))
                    total_item_price = price * quantity
                    total_order_price = total_order_price + total_item_price
                    
                items_for_insert.append((order_id, service_id, quantity, price, total_item_price))
                order_items_calculated.append({
                    'service_id': service_id,
                    'quantity': quantity,
                    'price': price,
                    'total_price': total_item_price or Decimal('0.0')
                })
            
            sql_items = """
                INSERT INTO order_items (order_id, service_id, quantity, price, total_price)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.executemany(sql_items, items_for_insert)
            
            # 4. Система скидок
            applied_discounts = []
            if total_order_price > 0:
                now = datetime.now()
                current_date = now.date()
                current_time = now.time()
                
                # Загружаем все потенциально доступные скидки (активные + подходящие по времени и лимитам)
                discount_sql = """
                    SELECT 
                        d.*,
                        GROUP_CONCAT(DISTINCT dc.city_id) as city_ids,
                        GROUP_CONCAT(DISTINCT ds.service_id) as service_ids,
                        GROUP_CONCAT(DISTINCT dp.price_type_id) as price_type_ids
                    FROM discounts d
                    LEFT JOIN discount_cities dc ON d.id = dc.discount_id
                    LEFT JOIN discount_services ds ON d.id = ds.discount_id
                    LEFT JOIN discount_price_types dp ON d.id = dp.discount_id
                    WHERE d.is_active = 1
                      AND (d.start_date IS NULL OR d.start_date <= %s)
                      AND (d.end_date IS NULL OR d.end_date >= %s)
                      AND (d.start_time IS NULL OR d.start_time <= %s)
                      AND (d.end_time IS NULL OR d.end_time >= %s)
                      AND (d.limit_count IS NULL OR d.usage_count < d.limit_count)
                    GROUP BY d.id
                """
                cursor.execute(discount_sql, (current_date, current_date, current_time, current_time))
                potential_discounts = cursor.fetchall()
                
                valid_discounts = []
                client_order_count = None  # Кэш для N-го заказа
                
                for d in potential_discounts:
                    # Разбираем GROUP_CONCAT
                    d_cities = [int(x) for x in d['city_ids'].split(',')] if d['city_ids'] else []
                    d_services = [int(x) for x in d['service_ids'].split(',')] if d['service_ids'] else []
                    d_prices = [int(x) for x in d['price_type_ids'].split(',')] if d['price_type_ids'] else []
                    
                    # Проверка города
                    if d_cities and client_city_id not in d_cities:
                        continue
                        
                    # Проверка типа прайс-листа
                    if d_prices and client_price_type_id not in d_prices:
                        continue
                        
                    # Определение базовой суммы для скидки (eligible_amount)
                    eligible_amount = Decimal('0.0')
                    if d_services:
                        # Если скидка привязана к услугам — считаем сумму только по этим услугам
                        has_service = False
                        for item in order_items_calculated:
                            if item['service_id'] in d_services:
                                has_service = True
                                eligible_amount = eligible_amount + Decimal(str(item['total_price']))
                        if not has_service:
                            continue
                    else:
                        # Если не привязана, скидка применяется ко всему заказу
                        eligible_amount = total_order_price

                    if eligible_amount <= 0:
                        continue

                    # Расчет размера самой скидки
                    amount = Decimal('0.0')
                    d_type = d['discount_type']
                    val = Decimal(str(d['value'])) if d.get('value') is not None else Decimal('0.0')
                    
                    if d_type == 'fixed_amount':
                        amount = min(val, eligible_amount)
                    elif d_type == 'percentage':
                        amount = (eligible_amount * val) / Decimal('100.0')
                    elif d_type == 'fixed_price':
                        if eligible_amount > val:
                            amount = eligible_amount - val
                    elif d_type == 'free_n_th_order':
                        nth = d.get('nth_order')
                        if nth and nth > 0:
                            if client_order_count is None:
                                cursor.execute("SELECT COUNT(*) as count FROM orders WHERE client_id = %s", (data['client_id'],))
                                client_order_count = cursor.fetchone()['count']
                            if (client_order_count + 1) % nth == 0:
                                amount = eligible_amount
                    
                    if amount > 0:
                        valid_discounts.append({
                            'discount_id': d['id'],
                            'amount': amount,
                            'is_combinable': bool(d['is_combinable'])
                        })
                
                # Выбор оптимальной комбинации скидок
                combinable = [d for d in valid_discounts if d['is_combinable']]
                non_combinable = [d for d in valid_discounts if not d['is_combinable']]
                
                combinable_total = sum(d['amount'] for d in combinable)
                best_nc = max(non_combinable, key=lambda x: x['amount']) if non_combinable else None
                best_nc_amount = best_nc['amount'] if best_nc else Decimal('0.0')
                
                chosen_discounts = []
                if combinable_total > best_nc_amount:
                    # Применяем все комбинируемые скидки, следим чтобы общая скидка не превысила сумму заказа
                    remaining = total_order_price
                    for d in combinable:
                        amt = min(d['amount'], remaining)
                        if amt > 0:
                            chosen_discounts.append({'id': d['discount_id'], 'amount': amt})
                            remaining -= amt
                elif best_nc:
                    # Применяем лучшую некомбинируемую скидку
                    amt = min(best_nc_amount, total_order_price)
                    if amt > 0:
                        chosen_discounts.append({'id': best_nc['discount_id'], 'amount': amt})

                # Запись скидок в БД
                for cd in chosen_discounts:
                    cursor.execute("""
                        INSERT INTO order_discounts (order_id, discount_id, discount_amount) 
                        VALUES (%s, %s, %s)
                    """, (order_id, cd['id'], cd['amount']))
                    cursor.execute("UPDATE discounts SET usage_count = usage_count + 1 WHERE id = %s", (cd['id'],))
                    applied_discounts.append(cd)

            # Вычисляем финальную сумму заказа с учетом скидок
            total_discount_amount = sum(d['amount'] for d in applied_discounts)
            final_order_price = total_order_price - total_discount_amount
            if final_order_price < 0:
                final_order_price = Decimal('0.0')

            # Обновляем total_amount в заказах
            cursor.execute("UPDATE orders SET total_amount = %s WHERE id = %s", (final_order_price, order_id))

            # 5. Обработка кредита
            if data['payment_type'] == PaymentTypes.CREDIT and final_order_price > 0:
                cursor.execute("SELECT id, credit_limit, used_credit FROM client_credits WHERE client_id = %s FOR UPDATE", 
                              (data['client_id'],))
                credit_row = cursor.fetchone()
                
                if not credit_row:
                    # Разрешен овердрафт или мы просто создаем нулевой лимит?
                    # В прошлой версии создавался нулевой лимит:
                    cursor.execute("INSERT INTO client_credits (client_id, credit_limit, used_credit) VALUES (%s, %s, %s)",
                                  (data['client_id'], 0, 0))
                    credit_id = cursor.lastrowid
                    available = Decimal('0.0')
                    used = Decimal('0.0')
                else:
                    credit_id = credit_row['id']
                    limit = Decimal(str(credit_row.get('credit_limit') or 0)) 
                    used = Decimal(str(credit_row.get('used_credit') or 0))
                    available = limit - used
                    
                if available < final_order_price:
                    conn.rollback()
                    return jsonify({
                        'error': 'Недостаточно кредитного лимита',
                        'available_credit': float(available),
                        'required_amount': float(final_order_price)
                    }), 400
                    
                new_used = used + final_order_price
                cursor.execute("UPDATE client_credits SET used_credit = %s WHERE id = %s", (new_used, credit_id))
                
                cursor.execute("""
                    INSERT INTO credit_payments (client_credit_id, order_id, payment_type, amount, description)
                    VALUES (%s, %s, %s, %s, %s)
                """, (credit_id, order_id, 'charge', final_order_price, f'Списание за заказ #{order_id}'))

            conn.commit()
            
            # 6. Возвращаем созданный заказ со всеми деталями
            cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            new_order = cursor.fetchone()
            
            # Форматирование дат и полей для JSON
            if new_order.get('delivery_date'): new_order['delivery_date'] = new_order['delivery_date'].isoformat()
            if new_order.get('created_at'): new_order['created_at'] = new_order['created_at'].isoformat()
            if new_order.get('delivery_time') and hasattr(new_order['delivery_time'], 'seconds'):
                hours, remainder = divmod(new_order['delivery_time'].seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                new_order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                
            new_order['total_order_price'] = float(total_order_price)
            new_order['total_discount_amount'] = float(total_discount_amount)
            new_order['total_amount'] = float(final_order_price)
            
            if new_order.get('cash_amount') is not None: new_order['cash_amount'] = float(new_order['cash_amount'])
            if new_order.get('card_amount') is not None: new_order['card_amount'] = float(new_order['card_amount'])
            
            # Добавим для полноты ответа скидки и услуги
            cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
            new_order['items'] = cursor.fetchall()
            for it in new_order['items']:
                if it.get('created_at'): it['created_at'] = it['created_at'].isoformat()
                
            cursor.execute("SELECT * FROM order_discounts WHERE order_id = %s", (order_id,))
            new_order['applied_discounts'] = cursor.fetchall()
            for dc in new_order['applied_discounts']:
                if dc.get('created_at'): dc['created_at'] = dc['created_at'].isoformat()
                
            return jsonify(new_order), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# Мониторинг заказов
# -------------------------------------------------------------
@operator_bp.route('/monitoring', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def monitoring_orders():
    lang = request.args.get('lang', 'ru')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    offset = (page - 1) * per_page
    
    delivery_date = request.args.get('delivery_date', type=str)
    phone = request.args.get('phone', type=str)
    
    conditions = []
    params = []
    
    if delivery_date:
        try:
            delivery_date_obj = datetime.strptime(delivery_date, '%Y-%m-%d').date()
            conditions.append("o.delivery_date = %s")
            params.append(delivery_date_obj)
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты. Используйте YYYY-MM-DD'}), 400
            
    if phone:
        conditions.append("cp.phone LIKE %s")
        params.append(f"%{phone}%")
        
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Подсчет количества
            count_sql = f"""
                SELECT COUNT(DISTINCT o.id) as total 
                FROM orders o
                LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
                {where_clause}
            """
            cursor.execute(count_sql, tuple(params))
            total = cursor.fetchone()['total']
            
            # Получение списка заказов
            sql = f"""
                SELECT 
                    o.id,
                    o.client_id,
                    c.full_name as client_name,
                    cp.phone as client_phone,
                    ca.address_line as client_address,
                    city.name as city_name,
                    o.delivery_time_type,
                    o.delivery_time,
                    o.payment_type,
                    o.status,
                    o.total_amount,
                    o.cash_amount,
                    o.card_amount,
                    u.full_name as operator_name,
                    cour_u.full_name as courier_name
                FROM orders o
                LEFT JOIN clients c ON o.client_id = c.id
                LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
                LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
                LEFT JOIN cities city ON ca.city_id = city.id
                LEFT JOIN users u ON o.user_id = u.id
                LEFT JOIN courier_profiles cprof ON o.courier_id = cprof.user_id
                LEFT JOIN users cour_u ON cprof.user_id = cour_u.id
                {where_clause}
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """
            query_params = params + [per_page, offset]
            cursor.execute(sql, tuple(query_params))
            orders = cursor.fetchall()
            
            if not orders:
                return jsonify({
                    'orders': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page,
                }), 200

            order_ids = [order['id'] for order in orders]
            placeholders = ', '.join(['%s'] * len(order_ids))

            # Получение услуг по заказам
            items_sql = f"""
                SELECT oi.order_id, oi.service_id, s.name as service_name, oi.quantity, oi.price, oi.total_price
                FROM order_items oi
                JOIN services s ON oi.service_id = s.id
                WHERE oi.order_id IN ({placeholders})
            """
            cursor.execute(items_sql, tuple(order_ids))
            items = cursor.fetchall()

            # Получение скидок по заказам
            discounts_sql = f"""
                SELECT od.order_id, d.name as discount_name, d.discount_type, od.discount_amount
                FROM order_discounts od
                JOIN discounts d ON od.discount_id = d.id
                WHERE od.order_id IN ({placeholders})
            """
            cursor.execute(discounts_sql, tuple(order_ids))
            discounts = cursor.fetchall()
            
            # Группировка
            items_by_order = {}
            for item in items:
                o_id = item['order_id']
                if o_id not in items_by_order:
                    items_by_order[o_id] = []
                items_by_order[o_id].append(item)
                
            discounts_by_order = {}
            for d in discounts:
                o_id = d['order_id']
                if o_id not in discounts_by_order:
                    discounts_by_order[o_id] = []
                discounts_by_order[o_id].append(d)

            # Форматирование ответа
            for order in orders:
                if order.get('delivery_time') and hasattr(order['delivery_time'], 'seconds'):
                    hours, remainder = divmod(order['delivery_time'].seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                    
                # Локализация типов
                time_type = order.get('delivery_time_type')
                time_type_lang = DeliveryTimes.LABELS.get(time_type, {}) if time_type else {}
                order['delivery_time_type_label'] = time_type_lang.get(lang) or time_type_lang.get('ru')
                
                pay_type = order.get('payment_type')
                payment_type_lang = PaymentTypes.LABELS.get(pay_type, {}) if pay_type else {}
                order['payment_type_label'] = payment_type_lang.get(lang) or payment_type_lang.get('ru')
                
                status_val = order.get('status')
                status_lang = OrderStatuses.LABELS.get(status_val, {}) if status_val else {}
                order['status_label'] = status_lang.get(lang) or status_lang.get('ru')

                order_items = items_by_order.get(order['id'], [])
                order_discounts = discounts_by_order.get(order['id'], [])
                
                # Теперь мы не вычисляем сумму заново, а отдаем ту, что сохранилась на момент создания (чтобы цены не "поплыли").
                # Суммы отдельно по услугам и скидкам остаются историческими, так как они копируются построчно в order_items и order_discounts
                order['services'] = order_items
                order['discounts'] = order_discounts
                
                # Превращаем Decimal в float для JSON
                order['total_amount'] = float(order['total_amount'])
                if order.get('cash_amount') is not None: order['cash_amount'] = float(order['cash_amount'])
                if order.get('card_amount') is not None: order['card_amount'] = float(order['card_amount'])
                
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
# История заказов конкретного клиента
# -------------------------------------------------------------
@operator_bp.route('/clients/<int:client_id>/orders', methods=['GET'])
@roles_required('admin', 'operator', 'courier', 'warehouse')
def client_order_history(client_id):
    lang = request.args.get('lang', 'ru')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверка, существует ли клиент
            cursor.execute("SELECT full_name FROM clients WHERE id = %s", (client_id,))
            client = cursor.fetchone()
            if not client:
                return jsonify({'error': 'Клиент не найден'}), 404
                
            # Подсчет количества заказов клиента
            count_sql = "SELECT COUNT(id) as total FROM orders WHERE client_id = %s"
            cursor.execute(count_sql, (client_id,))
            total = cursor.fetchone()['total']
            
            # Получение списка заказов клиента
            sql = """
                SELECT 
                    o.id,
                    o.created_at,
                    o.delivery_date,
                    cp.phone as client_phone,
                    ca.address_line as client_address,
                    o.payment_type,
                    o.total_amount,
                    o.cash_amount,
                    o.card_amount,
                    o.status,
                    o.note,
                    u.full_name as operator_name,
                    cour_u.full_name as courier_name
                FROM orders o
                LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
                LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
                LEFT JOIN users u ON o.user_id = u.id
                LEFT JOIN courier_profiles cprof ON o.courier_id = cprof.user_id
                LEFT JOIN users cour_u ON cprof.user_id = cour_u.id
                WHERE o.client_id = %s
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql, (client_id, per_page, offset))
            orders = cursor.fetchall()
            
            if not orders:
                return jsonify({
                    'client_id': client_id,
                    'client_name': client['full_name'],
                    'orders': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page
                }), 200

            order_ids = [order['id'] for order in orders]
            placeholders = ', '.join(['%s'] * len(order_ids))

            # Получение услуг по заказам
            items_sql = f"""
                SELECT oi.order_id, oi.service_id, s.name as service_name, oi.quantity, oi.price, oi.total_price
                FROM order_items oi
                JOIN services s ON oi.service_id = s.id
                WHERE oi.order_id IN ({placeholders})
            """
            cursor.execute(items_sql, tuple(order_ids))
            items = cursor.fetchall()

            # Получение скидок по заказам
            discounts_sql = f"""
                SELECT od.order_id, d.name as discount_name, d.discount_type, od.discount_amount
                FROM order_discounts od
                JOIN discounts d ON od.discount_id = d.id
                WHERE od.order_id IN ({placeholders})
            """
            cursor.execute(discounts_sql, tuple(order_ids))
            discounts = cursor.fetchall()
            
            # Группировка
            items_by_order = {}
            for item in items:
                o_id = item['order_id']
                if o_id not in items_by_order:
                    items_by_order[o_id] = []
                items_by_order[o_id].append(item)
                
            discounts_by_order = {}
            for d in discounts:
                o_id = d['order_id']
                if o_id not in discounts_by_order:
                    discounts_by_order[o_id] = []
                discounts_by_order[o_id].append(d)

            # Форматирование ответа
            for order in orders:
                if order.get('delivery_date'): order['delivery_date'] = order['delivery_date'].isoformat()
                if order.get('created_at'): order['created_at'] = order['created_at'].isoformat()
                
                # Локализация типов
                pay_type = order.get('payment_type')
                payment_type_lang = PaymentTypes.LABELS.get(pay_type, {}) if pay_type else {}
                order['payment_type_label'] = payment_type_lang.get(lang) or payment_type_lang.get('ru')
                
                status_val = order.get('status')
                status_lang = OrderStatuses.LABELS.get(status_val, {}) if status_val else {}
                order['status_label'] = status_lang.get(lang) or status_lang.get('ru')

                # Превращаем Decimal в float
                order['total_amount'] = float(order['total_amount'])
                if order.get('cash_amount') is not None: order['cash_amount'] = float(order['cash_amount'])
                if order.get('card_amount') is not None: order['card_amount'] = float(order['card_amount'])

                order['services'] = items_by_order.get(order['id'], [])
                order['discounts'] = discounts_by_order.get(order['id'], [])
                
        pages = (total + per_page - 1) // per_page if total > 0 else 1
            
        return jsonify({
            'client_id': client_id,
            'client_name': client['full_name'],
            'orders': orders,
            'total': total,
            'pages': pages,
            'current_page': page
        }), 200
        
    finally:
        conn.close()

# -------------------------------------------------------------
# Получение информации о курьерах на определенную дату
# -------------------------------------------------------------
@operator_bp.route('/couriers_info', methods=['GET'])
@roles_required('admin', 'operator')
def get_couriers_info():
    date_str = request.args.get('date', type=str)
    
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты. Используйте YYYY-MM-DD'}), 400
    else:
        target_date = date.today()
        
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Получаем список курьеров, их данные, телефоны, транспорт и количество заказов на выбранную дату
            sql = """
                SELECT 
                    cp.user_id as courier_id,
                    u.full_name as courier_name,
                    u.phone as courier_phone,
                    u.is_active,
                    t.number as transport_number,
                    COUNT(o.id) as orders_count,
                    GROUP_CONCAT(DISTINCT c.name SEPARATOR ', ') as cities,
                    GROUP_CONCAT(DISTINCT d.name SEPARATOR ', ') as districts
                FROM courier_profiles cp
                JOIN users u ON cp.user_id = u.id
                LEFT JOIN transports t ON cp.transport_id = t.id
                LEFT JOIN orders o ON o.courier_id = cp.user_id AND o.delivery_date = %s
                LEFT JOIN courier_districts cd ON cp.user_id = cd.courier_id
                LEFT JOIN districts d ON cd.district_id = d.id
                LEFT JOIN cities c ON d.city_id = c.id
                WHERE u.role = 'courier'
                GROUP BY cp.user_id
                ORDER BY courier_name
            """
            cursor.execute(sql, (target_date,))
            couriers = cursor.fetchall()

            for courier in couriers:
                courier['is_active'] = bool(courier['is_active'])
            
            return jsonify({
                'date': target_date.isoformat(),
                'couriers': couriers
            }), 200
            
    finally:
        conn.close()

# -------------------------------------------------------------
# Мониторинг заказов конкретного курьера
# -------------------------------------------------------------
@operator_bp.route('/specific_courier_info/<int:courier_id>', methods=['GET'])
@roles_required('admin', 'operator', 'courier')
def get_specific_courier_info(courier_id):
    lang = request.args.get('lang', 'ru')
    date_str = request.args.get('date', type=str)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты. Используйте YYYY-MM-DD'}), 400
    else:
        target_date = date.today()
        
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Проверка, существует ли курьер
            cursor.execute("SELECT full_name FROM users WHERE id = %s AND role = 'courier'", (courier_id,))
            courier = cursor.fetchone()
            if not courier:
                return jsonify({'error': 'Курьер не найден'}), 404
                
            # Подсчет количества заказов курьера
            count_sql = "SELECT COUNT(id) as total FROM orders WHERE courier_id = %s AND delivery_date = %s"
            cursor.execute(count_sql, (courier_id, target_date))
            total = cursor.fetchone()['total']
            
            # Получение списка заказов как в мониторинге
            sql = """
                SELECT 
                    o.id,
                    o.client_id,
                    c.full_name as client_name,
                    cp.phone as client_phone,
                    ca.address_line as client_address,
                    city.name as city_name,
                    o.delivery_time_type,
                    o.delivery_time,
                    o.payment_type,
                    o.status,
                    o.total_amount,
                    o.cash_amount,
                    o.card_amount,
                    u.full_name as operator_name,
                    cour_u.full_name as courier_name
                FROM orders o
                LEFT JOIN clients c ON o.client_id = c.id
                LEFT JOIN client_phones cp ON o.client_phone_id = cp.id
                LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
                LEFT JOIN cities city ON ca.city_id = city.id
                LEFT JOIN users u ON o.user_id = u.id
                LEFT JOIN courier_profiles cprof ON o.courier_id = cprof.user_id
                LEFT JOIN users cour_u ON cprof.user_id = cour_u.id
                WHERE o.courier_id = %s AND o.delivery_date = %s
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql, (courier_id, target_date, per_page, offset))
            orders = cursor.fetchall()
            
            if not orders:
                return jsonify({
                    'courier_id': courier_id,
                    'courier_name': courier['full_name'],
                    'date': target_date.isoformat(),
                    'orders': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page
                }), 200

            order_ids = [order['id'] for order in orders]
            placeholders = ', '.join(['%s'] * len(order_ids))

            # Получение услуг по заказам
            items_sql = f"""
                SELECT oi.order_id, oi.service_id, s.name as service_name, oi.quantity, oi.price, oi.total_price
                FROM order_items oi
                JOIN services s ON oi.service_id = s.id
                WHERE oi.order_id IN ({placeholders})
            """
            cursor.execute(items_sql, tuple(order_ids))
            items = cursor.fetchall()

            # Получение скидок по заказам
            discounts_sql = f"""
                SELECT od.order_id, d.name as discount_name, d.discount_type, od.discount_amount
                FROM order_discounts od
                JOIN discounts d ON od.discount_id = d.id
                WHERE od.order_id IN ({placeholders})
            """
            cursor.execute(discounts_sql, tuple(order_ids))
            discounts = cursor.fetchall()
            
            # Группировка
            items_by_order = {}
            for item in items:
                o_id = item['order_id']
                if o_id not in items_by_order:
                    items_by_order[o_id] = []
                items_by_order[o_id].append(item)
                
            discounts_by_order = {}
            for d in discounts:
                o_id = d['order_id']
                if o_id not in discounts_by_order:
                    discounts_by_order[o_id] = []
                discounts_by_order[o_id].append(d)

            # Форматирование ответа
            for order in orders:
                if order.get('delivery_time') and hasattr(order['delivery_time'], 'seconds'):
                    hours, remainder = divmod(order['delivery_time'].seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    order['delivery_time'] = f"{hours:02}:{minutes:02}:{seconds:02}"
                    
                # Локализация типов
                time_type = order.get('delivery_time_type')
                time_type_lang = DeliveryTimes.LABELS.get(time_type, {}) if time_type else {}
                order['delivery_time_type_label'] = time_type_lang.get(lang) or time_type_lang.get('ru')
                
                pay_type = order.get('payment_type')
                payment_type_lang = PaymentTypes.LABELS.get(pay_type, {}) if pay_type else {}
                order['payment_type_label'] = payment_type_lang.get(lang) or payment_type_lang.get('ru')
                
                status_val = order.get('status')
                status_lang = OrderStatuses.LABELS.get(status_val, {}) if status_val else {}
                order['status_label'] = status_lang.get(lang) or status_lang.get('ru')

                order['services'] = items_by_order.get(order['id'], [])
                order['discounts'] = discounts_by_order.get(order['id'], [])
                
                order['total_amount'] = float(order['total_amount'])
                if order.get('cash_amount') is not None: order['cash_amount'] = float(order['cash_amount'])
                if order.get('card_amount') is not None: order['card_amount'] = float(order['card_amount'])
                
        pages = (total + per_page - 1) // per_page if total > 0 else 1
            
        return jsonify({
            'courier_id': courier_id,
            'courier_name': courier['full_name'],
            'date': target_date.isoformat(),
            'orders': orders,
            'total': total,
            'pages': pages,
            'current_page': page
        }), 200
        
    finally:
        conn.close()

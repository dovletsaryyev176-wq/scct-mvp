from flask import jsonify, request, session
from datetime import date, datetime
from decimal import Decimal
from db import Db
from decorators import roles_required
from all_types_description import OrderStatuses, PaymentTypes
from . import accounter_bp

# -------------------------------------------------------------
# 1. Список курьеров с долгами (ожидающих кассы на дату)
# -------------------------------------------------------------
@accounter_bp.route('/couriers/debt', methods=['GET'])
@roles_required('admin', 'operator', 'accounter')
def get_couriers_debt():
    target_date_str = request.args.get('date')
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты. Ожидается YYYY-MM-DD'}), 400
    else:
        target_date = date.today()

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Получаем список всех курьеров, у которых были заказы ИЛИ есть записи о платежах в эту дату
            # Проще собрать статистику по таблице заказов + таблице платежей, сгруппировав по курьеру.
            
            # Узнаем общее число заказов и число исполненных заказов курьера за день
            orders_sql = """
                SELECT 
                    o.courier_id, 
                    u.full_name as courier_name,
                    COUNT(o.id) as total_orders,
                    SUM(CASE WHEN o.status = %s THEN 1 ELSE 0 END) as completed_orders
                FROM orders o
                JOIN users u ON o.courier_id = u.id
                WHERE o.delivery_date = %s
                GROUP BY o.courier_id, u.full_name
            """
            cursor.execute(orders_sql, (OrderStatuses.DELIVERED, target_date))
            orders_stats = cursor.fetchall()

            # Узнаем долги (только то, что физически у них на руках: is_handed_over = FALSE)
            # При этом группируем по типу оплаты (cash / cash_and_card / card - хотя card по сути безнал онлайн)
            debt_sql = """
                SELECT 
                    courier_id,
                    payment_type,
                    SUM(cash_amount) as total_cash,
                    SUM(card_amount) as total_card
                FROM courier_payments
                WHERE DATE(created_at) = %s AND is_handed_over = FALSE
                GROUP BY courier_id, payment_type
            """
            cursor.execute(debt_sql, (target_date,))
            debt_stats = cursor.fetchall()

            # Собираем все в один ответ
            couriers_dict = {}
            for stat in orders_stats:
                cid = stat['courier_id']
                couriers_dict[cid] = {
                    'courier_id': cid,
                    'courier_name': stat['courier_name'],
                    'total_orders': int(stat['total_orders']),
                    'completed_orders': int(stat['completed_orders']),
                    'debts_by_type': {},
                    'total_cash_debt': 0.0,
                    'total_card_debt': 0.0,
                    'total_debt': 0.0
                }

            # Могут быть курьеры, у которых нет новых заказов на эту дату,
            # но есть платежи (если они выполнили вчерашний заказ сегодня).
            for d in debt_stats:
                cid = d['courier_id']
                if cid not in couriers_dict:
                    # Узнаем имя курьера
                    cursor.execute("SELECT full_name FROM users WHERE id = %s", (cid,))
                    u_row = cursor.fetchone()
                    couriers_dict[cid] = {
                        'courier_id': cid,
                        'courier_name': u_row['full_name'] if u_row else f"Курьер ID {cid}",
                        'total_orders': 0,
                        'completed_orders': 0,
                        'debts_by_type': {},
                        'total_cash_debt': 0.0,
                        'total_card_debt': 0.0,
                        'total_debt': 0.0
                    }

                p_type = d['payment_type']
                cash_sum = float(d['total_cash']) if d['total_cash'] else 0.0
                card_sum = float(d['total_card']) if d['total_card'] else 0.0

                couriers_dict[cid]['debts_by_type'][p_type] = {
                    'cash': cash_sum,
                    'card': card_sum
                }

                couriers_dict[cid]['total_cash_debt'] += cash_sum
                couriers_dict[cid]['total_card_debt'] += card_sum
                couriers_dict[cid]['total_debt'] += (cash_sum + card_sum)

            result_list = list(couriers_dict.values())
            # Сортируем по имени курьера
            result_list.sort(key=lambda x: x['courier_name'])

            return jsonify({
                'date': target_date.isoformat(),
                'couriers': result_list
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 2. Детализация платежей и заказов конкретного курьера за день
# -------------------------------------------------------------
@accounter_bp.route('/couriers/<int:courier_id>/payments', methods=['GET'])
@roles_required('admin', 'operator', 'accounter')
def get_courier_payments_details(courier_id):
    target_date_str = request.args.get('date')
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты'}), 400
    else:
        target_date = date.today()

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Получаем детальный список
            details_sql = """
                SELECT 
                    cp.id as payment_id,
                    cp.payment_type as payment_collected_type,
                    cp.cash_amount,
                    cp.card_amount,
                    cp.created_at as payment_date,
                    cp.is_handed_over,
                    cp.handed_over_at,
                    cp.accounter_note,
                    
                    o.id as order_id,
                    o.client_id,
                    c.full_name as client_name,
                    cphone.phone as client_phone,
                    ca.address_line as client_address,
                    o.status as order_status,
                    o.total_amount as order_total_amount
                FROM courier_payments cp
                JOIN orders o ON cp.order_id = o.id
                LEFT JOIN clients c ON o.client_id = c.id
                LEFT JOIN client_phones cphone ON o.client_phone_id = cphone.id
                LEFT JOIN client_addresses ca ON o.client_address_id = ca.id
                WHERE cp.courier_id = %s AND DATE(cp.created_at) = %s
                ORDER BY cp.created_at DESC
            """
            cursor.execute(details_sql, (courier_id, target_date))
            details = cursor.fetchall()

            for d in details:
                d['cash_amount'] = float(d['cash_amount'])
                d['card_amount'] = float(d['card_amount'])
                d['order_total_amount'] = float(d['order_total_amount']) if d.get('order_total_amount') is not None else 0.0
                if d['payment_date']:
                    d['payment_date'] = d['payment_date'].isoformat()
                if d['handed_over_at']:
                    d['handed_over_at'] = d['handed_over_at'].isoformat()

            return jsonify({
                'date': target_date.isoformat(),
                'courier_id': courier_id,
                'details': details
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 3. Принять кассу (Передача денег бухгалтеру)
# -------------------------------------------------------------
@accounter_bp.route('/couriers/<int:courier_id>/handover', methods=['POST'])
@roles_required('admin', 'accounter')
def accept_courier_handover(courier_id):
    accounter_id = session.get('user_id')
    
    data = request.get_json() or {}
    target_date_str = data.get('date') # Если хотят закрыть долг за вчерашний день
    note = data.get('note') # Заметка бухгалтера

    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Неправильный формат даты'}), 400
    else:
        target_date = date.today()

    conn = Db.get_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            # Находим записи, которые еще не сданы
            find_sql = """
                SELECT id 
                FROM courier_payments 
                WHERE courier_id = %s AND DATE(created_at) = %s AND is_handed_over = FALSE
                FOR UPDATE
            """
            cursor.execute(find_sql, (courier_id, target_date))
            pending_records = cursor.fetchall()

            if not pending_records:
                conn.rollback()
                return jsonify({'error': 'У данного курьера нет несданных платежей на указанную дату'}), 400

            ids = [r['id'] for r in pending_records]
            placeholders = ', '.join(['%s'] * len(ids))
            
            # Обновляем статусы
            update_sql = f"""
                UPDATE courier_payments 
                SET is_handed_over = TRUE, 
                    handed_over_at = NOW(), 
                    accounter_id = %s,
                    accounter_note = %s
                WHERE id IN ({placeholders})
            """
            params = [accounter_id, note] + ids
            cursor.execute(update_sql, tuple(params))
            
            conn.commit()
            
            return jsonify({
                'message': 'Деньги успешно приняты',
                'courier_id': courier_id,
                'date': target_date.isoformat(),
                'records_updated': len(ids)
            }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

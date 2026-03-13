from flask import jsonify, request, session
from datetime import date, datetime
from db import Db
from . import director_bp
from decorators import roles_required

# -------------------------------------------------------------
# 1. Суммарное количество клиентов с распределением по типам цен
# -------------------------------------------------------------
@director_bp.route('/clients/by-price-type', methods=['GET'])
@roles_required('admin', 'director')
def get_clients_by_price_type():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT pt.id, pt.name, COUNT(c.id) as client_count
                FROM price_types pt
                LEFT JOIN clients c ON pt.id = c.price_type_id
                GROUP BY pt.id, pt.name
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            return jsonify({'data': results}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 2. Суммарное количество заблокированного транспорта
# -------------------------------------------------------------
@director_bp.route('/transports/blocked', methods=['GET'])
@roles_required('admin', 'director')
def get_blocked_transports():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT COUNT(id) as blocked_count FROM transports WHERE is_active = FALSE"
            cursor.execute(sql)
            result = cursor.fetchone()
            return jsonify({'blocked_count': result['blocked_count']}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 3. Суммарное количество клиентов по районам городов
# -------------------------------------------------------------
@director_bp.route('/clients/by-district', methods=['GET'])
@roles_required('admin', 'director')
def get_clients_by_district():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            # Считаем уникальных клиентов (COUNT(DISTINCT ca.client_id)) 
            # по каждому району, чтобы если у клиента несколько адресов 
            # в одном районе, он считался 1 раз для этого района.
            sql = """
                SELECT 
                    c.name as city_name, 
                    d.name as district_name, 
                    COUNT(DISTINCT ca.client_id) as client_count
                FROM districts d
                JOIN cities c ON d.city_id = c.id
                LEFT JOIN client_addresses ca ON d.id = ca.district_id
                GROUP BY d.id, c.name, d.name
                ORDER BY c.name, d.name
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            return jsonify({'data': results}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 4. Информация о принятых деньгах бухгалтером
# -------------------------------------------------------------
@director_bp.route('/money/accepted', methods=['GET'])
@roles_required('admin', 'director')
def get_accepted_money():
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
            sql = """
                SELECT 
                    SUM(cash_amount) as total_cash,
                    SUM(card_amount) as total_card
                FROM courier_payments
                WHERE DATE(handed_over_at) = %s AND is_handed_over = TRUE
            """
            cursor.execute(sql, (target_date,))
            res = cursor.fetchone()
            
            cash = float(res['total_cash']) if res and res['total_cash'] else 0.0
            card = float(res['total_card']) if res and res['total_card'] else 0.0
            
            return jsonify({
                'date': target_date.isoformat(),
                'total_cash': cash,
                'total_card': card,
                'total_money': cash + card
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 5. Суммарное количество заказов с распределением по статусу
# -------------------------------------------------------------
@director_bp.route('/orders/by-status', methods=['GET'])
@roles_required('admin', 'director')
def get_orders_by_status():
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
            sql = """
                SELECT status, COUNT(id) as order_count
                FROM orders
                WHERE delivery_date = %s
                GROUP BY status
            """
            cursor.execute(sql, (target_date,))
            results = cursor.fetchall()
            
            total_orders = sum(row['order_count'] for row in results)
            
            return jsonify({
                'date': target_date.isoformat(),
                'total_orders': total_orders,
                'status_distribution': results
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 6. Суммарный доход за каждый месяц текущего года
# -------------------------------------------------------------
@director_bp.route('/money/monthly-income-yearly', methods=['GET'])
@roles_required('admin', 'director')
def get_yearly_monthly_income():
    year_str = request.args.get('year')
    if year_str:
        try:
            target_year = int(year_str)
        except ValueError:
            return jsonify({'error': 'Неправильный формат года'}), 400
    else:
        target_year = date.today().year

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    MONTH(handed_over_at) as month,
                    SUM(cash_amount) as total_cash,
                    SUM(card_amount) as total_card
                FROM courier_payments
                WHERE YEAR(handed_over_at) = %s AND is_handed_over = TRUE
                GROUP BY MONTH(handed_over_at)
                ORDER BY MONTH(handed_over_at)
            """
            cursor.execute(sql, (target_year,))
            rows = cursor.fetchall()
            
            monthly_data = []
            total_year_income = 0.0
            for row in rows:
                cash = float(row['total_cash']) if row['total_cash'] else 0.0
                card = float(row['total_card']) if row['total_card'] else 0.0
                total = cash + card
                total_year_income += total
                monthly_data.append({
                    'month': row['month'],
                    'total_cash': cash,
                    'total_card': card,
                    'total_income': total
                })
                
            return jsonify({
                'year': target_year,
                'total_year_income': total_year_income,
                'months': monthly_data
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# -------------------------------------------------------------
# 7. Суммарный доход за текущий месяц (с фильтром по месяцу и году)
# -------------------------------------------------------------
@director_bp.route('/money/monthly-income', methods=['GET'])
@roles_required('admin', 'director')
def get_monthly_income():
    month_str = request.args.get('month')
    year_str = request.args.get('year')
    
    today = date.today()
    target_month = today.month
    target_year = today.year
    
    try:
        if month_str: target_month = int(month_str)
        if year_str: target_year = int(year_str)
    except ValueError:
        return jsonify({'error': 'Месяц и год должны быть числами'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    SUM(cash_amount) as total_cash,
                    SUM(card_amount) as total_card
                FROM courier_payments
                WHERE MONTH(handed_over_at) = %s 
                  AND YEAR(handed_over_at) = %s 
                  AND is_handed_over = TRUE
            """
            cursor.execute(sql, (target_month, target_year))
            res = cursor.fetchone()
            
            cash = float(res['total_cash']) if res and res['total_cash'] else 0.0
            card = float(res['total_card']) if res and res['total_card'] else 0.0
            
            return jsonify({
                'month': target_month,
                'year': target_year,
                'total_cash': cash,
                'total_card': card,
                'total_income': cash + card
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

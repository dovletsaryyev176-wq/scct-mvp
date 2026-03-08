from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db
import math
from decimal import Decimal


#Взять информацию о кредите конкретного клиента
@admin_bp.route('/clients/<int:client_id>/credit', methods=['GET'])
def get_client_credit(client_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Client not found'}), 404
            

            cursor.execute("""
                SELECT id, client_id, credit_limit, used_credit, is_active, created_at 
                FROM client_credits 
                WHERE client_id = %s
            """, (client_id,))
            credit = cursor.fetchone()
            
            if not credit:
                return jsonify({'error': 'Client credit information not found'}), 404
            

            credit['credit_limit'] = float(credit['credit_limit'])
            credit['used_credit'] = float(credit['used_credit'])
            credit['available_credit'] = credit['credit_limit'] - credit['used_credit']
            credit['created_at'] = credit['created_at'].isoformat() if credit['created_at'] else None
            
            return jsonify(credit), 200
    finally:
        conn.close()


#Добавить информацию о кредитах клиенту-установка или обновление лимита
@admin_bp.route('/clients/<int:client_id>/credit', methods=['POST'])
@roles_required('admin')
def set_client_credit_limit(client_id):
    data = request.get_json()
    if 'credit_limit' not in data:
        return jsonify({'error': 'credit_limit is required'}), 400
    
    try:
        new_limit = Decimal(str(data['credit_limit']))
        if new_limit < 0:
            return jsonify({'error': 'credit_limit cannot be negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid credit_limit format'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Client not found'}), 404

            
            cursor.execute("SELECT id FROM client_credits WHERE client_id = %s", (client_id,))
            credit_record = cursor.fetchone()

            if credit_record:
                
                cursor.execute(
                    "UPDATE client_credits SET credit_limit = %s WHERE client_id = %s",
                    (new_limit, client_id)
                )
            else:
                
                cursor.execute(
                    "INSERT INTO client_credits (client_id, credit_limit, used_credit) VALUES (%s, %s, 0.00)",
                    (client_id, new_limit)
                )
            
            conn.commit()
            
            
            cursor.execute("SELECT * FROM client_credits WHERE client_id = %s", (client_id,))
            updated_credit = cursor.fetchone()
            
            updated_credit['credit_limit'] = float(updated_credit['credit_limit'])
            updated_credit['used_credit'] = float(updated_credit['used_credit'])
            
            return jsonify(updated_credit), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


#Информация о платежах кредита
@admin_bp.route('/clients/<int:client_id>/credit/payments', methods=['GET'])
def get_client_credit_payments(client_id):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT id FROM client_credits WHERE client_id = %s", (client_id,))
            credit = cursor.fetchone()
            if not credit:
                return jsonify({'error': 'Client credit information not found'}), 404
            
            client_credit_id = credit['id']

            
            cursor.execute("SELECT COUNT(*) as total FROM credit_payments WHERE client_credit_id = %s", (client_credit_id,))
            total_items = cursor.fetchone()['total']
            total_pages = math.ceil(total_items / per_page)

            #
            cursor.execute("""
                SELECT id, client_credit_id, order_id, payment_type, amount, description, created_at 
                FROM credit_payments 
                WHERE client_credit_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s
            """, (client_credit_id, per_page, offset))
            
            payments = cursor.fetchall()
            for p in payments:
                p['amount'] = float(p['amount'])
                p['created_at'] = p['created_at'].isoformat() if p['created_at'] else None

            return jsonify({
                'client_id': client_id,
                'payments': payments,
                'total': total_items,
                'pages': total_pages,
                'current_page': page,
            }), 200
    finally:
        conn.close()


#Оплата по кредиту-создание платежа или списания
@admin_bp.route('/credit-payments', methods=['POST'])
@roles_required('admin', 'operator')
def create_credit_payment():
    data = request.get_json()
    required = ['client_credit_id', 'amount', 'payment_type']
    
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        amount = Decimal(str(data['amount']))
        if amount <= 0:
            return jsonify({'error': 'Amount must be positive'}), 400
            
        payment_type = data['payment_type']
        if payment_type not in ['payment', 'write_off']:
            return jsonify({'error': "payment_type must be 'payment' or 'write_off'"}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid amount format'}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT id, used_credit FROM client_credits WHERE id = %s FOR UPDATE", (data['client_credit_id'],))
            credit = cursor.fetchone()
            
            if not credit:
                return jsonify({'error': 'Client credit not found'}), 404
            
            current_used = Decimal(str(credit['used_credit']))
            
            if current_used < amount:
                return jsonify({'error': 'Payment amount exceeds used credit'}), 400

            
            new_used = current_used - amount
            cursor.execute(
                "UPDATE client_credits SET used_credit = %s WHERE id = %s",
                (new_used, data['client_credit_id'])
            )

            
            cursor.execute("""
                INSERT INTO credit_payments (client_credit_id, payment_type, amount, description) 
                VALUES (%s, %s, %s, %s)
            """, (data['client_credit_id'], payment_type, amount, data.get('description')))
            
            payment_id = cursor.lastrowid
            conn.commit()

            return jsonify({
                'message': 'Payment successful',
                'payment_id': payment_id,
                'new_used_credit': float(new_used)
            }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


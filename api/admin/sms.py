from flask import jsonify, request, session
from . import admin_bp
from db import Db
from decorators import roles_required
import requests

@admin_bp.route('/sms/send', methods=['POST'])
@roles_required('admin')
def send_sms():
    data = request.get_json() or {}
    phone = data.get('phone')
    text = data.get('text')

    if not phone or not text:
        return jsonify({'error': 'Необходимы phone и text'}), 400

    user_id = session.get('user_id')

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            phones_to_send = []
            if phone.lower() == 'all' or phone.lower() == 'все':
                # Получаем все уникальные номера клиентов
                cursor.execute("SELECT DISTINCT phone FROM client_phones")
                rows = cursor.fetchall()
                phones_to_send = [row['phone'] for row in rows if row.get('phone')]
                target_phone_record = 'все'
            else:
                phones_to_send = [phone]
                target_phone_record = phone

            # Отправляем запросы в стороннее API
            for p in phones_to_send:
                try:
                    payload = {
                        "code": text,
                        "phoneNumber": p
                    }
                    requests.post("https://tagma.biz/otp/send-code", json=payload, timeout=5)
                except Exception as e:
                    print(f"Ошибка при отправке SMS на номер {p}: {e}")
                    # Продолжаем отправлять остальным несмотря на ошибку

            # Сохраняем в историю
            cursor.execute("""
                INSERT INTO sms_history (sender_id, recipient_phone, message_text)
                VALUES (%s, %s, %s)
            """, (user_id, target_phone_record, text))
            
            sms_id = cursor.lastrowid
            conn.commit()

            return jsonify({'message': 'Сообщения успешно отправлены', 'id': sms_id}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/sms', methods=['GET'])
@roles_required('admin')
def get_sms_history():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    sh.id,
                    sh.recipient_phone,
                    sh.message_text,
                    sh.created_at,
                    sh.sender_id,
                    u.full_name as sender_name
                FROM sms_history sh
                LEFT JOIN users u ON sh.sender_id = u.id
                ORDER BY sh.created_at DESC
            """)
            logs = cursor.fetchall()
            
            for log in logs:
                if log['created_at']:
                    log['created_at'] = log['created_at'].isoformat()
                    
            return jsonify(logs), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/sms/<int:sms_id>', methods=['GET'])
@roles_required('admin')
def get_sms_detail(sms_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    sh.id,
                    sh.recipient_phone,
                    sh.message_text,
                    sh.created_at,
                    sh.sender_id,
                    u.full_name as sender_name
                FROM sms_history sh
                LEFT JOIN users u ON sh.sender_id = u.id
                WHERE sh.id = %s
            """, (sms_id,))
            log = cursor.fetchone()
            
            if not log:
                return jsonify({'error': 'Запись не найдена'}), 404
                
            if log['created_at']:
                log['created_at'] = log['created_at'].isoformat()
                
            return jsonify(log), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

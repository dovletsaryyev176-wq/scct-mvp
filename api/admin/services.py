from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db
import math
from decimal import Decimal


#Добавление услуги
@admin_bp.route('/services', methods=['POST'])
@roles_required('admin')
def add_service():
    data = request.get_json()
    name = data.get('name')
    is_active = data.get('is_active', True)
    
    if not name:
        return jsonify({"error": "Название услуги обязательно"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO services (name, is_active) VALUES (%s, %s)",
                (name, is_active)
            )
            service_id = cursor.lastrowid
            conn.commit()
        return jsonify({"message": "Услуга добавлена", "id": service_id}), 201
    finally:
        conn.close()


#Заблокировать или разблокировать услугу
@admin_bp.route('/services/<int:service_id>/toggle', methods=['PATCH'])
@roles_required('admin')
def toggle_service(service_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT is_active FROM services WHERE id = %s", (service_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "Услуга не найдена"}), 404
            
            new_status = not bool(row['is_active'])
            cursor.execute("UPDATE services SET is_active = %s WHERE id = %s", (new_status, service_id))
            conn.commit()
            
        status_text = "активна" if new_status else "заблокирована"
        return jsonify({"message": f"Услуга теперь {status_text}", "is_active": new_status}), 200
    finally:
        conn.close()


#Добавить или изменить цену для конкретной услуги
@admin_bp.route('/services/prices', methods=['POST'])
@roles_required('admin')
def add_or_update_price():
    data = request.get_json()
    service_id = data.get('service_id')
    city_id = data.get('city_id')
    price_type_id = data.get('price_type_id')
    price = data.get('price')

    if not all([service_id, city_id, price_type_id, price is not None]):
        return jsonify({"error": "Не все поля заполнены"}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("""
                SELECT id FROM service_prices 
                WHERE service_id = %s AND city_id = %s AND price_type_id = %s
            """, (service_id, city_id, price_type_id))
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE service_prices SET price = %s WHERE id = %s",
                    (price, existing['id'])
                )
                price_id = existing['id']
                message = "Цена обновлена"
            else:
                cursor.execute("""
                    INSERT INTO service_prices (service_id, city_id, price_type_id, price) 
                    VALUES (%s, %s, %s, %s)
                """, (service_id, city_id, price_type_id, price))
                price_id = cursor.lastrowid
                message = "Цена добавлена"
            
            conn.commit()
        return jsonify({"message": message, "id": price_id}), 201
    finally:
        conn.close()


#Берем информацию по услугам
@admin_bp.route('/services', methods=['GET'])
def get_services():
    city_id = request.args.get('city_id', type=int)
    is_active_str = request.args.get('is_active')

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            sql = "SELECT id, name, is_active FROM services WHERE 1=1"
            params = []

            if is_active_str is not None:
                sql += " AND is_active = %s"
                params.append(is_active_str.lower() == 'true')

            if city_id:
                sql += " AND id IN (SELECT service_id FROM service_prices WHERE city_id = %s)"
                params.append(city_id)

            cursor.execute(sql, tuple(params))
            services = cursor.fetchall()

            for service in services:
                
                price_sql = """
                    SELECT sp.id, sp.city_id, c.name as city_name, sp.price_type_id, pt.name as price_type_name, sp.price
                    FROM service_prices sp
                    LEFT JOIN cities c ON sp.city_id = c.id
                    LEFT JOIN price_types pt ON sp.price_type_id = pt.id
                    WHERE sp.service_id = %s
                """
                price_params = [service['id']]
                if city_id:
                    price_sql += " AND sp.city_id = %s"
                    price_params.append(city_id)
                
                cursor.execute(price_sql, tuple(price_params))
                prices = cursor.fetchall()
                for p in prices: p['price'] = float(p['price'])
                service['prices'] = prices

                
                cursor.execute("""
                    SELECT sr.id, sr.product_id, p.name as product_name, sr.service_type, sr.quantity
                    FROM service_rules sr
                    LEFT JOIN products p ON sr.product_id = p.id
                    WHERE sr.service_id = %s
                """, (service['id'],))
                rules = cursor.fetchall()
                for r in rules: r['quantity'] = float(r['quantity'])
                service['rules'] = rules

        return jsonify(services), 200
    finally:
        conn.close()


#Добавляем правила услуги
@admin_bp.route('/services/<int:service_id>/rules', methods=['POST'])
@roles_required('admin')
def add_service_rule(service_id):
    data = request.get_json()
    product_id = data.get('product_id')
    service_type = data.get('service_type')
    quantity = data.get('quantity')

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT id FROM services WHERE id = %s", (service_id,))
            if not cursor.fetchone(): return jsonify({"error": "Услуга не найдена"}), 404
            
            cursor.execute("SELECT id FROM products WHERE id = %s", (product_id,))
            if not cursor.fetchone(): return jsonify({"error": "Продукт не найден"}), 404

            cursor.execute("""
                INSERT INTO service_rules (service_id, product_id, service_type, quantity)
                VALUES (%s, %s, %s, %s)
            """, (service_id, product_id, service_type, quantity))
            rule_id = cursor.lastrowid
            conn.commit()
            
        return jsonify({"message": "Правило добавлено", "id": rule_id}), 201
    finally:
        conn.close()

#Удаляем правила по услугам
@admin_bp.route('/services/rules/<int:rule_id>', methods=['DELETE'])
@roles_required('admin')
def delete_service_rule(rule_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM service_rules WHERE id = %s", (rule_id,))
            if cursor.rowcount == 0:
                return jsonify({"error": "Правило не найдено"}), 404
            conn.commit()
        return jsonify({"message": "Правило удалено"}), 200
    finally:
        conn.close()


#Удаляем правила по ценам
@admin_bp.route('/services/prices/<int:price_id>', methods=['DELETE'])
@roles_required('admin')
def delete_price(price_id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:

            cursor.execute("DELETE FROM service_prices WHERE id = %s", (price_id,))
            
            if cursor.rowcount == 0:
                return jsonify({"error": "Ценовое правило не найдено"}), 404
            
            conn.commit()
            
        return jsonify({"message": "Ценовое правило удалено"}), 200
    finally:
        conn.close()
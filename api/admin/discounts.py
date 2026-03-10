from flask import jsonify, request
from . import admin_bp
from decorators import roles_required
from db import Db
from all_types_description import DiscountTypes
import datetime


VALID_DISCOUNT_TYPES = set(DiscountTypes.LABELS.keys())


def validate_discount_data(data, is_create=False):

    discount_type = data.get('discount_type')

    if is_create and not discount_type:
        return "Поле 'discount_type' обязательно"

    if discount_type and discount_type not in VALID_DISCOUNT_TYPES:
        valid = ', '.join(VALID_DISCOUNT_TYPES)
        return f"Недопустимый тип скидки '{discount_type}'. Допустимые: {valid}"

    if is_create:
        if not data.get('start_date'): return "Поле 'start_date' обязательно"
        if not data.get('end_date'): return "Поле 'end_date' обязательно"
        if not data.get('start_time'): return "Поле 'start_time' обязательно"
        if not data.get('end_time'): return "Поле 'end_time' обязательно"
        if data.get('limit_count') is None: return "Поле 'limit_count' обязательно"
        if data.get('is_combinable') is None: return "Поле 'is_combinable' (bool) обязательно"

    start = data.get('start_date')
    end = data.get('end_date')
    if start and end and end < start:
        return "'end_date' не может быть раньше 'start_date'"

    if is_create or (discount_type and 'value' in data) or (discount_type and 'nth_order' in data):
        # 1. Скидка на N-й заказ бесплатно
        if discount_type == DiscountTypes.FREE_N_TH_ORDER:
            # Для этого типа value мапится в nth_order
            val = data.get('value')
            if is_create and not val:
                return "Для типа 'free_n_th_order' значение скидки (на какой заказ) передаётся в поле 'value' и обязательно"
            if val is not None and int(val) <= 0:
                return "Значение 'value' (на какой заказ) должно быть больше 0"

        # 2, 3, 5. FIXED_AMOUNT, PERCENTAGE, FIXED_PRICE
        elif discount_type in (DiscountTypes.FIXED_AMOUNT, DiscountTypes.PERCENTAGE, DiscountTypes.FIXED_PRICE):
            val = data.get('value')
            if is_create and val is None:
                return f"Для данного типа скидки ({discount_type}) необходимо указать 'value'"
            
            # Доп. валидация для PERCENTAGE
            if discount_type == DiscountTypes.PERCENTAGE:
                if val is not None and not (0 <= float(val) <= 100):
                    return "Для типа 'percentage' значение 'value' должно быть от 0 до 100"

    return None


def parse_date(value, fmt='%Y-%m-%d'):
    return datetime.datetime.strptime(value, fmt).date() if value else None


def parse_time(value, fmt='%H:%M'):
    return datetime.datetime.strptime(value, fmt).time() if value else None


def serialize_discount(d, lang='ru'):
    if d.get('value') is not None: 
        d['value'] = float(d['value'])
        
    if d.get('start_date'): 
        d['start_date'] = d['start_date'].isoformat()
        
    if d.get('end_date'): 
        d['end_date'] = d['end_date'].isoformat()

    # --- ИСПРАВЛЕННЫЙ БЛОК ДЛЯ ВРЕМЕНИ ---
    for time_field in ['start_time', 'end_time']:
        val = d.get(time_field)
        if val is not None: # Строго проверяем на None (чтобы '00:00:00' не отсеивалось)
            if isinstance(val, datetime.timedelta):
                # Если это timedelta (например, от PyMySQL)
                total_seconds = int(val.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                d[time_field] = f"{hours:02}:{minutes:02}"
            elif isinstance(val, datetime.time):
                # Если это стандартный объект time
                d[time_field] = val.strftime('%H:%M')
            else:
                # Фолбэк для строк
                d[time_field] = str(val)[:5]
    # ---------------------------------------

    d['is_combinable'] = bool(d.get('is_combinable'))
    d['is_active'] = bool(d.get('is_active'))

    for key in ['service_ids', 'city_ids', 'price_type_ids']:
        val = d.get(key)
        # Учитываем, что val может быть не строкой (добавляем str(val))
        d[key] = [int(x) for x in str(val).split(',')] if val else []

    discount_type = d.get('discount_type')
    labels = DiscountTypes.LABELS.get(discount_type, {})
    d['discount_type_label'] = labels.get(lang) or labels.get('ru')

    return d

@admin_bp.route('/discounts', methods=['GET'])
def get_discounts():
    lang = request.args.get('lang', 'ru')
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    d.*,
                    GROUP_CONCAT(DISTINCT ds.service_id) as service_ids,
                    GROUP_CONCAT(DISTINCT dc.city_id) as city_ids,
                    GROUP_CONCAT(DISTINCT dp.price_type_id) as price_type_ids
                FROM discounts d
                LEFT JOIN discount_services ds ON d.id = ds.discount_id
                LEFT JOIN discount_cities dc ON d.id = dc.discount_id
                LEFT JOIN discount_price_types dp ON d.id = dp.discount_id
                GROUP BY d.id
                ORDER BY d.id DESC
            """
            cursor.execute(sql)
            discounts = cursor.fetchall()
            result = [serialize_discount(d, lang) for d in discounts]
        return jsonify(result), 200
    finally:
        conn.close()


@admin_bp.route('/discounts', methods=['POST'])
@roles_required('admin')
def create_discount():
    data = request.json

    error = validate_discount_data(data, is_create=True)
    if error:
        return jsonify({'error': error}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            start_date = parse_date(data.get('start_date'))
            end_date   = parse_date(data.get('end_date'))
            start_time = parse_time(data.get('start_time'))
            end_time   = parse_time(data.get('end_time'))

            # Для FREE_N_TH_ORDER фронтенд пришлёт 'value', а в базе это колонка 'nth_order'
            val = data.get('value')
            nth_order = None
            if data['discount_type'] == DiscountTypes.FREE_N_TH_ORDER:
                nth_order = val
                val = None  # само значение value для этого типа пустое в БД

            sql = """
                INSERT INTO discounts 
                (name, discount_type, value, limit_count, nth_order, start_date, end_date, start_time, end_time, is_combinable, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                data['name'], data['discount_type'], val,
                data.get('limit_count'), nth_order,
                start_date, end_date, start_time, end_time, 
                data.get('is_combinable', False), data.get('is_active', True)
            )
            cursor.execute(sql, params)
            discount_id = cursor.lastrowid

            if 'service_ids' in data and isinstance(data['service_ids'], list):
                for s_id in data['service_ids']:
                    cursor.execute("INSERT INTO discount_services (discount_id, service_id) VALUES (%s, %s)", (discount_id, s_id))

            if 'city_ids' in data and isinstance(data['city_ids'], list):
                for c_id in data['city_ids']:
                    cursor.execute("INSERT INTO discount_cities (discount_id, city_id) VALUES (%s, %s)", (discount_id, c_id))

            if 'price_type_ids' in data and isinstance(data['price_type_ids'], list):
                for p_id in data['price_type_ids']:
                    cursor.execute("INSERT INTO discount_price_types (discount_id, price_type_id) VALUES (%s, %s)", (discount_id, p_id))

            conn.commit()
            return jsonify({"message": "Скидка создана", "id": discount_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@admin_bp.route('/discounts/<int:id>', methods=['PUT'])
@roles_required('admin')
def update_discount(id):
    data = request.json

    error = validate_discount_data(data, is_create=False)
    if error:
        return jsonify({'error': error}), 400

    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, discount_type FROM discounts WHERE id = %s", (id,))
            current_discount = cursor.fetchone()
            if not current_discount:
                return jsonify({'error': 'Скидка не найдена'}), 404

            fields = []
            params = []

            # Особая обработка value vs nth_order
            discount_type = data.get('discount_type', current_discount['discount_type'])
            
            if 'value' in data:
                if discount_type == DiscountTypes.FREE_N_TH_ORDER:
                    fields.append("nth_order = %s")
                    params.append(data['value'])
                    fields.append("value = NULL")
                else:
                    fields.append("value = %s")
                    params.append(data['value'])
                    fields.append("nth_order = NULL")

            mapping = {
                'name': 'name', 'discount_type': 'discount_type',
                'limit_count': 'limit_count', 'is_combinable': 'is_combinable', 
                'is_active': 'is_active'
            }
            
            for key, col in mapping.items():
                if key in data:
                    fields.append(f"{col} = %s")
                    params.append(data[key])

            date_time_fields = [
                ('start_date', parse_date, '%Y-%m-%d'),
                ('end_date',   parse_date, '%Y-%m-%d'),
                ('start_time', parse_time, '%H:%M'),
                ('end_time',   parse_time, '%H:%M'),
            ]
            for field, parser, _ in date_time_fields:
                if field in data:
                    fields.append(f"{field} = %s")
                    params.append(parser(data[field]))

            if fields:
                sql = f"UPDATE discounts SET {', '.join(fields)} WHERE id = %s"
                params.append(id)
                cursor.execute(sql, tuple(params))

            # Обновление связей (удалить старые + вставить новые)
            relationships = [
                ('service_ids', 'discount_services', 'service_id'),
                ('city_ids', 'discount_cities', 'city_id'),
                ('price_type_ids', 'discount_price_types', 'price_type_id')
            ]
            
            for field_name, table_name, col_name in relationships:
                if field_name in data and isinstance(data[field_name], list):
                    cursor.execute(f"DELETE FROM {table_name} WHERE discount_id = %s", (id,))
                    for rel_id in data[field_name]:
                        cursor.execute(
                            f"INSERT INTO {table_name} (discount_id, {col_name}) VALUES (%s, %s)",
                            (id, rel_id)
                        )

            conn.commit()
            return jsonify({"message": "Скидка обновлена"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@admin_bp.route('/discounts/<int:id>', methods=['DELETE'])
@roles_required('admin')
def delete_discount(id):
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE discounts SET is_active = 0 WHERE id = %s", (id,))
            if cursor.rowcount == 0:
                return jsonify({'error': 'Скидка не найдена'}), 404
            conn.commit()
        return jsonify({'message': 'Скидка деактивирована'}), 200
    finally:
        conn.close()

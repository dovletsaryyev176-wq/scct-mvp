from flask import jsonify, request
from . import admin_bp
from db import Db
from decorators import roles_required


@admin_bp.route('/products', methods=['GET'])
def get_products():

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT 
                    p.id,
                    p.name,
                    p.volume,
                    p.quantity_per_block,
                    p.is_active,

                    pt.id AS product_type_id,
                    pt.name AS product_type_name,

                    b.id AS brand_id,
                    b.name AS brand_name

                FROM products p
                JOIN product_types pt ON p.product_type_id = pt.id
                JOIN brands b ON p.brand_id = b.id
            """)

            products = cursor.fetchall()

        return jsonify(products), 200

    finally:
        conn.close()


@admin_bp.route('/products', methods=['POST'])
@roles_required('admin')
def add_product():

    data = request.get_json()

    name = data.get('name')
    product_type_id = data.get('product_type_id')
    brand_id = data.get('brand_id')
    volume = data.get('volume')
    quantity_per_block = data.get('quantity_per_block')

    if not name or not product_type_id or not brand_id:
        return jsonify({"error": "name, product_type_id и brand_id обязательны"}), 400

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM product_types WHERE id=%s", (product_type_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Тип продукта не найден"}), 404

            cursor.execute("SELECT id FROM brands WHERE id=%s", (brand_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Бренд не найден"}), 404

            cursor.execute("""
                INSERT INTO products 
                (name, product_type_id, brand_id, volume, quantity_per_block)
                VALUES (%s,%s,%s,%s,%s)
            """, (name, product_type_id, brand_id, volume, quantity_per_block))

            conn.commit()

            product_id = cursor.lastrowid

            cursor.execute("""
                SELECT 
                    id,
                    name,
                    product_type_id,
                    brand_id,
                    volume,
                    quantity_per_block,
                    is_active
                FROM products
                WHERE id=%s
            """, (product_id,))

            new_product = cursor.fetchone()

        return jsonify(new_product), 201

    finally:
        conn.close()


@admin_bp.route('/products/<int:p_id>', methods=['PUT'])
@roles_required('admin','operator','courier','warehouse')
def update_product(p_id):

    data = request.get_json()

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM products WHERE id=%s", (p_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Продукт не найден"}), 404

            fields = []
            values = []

            if 'name' in data:
                fields.append("name=%s")
                values.append(data['name'])

            if 'product_type_id' in data:
                cursor.execute("SELECT id FROM product_types WHERE id=%s", (data['product_type_id'],))
                if not cursor.fetchone():
                    return jsonify({"error": "Тип продукта не найден"}), 404

                fields.append("product_type_id=%s")
                values.append(data['product_type_id'])

            if 'brand_id' in data:
                cursor.execute("SELECT id FROM brands WHERE id=%s", (data['brand_id'],))
                if not cursor.fetchone():
                    return jsonify({"error": "Бренд не найден"}), 404

                fields.append("brand_id=%s")
                values.append(data['brand_id'])

            if 'volume' in data:
                fields.append("volume=%s")
                values.append(data['volume'])

            if 'quantity_per_block' in data:
                fields.append("quantity_per_block=%s")
                values.append(data['quantity_per_block'])

            if fields:
                sql = f"UPDATE products SET {', '.join(fields)} WHERE id=%s"
                values.append(p_id)
                cursor.execute(sql, tuple(values))
                conn.commit()

            cursor.execute("""
                SELECT 
                    id,
                    name,
                    product_type_id,
                    brand_id,
                    volume,
                    quantity_per_block,
                    is_active
                FROM products
                WHERE id=%s
            """, (p_id,))

            updated_product = cursor.fetchone()

        return jsonify(updated_product), 200

    finally:
        conn.close()


@admin_bp.route('/products/<int:p_id>/block', methods=['PATCH'])
@roles_required('admin','operator','courier','warehouse')
def block_product(p_id):

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute("UPDATE products SET is_active=FALSE WHERE id=%s", (p_id,))
            conn.commit()

            cursor.execute("""
                SELECT id, name, product_type_id, brand_id, volume, quantity_per_block, is_active
                FROM products
                WHERE id=%s
            """, (p_id,))

            product = cursor.fetchone()

        return jsonify(product), 200

    finally:
        conn.close()


@admin_bp.route('/products/<int:p_id>/unblock', methods=['PATCH'])
@roles_required('admin','operator','courier','warehouse')
def unblock_product(p_id):

    conn = Db.get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute("UPDATE products SET is_active=TRUE WHERE id=%s", (p_id,))
            conn.commit()

            cursor.execute("""
                SELECT id, name, product_type_id, brand_id, volume, quantity_per_block, is_active
                FROM products
                WHERE id=%s
            """, (p_id,))

            product = cursor.fetchone()

        return jsonify(product), 200

    finally:
        conn.close()

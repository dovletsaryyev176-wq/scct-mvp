from flask import jsonify
from . import warehouse_bp
from db import Db


@warehouse_bp.route('/locations/counterparties', methods=['GET'])
def get_counterparty_locations():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM locations WHERE type='counterparty'")
            locs = cursor.fetchall()
        return jsonify(locs), 200
    finally:
        conn.close()


@warehouse_bp.route('/locations/warehouses', methods=['GET'])
def get_warehouse_locations():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM locations WHERE type='warehouse'")
            locs = cursor.fetchall()
        return jsonify(locs), 200
    finally:
        conn.close()


@warehouse_bp.route('/locations/couriers', methods=['GET'])
def get_courier_locations():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM locations WHERE type='courier'")
            locs = cursor.fetchall()
        return jsonify(locs), 200
    finally:
        conn.close()

@warehouse_bp.route('/locations/clients', methods=['GET'])
def get_client_locations():
    conn = Db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM locations WHERE type='client'")
            locs = cursor.fetchall()
        return jsonify(locs), 200
    finally:
        conn.close()

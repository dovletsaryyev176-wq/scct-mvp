from flask import jsonify
from . import admin_bp
from all_types_description import DeliveryTimes, OrderStatuses, PaymentTypes, ServiceTypes, TransactionTypes, DiscountTypes

# ------------------------------
# GET: Варианты времени доставки
# ------------------------------
@admin_bp.route('/delivery-times', methods=['GET'])
def get_delivery_times():
    data = [
        {"value": choice, "label": DeliveryTimes.LABELS[choice]}
        for choice in DeliveryTimes.CHOICES
    ]
    return jsonify(data), 200

# ------------------------------
# GET: Статусы заказов
# ------------------------------
@admin_bp.route('/order-statuses', methods=['GET'])
def get_order_statuses():
    data = [
        {"value": choice, "label": OrderStatuses.LABELS[choice]}
        for choice in OrderStatuses.CHOICES
    ]
    return jsonify(data), 200

# ------------------------------
# GET: Типы оплаты
# ------------------------------
@admin_bp.route('/payment-types', methods=['GET'])
def get_payment_types():
    data = [
        {"value": choice, "label": PaymentTypes.LABELS[choice]}
        for choice in PaymentTypes.CHOICES
    ]
    return jsonify(data), 200

# ------------------------------
# GET: Типы сервисов
# ------------------------------
@admin_bp.route('/service-types', methods=['GET'])
def get_service_types():
    data = [
        {"value": key, "label": ServiceTypes.LABELS[key]}
        for key in ServiceTypes.LABELS
    ]
    return jsonify(data), 200

# ------------------------------
# GET: Типы транзакций
# ------------------------------
@admin_bp.route('/transaction-types', methods=['GET'])
def get_transaction_types():
    data = [
        {"value": key, "label": TransactionTypes.LABELS[key]}
        for key in TransactionTypes.LABELS
    ]
    return jsonify(data), 200

# -------------------------------------------
# GET: Типы транзакций для курьеров (выдача/возврат)
# -------------------------------------------
@admin_bp.route('/courier-transaction-types', methods=['GET'])
def get_courier_transaction_types():
    keys = [TransactionTypes.COURIER_ISSUE, TransactionTypes.COURIER_RETURN]
    data = [{"value": key, "label": TransactionTypes.LABELS[key]} for key in keys]
    return jsonify(data), 200

# ------------------------------
# GET: Типы скидок
# ------------------------------
@admin_bp.route('/discount-types', methods=['GET'])
def get_discount_types():
    data = [
        {"value": key, "label": DiscountTypes.LABELS[key]}
        for key in DiscountTypes.LABELS
    ]
    return jsonify(data), 200
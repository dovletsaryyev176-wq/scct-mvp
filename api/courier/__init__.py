from flask import Blueprint
courier_bp = Blueprint('courier_api', __name__)
from . import warehouse_part
from . import orders_part
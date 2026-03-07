from flask import Blueprint
warehouse_bp = Blueprint('warehouse_api', __name__)
from . import get_locations
from . import warehouse
from . import couriers
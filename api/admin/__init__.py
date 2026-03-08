from flask import Blueprint
admin_bp = Blueprint('admin_api', __name__)
from . import all_types
from . import brands
from . import cities
from . import clients
from . import counterparties
from . import courier_info
from . import credits
from . import districts
from . import price_types
from . import product_states
from . import product_types
from . import products
from . import services
from . import transports
from . import users
from . import warehouses

 
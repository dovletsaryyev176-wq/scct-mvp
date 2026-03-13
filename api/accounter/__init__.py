from flask import Blueprint
accounter_bp = Blueprint('accounter_api', __name__)
from . import money
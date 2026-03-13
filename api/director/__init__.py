from flask import Blueprint
director_bp = Blueprint('director_api', __name__)
from . import routes
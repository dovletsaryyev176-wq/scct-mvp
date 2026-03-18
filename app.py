from flask import Flask
from config import Config
from api.auth.routes import auth_bp
from api.admin import admin_bp
from api.warehouse import warehouse_bp
from api.courier import courier_bp
from flask_cors import CORS
import os
from db import Db
from api.operator import operator_bp
from api.accounter import accounter_bp
from api.director import director_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Db.init(
    host="localhost",
    user="root",
    password="19121987",
    database="sarwan",
    maxconnections=20
    )
    
    cors_origins_env = os.environ.get("CORS_ORIGINS", "").strip()
    if cors_origins_env:
        allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    else:
        allowed_origins = r".*"

    CORS(app, supports_credentials=True, resources={r"/*": {"origins": allowed_origins}})

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(warehouse_bp, url_prefix='/api/warehouse')
    app.register_blueprint(courier_bp, url_prefix='/api/courier')
    app.register_blueprint(operator_bp, url_prefix='/api/operator')
    app.register_blueprint(accounter_bp, url_prefix='/api/accounter')
    app.register_blueprint(director_bp, url_prefix='/api/director')

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))    
    app.run(host='0.0.0.0', port=port, debug=False)
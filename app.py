from flask import Flask, app
from config import Config
from api.auth.routes import auth_bp
from api.admin import admin_bp
from api.warehouse import warehouse_bp
from api.courier import courier_bp
from flask_cors import CORS
import os
from db import Db


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
    CORS(app,supports_credentials=True)

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(warehouse_bp, url_prefix='/api/warehouse')
    app.register_blueprint(courier_bp, url_prefix='/api/courier')

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))    
    app.run(host='0.0.0.0', port=port, debug=False)
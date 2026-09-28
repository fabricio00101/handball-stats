from flask import Flask, jsonify
import config
import db

def create_app(config_class=config.Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializar Base de Datos (teardown_appcontext)
    db.init_app(app)

    # Registrar Blueprints
    from blueprints.web import web_bp
    from blueprints.api import api_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    # Manejo de Errores Global para API
    @app.errorhandler(404)
    def resource_not_found(e):
        return jsonify(error=str(e)), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify(error="Error interno del servidor"), 500

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), port=5000)

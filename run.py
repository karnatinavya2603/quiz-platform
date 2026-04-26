from flask import Flask
from config import SECRET_KEY
from database import init_db
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.user import user_bp
from routes.exam import exam_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(exam_bp)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

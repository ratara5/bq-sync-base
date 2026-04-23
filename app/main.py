# ========================================
# app/main.py
# Entrypoint
# ========================================

from server import create_app
from settings import settings

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0", 
        port=settings.port,
        debug=settings.flask_debug,
        use_reloader=settings.flask_use_reloader
    )
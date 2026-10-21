import asyncio
import os
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

# Импортируем твой код бота
import MAX_BOT 

# --- Крошечный веб-сервер для Render (чтобы сервис не засыпал) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Health check server listening on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    # Запускаем веб-сервер в отдельном потоке
    Thread(target=run_health_server, daemon=True).start()
    
    # Запускаем бота
    asyncio.run(MAX_BOT.main())
    

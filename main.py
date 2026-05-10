from flask import Flask
from waitress import serve
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Railway Works"

PORT = int(os.environ.get("PORT", 8080))

print(f"Starting on port {PORT}")

serve(
    app,
    host="0.0.0.0",
    port=PORT
)

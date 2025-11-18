from server import app

# Vercel expects a module-level variable named "app" that exposes
# the WSGI application. By importing from server.py we reuse the
# existing Flask configuration both for local development and the
# serverless deployment.

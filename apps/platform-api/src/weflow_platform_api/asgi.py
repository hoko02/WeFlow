"""ASGI deployment entrypoint; importing the factory package stays side-effect free."""

from .main import create_app

app = create_app()

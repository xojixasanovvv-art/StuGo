"""
ASGI config for StuGo project.

HTTP — Django, WebSocket (chat) — Django Channels.

Start:
    daphne config.asgi:application -p 8000
    yoki  python manage.py runserver  (daphne INSTALLED_APPS da bo'lgani uchun)
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Django'ni avval yuklash shart (models import qilinishi kerak).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
    }
)

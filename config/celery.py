"""Celery konfiguratsiyasi.

Hali background tasklar ishlatilmaydi, lekin worker buyruqlari tayyor:

    celery -A config worker -l info

Worker alohida terminalda ishga tushiriladi. Django settings import
qilinishi uchun `config/__init__.py` `celery_app` ni import qiladi.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("stugo")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
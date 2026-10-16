"""Prepare the bundled UI database before accepting public requests."""

import os
from pathlib import Path
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qlever.settings")

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import transaction
from backend.models import Backend

if settings.DEBUG or len(settings.SECRET_KEY.strip()) < 50:
    raise RuntimeError("Disable DEBUG and provide a secret key of at least 50 characters")

call_command("migrate", interactive=False)
marker = Path("/app/db/.production-initialized")
slug = os.environ["QLEVERUI_BACKEND"]

with transaction.atomic():
    # The shipped database includes demo credentials. Disable every bundled
    # account exactly once; explicitly created administrators survive restarts.
    if not marker.exists():
        for user in get_user_model().objects.all():
            user.is_active = False
            user.set_unusable_password()
            user.save()
        Session.objects.all().delete()

    backend = Backend.objects.get(slug=slug)
    Backend.objects.exclude(pk=backend.pk).update(isDefault=False, sortKey=0)
    backend.baseUrl = os.environ["QLEVERUI_PUBLIC_ENDPOINT"]
    backend.isDefault = True
    backend.sortKey = 1
    backend.save(update_fields=["baseUrl", "isDefault", "sortKey"])

marker.touch()
print(f"UI configured for backend {slug!r}; bundled accounts disabled on first boot.")

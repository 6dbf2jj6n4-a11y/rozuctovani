"""
Pri prvnim nasazeni automaticky zalozi administratorsky ucet
podle promennych prostredi - aby se uzivatel bez zkusenosti
s prikazovou radkou dostal do administrace.

Pouziti: nastav DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL
a DJANGO_SUPERUSER_PASSWORD jako env. promenne hostingu. Prikaz je
mozne spoustet opakovane (napr. pri kazdem nasazeni) - pokud ucet
uz existuje, nic se nestane.
"""
import os

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Vytvori administratorsky ucet z env. promennych, pokud jeste neexistuje."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write(
                "DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD nejsou "
                "nastaveny - přeskakuji vytvoření administrátora."
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Uživatel '{username}' už existuje, nic se nevytváří.")
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            role=User.Role.ADMIN,
        )
        self.stdout.write(self.style.SUCCESS(f"Administrátorský účet '{username}' vytvořen."))

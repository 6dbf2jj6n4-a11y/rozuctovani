"""
Spusti vsechny 4 importy klicu (FM elektro/voda/teplo + NJ) a vypise jen
strucne shrnuti - potlaci Django DEBUG SQL log i podrobny radek-po-radku
vystup jednotlivych importu, ukaze jen zaverecne "Hotovo: ..." hlasky
a pripadne varovani/chyby (Karta nenalezena, Meridlo nenalezeno, Neznamy
typ apod.).

Pouziti:
  python manage.py importovat_klice_strucne
"""
import io
import logging
from contextlib import redirect_stdout

from django.core.management import call_command
from django.core.management.base import BaseCommand

IMPORTS = [
    ("FM elektro", "import_klice_elektro", ["core/management/commands/Klice_Elektro.xlsx", "--site", "FM"]),
    ("FM voda", "import_klice_voda", ["core/management/commands/Klice_Voda.xlsx", "--site", "FM"]),
    ("FM teplo", "import_klice_teplo", ["core/management/commands/Klice_Teplo.xlsx", "--site", "FM"]),
    ("NJ", "import_klice_nj", ["core/management/commands/klice_NJ.xlsx", "--site", "NJ"]),
]

INTERESTING_KEYWORDS = (
    "Hotovo:", "nenalezen", "Nenalezeno", "Neznámý", "Neznámá", "chybí", "Chybí", "Přeskočeno",
)


class Command(BaseCommand):
    help = "Spustí všechny importy klíčů a vypíše jen stručné shrnutí (bez SQL logu a bez řádek-po-řádku výpisu)."

    def handle(self, *args, **options):
        django_logger = logging.getLogger("django")
        original_level = django_logger.level
        django_logger.setLevel(logging.WARNING)

        try:
            for label, command_name, args_list in IMPORTS:
                self.stdout.write(self.style.WARNING(f"\n=== {label} ==="))
                buf = io.StringIO()
                try:
                    with redirect_stdout(buf):
                        call_command(command_name, *args_list)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  CHYBA: {e}"))
                    continue

                output = buf.getvalue()
                lines = [line for line in output.splitlines() if any(k in line for k in INTERESTING_KEYWORDS)]
                if not lines:
                    self.stdout.write("  (žádné zajímavé řádky - zkontroluj, jestli import vůbec něco zpracoval)")
                for line in lines:
                    self.stdout.write(f"  {line.strip()}")
        finally:
            django_logger.setLevel(original_level)

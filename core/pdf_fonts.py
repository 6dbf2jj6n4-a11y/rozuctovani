"""
Sdílená registrace TTF fontu pro PDF výstupy (Karta nájemce, Vyúčtování).

Používá se DejaVu Sans (core/fonts/) místo vestavěného reportlab fontu
Vera - ten má vadný/chybějící glyf pro "ě"/"Ě" (U+011B/U+011A), časté
znaky v češtině, které by se jinak tiše vykreslily jako prázdný
čtvereček. Ověřeno přímým testem přes canvas.drawString.
"""
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = "DejaVu"
FONT_BOLD = "DejaVu-Bold"

pdfmetrics.registerFont(TTFont(FONT_REGULAR, os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))

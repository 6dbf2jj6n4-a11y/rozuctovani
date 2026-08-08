"""
Sdílená registrace TTF fontu pro PDF výstupy (Karta nájemce, Vyúčtování).

Používá se DejaVu Sans (core/fonts/) místo vestavěného reportlab fontu
Vera - ten má vadný/chybějící glyf pro "ě"/"Ě" (U+011B/U+011A), časté
znaky v češtině, které by se jinak tiše vykreslily jako prázdný
čtvereček. Ověřeno přímým testem přes canvas.drawString.

Karta nájemce navíc pouziva PT Sans Narrow - vizualne blizky font
Arial Narrow, kterym je psana Smlouva (viz core/contract_templates/),
Karta je jeji Priloha c. 1 a ma tak vypadat stejne. Skutecny Arial
Narrow je komercni font (Monotype) a nelze ho legalne redistribuovat
na server (Railway) - PT Sans Narrow je volne siritelny (ParaType Free
Font License), extrahovany z /System/Library/Fonts/Supplemental/PTSans.ttc.
"""
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = "DejaVu"
FONT_BOLD = "DejaVu-Bold"
FONT_CARD_REGULAR = "PTSansNarrow"
FONT_CARD_BOLD = "PTSansNarrow-Bold"

pdfmetrics.registerFont(TTFont(FONT_REGULAR, os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont(FONT_CARD_REGULAR, os.path.join(FONT_DIR, "PTSansNarrow.ttf")))
pdfmetrics.registerFont(TTFont(FONT_CARD_BOLD, os.path.join(FONT_DIR, "PTSansNarrow-Bold.ttf")))

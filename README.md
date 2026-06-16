# Rozúčtování energií a služeb

Základ aplikace pro měsíční rozúčtování nákladů na energie a služby
mezi nájemce (klienty) - podle datového modelu a výpočetní logiky,
na které jsme se domluvili.

## Struktura projektu

- `core` - areály/objekty (Site), pronajímané prostory (Unit), klienti
  (Client) a jejich karty (ClientCard) s platností.
- `meters` - období (Period), hierarchie měřidel (Meter, libovolně
  hluboké podružné měřidlo) a jejich odečty (MeterReading).
- `billing` - Zásobník (ServicePoolItem), klíče pro rozpočet
  (AllocationKey), skutečné náklady za období (CostEntry), výsledné
  vyúčtování (BillingLine) a samotný výpočetní `engine.py`.
- `accounts` - vlastní uživatelský model s rolemi `admin` / `spravce`
  / `klient`.

## Jak to spustit (lokálně, s Dockerem)

1. `cp .env.example .env` a případně uprav hodnoty.
2. `docker compose up --build`
3. V novém terminálu vytvoř superuživatele:
   `docker compose exec web python manage.py createsuperuser`
4. Administrace běží na `http://localhost:8000/admin/`.

## Jak to spustit bez Dockeru (např. pro rychlé vyzkoušení)

1. `python -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. `export DJANGO_DB_ENGINE=sqlite3`
4. `python manage.py migrate`
5. `python manage.py createsuperuser`
6. `python manage.py runserver`

## Typický pracovní postup správce

1. V administraci založ Areály, Prostory, Klienty a Karty klientů
   (s platností od/do).
2. Založ Měřidla a jejich hierarchii (nadřazené měřidlo).
3. Založ položky Zásobníku - u měřených přiřaď měřidlo, u
   neměřených ne.
4. U karet klientů přiřaď Klíče (typ rozpočtu, hodnota, platnost).
5. Na konci měsíce: zadej Odečty měřidel pro nové Období a Náklady
   za období (skutečné částky z faktur).
6. V administraci u Období vyber měsíc a použij akci "Spočítat
   rozúčtování za vybraná období" - vytvoří se Vyúčtované položky
   (BillingLine) pro všechny klienty.

## Klientský portál (API)

`GET /api/billing-lines/` - přihlášený uživatel s rolí `klient`
uvidí jen položky týkající se jeho karet, `admin`/`spravce` uvidí
vše (lze filtrovat `?period=<id>` a `?client_card=<id>`). Toto
je základ pro webový klientský přehled spotřeb a vyúčtování -
frontend zatím není součástí tohoto základu.

## Nasazení do cloudu (Railway) - krok za krokem

Toto je doporučený postup pro nasazení bez nutnosti pracovat s
příkazovou řádkou.

1. **GitHub** - vytvoř si zdarma účet na github.com. Vytvoř nové
   repozitář (např. `rozuctovani`) a nahraj do něj obsah tohoto
   adresáře (přes webové rozhraní "Add file → Upload files", nebo
   pohodlněji přes aplikaci GitHub Desktop).
2. **Railway** - na railway.app se zaregistruj přes GitHub účet.
3. V Railway klikni na "New Project" → "Deploy from GitHub repo" a
   vyber repozitář `rozuctovani`. Railway automaticky rozpozná
   `Dockerfile` a aplikaci postaví.
4. V tomtéž projektu klikni "New" → "Database" → "Add PostgreSQL".
   Railway vytvoří databázi a sám nastaví proměnnou `DATABASE_URL`.
5. U služby s aplikací (ne databáze) otevři záložku "Variables" a
   doplň proměnné podle `.env.example`:
   - `DJANGO_SECRET_KEY` - vlož libovolný dlouhý náhodný text
   - `DJANGO_DEBUG` = `0`
   - `DJANGO_ALLOWED_HOSTS` = `*` (lze později zpřísnit na konkrétní
     domain)
   - `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`,
     `DJANGO_SUPERUSER_PASSWORD` - přihlašovací údaje pro tvůj
     administrátorský účet
   - `DATABASE_URL` přidej propojením na databázi: napiš
     `${{Postgres.DATABASE_URL}}` (Railway nabídne automatické
     doplnění).
6. Po uložení proměnných Railway aplikaci znovu nasadí. Při startu
   se automaticky provedou databázové migrace a vytvoří se tvůj
   administrátorský účet.
7. V Railway u služby klikni na "Settings" → "Generate Domain" -
   získáš veřejnou adresu, na které appka běží (něco jako
   `https://rozuctovani.up.railway.app`).
8. Administrace je na `<tvoje-adresa>/admin/` - přihlas se údaji
   z bodu 5.

Pokud při nasazení něco selže, v Railway je záložka "Deployments" →
"View Logs", kde uvidíš chybovou hlášku - klidně mi ji pošli, pomůžu
ji vyřešit.

## Co je potřeba doplnit / rozhodnout dál

- Frontend pro klientský portál (jednoduché šablony, nebo
  samostatná React aplikace nad API).
- Formulář pro hromadné zadávání odečtů měřidel správcem
  (administrace to umí po jednom, pro desítky měřidel měsíčně
  by se vyplatil rychlejší formulář).
- Export vyúčtování (PDF/Excel) pro klienty.
- `billing/engine.py` je první funkční verze - doporučuji ji
  prověřit na reálných datech z aktuálního Excelu a doladit
  hraniční případy (chybějící odečty, nulové váhy apod.), na
  které engine zatím jen upozorní ve `warnings`.

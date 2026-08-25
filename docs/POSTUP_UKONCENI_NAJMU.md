# Postup: klient dal výpověď

Checklist od doručení výpovědi po nastěhování dalšího nájemce.

> **Základní pravidlo: všechno se láme ke konci měsíce.** Odečet, konec staré
> karty i začátek nové. Systém pak nemá co rozdělovat napůl a čísla sedí sama.
> Dohoda s Danielem 2026-08-25.

---

## 1. Vyplnit „Platnost do" na Kartě klienta

Poslední den měsíce, kterým nájem končí. **Tohle je hlavní krok** — řídí se
podle něj celý výpočet:

| co se stane samo | kde |
|---|---|
| nájem se zkrátí podle počtu dnů | `ClientCard.rent_for_period` |
| paušály a služby se zkrátí stejně | `billing/engine.py` `_kraceno_dny` |
| váhy v klíčích (osoby, radiátory, m²) se zkrátí poměrem dnů | `_weighted_shares` |
| klíče se po skončení platnosti přeskočí úplně | `calculate_period` |
| příznak **Aktivní** se přepne sám při výpočtu rozúčtování | `sync_card_activity` |
| plocha v plánku zezelená jako volná (a 90 dní předem svítí „končí") | `core/floorplan.py` |
| karta zmizí z Přehledu nájemného, jakmile v období neplatí ani den | |

Klíče ani váhy tedy **nemaž** — samy přestanou platit.

## 2. Zapsat konečný odečet měřidel

Normální měsíční odečet za období, ve kterém nájem končí. Protože se láme ke
konci měsíce, žádný zvláštní postup není potřeba.

> ⚠️ Kdyby někdy bylo nutné ukončit **uprostřed** měsíce: na měřidlo a období
> smí být jen **jeden** odečet (`unique_together`), takže konečný stav není kam
> zapsat a celá měsíční spotřeba se přiřadí odcházejícímu nájemci — včetně dnů,
> kdy tam už bydlel někdo jiný. Nájem a paušály se zkrátí správně, měřená
> spotřeba ne. Pustit na měřidlo víc odečtů za období je zásah do modelu.

## 3. Spustit vyúčtování za poslední období

Než se karta ztratí z dohledu. Zkontrolovat, že částky odpovídají zkrácené
době.

## 4. Ukončit Smlouvu

Smlouva je samostatný záznam s vlastní **Platností do**, **Výpovědní lhůtou**
a **Kaucí** — ukončení karty se do ní nepromítne.

Vrácení kauce model neeviduje (jsou jen pole *Kauce* a *Kauce zaplacena*),
stejně jako samotnou výpověď — datum podání, lhůtu, důvod. Zatím na to stačí
poznámka na kartě.

## 5. Klienta NEdeaktivovat

Když u klienta shodíš **Aktivní**, model automaticky deaktivuje **všechny jeho
karty** — i v druhém areálu (`Client.save`). U klienta, který odchází jen
z jednoho místa, to nechceš. Kartu už ukončilo datum v kroku 1.

Deaktivovat klienta má smysl jen tehdy, když s ním končí spolupráce úplně.

## 6. Nový nájemce = nová karta

**Platnost od** = první den následujícího měsíce. Starou kartu needituj,
zůstává jako historie.

Po přepsání projeď sestavu **Konflikt ploch** (Reporty). Systém sám nehlídá,
že jsou na jedné ploše dva **různí** klienti současně — vestavěná kontrola řeší
jen dvě aktivní karty téhož klienta ve stejném areálu.

## 7. Zkontrolovat plánek

Plocha má svítit jako volná. Pokud ne, karta nejspíš pořád nemá vyplněnou
platnost, nebo na ní visí druhá aktivní karta.

# Postup: nové zúčtovací období

Checklist od založení období až po jeho uzavření. Kroky jsou v pořadí,
v jakém na sebe navazují — přeskočit jde jen to, co je označené jako
volitelné.

> Zkratky: **[A]** = hromadná akce (zaškrtnout období v seznamu → rozbalovací
> menu „Akce" nad tabulkou), **[T]** = tlačítko přímo v řádku období.

---

## 1. Založit období

**Období → Přidat**, nebo tlačítko **Generovat pro celý rok** nad tabulkou,
které vytvoří všech dvanáct měsíců najednou.

## 2. Nastavit jako aktuální  **[A]**

Akce **„Nastavit jako aktuální období"**. Tím se období předvyplní ve všech
sestavách (Přehled Náklad/Výnos, Detail výpočtu, Spotřeby měřidel, Odečty…).

Aktuální může být vždy jen jedno — zaškrtnutím se předchozí samo odznačí.
Pracovní období není totéž co kalendářní měsíc: v srpnu se běžně
rozúčtovává červenec.

## 3. Zadat odečty měřidel  **[T]**

Tlačítko **Zadat odečty** v řádku období otevře zadávací formulář rovnou
pro tohle období.

Nezapomenout na měřidla, která nejsou fyzická, ale nesou počty:

| měřidlo | co se do něj píše |
|---|---|
| `T_SPOLECNA` (NJ) | počet radiátorů ve společných prostorách (trvale 10) |
| `T_INDIVIDUALNI` (NJ) | počet radiátorů v pronajatých kancelářích (mění se) |

Obě jsou v režimu **Spotřeba za období**, takže odečet *je* ten počet.
Když se počet změní, zapíše se nová hodnota do toho období, kde ke změně
došlo — starší období si drží svou historii.

## 4. Zadat náklady za období

**Náklady za období → Přidat**, nebo si nejdřív nechat vygenerovat prázdné
řádky:

- **[A] „Vygenerovat chybějící Náklady za období"** založí prázdný náklad
  pro každou položku, která ho ještě nemá, s poznámkou `K DOPLNĚNÍ`.
  Pak stačí v seznamu filtrovat na období a čísla dopsat přímo v tabulce
  (sloupce Fakturované množství a Částka jsou editovatelné).

Pro měřené služby se vyplňuje **Fakturované množství** (kWh, m³, GJ) a Kč
se dopočítá z Ceníku. Pro neměřené (úklid, ostraha…) se vyplňuje **Částka
v Kč** a množství zůstane prázdné.

> Nikdy nepiš 0 do pole, které se tě netýká — nula je platná hodnota
> a položka by se potichu vyúčtovala na nulu. Nech pole prázdné.

## 5. Zkontrolovat ceníky

Ceny se **dědí z dřívějších období** — pokud se nemění, není potřeba dělat
nic. V **Cenících** (po filtru na období) najdeš pod tabulkou sekci
**„Ceny převzaté z dřívějších období"**, kde je vidět, která cena odkud
platí. Tlačítkem **Převzít do období** si můžeš cenu „zhmotnit" do tohohle
období a pak ji upravit.

## 6. Dotáhnout fakturovaná množství  **[A]**  *(volitelné)*

Akce **„Dotáhnout fakturovaná množství do přívodních měřidel"** přepíše
fakturované množství z Nákladů do přívodních měřidel odběrných míst, aby
se „dodáno" nemuselo zadávat dvakrát.

Týká se jen odběrů, které mají vyplněný **Náklad, ze kterého brát
fakturované množství** (pole na Odběrném místě). Slouží pouze reportu
Spotřeby měřidel — na rozúčtování nemá vliv.

## 7. Kontrola před výpočtem  **[A]**

Akce **„Zkontrolovat, co je potřeba zadat"** projde všechny položky a
nahlásí:

- položky **bez nákladu** a zároveň bez výchozí měsíční částky — ty by se
  potichu přeskočily a nikomu by se nevyúčtovaly,
- měřené položky **bez platné ceny** v Ceníku.

Sezónní služby (odklízení sněhu…) se hlásí i v měsících, kdy tam náklad
správně být nemá — to je v pořádku, jen si toho všimni a přejdi to.

## 8. Spočítat rozúčtování  **[T]** nebo **[A]**

Tlačítko **Výpočet** v řádku období, nebo akce **„Spočítat rozúčtování za
vybraná období"**.

Výpočet **smaže a znovu vytvoří** všechny vyúčtované řádky daného období.
Přečti si varování, která vypíše — typicky upozorní na chybějící odečet
nebo na kartu bez klíče.

## 9. Zkontrolovat výsledek

| kde | co ověřit |
|---|---|
| **Spotřeby měřidel** | dodáno vs. naměřeno po odběrných místech, ztráty |
| **Detail výpočtu vyúčtování** | rozpad po klíčích, podíly na měřidlech |
| **Přehled Náklad/Výnos** | že se náklad rovná rozúčtované částce |
| **Paušální klienti** | u koho je paušál ztrátový |

K interpretaci ztrát: **zákonná ztráta** (4 %, jen odběry TEDOM) je
konstanta, kterou dodavatel účtuje vždy, a je kladná. **Ztráta měření** je
rozdíl mezi tím, co reálně došlo, a tím, co naměřila naše měřidla — může
vyjít i **záporně** (naměřili jsme víc), typicky posunem odečtů oproti
dodavateli. Záporná hodnota jde ve prospěch klientů a v dalším období bývá
odchylka opačná.

## 10. Uzavřít období  **[T]**

Tlačítko **Uzavřít** v řádku období. Zámek pak nedovolí měnit odečty,
náklady ani ceníky a odmítne i přepočet.

Když je potřeba se k období vrátit, tlačítkem **Otevřít** se odemkne;
po opravě nezapomeň znovu spočítat rozúčtování a zase zavřít.

---

## Rychlý přehled

```
1. Založit období                        Období → Přidat / Generovat pro celý rok
2. Nastavit jako aktuální            [A]
3. Zadat odečty                      [T] (vč. počtů radiátorů NJ)
4. Zadat náklady                         [A] Vygenerovat chybějící → doplnit čísla
5. Zkontrolovat ceníky                   (dědí se; „Převzít do období")
6. Dotáhnout fakturovaná množství    [A] (volitelné, jen pro report)
7. Zkontrolovat, co je potřeba zadat [A]
8. Spočítat rozúčtování              [T]
9. Zkontrolovat sestavy
10. Uzavřít období                   [T]
```

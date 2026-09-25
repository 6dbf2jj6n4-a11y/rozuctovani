"""
Klientský portál - přehled historických vyúčtování.

Čte výhradně z BillingLine (nikdy nic nepřepočítává) - jakmile je
Období uzavřené, tady zobrazené hodnoty se už nezmění, viz
billing/engine.py (BillingPeriodClosedError).
"""
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify

from accounts.models import User
from core.models import BillingLine, Client, Period, PodkladovaFaktura
from billing.statement_generator import (
    build_statement_data, generate_client_statement_pdf, poznamka_k_rozpadu,
)


def _resolve_client(request):
    """Klient vidí jen sebe. Admin/správce si může přes ?client=<id> zobrazit
    kteréhokoli klienta (podpora/kontrola) - bez parametru nevybere nikoho."""
    user = request.user
    if user.role == User.Role.KLIENT:
        return user.client

    client_id = request.GET.get("client")
    if client_id:
        return get_object_or_404(Client, pk=client_id)
    return None


def _obdobi_klienta(client):
    """Obdobi, za ktera ma klient nejake vyuctovani - nejnovejsi nahore."""
    return (
        Period.objects.filter(billing_lines__client_card__client=client)
        .distinct()
        .order_by("-year", "-month")
    )


def _klient_a_obdobi(request, period_id):
    """Spolecna kontrola pro detail i PDF: klient smi videt jen obdobi,
    za ktere ma vyuctovane polozky."""
    client = _resolve_client(request)
    if client is None:
        raise PermissionDenied("Není vybraný klient.")
    period = get_object_or_404(Period, pk=period_id)
    if not BillingLine.objects.filter(period=period, client_card__client=client).exists():
        raise PermissionDenied("Pro tohoto klienta a období nejsou k dispozici žádná data.")
    return client, period


def _faktury_klienta(client, period):
    """Podkladove faktury dodavatelu k polozkam, ktere ma klient v obdobi
    vyuctovane - jen ty, ktere uz maji PDF v ulozisti. Faktura kryjici
    vic polozek (SMVAK NJ = voda i srazkove) se ukaze jednou se vsemi."""
    polozky = BillingLine.objects.filter(
        period=period, client_card__client=client,
    ).values_list("service_item_id", flat=True)
    faktury = {}
    for f in (
        PodkladovaFaktura.objects
        .filter(period=period, service_item_id__in=polozky)
        .exclude(soubor="")
        .select_related("service_item").order_by("dodavatel", "kod")
    ):
        # Rucne nahrane nemaji flexi_id - seskupuji se podle souboru.
        zaznam = faktury.setdefault(f.flexi_id or f.soubor.name, {"faktura": f, "polozky": []})
        zaznam["polozky"].append(f.service_item.name)
    return list(faktury.values())


def _dotaz(request, client):
    """?client=<id> pro odkazy - jen spravce si vybira klienta parametrem,
    klient sam vidi vzdycky sebe."""
    return f"?client={client.pk}" if request.user.role != User.Role.KLIENT else ""


@login_required
def periods_list(request):
    client = _resolve_client(request)

    all_clients = None
    if request.user.role != User.Role.KLIENT:
        all_clients = Client.objects.filter(is_active=True).order_by("name")

    periods = _obdobi_klienta(client) if client is not None else []

    return render(request, "billing/periods_list.html", {
        "client": client,
        "all_clients": all_clients,
        "periods": periods,
    })


@login_required
def period_detail(request, period_id):
    client, period = _klient_a_obdobi(request, period_id)
    data = build_statement_data(client, period)
    all_cards = {line["card"] for cls in data["classes"] for line in cls["lines"]}

    return render(request, "billing/period_detail.html", {
        "client": client,
        "period": period,
        "classes": data["classes"],
        "grand_total": data["grand_total"],
        "any_unbilled": data["any_unbilled"],
        "any_surcharge": data["any_surcharge"],
        "poznamka_k_rozpadu": poznamka_k_rozpadu(data["any_vyrovnani"]),
        "show_card_column": len(all_cards) > 1,
        # Seznam obdobi vlevo - rychle prepinani mezi mesici bez vraceni
        # na prehled. Viz Daniel 2026-09-25.
        "obdobi": _obdobi_klienta(client),
        "dotaz": _dotaz(request, client),
        "faktury": _faktury_klienta(client, period),
    })


@login_required
def period_faktura(request, period_id, faktura_id):
    """Podkladova faktura dodavatele - PDF z vlastniho uloziste (R2), ne
    z ucetnictvi, takze funguje i po zmene ucetniho systemu. Klient smi
    otevrit jen fakturu k polozce, kterou ma v tomto obdobi vyuctovanou.
    Viz core.models.PodkladovaFaktura a NapojeniUcetnictvi."""
    client, period = _klient_a_obdobi(request, period_id)
    faktura = get_object_or_404(PodkladovaFaktura, pk=faktura_id, period=period)
    if not faktura.soubor:
        raise Http404("Faktura zatím nemá nahrané PDF.")
    if not BillingLine.objects.filter(
        period=period, client_card__client=client, service_item_id=faktura.service_item_id,
    ).exists():
        raise PermissionDenied("Tahle faktura k vašemu vyúčtování nepatří.")
    try:
        soubor = faktura.soubor.open("rb")
    except Exception:
        raise Http404("Fakturu se teď nepodařilo načíst, zkuste to prosím později.")
    nazev = faktura.nazev_souboru or faktura.soubor.name.rsplit("/", 1)[-1]
    # Inline - prohlizec fakturu rovnou ukaze, stahnout jde odtamtud.
    return FileResponse(soubor, filename=nazev, content_type="application/pdf")


@login_required
def period_pdf(request, period_id):
    """Vyuctovani ke stazeni v PDF - stejny dokument, jaky jde klientovi
    (billing/statement_generator.py), jen na vyzadani z portalu."""
    client, period = _klient_a_obdobi(request, period_id)
    buf = BytesIO()
    generate_client_statement_pdf(client, period, buf)
    buf.seek(0)
    nazev = f"vyuctovani_{slugify(client.name)}_{period.year}-{period.month:02d}.pdf"
    return FileResponse(buf, as_attachment=True, filename=nazev, content_type="application/pdf")

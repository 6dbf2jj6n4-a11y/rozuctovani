"""
Obrazovka pro spravce na zadavani odectu meridel - jedno meridlo na
obrazovku, navigace sipkami/swipem, kontrola odchylky proti historii.
Viz core/models.py Meter.consumption_for pro vypocet spotreby.
"""
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Client, Meter, MeterReading, Period


def _require_spravce(user):
    if not user.is_spravce_role:
        raise PermissionDenied("Zadávání odečtů je jen pro správce.")


@login_required
def readings_entry(request):
    user = request.user
    _require_spravce(user)

    sites = user.get_accessible_sites().order_by("name")
    site_id = request.GET.get("site")
    site = sites.filter(pk=site_id).first() if site_id else sites.first()

    periods = Period.objects.order_by("-year", "-month")[:24]
    period_id = request.GET.get("period")
    period = Period.objects.filter(pk=period_id).first() if period_id else None
    if period is None:
        # Aktualni mesic (Period.current) ma prednost pred "nejnovejsi
        # otevrene" - od tlacitka "Generovat pro cely rok" jsou v DB i
        # budouci obdobi, ktera jsou taky otevrena, takze zadavani odectu
        # najizdelo napr. na prosinec. Viz konverzace s Danielem 2026-08-15.
        period = Period.current() or Period.objects.filter(status=Period.Status.OPEN).first()

    meters_data = []
    if site and period:
        meters = list(
            Meter.objects.filter(site=site, is_virtual=False)
            .order_by("display_order", "meter_type", "code")
        )

        # Vsechna obdobi a odecty nactena hromadne dopredu (misto dotazu
        # na kazde meridlo/obdobi zvlast) - u arealu s vic meridly to
        # driv delalo stovky az tisice DB dotazu na jedno nacteni
        # stranky a gunicorn worker to po 30s zabil (viz konverzace s
        # Danielem 2026-08-06, NJ/FM vs. male DV).
        all_periods = list(Period.objects.all())
        periods_by_ym = {(p.year, p.month): p for p in all_periods}

        def prev_of(p):
            if p is None:
                return None
            y, mo = (p.year - 1, 12) if p.month == 1 else (p.year, p.month - 1)
            return periods_by_ym.get((y, mo))

        prev_period = prev_of(period)
        yoy_period = periods_by_ym.get((period.year - 1, period.month))
        earlier_periods = sorted(
            (p for p in all_periods if (p.year, p.month) < (period.year, period.month)),
            key=lambda p: (p.year, p.month),
            reverse=True,
        )[:8]

        needed_periods = {period, prev_period, yoy_period, prev_of(yoy_period)}
        for hp in earlier_periods:
            needed_periods.add(hp)
            needed_periods.add(prev_of(hp))
        needed_periods.discard(None)

        readings_map = {
            (r.meter_id, r.period_id): r
            for r in MeterReading.objects.filter(meter__in=meters, period__in=needed_periods)
        }

        def consumption_of(m, p):
            if p is None:
                return None
            current = readings_map.get((m.id, p.id))
            if current is None:
                return None
            if m.reading_mode == Meter.ReadingMode.CONSUMPTION:
                return current.value
            if current.reset_from_value is not None:
                return current.value - current.reset_from_value
            previous = readings_map.get((m.id, prev_of(p).id)) if prev_of(p) else None
            return (current.value - previous.value) if previous else None

        for m in meters:
            existing = readings_map.get((m.id, period.id))
            previous = readings_map.get((m.id, prev_period.id)) if prev_period else None

            hist = []
            for p in earlier_periods:
                c = consumption_of(m, p)
                if c is not None:
                    hist.append({"label": str(p), "value": float(c)})
            hist.reverse()

            yoy_value = consumption_of(m, yoy_period) if yoy_period else None

            meters_data.append({
                "id": m.id,
                "code": m.code,
                "name": m.name,
                "meter_type_label": m.get_meter_type_display(),
                "unit": m.jednotka_odectu,
                "reading_mode": m.reading_mode,
                "parent_id": m.parent_meter_id,
                "prev_value": float(previous.value) if previous else None,
                "prev_date": previous.reading_date.strftime("%d. %m. %Y") if previous else None,
                "yoy_value": float(yoy_value) if yoy_value is not None else None,
                "yoy_label": str(yoy_period) if yoy_period else None,
                "hist": hist,
                "existing": {
                    "value": float(existing.value) if existing else None,
                    "note": existing.note if existing else "",
                    "reset_from_value": (
                        float(existing.reset_from_value)
                        if existing and existing.reset_from_value is not None else None
                    ),
                    "photo_url": existing.photo.url if existing and existing.photo else None,
                } if existing else None,
            })

    landlord = Client.objects.filter(is_landlord=True).first()

    return render(request, "meters/readings_entry.html", {
        "sites": sites,
        "site": site,
        "periods": periods,
        "period": period,
        "meters_data": meters_data,
        "period_closed": bool(period and period.status == Period.Status.CLOSED),
        # Stejna hlavicka (logo/verze/pronajimatel) jako v Django adminu
        # (config.settings.UNFOLD SITE_ICON/SITE_HEADER/SITE_SUBHEADER) -
        # viz konverzace s Danielem 2026-08-09, chtel sjednoceny vzhled.
        "app_version": settings.APP_VERSION,
        "landlord_name": landlord.name if landlord else None,
    })


@login_required
@require_POST
def readings_save(request):
    user = request.user
    _require_spravce(user)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Neplatná data."}, status=400)

    meter = get_object_or_404(Meter, pk=payload.get("meter_id"))
    if not user.get_accessible_sites().filter(pk=meter.site_id).exists():
        raise PermissionDenied("K tomuto areálu nemáš přístup.")

    period = get_object_or_404(Period, pk=payload.get("period_id"))
    if period.status == Period.Status.CLOSED:
        return JsonResponse(
            {"ok": False, "error": "Období je uzavřené, odečet nejde upravit."}, status=400
        )

    try:
        value = Decimal(str(payload.get("value")))
    except (InvalidOperation, TypeError):
        return JsonResponse({"ok": False, "error": "Zadej číselnou hodnotu."}, status=400)

    reset_raw = payload.get("reset_from_value")
    reset_from_value = None
    if reset_raw not in (None, ""):
        try:
            reset_from_value = Decimal(str(reset_raw))
        except InvalidOperation:
            return JsonResponse({"ok": False, "error": "Neplatný počáteční stav."}, status=400)

    if meter.reading_mode == Meter.ReadingMode.CONSUMPTION:
        consumption = value
    elif reset_from_value is not None:
        consumption = value - reset_from_value
    else:
        prev_period = period.previous_period()
        previous = meter.readings.filter(period=prev_period).first() if prev_period else None
        consumption = (value - previous.value) if previous else None

    if consumption is not None and consumption < 0:
        return JsonResponse({
            "ok": False,
            "error": (
                "Spotřeba nemůže být záporná. Pokud bylo měřidlo vyměněno, "
                "zadej počáteční stav nového měřidla."
            ),
        }, status=400)

    MeterReading.objects.update_or_create(
        meter=meter, period=period,
        defaults={
            "value": value,
            "reset_from_value": reset_from_value,
            "note": (payload.get("note") or "")[:300],
            "reading_date": timezone.localdate(),
        },
    )
    return JsonResponse({
        "ok": True,
        "consumption": float(consumption) if consumption is not None else None,
    })


@login_required
@require_POST
def readings_photo(request):
    user = request.user
    _require_spravce(user)

    meter = get_object_or_404(Meter, pk=request.POST.get("meter_id"))
    if not user.get_accessible_sites().filter(pk=meter.site_id).exists():
        raise PermissionDenied("K tomuto areálu nemáš přístup.")

    period = get_object_or_404(Period, pk=request.POST.get("period_id"))
    if period.status == Period.Status.CLOSED:
        return JsonResponse(
            {"ok": False, "error": "Období je uzavřené, foto nejde přidat."}, status=400
        )

    reading = MeterReading.objects.filter(meter=meter, period=period).first()
    if reading is None:
        return JsonResponse(
            {"ok": False, "error": "Nejdřív ulož odečet, pak přidej foto."}, status=400
        )

    photo = request.FILES.get("photo")
    if not photo:
        return JsonResponse({"ok": False, "error": "Nebyl vybrán žádný soubor."}, status=400)

    reading.photo = photo
    reading.save()
    return JsonResponse({"ok": True, "photo_url": reading.photo.url})


@login_required
@require_POST
def readings_photo_delete(request):
    user = request.user
    _require_spravce(user)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Neplatná data."}, status=400)

    meter = get_object_or_404(Meter, pk=payload.get("meter_id"))
    if not user.get_accessible_sites().filter(pk=meter.site_id).exists():
        raise PermissionDenied("K tomuto areálu nemáš přístup.")

    period = get_object_or_404(Period, pk=payload.get("period_id"))
    if period.status == Period.Status.CLOSED:
        return JsonResponse(
            {"ok": False, "error": "Období je uzavřené, foto nejde smazat."}, status=400
        )

    reading = MeterReading.objects.filter(meter=meter, period=period).first()
    if reading is None or not reading.photo:
        return JsonResponse({"ok": False, "error": "Foto neexistuje."}, status=400)

    reading.photo.delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def readings_reorder(request):
    user = request.user
    _require_spravce(user)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Neplatná data."}, status=400)

    site_id = payload.get("site_id")
    meter_ids = payload.get("meter_ids")
    if not site_id or not isinstance(meter_ids, list):
        return JsonResponse({"ok": False, "error": "Neplatná data."}, status=400)
    if not user.get_accessible_sites().filter(pk=site_id).exists():
        raise PermissionDenied("K tomuto areálu nemáš přístup.")

    meters_by_id = {m.id: m for m in Meter.objects.filter(site_id=site_id, id__in=meter_ids)}
    if len(meters_by_id) != len(meter_ids):
        return JsonResponse({"ok": False, "error": "Neplatná data."}, status=400)

    for position, meter_id in enumerate(meter_ids):
        meters_by_id[meter_id].display_order = position
    Meter.objects.bulk_update(meters_by_id.values(), ["display_order"])

    return JsonResponse({"ok": True})

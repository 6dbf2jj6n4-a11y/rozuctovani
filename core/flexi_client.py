"""
Klient pro ABRA Flexi REST API.

Autentizace přes HTTP Basic (FLEXI_USER / FLEXI_PASS), komunikace v JSON.
Konfigurace čte z env proměnných:
    FLEXI_URL      - např. https://demo.flexibee.eu
    FLEXI_COMPANY  - kód firmy (databáze) ve Flexi
    FLEXI_USER     - uživatelské jméno
    FLEXI_PASS     - heslo

Formát obálky odpovědí/požadavků ABRA Flexi REST API je vždy:
    {"winstrom": {"<evidence>": [...] }}
"""

import os

import requests
from requests.auth import HTTPBasicAuth

EVIDENCE_INVOICES_ISSUED = "faktura-vydana"
EVIDENCE_INVOICES_RECEIVED = "faktura-prijata"
EVIDENCE_LIABILITIES = "zavazek"


class FlexiAPIError(Exception):
    def __init__(self, status_code, message, response_body=None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"Flexi API error {status_code}: {message}")


class FlexiClient:
    def __init__(self, url=None, company=None, user=None, password=None):
        self.url = (url or os.environ["FLEXI_URL"]).rstrip("/")
        self.company = company or os.environ["FLEXI_COMPANY"]
        self.user = user or os.environ["FLEXI_USER"]
        self.password = password or os.environ["FLEXI_PASS"]

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(self.user, self.password)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _evidence_url(self, evidence, suffix=""):
        return f"{self.url}/c/{self.company}/{evidence}{suffix}.json"

    def _request(self, method, url, **kwargs):
        response = self.session.request(method, url, timeout=30, **kwargs)
        if response.status_code >= 400:
            raise FlexiAPIError(response.status_code, response.reason, response.text)
        if not response.content:
            return None
        return response.json()

    # ------------------------------------------------------------------
    # Obecné CRUD metody použitelné pro libovolnou evidenci
    # ------------------------------------------------------------------

    def list_records(self, evidence, filter_expr=None, extra_params=None):
        """Vrátí seznam záznamů dané evidence. filter_expr je Flexi filtrovací výraz,
        např. "stavUhrK != 'stavUhr.uhrazeno'"."""
        params = dict(extra_params or {})
        if filter_expr:
            params["filter"] = filter_expr

        data = self._request("GET", self._evidence_url(evidence), params=params)
        return (data or {}).get("winstrom", {}).get(evidence, [])

    def get_record(self, evidence, record_id):
        """Vrátí jeden záznam podle interního id nebo kódu (např. 'code:FAV0001')."""
        data = self._request("GET", self._evidence_url(evidence, f"/{record_id}"))
        records = (data or {}).get("winstrom", {}).get(evidence, [])
        return records[0] if records else None

    def create_record(self, evidence, fields):
        payload = {"winstrom": {evidence: fields}}
        data = self._request("POST", self._evidence_url(evidence), json=payload)
        return (data or {}).get("winstrom", {}).get("results", [])

    def update_record(self, evidence, record_id, fields):
        payload = {"winstrom": {evidence: fields}}
        data = self._request("PUT", self._evidence_url(evidence, f"/{record_id}"), json=payload)
        return (data or {}).get("winstrom", {}).get("results", [])

    def delete_record(self, evidence, record_id):
        self._request("DELETE", self._evidence_url(evidence, f"/{record_id}"))

    # ------------------------------------------------------------------
    # Faktury vydané / přijaté
    # ------------------------------------------------------------------

    def get_invoices_issued(self, filter_expr=None):
        return self.list_records(EVIDENCE_INVOICES_ISSUED, filter_expr=filter_expr)

    def get_invoices_received(self, filter_expr=None):
        return self.list_records(EVIDENCE_INVOICES_RECEIVED, filter_expr=filter_expr)

    def create_invoice_issued(self, fields):
        return self.create_record(EVIDENCE_INVOICES_ISSUED, fields)

    def create_invoice_received(self, fields):
        return self.create_record(EVIDENCE_INVOICES_RECEIVED, fields)

    # ------------------------------------------------------------------
    # Ostatní závazky
    # ------------------------------------------------------------------

    def get_unpaid_other_liabilities(self):
        """Neuhrazené ostatní závazky (evidence 'zavazek')."""
        return self.list_records(
            EVIDENCE_LIABILITIES,
            filter_expr="stavUhrK != 'stavUhr.uhrazeno'",
        )

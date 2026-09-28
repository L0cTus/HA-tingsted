"""Konstanter for Tingsted-integrasjonen."""
DOMAIN = "tingsted"
CONF_URL = "url"
CONF_KEY = "api_key"
CONF_SCAN = "scan_interval"
DEFAULT_SCAN = 300          # sekunder; webhooken gir oppdateringer med en gang uansett
EVENT = "tingsted_event"    # alle hendelser; i tillegg f.eks. tingsted_item_lent

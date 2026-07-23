"""Research sources for the weekly swimming-science agent.

Each source implements a common interface: a `fetch()` method returning a list
of plain dicts, one per item, with these keys:

    {
        'source':          short source slug, e.g. 'europepmc'
        'external_id':     globally-unique id for dedupe, e.g. 'europepmc:MED:42152785'
        'title':           str
        'authors':         str
        'abstract':        str
        'url':             str (link a coach can open)
        'published_date':  str, the source's date as-is (may be partial, e.g. '2026')
    }

Novelty and cost control do NOT live here -- the caller dedupes on
`external_id` (unique-indexed on ResearchItem) BEFORE any LLM call. A source
just returns what a date-filtered query gave back; overlap between weekly runs
is expected and handled downstream.

Only Europe PMC is implemented today. To add another source later, write a
class with the same `name` attribute and `fetch()` signature and append an
instance to `ALL_SOURCES` -- nothing else in the pipeline needs to change.

Every network call is wrapped so a single failing source (or query) logs and
returns what it has rather than killing the whole run.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Shared, polite HTTP settings. Europe PMC asks for a descriptive User-Agent so
# they can identify traffic; a short timeout keeps a slow source from stalling
# the whole weekly run.
USER_AGENT = 'STROKE-research-agent/1.0 (swim coaching platform)'
HTTP_TIMEOUT = 20
# Hard cap on any response body we'll read into memory -- a hostile or broken
# source must not be able to OOM the cron worker. Europe PMC pages are tens of
# KB; 8 MB is generous headroom while still bounding the blast radius.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
# One quick retry smooths over transient network blips without turning a flaky
# source into a retry storm.
HTTP_RETRIES = 1
RETRY_BACKOFF_SECONDS = 1.5


class _HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """SSRF guard: only follow redirects that stay on https. A source that
    303s us toward http:// or a non-http scheme (which is how an attacker would
    try to bounce us at an internal/metadata endpoint) gets refused."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not (newurl or '').lower().startswith('https://'):
            raise urllib.error.HTTPError(
                newurl, code, 'refused non-https redirect', headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Build one opener that enforces the https-only redirect policy for every GET.
_OPENER = urllib.request.build_opener(_HTTPSOnlyRedirectHandler())


def _http_get_json(url):
    """GET an https URL and parse JSON. Returns the decoded object, or None on
    any failure (bad scheme, network, timeout, oversized body, bad JSON) --
    never raises. Refuses non-https URLs outright (SSRF hardening) and reads at
    most MAX_RESPONSE_BYTES so a pathological response can't exhaust memory."""
    if not (url or '').lower().startswith('https://'):
        logger.error('research source: refusing non-https URL: %s', url)
        return None

    last_exc = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with _OPENER.open(req, timeout=HTTP_TIMEOUT) as resp:
                # Read one byte past the cap so we can tell "exactly at cap" from
                # "over cap" and reject the latter rather than silently truncating
                # into invalid JSON.
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                logger.error('research source: response exceeded %s bytes, discarding: %s',
                             MAX_RESPONSE_BYTES, url)
                return None
            return json.loads(raw.decode('utf-8', errors='replace'))
        except Exception as exc:
            last_exc = exc
            if attempt < HTTP_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)
    logger.warning('research source HTTP GET failed after %s attempt(s): %s (%s)',
                   HTTP_RETRIES + 1, url, last_exc)
    return None


class EuropePMCSource:
    """Europe PMC REST search (europepmc.org/RestfulWebService) -- free, no key,
    structured, date-filterable. We run a handful of competitive-swimming query
    terms, each constrained to items first published in the recent window, and
    flatten the results into the common item-dict shape."""

    name = 'europepmc'

    BASE_URL = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'

    # Broad-but-relevant terms for competitive swim coaching. Kept as a simple
    # list so it's easy to iterate on. Each runs as its own date-filtered query.
    QUERY_TERMS = (
        'swimming biomechanics',
        'swim training periodization',
        'competitive swimming physiology',
        'swimming stroke technique',
        'swimming performance analysis',
        # Verified against the live Europe PMC index to actually return hits as
        # quoted phrases (a phrase like "swimming taper and peaking" matches
        # almost nothing, so keep these tight and real).
        'swimming strength training',
        'swimming kinematics',
        'swimming propulsion',
        'swimming pacing',
        'swimming start performance',
    )

    # A stored item URL is rendered as a clickable href to a coach. Only these
    # schemes are ever safe there -- validating here (not just escaping in the
    # template) blocks a javascript:/data: URL from a compromised source turning
    # into stored XSS. Keep this in sync with the ResearchItem.url column length.
    _SAFE_URL_SCHEMES = ('https://', 'http://')
    _MAX_URL_LEN = 500

    def __init__(self, query_terms=None, page_size=25):
        self.query_terms = tuple(query_terms) if query_terms else self.QUERY_TERMS
        self.page_size = page_size

    def _build_url(self, term, start, end):
        # FIRST_PDATE limits to first-publication date -- the closest Europe PMC
        # field to "new this week". Quote the term so multi-word phrases stay
        # together, then AND the date range on.
        query = f'"{term}" AND (FIRST_PDATE:[{start.isoformat()} TO {end.isoformat()}])'
        params = {
            'query': query,
            'format': 'json',
            'pageSize': self.page_size,
            'resultType': 'core',  # includes abstractText / authorString
        }
        return f'{self.BASE_URL}?{urllib.parse.urlencode(params)}'

    @classmethod
    def _safe_url(cls, url):
        """Return url only if it's a safe, sane http(s) link within the column
        length; otherwise ''. Belt-and-braces against a rendered javascript: or
        data: href even though we construct the URL ourselves."""
        url = (url or '').strip()
        if not url:
            return ''
        if not url.lower().startswith(cls._SAFE_URL_SCHEMES):
            return ''
        if len(url) > cls._MAX_URL_LEN:
            return ''
        return url

    def _to_item(self, result):
        """Map one Europe PMC result object onto the common item dict, or None
        if it lacks the identifiers we need to dedupe/link on."""
        src = (result.get('source') or '').strip()
        rid = str(result.get('id') or '').strip()
        if not src or not rid:
            return None

        # external_id is namespaced by our source slug AND the PMC source/id so
        # it stays unique even if we add other providers later.
        external_id = f'{self.name}:{src}:{rid}'

        # Europe PMC gives no direct article-page URL; build the canonical one
        # from source+id (percent-encoding the path segments so a weird id can't
        # break out of the path), falling back to the DOI resolver.
        doi = (result.get('doi') or '').strip()
        if src and rid:
            url = f'https://europepmc.org/article/{urllib.parse.quote(src, safe="")}/{urllib.parse.quote(rid, safe="")}'
        elif doi:
            url = f'https://doi.org/{urllib.parse.quote(doi, safe="/")}'
        else:
            url = ''
        url = self._safe_url(url)

        return {
            'source': self.name,
            'external_id': external_id,
            'title': (result.get('title') or '').strip(),
            'authors': (result.get('authorString') or '').strip(),
            'abstract': (result.get('abstractText') or '').strip(),
            'url': url,
            'published_date': (result.get('firstPublicationDate')
                               or str(result.get('pubYear') or '')).strip(),
        }

    def fetch(self, since_days=10):
        """Run every query term over the last `since_days` and return a flat,
        de-duplicated (within this call) list of item dicts. A failure on one
        term is logged and skipped so the others still contribute."""
        end = date.today()
        start = end - timedelta(days=since_days)

        items = {}
        for term in self.query_terms:
            url = self._build_url(term, start, end)
            data = _http_get_json(url)
            if not data:
                continue  # already logged in _http_get_json
            results = ((data.get('resultList') or {}).get('result')) or []
            for result in results:
                item = self._to_item(result)
                if item is None:
                    continue
                # De-dupe within this run: the same paper often matches several
                # query terms. Cross-run dedupe happens later against the DB.
                items.setdefault(item['external_id'], item)

        logger.info('EuropePMCSource.fetch: %s unique items over last %s days',
                    len(items), since_days)
        return list(items.values())


# Registry the pipeline iterates over. Add future sources here.
ALL_SOURCES = [EuropePMCSource()]

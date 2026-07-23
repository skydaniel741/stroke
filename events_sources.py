"""External event-calendar sources for auto-importing meets/key dates into a
squad's calendar (SquadEvent), so a coach doesn't have to type them in.

Same seam idea as sources.py (research), but these return CALENDAR events, not
research papers. Each source implements `fetch()` returning a list of dicts:

    {
        'source':       short slug, e.g. 'scwc'
        'external_id':  stable unique id, e.g. 'scwc:68dce0005428d60173bd8238'
        'title':        str
        'start_date':   datetime.date
        'end_date':     datetime.date or None (multi-day meets)
        'location':     str ('' if unknown)
        'url':          str link to the event page ('' if none/unsafe)
    }

Dates come from STRUCTURED source data, never from an LLM guessing -- an AI pass
downstream only classifies event type / relevance, it never invents a date.

Only the Squarespace-backed SCWC calendar is implemented today; add another
class with the same `fetch()` shape and append it to build a registry later.
"""
import datetime
import html
import logging
import urllib.parse

from sources import _http_get_json  # reuse the hardened https-only JSON GET

logger = logging.getLogger(__name__)


def _epoch_ms_to_local_date(ms, tz):
    """Convert a Squarespace startDate/endDate (epoch milliseconds, UTC) to the
    event's LOCAL calendar date. Squarespace stores local midnight as UTC, so a
    naive UTC read lands a day early for NZ -- convert through the site tz."""
    if not isinstance(ms, (int, float)):
        return None
    try:
        utc = datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)
        if tz is not None:
            return utc.astimezone(tz).date()
        # Fallback if the tz database isn't available: NZ is UTC+12/+13, and
        # these timestamps are local-midnight, so +12h recovers the local date.
        return (utc + datetime.timedelta(hours=12)).date()
    except (ValueError, OverflowError, OSError):
        return None


class SquarespaceEventsSource:
    """Reads a Squarespace Events collection via its JSON view
    (`<events-url>?format=json`), which exposes `upcoming`/`past` lists with
    real title / startDate / endDate / location fields. Far more reliable than
    scraping the rendered cards."""

    def __init__(self, events_url='https://wearescwc.org/events', source='scwc',
                 site_tz='Pacific/Auckland'):
        self.events_url = events_url
        self.source = source
        self._tz = self._load_tz(site_tz)

    @staticmethod
    def _load_tz(name):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            logger.warning('events source: timezone %r unavailable, using +12h fallback', name)
            return None

    def _json_url(self):
        # Add format=json without clobbering any existing query string.
        parts = urllib.parse.urlsplit(self.events_url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        query['format'] = 'json'
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ''))

    def _site_base(self):
        parts = urllib.parse.urlsplit(self.events_url)
        return f'{parts.scheme}://{parts.netloc}'

    def _to_event(self, raw):
        """Map one Squarespace item onto the common event dict, or None if it
        lacks the id/title/date we need."""
        eid = str(raw.get('id') or '').strip()
        # Source strings are HTML-escaped (e.g. 'Recreation &amp; Sport'); unescape
        # so they don't render double-escaped once Jinja re-escapes them.
        title = html.unescape((raw.get('title') or '').strip())
        start_date = _epoch_ms_to_local_date(raw.get('startDate'), self._tz)
        if not eid or not title or start_date is None:
            return None

        end_date = _epoch_ms_to_local_date(raw.get('endDate'), self._tz)
        if end_date and end_date < start_date:
            end_date = None

        loc = raw.get('location') or {}
        location = html.unescape((loc.get('addressTitle') or '').strip()) if isinstance(loc, dict) else ''

        # Build a safe absolute URL to the event page, if any.
        full = (raw.get('fullUrl') or '').strip()
        url = ''
        if full.startswith('/'):
            url = self._site_base() + full
        if not url.lower().startswith('https://'):
            url = ''

        return {
            'source': self.source,
            'external_id': f'{self.source}:{eid}',
            'title': title,
            'start_date': start_date,
            'end_date': end_date,
            'location': location,
            'url': url,
        }

    def fetch(self, include_past=False):
        """Return normalized event dicts. Only upcoming events by default (a
        coach wants their forward calendar, not last season). Never raises."""
        data = _http_get_json(self._json_url())
        if not data:
            logger.warning('events source: no data from %s', self.events_url)
            return []

        raw_items = list(data.get('upcoming') or [])
        if include_past:
            raw_items += list(data.get('past') or [])

        events = {}
        for raw in raw_items:
            ev = self._to_event(raw)
            if ev is not None:
                events.setdefault(ev['external_id'], ev)

        logger.info('events source %s: %s events (%s upcoming raw)',
                    self.source, len(events), len(data.get('upcoming') or []))
        return list(events.values())

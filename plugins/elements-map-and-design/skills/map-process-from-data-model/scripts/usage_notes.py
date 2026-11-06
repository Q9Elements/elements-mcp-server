"""The usage note on each lifecycle level (basis usage only): how much the org uses the object or record type
the level follows, as one sticky note beside step 1.

Why: a lifecycle level drawn from metadata shows what is configured. A business analyst (or an agent) looking at
it also needs to know whether anyone still works that way: an Initial Opportunity level with 100 records changed
last week reads differently from a Stripe Opportunity level that has held no records for a year. Under basis usage
the run has read the figures already (inventory.py usage, from get_component_usage), so each level says them.

What the figures are, and are not (get_component_usage):
  - a record total for the object, and a count per record type (records of the Master record type are counted as
    "no record type");
  - the dates of the last created and last modified record, for the object as a whole: there are none per record
    type, so a record-type level marks them and the net change "(Opportunity-wide)";
  - the net change in the record count over 7 and 30 days, from daily snapshots, and its trend. It is a net
    figure: there is no separate count or date of deletions, so the note says 'Deletions not tracked.';
  - telemetry that is missing (usage.available false, or no velocity data) is a gap and is said to be one: it is
    never read as zero.

The reading, with fixed thresholds counted back from the day usage was read (readAt), not from today:
  No records   the object or record type holds none;
  Active       a record was created or modified in the last ACTIVE_DAYS days;
  Slowing      the last activity was ACTIVE_DAYS + 1 to DORMANT_DAYS days ago;
  Dormant      the last activity was more than DORMANT_DAYS days ago.
Without either date the reading is "Activity dates not available". On a record-type level the reading comes from
the object-wide dates, except that a record type with no records reads "No records".

The note is plain short sentences without line breaks (a level note loses them); parentheses are kept, as a note
stores them unchanged. The figures stay under about 300 characters; then comes every object related to the level's
object (a direct Lookup or Master-Detail either way, related_objects) that holds no records, never truncated.

Standard library only; Python 3.8 or later.
"""

import re
from datetime import date

ACTIVE_DAYS = 30      # Active: last created or modified within this many days of readAt
DORMANT_DAYS = 180    # Slowing up to this many days; Dormant beyond it
READINGS = ("No records", "Active", "Slowing", "Dormant")
NO_DATES = "Activity dates not available"
DELETIONS = "Deletions not tracked."   # the net change is records gained minus lost; no deletion count or date exists
PURPOSE = "usage"     # levelNotes[].purpose of these notes
DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def day(text):
    """A date from an ISO date or timestamp ('2026-10-01T09:00:00.000Z'), or None."""
    match = DATE.match(str(text or ""))
    if not match:
        return None
    try:
        return date(*(int(g) for g in match.groups()))
    except ValueError:
        return None


def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def reading(usage, total=None):
    """(reading, days since the last activity or None). total: the count the reading is about (a record type's),
    the object's total when left out."""
    usage = usage or {}
    total = count(usage.get("total")) if total is None else count(total)
    if total == 0:
        return "No records", None
    dates = [d for d in (day(usage.get("lastCreated")), day(usage.get("lastModified"))) if d]
    as_of = day(usage.get("readAt"))
    if not dates or not as_of:
        return NO_DATES, None
    days = max(0, (as_of - max(dates)).days)
    if days <= ACTIVE_DAYS:
        return "Active", days
    if days <= DORMANT_DAYS:
        return "Slowing", days
    return "Dormant", days


def number(n):
    return f"{n:,}"


def share(part, whole):
    if not whole:
        return None
    pct = 100.0 * part / whole
    return "under 1%" if 0 < pct < 0.5 else f"{pct:.0f}%"


def dates_sentence(usage, scope=""):
    """'Last created 2026-10-20, last modified 2026-10-21.' (with ' (Opportunity-wide)' before the full stop when
    scope is given), or '' when neither date is known."""
    created, modified = day(usage.get("lastCreated")), day(usage.get("lastModified"))
    if not created and not modified:
        return ""
    return (f"Last created {created.isoformat() if created else 'not recorded'}, "
            f"last modified {modified.isoformat() if modified else 'not recorded'}{scope}.")


def change_sentence(usage, scope=""):
    """'Net change over 30 days: +12, trend up.' Over the days recorded when there are fewer than 30."""
    net = count(usage.get("net30"))
    if net is None:
        return "Net change not available."
    window = count(usage.get("windowDays"))
    span = "30 days" if window is None or window >= 30 else f"{window} days"
    trend = f", trend {usage['trend']}" if usage.get("trend") else ""
    return f"Net change over {span}: {net:+,}{trend}{scope}." if net else f"Net change over {span}: 0{trend}{scope}."


def tail(usage, kind, scope=""):
    """The sentences every note ends with: dates, net change, deletions, reading."""
    dates = dates_sentence(usage, scope)
    change = change_sentence(usage, scope)   # on a record-type level both figures are the object's, and say so
    return " ".join(p for p in (dates, change, DELETIONS, f"Reading: {kind}.") if p)


def title(name, usage):
    read = (usage or {}).get("readAt")
    return f"Usage of {name}" + (f" as of {read}" if read else "")


def unavailable(usage):
    reason = " ".join(str((usage or {}).get("reason") or "").split()).rstrip(".")
    reason = " ".join(re.sub(r"[()\"'/]", " ", reason).split())
    return "Usage not available" + (f": {reason}" if reason else "") + ". A telemetry gap, not zero records."


def records(n):
    return f"{number(n)} record{'' if n == 1 else 's'}"


def object_text(usage):
    """The note text (after its title) for an object lifecycle level: an object without custom record types."""
    usage = usage or {}
    total = count(usage.get("total"))
    if not usage.get("available") or total is None:
        return unavailable(usage)
    kind, _ = reading(usage)
    return f"{records(total)}. " + tail(usage, kind)


def record_type_text(usage, rt_label, rt_total, object_name):
    """The note text for a record type's lifecycle level: its records and share of the object's, then the
    object-wide dates and change, labelled so (there are none per record type), then the reading."""
    usage = usage or {}
    total = count(usage.get("total"))
    if not usage.get("available") or total is None:
        return unavailable(usage)
    rt_total = count(rt_total)
    if rt_total is None:
        first = f"Records of {rt_label} not available, of {number(total)} {object_name} records."
    elif total == 0:
        first = f"0 records, {object_name} holds none."
    else:
        first = f"{records(rt_total)} ({share(rt_total, total)} of {number(total)} {object_name} records)."
    kind = "No records" if rt_total == 0 else reading(usage, total)[0]
    return f"{first} " + tail(usage, kind, f" ({object_name}-wide)")


def split_text(usage, record_types):
    """The note text for a record-type split level: the object's total, the count per record type (record_types:
    [(label, count or None)], most first) and records without a record type, the dates, the change, the reading."""
    usage = usage or {}
    total = count(usage.get("total"))
    if not usage.get("available") or total is None:
        return unavailable(usage)
    rows = [(label, count(n)) for label, n in record_types]
    known = sorted([r for r in rows if r[1] is not None], key=lambda r: -r[1])
    pieces = [f"{label} {number(n)}" for label, n in known] + [f"{label} not available" for label, n in rows if n is None]
    without = count(usage.get("withoutRecordType"))
    if without is not None:
        pieces.append(f"no record type {number(without)}")
    kind, _ = reading(usage)
    return f"{records(total)}: " + ", ".join(pieces) + ". " + tail(usage, kind)


def record_type_count(usage, rt):
    """A record type's records: the inventory's lifecycle record type usage, else the object's byRecordType by
    label, then by API name; None when unknown."""
    n = count(((rt or {}).get("usage") or {}).get("total"))
    if n is not None:
        return n
    by_rt = (usage or {}).get("byRecordType") or {}
    for key in ((rt or {}).get("label"), (rt or {}).get("name")):
        if key in by_rt and count(by_rt[key]) is not None:
            return by_rt[key]
    return None


RELATED_KINDS = ("lookup", "master-detail")   # inventory relationships[].kind that count as related


def related_objects(inv, api):
    """API names of the objects with a direct Lookup or Master-Detail relationship to api, either way round, from
    the inventory's relationships (the reference fields Elements synced: 'from' holds the field, 'to' is its
    target). A polymorphic field (one that can point at many object types, such as Task.WhatId) counts only when
    api is its target ('to'): api's own polymorphic fields are ignored, as #1 ignores them for grouping."""
    found = []
    for rel in inv.get("relationships", []):
        if rel.get("kind") not in RELATED_KINDS or rel["from"] == rel["to"]:
            continue
        if rel["to"] == api:
            found.append(rel["from"])
        elif rel["from"] == api and not rel.get("polymorphic"):
            found.append(rel["to"])
    return list(dict.fromkeys(found))


def no_records_sentence(names):
    """'7 objects that have a relationship to this object hold no records: A, B, C.' (all of them, alphabetical),
    the singular for one, '' for none."""
    names = sorted(names, key=lambda n: n.casefold())
    if not names:
        return ""
    if len(names) == 1:
        return f"1 object that has a relationship to this object holds no records: {names[0]}."
    return f"{len(names)} objects that have a relationship to this object hold no records: {', '.join(names)}."


def level_note(title_text, text, extra=""):
    """A levelNotes entry (ba-model.schema.json) without parent and near, which the build adds."""
    return {"title": title_text, "text": (text + (" " + extra if extra else "")).strip(), "purpose": PURPOSE}

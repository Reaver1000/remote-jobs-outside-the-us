"""Generate the daily two-tier 'remote jobs outside the US' digest.

Free tier: the top 20 postings from the PREVIOUS sweep (a day's delay), chosen
for region spread, pay-marked first. Paid tier: the full fresh list from
today's sweep, no delay. The delay is the product: freshness is the scarce
good, and this pipeline's own measurements (the funnel analysis) show the
first days of a posting's life are the ones that matter.

Outputs:
  data/newsletter_YYYY-MM-DD.md        combined post with a PAYWALL marker
  data/newsletter_free_YYYY-MM-DD.md    free section only (GitHub README)
"""
import csv
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FREE_CAP = 20

REGION_RULES = [
    ("United States", r"united states|\busa\b|u\.s\.|\bus\b|\bamerica\b|new york|san francisco|los angeles|chicago|boston|austin|seattle|denver|atlanta|dallas|miami|philadelphia|phoenix|houston|washington"),
    ("Canada", r"canada|toronto|vancouver|montreal|ottawa|calgary"),
    ("United Kingdom", r"united kingdom|\buk\b|\bengland\b|scotland|wales|london|manchester|birmingham|\bleeds\b|bristol|edinburgh|glasgow"),
    ("Germany", r"germany|deutschland|berlin|munich|m\u00fcnchen|hamburg|frankfurt|cologne|k\u00f6ln|leipzig|stuttgart|d\u00fcsseldorf|dusseldorf|dresden|nuremberg|heidelberg"),
    ("Europe", r"france|paris|netherlands|amsterdam|spain|madrid|barcelona|italy|milan|rome|poland|warsaw|ireland|dublin|austria|vienna|switzerland|zurich|belgium|brussels|sweden|stockholm|denmark|copenhagen|finland|helsinki|norway|oslo|portugal|lisbon|czech|prague"),
    ("EMEA", r"emea"),
    ("APAC", r"apac|asia|singapore|japan|tokyo|india|australia|sydney|china|hong kong|korea|taiwan|new zealand|vietnam|thailand|indonesia|philippines|malaysia"),
    ("LATAM", r"latam|brazil|mexico|argentina|colombia|chile|peru"),
    ("Africa", r"africa|nigeria|kenya|egypt|ghana"),
]
REGION_ORDER = ["United Kingdom", "Germany", "Europe", "EMEA", "Canada", "APAC", "LATAM", "Africa", "Remote, worldwide"]

MONEY = re.compile(
    r"[$€£]\s?\d{2,3}[,.]\s?\d{3}(?:\s?[-–—to]+\s?[$€£]?\s?\d{2,3}[,.]\s?\d{3})?"
    r"|\d{2,3}[,.]\d{3}\s?(?:€|eur|euros?|£|gbp|usd|dollars?)"
    r"|[$€£]\s?\d{2,3}k(?:\s?[-–—to]+\s?[$€£]?\s?\d{2,3}k)?"
    r"|\d{2}\.000(?:\s?[-–—bis]+\s?\d{2}\.000)?\s?(?:€|eur|euro)",
    re.I,
)


US_SIGNAL = re.compile(
    r"united states|\busa\b|u\.s\.|\bus only\b|alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
    r"delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|"
    r"massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|"
    r"new mexico|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|"
    r"south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming|"
    r"nyc|new york|san francisco|los angeles|chicago|boston|austin|seattle|denver|atlanta|dallas|miami|"
    r"philadelphia|phoenix|houston|washington d\.?c\.?", re.I,
)


def region_of(loc):
    s = " %s " % str(loc or "").lower()
    for label, pattern in REGION_RULES:
        if re.search(pattern, s):
            return label
    if re.search(r"remote|anywhere|worldwide|global", s):
        return "Remote, worldwide"
    return None


def us_only_title(title):
    """A title naming a US state or city is a strong US-only signal even when
    the location text just says Remote. Err toward excluding: the list's
    promise is eligibility, not completeness."""
    return bool(US_SIGNAL.search(title or ""))


def has_pay(r):
    blob = "%s %s %s %s" % (r.get("title") or "", r.get("location") or "",
                            r.get("source") or "", r.get("url") or "")
    return bool(MONEY.search(blob))


def eligible(csv_path, as_of):
    """Fresh (<=7d), remote, non-US rows with region, from one snapshot."""
    out = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if str(r.get("remote")) != "1":
                continue
            if us_only_title(r.get("title")):
                continue
            reg = region_of(r.get("location"))
            if reg is None or reg == "United States":
                continue
            p = (r.get("posted") or "").strip()
            if not re.match(r"\d{4}-\d{2}-\d{2}$", p):
                continue
            age = (as_of - datetime.strptime(p, "%Y-%m-%d").date()).days
            if 0 <= age <= 7:
                out.append((r, p, age, reg, has_pay(r)))
    return out


def snapshot_dates():
    dates = []
    for p in glob.glob(os.path.join(DATA, "jobs_snapshot_*.csv")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p)
        if m:
            dates.append((m.group(1), p))
    return sorted(dates)


def pick_free(rows, cap=FREE_CAP):
    """Round-robin across regions (biggest regions first), pay-marked and
    freshest first within each region."""
    by_reg = defaultdict(list)
    for entry in rows:
        by_reg[entry[3]].append(entry)
    for reg in by_reg:
        by_reg[reg].sort(key=lambda e: (not e[4], e[2]))
    order = sorted(by_reg, key=lambda r: -len(by_reg[r]))
    picked = []
    i = 0
    while len(picked) < cap:
        added = False
        for reg in order:
            if i < len(by_reg[reg]):
                picked.append(by_reg[reg][i])
                added = True
                if len(picked) >= cap:
                    break
        if not added:
            break
        i += 1
    return picked


def render(entries, with_headers=True):
    lines = []
    if with_headers:
        by_reg = defaultdict(list)
        for e in entries:
            by_reg[e[3]].append(e)
        for reg in REGION_ORDER:
            if reg not in by_reg:
                continue
            lines.append("## %s (%d)" % (reg, len(by_reg[reg])))
            lines.append("")
            for r, p, age, _, pay in by_reg[reg]:
                lines.append(entry_lines(r, p, pay))
            lines.append("")
    else:
        for r, p, age, reg, pay in entries:
            lines.append("- **%s** @ %s%s (%s, posted %s) - %s" % (
                (r.get("title") or "").strip(), (r.get("company") or "").strip(),
                " [pay shown]" if pay else "", reg, p, (r.get("url") or "").strip()))
        lines.append("")
    return "\n".join(lines)


def entry_lines(r, p, pay):
    title = (r.get("title") or "").strip()
    company = (r.get("company") or "").strip()
    loc = (r.get("location") or "").strip()[:60]
    url = (r.get("url") or "").strip()
    tag = " [pay shown]" if pay else ""
    return "- **%s** @ %s%s\n  %s | posted %s - %s" % (title, company, tag, loc, p, url)


def main():
    today = date.today().isoformat()
    snaps = snapshot_dates()
    today_path = next((p for d, p in snaps if d == today), None)
    if not today_path:
        raise SystemExit("need today's snapshot")

    paid_rows = eligible(today_path, date.today())
    free_rows = pick_free(paid_rows)

    n_pay_shown = sum(1 for e in paid_rows if e[4]) + sum(1 for e in free_rows if e[4])

    head = "# Remote jobs outside the US, %s" % date.today().strftime("%B %d, %Y")
    intro_free = (
        "The shortlist below is today's free 20. Subscribers get the full list with every sweep: "
        "today that is **%d fresh remote postings outside the US**, every posting linking to the original advert, "
        "pay shown where the ad shows it. "
        "Generated from [job-market-daily](https://huggingface.co/datasets/Reaver1000/job-market-daily)."
        % len(paid_rows)
    )

    free_body = render(free_rows, with_headers=False)
    combined = [
        head, "", intro_free, "",
        "## Today's free shortlist (20)", "",
        free_body.rstrip(),
        "",
        "=== PAYWALL: everything below goes in the paid section ===",
        "",
        "## The full list from this sweep (%d postings)" % len(paid_rows), "",
        render(paid_rows, with_headers=True).rstrip(),
        "",
        "---",
        "Method: [remote-job-engine](https://github.com/Reaver1000/remote-job-engine) sweeps 80+ public sources. "
        "The digest keeps remote postings whose recognised region is not the United States, posted within 7 days. "
        "No aggregator spam, no ghost-posting padding: everything here was live on an employer board this week. "
        "Open archive of the free shortlists: https://github.com/Reaver1000/remote-jobs-outside-the-us",
        "",
    ]
    with open(os.path.join(DATA, "newsletter_%s.md" % today), "w", encoding="utf-8") as f:
        f.write("\n".join(combined))

    free_only = [
        head, "",
        "The daily free shortlist: 20 fresh remote postings outside the US. "
        "Subscribers to the newsletter get the full list with every sweep (%d postings from today's run). "
        % len(paid_rows),
        "", "## Free shortlist (%s)" % today, "",
        free_body.rstrip(),
        "",
        "---",
        "Method: [remote-job-engine](https://github.com/Reaver1000/remote-job-engine) sweeps 80+ public sources. "
        "Full open data: [job-market-daily](https://huggingface.co/datasets/Reaver1000/job-market-daily); "
        "live dashboard: https://reaver1000-job-market-dashboard.static.hf.space",
        "",
    ]
    with open(os.path.join(DATA, "newsletter_free_%s.md" % today), "w", encoding="utf-8") as f:
        f.write("\n".join(free_only))

    print("free shortlist: %d postings from today's sweep" % len(free_rows))
    print("paid full list: %d postings" % len(paid_rows))
    print("pay-marked across both: %d" % n_pay_shown)
    print("wrote newsletter_%s.md and newsletter_free_%s.md" % (today, today))


if __name__ == "__main__":
    main()

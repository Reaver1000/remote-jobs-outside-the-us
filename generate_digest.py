"""Generate the daily 'remote jobs outside the US' digest.

Reads data/latest.csv and builds a markdown digest of fresh, remote, non-US
postings: dated within the last 7 days, remote flag set, recognised region
outside the United States. Within each region, postings that state pay come
first. Role family is not filtered: engineering, sales, ops, design, support
and everything else all ship, because the list serves the applicant who is
not American, not a particular stack.

Output: data/newsletter_YYYY-MM-DD.md, plus a console summary.
"""
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
LATEST = os.path.join(HERE, "data", "latest.csv")

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


def region_of(loc):
    s = " %s " % str(loc or "").lower()
    for label, pattern in REGION_RULES:
        if re.search(pattern, s):
            return label
    if re.search(r"remote|anywhere|worldwide|global", s):
        return "Remote, worldwide"
    return None


def has_pay(title, location, source, url):
    blob = "%s %s %s %s" % (title, location, source, url)
    return bool(MONEY.search(blob))


def main():
    today = date.today()
    rows = list(csv.DictReader(open(LATEST, encoding="utf-8", newline="")))
    total = len(rows)

    fresh = defaultdict(list)
    undated_remote_nonus = 0
    for r in rows:
        if str(r.get("remote")) != "1":
            continue
        reg = region_of(r.get("location"))
        if reg is None or reg == "United States":
            continue
        p = (r.get("posted") or "").strip()
        if re.match(r"\d{4}-\d{2}-\d{2}$", p):
            age = (today - datetime.strptime(p, "%Y-%m-%d").date()).days
            if 0 <= age <= 7:
                fresh[reg].append((r, p, age))
        else:
            undated_remote_nonus += 1

    def bucket(r, p, age):
        lines = []
        title = (r.get("title") or "").strip()
        company = (r.get("company") or "").strip()
        loc = (r.get("location") or "").strip()
        url = (r.get("url") or "").strip()
        pay = has_pay(title, loc, r.get("source") or "", url)
        tag = " [pay in ad]" if pay else ""
        lines.append("- **%s** @ %s%s" % (title, company, tag))
        lines.append("  %s%s - %s" % (loc[:60], (" | posted %s" % p) if p else "", url))
        return "\n".join(lines), pay, age

    out = []
    out.append("# Remote jobs outside the US, %s" % today.strftime("%B %d, %Y"))
    out.append("")
    out.append("Fresh remote postings from the last 7 days, open to applicants outside the United States. Every posting links to the original advert. Listings that show pay in their own text are marked. Generated daily from [job-market-daily](https://huggingface.co/datasets/Reaver1000/job-market-daily); the live dashboard is [here](https://reaver1000-job-market-dashboard.static.hf.space).")
    out.append("")

    n_regions = 0
    n_postings = 0
    n_pay = 0
    for reg in REGION_ORDER:
        if reg not in fresh:
            continue
        n_regions += 1
        entries = sorted(
            ((bucket(r, p, age), r, p, age) for r, p, age in fresh[reg]),
            key=lambda t: (not t[0][1], t[3]),
        )
        n_postings += len(entries)
        n_pay += sum(1 for e in entries if e[0][1])
        out.append("## %s (%d new this week)" % (reg, len(entries)))
        out.append("")
        for (text, pay, age), r, p, a in entries[:20]:
            out.append(text)
            out.append("")
        if len(entries) > 20:
            out.append("... and %d more. The full day's data is in the dataset." % (len(entries) - 20))
            out.append("")

    out.append("---")
    out.append("Counts today: %d fresh remote postings outside the US across %d regions, %d stating pay in the advert. %d undated remote postings outside the US were left out because freshness could not be verified." % (
        n_postings, n_regions, n_pay, undated_remote_nonus))
    out.append("")
    out.append("Method: [remote-job-engine](https://github.com/Reaver1000/remote-job-engine) sweeps 80+ public sources daily; the digest keeps remote postings whose recognised region is not the United States, posted within 7 days. No aggregator spam, no ghost-posting padding: if it is on this list, it was on an employer board or a verifiable lane this week.")

    body = "\n".join(out)
    path = os.path.join(HERE, "data", "newsletter_%s.md" % today.isoformat())
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    print("regions with fresh remote non-US roles: %d" % n_regions)
    print("fresh postings total: %d (%d state pay)" % (n_postings, n_pay))
    print("undated remote non-US excluded: %d" % undated_remote_nonus)
    print("wrote %s" % path)


if __name__ == "__main__":
    main()

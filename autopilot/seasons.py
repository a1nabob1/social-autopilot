"""Seasonal and holiday post calendar. Each event shows up in the first open slot from 4 days before to 1 day after."""
import datetime as dt

EVENTS = [
    # --- insurance (hoinow.com) ---
    ("01-06", "insurance", "new-year-review", "New Year", "Start the year with a policy check-up",
     "Life changes, and so do home values. A quick yearly review makes sure your coverage still fits your home, cars and family.", ["home"]),
    ("03-15", "insurance", "spring-storms", "Spring storm season", "Spring storms are coming. Is your home ready?",
     "Hail and high winds hit the Gulf Coast every spring. Take photos of your home and belongings now so a claim is easier later.", ["storm", "home"]),
    ("05-01", "insurance", "flood-wait", "Before hurricane season", "Flood policies usually have a 30-day wait",
     "Most flood policies don't start right away. If you want flood coverage before hurricane season, now is the time to ask.", ["flood"]),
    ("06-01", "insurance", "hurricane-start", "Hurricane season", "Hurricane season starts June 1",
     "Make your plan, check your deductible, and know where your policy documents are. Our preparedness guide walks you through it.", ["hurricane", "prepared"]),
    ("08-15", "insurance", "hurricane-peak", "Peak hurricane season", "We're entering peak hurricane season",
     "The busiest weeks of the season are here. Review your hurricane deductible and your evacuation plan this weekend.", ["hurricane", "storm"]),
    ("11-30", "insurance", "hurricane-end", "End of hurricane season", "Hurricane season ends November 30",
     "A good time to look back: did your coverage feel right this year? We're happy to walk through it with you.", ["storm-recovery", "home"]),
    ("11-24", "insurance", "turkey-fryer", "Thanksgiving", "Frying a turkey this year?",
     "Keep the fryer outdoors, away from the house and off the deck, and never leave it alone. Have a safe Thanksgiving.", ["home"]),
    ("12-18", "insurance", "holiday-travel", "Holiday travel", "Driving for the holidays?",
     "Check your tires, pack a phone charger and keep your insurance card handy. Safe travels from our family to yours.", ["auto"]),
    # --- mortgage (finehomeloan.com) ---
    ("01-08", "mortgage", "new-year-plan", "New Year", "Thinking about buying this year?",
     "The best time to start is months before you shop. Checking your credit and budget early gives you more choices later.", ["apply", "conventional"]),
    ("03-01", "mortgage", "spring-market", "Spring buying season", "Spring is the busiest time to buy on the Gulf Coast",
     "Sellers list more homes in spring. Getting your paperwork ready now helps you move fast when the right home shows up.", ["gulf-coast", "baldwin"]),
    ("06-01", "mortgage", "homeownership-month", "National Homeownership Month", "June is National Homeownership Month",
     "Owning a home is a big step. Here's a plain-English look at the loan options people use most along the Gulf Coast.", ["conventional", "gulf-coast"]),
    ("07-04", "mortgage", "july-4", "Independence Day", "Happy Fourth of July from Fine Home Loan",
     "Wishing you a safe and happy holiday with family and friends.", []),
    ("11-11", "mortgage", "veterans-day", "Veterans Day", "Thank you, veterans",
     "Today we honor those who served. If you're a veteran thinking about a home, VA loans were made for you.", ["va-loans"]),
    ("11-26", "mortgage", "thanksgiving", "Thanksgiving", "Happy Thanksgiving",
     "We're grateful for every family we've helped find a home on the Gulf Coast.", []),
    ("12-27", "mortgage", "year-end", "Year end", "Planning a move next year?",
     "Moving to the Gulf Coast in the new year? Our guide covers neighborhoods, taxes and what to expect.", ["moving", "property-taxes"]),
]


def due(industry, day):
    out = []
    for md, ind, key, label, headline, body, match in EVENTS:
        if ind != industry:
            continue
        m, d = map(int, md.split("-"))
        ev = dt.date(day.year, m, d)
        if ev - dt.timedelta(days=4) <= day <= ev + dt.timedelta(days=1):
            out.append({"key": key, "label": label, "headline": headline, "body": body, "match": match})
    return out


def best_page(store, words):
    for w in words:
        for url, page in store["pages"].items():
            if w in url.lower():
                return page
    return None

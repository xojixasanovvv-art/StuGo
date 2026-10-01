"""TZ 5.4 — Moslik foizi (matching score): oddiy vaznli algoritm."""

from decimal import Decimal

from apps.roommates.models import RoommateProfile

# Vaznlar (jami 100)
WEIGHTS = {
    "city": 25,
    "budget": 25,
    "sleep": 15,
    "cleanliness": 15,
    "smoking": 10,
    "pets": 5,
    "guests": 5,
}


def _budget_overlap(a_max, b_min, a_min, b_max) -> float:
    """Ikkala byudjet oraliqlari kesishishiga qarab 0..1."""
    a_min, a_max = a_min or Decimal(0), a_max or Decimal("999999999")
    b_min, b_max = b_min or Decimal(0), b_max or Decimal("999999999")
    lo = max(a_min, b_min)
    hi = min(a_max, b_max)
    if hi <= lo:
        return 0.0
    span = float(hi - lo)
    avg = float((min(a_max, b_max) - max(a_min, b_min) + 1)) or 1.0
    return min(1.0, span / avg)


def compatibility_score(a: RoommateProfile, b: RoommateProfile) -> int:
    """Ikkita anketa orasidagi moslik foizi (0..100)."""
    if a.user_id == b.user_id:
        return 0

    score = 0.0

    # 1. Shahar
    if a.city.lower() == b.city.lower():
        score += WEIGHTS["city"]

    # 2. Byudjet: ikkala tomon ham kiritgan bo'lsa — kesishish; aks holda neytral (yarim ball)
    if a.budget_min is not None and a.budget_max is not None and b.budget_min is not None and b.budget_max is not None:
        score += WEIGHTS["budget"] * _budget_overlap(
            a.budget_max, b.budget_min, a.budget_min, b.budget_max
        )
    else:
        score += WEIGHTS["budget"] * 0.5

    # 3. Uyqu tartibi
    if a.sleep_schedule == b.sleep_schedule:
        score += WEIGHTS["sleep"]
    elif {a.sleep_schedule, b.sleep_schedule} == {"early", "late"}:
        score += WEIGHTS["sleep"] * 0.3  # qarama-qarshi — kichik ball

    # 4. Tozalik
    diff = abs(
        ["relaxed", "average", "tidy", "very_tidy"].index(a.cleanliness)
        - ["relaxed", "average", "tidy", "very_tidy"].index(b.cleanliness)
    )
    score += WEIGHTS["cleanliness"] * (1 - diff / 3)

    # 5. Chekish (mos kelishi muhim)
    if a.smoking == b.smoking:
        score += WEIGHTS["smoking"]

    # 6. Uy hayvoni
    if a.pets == b.pets:
        score += WEIGHTS["pets"]

    # 7. Mehmonlar
    if a.guests_ok == b.guests_ok:
        score += WEIGHTS["guests"]

    return round(score)

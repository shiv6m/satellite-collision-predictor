"""
Risk classification for a screened conjunction.

Real conjunction assessments (like those from Space-Track / 18th Space
Defense Squadron) use probability of collision, which factors in position
*uncertainty*, not just miss distance -- two objects with a predicted miss
distance of 500m but huge position uncertainty can be higher risk than
objects with a tighter, well-known 200m pass. We don't have covariance
data here (that requires the restricted CDM feed), so we use miss
distance as a practical proxy, which is standard for a screening-level
system like this.
"""

REPORT_THRESHOLD_KM = 10.0   # ignore anything farther than this
HIGH_RISK_KM = 1.0
MODERATE_RISK_KM = 5.0

# Docked spacecraft (ISS + its docked capsules, CSS + its modules) move as a
# single rigid structure, so their relative speed at "closest approach" is
# essentially zero -- unlike two independent objects on separate orbits,
# which are always closing or separating at real speed even at their nearest
# point. This threshold catches "moving together" vs "actually converging."
COORBITING_SPEED_KM_S = 0.05  # 50 m/s


def classify(miss_distance_km: float, relative_speed_km_s: float) -> str:
    if relative_speed_km_s < COORBITING_SPEED_KM_S:
        return "co-orbiting"  # docked/formation flying, not a collision risk
    if miss_distance_km < HIGH_RISK_KM:
        return "high"
    if miss_distance_km < MODERATE_RISK_KM:
        return "moderate"
    return "low"


def is_reportable(miss_distance_km: float) -> bool:
    return miss_distance_km < REPORT_THRESHOLD_KM

"""Single home for data sources, the circuit mapping and every threshold."""
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "analysis" / "reports"

# --- Sources -----------------------------------------------------------------
# Pinned commits: results cannot change under us. To add a later event, bump the
# SHA; files already cached are never fetched again (the manifest records which
# SHA each file came from).
REPO = "TracingInsights/{season}"
SHA = {
    2025: "dfb3ea3f50b69857fe8e40cabe5e899743c59f6a",
    2026: "f2c7692c87817a48fa7d85749f2767743d62be70",
}
SEASONS = (2025, 2026)
SESSION = "Qualifying"
SESSION_FILES = (
    "session_info.json", "session_laptimes.json", "drivers.json",
    "corners.json", "weather.json",
)
HTTP_WORKERS = 6
HTTP_RETRIES = 4
HTTP_TIMEOUT = 30


# --- Circuits ----------------------------------------------------------------
class Circuit(NamedTuple):
    id: str
    key: int            # F1 circuit key, asserted against session_info.json
    name: str
    event2025: str      # folder name without " Grand Prix"
    event2026: str

    def event(self, season: int) -> str:
        return f"{self.event2025 if season == 2025 else self.event2026} Grand Prix"


# Ordered by 2026 date. NEVER match on event name: in 2026 the "Bahrain" GP was
# run at Kuala Lumpur and the "Spanish" GP at Madring.
CIRCUITS = (
    Circuit("melbourne", 10, "Melbourne", "Australian", "Australian"),
    Circuit("shanghai", 49, "Shanghai", "Chinese", "Chinese"),
    Circuit("suzuka", 46, "Suzuka", "Japanese", "Japanese"),
    Circuit("miami", 151, "Miami", "Miami", "Miami"),
    Circuit("montreal", 23, "Montréal", "Canadian", "Canadian"),
    Circuit("monaco", 22, "Monaco", "Monaco", "Monaco"),
    Circuit("catalunya", 15, "Barcelona-Catalunya", "Spanish", "Barcelona"),
    Circuit("spielberg", 19, "Spielberg", "Austrian", "Austrian"),
    Circuit("silverstone", 2, "Silverstone", "British", "British"),
    Circuit("spa", 7, "Spa-Francorchamps", "Belgian", "Belgian"),
    Circuit("hungaroring", 4, "Hungaroring", "Hungarian", "Hungarian"),
    Circuit("zandvoort", 55, "Zandvoort", "Dutch", "Dutch"),
    Circuit("monza", 39, "Monza", "Italian", "Italian"),
    Circuit("baku", 144, "Baku", "Azerbaijan", "Azerbaijan"),
    Circuit("singapore", 61, "Singapore", "Singapore", "Singapore"),
    Circuit("austin", 9, "Austin", "United States", "United States"),
    Circuit("mexico", 65, "Mexico City", "Mexico City", "Mexico City"),
    Circuit("interlagos", 14, "Interlagos", "São Paulo", "São Paulo"),
    Circuit("vegas", 152, "Las Vegas", "Las Vegas", "Las Vegas"),
)

# Events deliberately not compared: (season, event without "Grand Prix") -> reason
EXCLUDED = {
    (2026, "Bahrain"): "Run at Kuala Lumpur; no 2025 race there",
    (2026, "Spanish"): "Madring, a new circuit; no 2025 race there",
    (2025, "Bahrain"): "Sakhir; no 2026 race there in the data",
    (2025, "Saudi Arabian"): "Jeddah; no 2026 race there in the data",
    (2025, "Emilia Romagna"): "Imola; no 2026 race there in the data",
    (2025, "Qatar"): "Lusail; 2026 race not yet in the data",
    (2025, "Abu Dhabi"): "Yas Marina; 2026 race not yet in the data",
}
# Sessions expected to have no dry laps at all; anything else with none is an error.
EXPECTED_WET = {(2025, "vegas"), (2026, "interlagos")}

# Laps the narrative needs even when they are not a team's best.
EXTRA_LAPS = ((2025, "spa", "ANT", 5),)

# --- Lap selection -----------------------------------------------------------
DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")
REPLACE_WITHIN = 0.015      # replacement lap may be at most 1.5% off the team's best
MIN_COVERAGE = 0.85         # masked laps need at least this much good telemetry
MIN_TEAMS = 6               # teams a circuit-season needs for a circuit average

# --- Lap quality checks ------------------------------------------------------
QC_FROZEN_S = 1.0           # speed AND rpm unchanged for longer than this ...
QC_FROZEN_MIN_SPEED = 50    # ... while faster than this (km/h)
QC_DIST_VS_XY = 0.01        # telemetry distance vs x/y path length
QC_XY_VS_REF = 0.01         # x/y path length vs the circuit reference
QC_MAX_GAP_S = 1.5          # longest time without a sample
QC_DURATION_S = 0.1         # telemetry duration vs lap time
QC_LINE_P95_M = 15          # p95 distance from the reference line
# Approved 2026-11-24: Shanghai's 2026 x/y runs ~1.4% long with a ~5 m offset, but
# alignment projects onto the reference line and never uses path length.
QC_SKIP = {"shanghai": {"xy_vs_ref", "dist_vs_xy"}}
LOW_CONFIDENCE = {"shanghai": "2026 positions are noisy; alignment is looser here"}
UNITS_PER_M = 10.0          # x, y, z are decimetres (the docs say metres)

# --- Alignment ---------------------------------------------------------------
FIGURES = ROOT / "analysis" / "figures"
STEP = 5.0                  # grid spacing along the reference line (m)
REF_SMOOTH_M = 55           # smoothing of the mean racing line before curvature
Z_SMOOTH_M = 105            # smoothing of elevation before the gradient
RESIDUAL_SIGMA_S = 0.8      # smoothing of (projected - integrated) distance
MASK_FROZEN_S = 0.5         # freezes at least this long are masked (QC fails at 1.0)
MASK_GAP_S = 0.6            # gaps longer than this are masked
THROTTLE_SENTINEL = 100.5   # FastF1 writes 104 when there is no throttle reading
# Physically impossible changes of speed (m/s^2) are telemetry glitches: F1 cars reach
# roughly +20 accelerating and -60 braking.
MAX_ACCEL = 30.0
MAX_DECEL = -75.0
GLITCH_MERGE_M = 60         # a drop and the jump back are masked together
MASK_PAD_M = 10             # extra metres masked either side of bad stretches


# --- Clipping detection --------------------------------------------------------
class Detect(NamedTuple):
    throttle_min: float = 98.0      # %
    brake_max: float = 0.0
    speed_min: float = 180.0        # km/h
    smooth_m: float = 105.0         # local straight-line fit window for speed
    edge_trim_m: float = 25.0       # trimmed before lift/brake
    accel_max: float = -0.3         # m/s^2
    gravity: bool = True            # compare accel_max with gravity-corrected acceleration
    lat_g_max: float = 1.5          # rejects flat-out corners
    min_length_m: float = 100.0
    min_drop: float = 5.0           # km/h lost across a zone
    merge_gap_m: float = 40.0
    tow_gap_m: float = 100.0        # flag only


# A is the original rule; B drops the gravity correction.
RULE_A = Detect()
RULE_B = Detect(gravity=False)
DETECT = RULE_B
# Presets bracket the base settings; their results are the robustness band.
LOOSE = DETECT._replace(accel_max=-0.15, lat_g_max=2.0, min_length_m=75, min_drop=3)
STRICT = DETECT._replace(accel_max=-0.6, lat_g_max=1.0, min_length_m=150, min_drop=8)

# --- Trust gates ----------------------------------------------------
GATE_2025_MEAN = 0.005
GATE_2025_CIRCUIT = 0.02
GATE_CORNER_M = 20
# Straights that must be found in 2026: circuit, s0, s1, metres the median team must show.
KNOWN_STRAIGHTS = {"Kemmel": ("spa", 1400, 2300, 250), "Blanchimont": ("spa", 5600, 6300, 100),
                   "Baku straight": ("baku", 4600, 5950, 200)}
NEGATIVE_CONTROLS = ("monaco", "hungaroring", "singapore")

# --- Site export -----------------------------------------------------------------
SITE_DATA = ROOT / "site" / "data"
SITE_STEP = 10              # m; finer than the true sampling (~22 m at 320 km/h)

# id -> (name, 2025 team name, 2026 team name, 2025 power unit, 2026 power unit)
# Alpine moved from Renault to Mercedes power; Kick Sauber became Audi.
TEAMS = {
    "mercedes": ("Mercedes", "Mercedes", "Mercedes", "Mercedes", "Mercedes"),
    "mclaren": ("McLaren", "McLaren", "McLaren", "Mercedes", "Mercedes"),
    "williams": ("Williams", "Williams", "Williams", "Mercedes", "Mercedes"),
    "alpine": ("Alpine", "Alpine", "Alpine", "Renault", "Mercedes"),
    "ferrari": ("Ferrari", "Ferrari", "Ferrari", "Ferrari", "Ferrari"),
    "haas": ("Haas", "Haas F1 Team", "Haas F1 Team", "Ferrari", "Ferrari"),
    "cadillac": ("Cadillac", None, "Cadillac", None, "Ferrari"),
    "redbull": ("Red Bull", "Red Bull Racing", "Red Bull Racing", "Honda RBPT", "Red Bull Ford"),
    "racingbulls": ("Racing Bulls", "Racing Bulls", "Racing Bulls", "Honda RBPT", "Red Bull Ford"),
    "astonmartin": ("Aston Martin", "Aston Martin", "Aston Martin", "Mercedes", "Honda"),
    "audi": ("Audi / Kick Sauber", "Kick Sauber", "Audi", "Ferrari", "Audi"),
}
SECTION_MIN_M = 350         # full-throttle stretches this long become named sections
# Extra words for well-known places, keyed by circuit and corner-based name.
SECTION_NOTES = {("spa", "T1 to T5"): "Kemmel straight", ("spa", "T14 to T18"): "Blanchimont"}

# Short circuit labels for the season view.
SHORT = {"catalunya": "Barcelona", "spa": "Spa", "mexico": "Mexico City", "vegas": "Las Vegas"}

# Only what F1.com (20 Apr 2026) and PlanetF1 (1 May 2026) agree on. They disagree about
# the qualifying recharge limit, so that is not stated.
RULE_CHANGES = ({"before": "miami", "label": "Super-clip recovery limit raised, 250 to 350 kW",
                 "source": "https://www.fia.com/news/refinements-2026-fia-formula-1-regulations-"
                           "agreed-all-stakeholders"},)
BOOTSTRAP = 4000

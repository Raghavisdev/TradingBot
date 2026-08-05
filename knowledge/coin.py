import uuid
from datetime import datetime


class Coin:

    def __init__(self):

        # ==================================================
        # RESEARCH
        # ==================================================

        self.signal_id = str(uuid.uuid4())

        self.signal_time = datetime.now().isoformat()

        self.source = "GemTools"

        self.raw_message = ""

        self.bot_version = "1.0"

        # ==================================================
        # VALIDATION
        # ==================================================

        self.valid = True

        self.reject_reason = ""

        self.warnings = []

        self.strengths = []

        self.weaknesses = []

        # ==================================================
        # PIPELINE OUTCOME METADATA
        # ==================================================

        self.bought = False

        self.buy_blocked_by = ""

        self.last_api_success = True

        self.tracking_end_reason = "NORMAL_24H"

        # ==================================================
        # SIGNAL INFORMATION
        # ==================================================

        self.symbol = None

        self.name = None

        self.contract = None

        self.chain = None

        self.gt_score = 0

        self.gt_stars = ""

        self.signal_market_cap = None

        self.signal_price = None

        self.age = ""

        self.gemtools_breakdown = {}

        # ==================================================
        # HOLDERS
        # ==================================================

        self.holders = 0

        self.top10 = 0

        self.bundled = 0

        self.first50 = 0

        self.jeeters = 0

        self.fresh = None

        self.snipers = 0

        self.insiders = 0

        self.dev = 0

        self.safe = 0

        self.poor = 0

        self.community = 0

        self.whales = 0

        self.win_rate = 0

        # ==================================================
        # LIVE MARKET
        # ==================================================

        self.market_cap = None

        self.live_market_cap = None

        self.price = None

        self.fdv = None

        self.liquidity = None

        self.volume_5m = 0

        self.volume_1h = 0

        self.volume_24h = 0

        self.buys_5m = 0

        self.sells_5m = 0

        self.dex = None

        self.dex_url = None

        self.pair_created = None

        # ==================================================
        # SOCIAL
        # ==================================================

        self.twitter = None

        self.telegram = None

        self.website = None

        # ==================================================
        # AI SCORES
        # ==================================================

        self.fundamental_score = 0

        self.wallet_score = 0

        self.social_score = 0

        self.narrative_score = 0

        self.gemtools_score = 0

        self.final_score = 0

        self.entry_confidence = 0

        self.exit_confidence = 0

        self.position_confidence = 0

        # ==================================================
        # MODULE FLAGS
        # ==================================================

        self.has_fundamental = False

        self.has_wallet = False

        self.has_social = False

        self.has_narrative = False

        self.has_gemtools = False

        # ==================================================
        # ANALYSIS
        # ==================================================

        self.fundamental_breakdown = {}

        self.decision = ""

        self.decision_reasons = []

        # ==================================================
        # TRACKING
        # ==================================================

        self.tracking = False

        self.snapshot_count = 0

        self.tracking_started = None

        self.tracking_finished = None

        self.last_snapshot_time = None

        self.market_health = 0

        # ==================================================
        # OUTCOME
        # ==================================================

        self.peak_market_cap = None

        self.lowest_market_cap = None

        self.peak_price = None

        self.lowest_price = None

        self.max_return = 0

        self.min_return = 0

        self.time_to_peak = None

        self.rugged = False

        self.returned_2x = False

        self.returned_5x = False

        self.returned_10x = False

        # ==================================================
        # REPLAY / HISTORY
        # ==================================================

        self.highest_market_health = 0

        self.lowest_market_health = 100

        self.best_exit_action = None

        self.final_exit_action = None

        self.market_health_history = []

        self.price_history = []

        self.market_cap_history = []

        # ==================================================
        # PAPER TRADE LINK
        # ==================================================

        self.position = None

    def __str__(self):

        return f"""
==============================
Coin Profile
==============================

Signal ID       : {self.signal_id}

Source          : {self.source}

Symbol          : {self.symbol}

Name            : {self.name}

Contract        : {self.contract}

--------------------------------

Signal MC       : {self.signal_market_cap}

Live MC         : {self.live_market_cap}

Peak MC         : {self.peak_market_cap}

--------------------------------

Price           : {self.price}

Peak Price      : {self.peak_price}

Liquidity       : {self.liquidity}

--------------------------------

Volume 5m       : {self.volume_5m}

Buys            : {self.buys_5m}

Sells           : {self.sells_5m}

--------------------------------

GT Score        : {self.gt_score}

Fundamental     : {self.fundamental_score}

GemTools        : {self.gemtools_score}

Wallet          : {self.wallet_score}

Narrative       : {self.narrative_score}

Social          : {self.social_score}

--------------------------------

Final Score     : {self.final_score}

Decision        : {self.decision}

--------------------------------

Snapshots       : {self.snapshot_count}

Tracking        : {self.tracking}

Max Return      : {self.max_return:.2f}%

Rugged          : {self.rugged}

==============================
"""
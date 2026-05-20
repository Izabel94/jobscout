import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from jobscout.models import Listing, Source


@dataclass
class CadenceRule:
    jitter_pct: float = 30.0
    max_results_per_run: int | None = None
    use_residential_proxy: bool = False
    ua: str = ""


class SourceAdapter(ABC):
    source: Source
    policy: CadenceRule

    @abstractmethod
    def discover(self) -> list[Listing]: ...

    def sleep_jitter(self, base_seconds: float = 1.0) -> None:
        delta = base_seconds * (self.policy.jitter_pct / 100.0)
        time.sleep(max(0.1, base_seconds + random.uniform(-delta, delta)))


CONTACT_EMAIL = os.environ.get("SCRAPER_CONTACT_EMAIL", "")
BRAND_UA = "jobscout/0.1 (+personal application funnel)"
CONTACT_UA = f"jobscout/0.1 (+personal application funnel; contact: {CONTACT_EMAIL})"

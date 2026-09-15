from dataclasses import dataclass
from datetime import time

@dataclass(frozen=True)
class DailySchedule:
    collector_start: time=time(5,20)
    cutoff: time=time(5,45)
    synthesis_start: time=time(5,50)
    publish_target: time=time(6,0)
    def validate(self):
        assert self.collector_start < self.cutoff < self.synthesis_start <= self.publish_target
        return True

SCHEDULE=DailySchedule()

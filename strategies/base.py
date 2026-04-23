from abc import ABC, abstractmethod
import pandas as pd

class TradingStrategy(ABC):
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def score(self, df: pd.DataFrame) -> int:
        pass

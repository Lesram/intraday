# BRANCH 2.8: Risk Manager
class RiskMathUtils:
    @staticmethod
    def kelly_fraction(mean_return, variance, kelly_floor=0.0, kelly_ceiling=0.2):
        if variance < 1e-12 or mean_return <= 0:
            return kelly_floor
        kelly = mean_return / variance
        return max(kelly_floor, min(kelly, kelly_ceiling))

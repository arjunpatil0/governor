"""Online model of the background token time versus SM clock. Prior = the committed llama.cpp decode table of L (data/w2_L_results.md via sim.params); the correction is
multiplicative in log space and quadratic in u = ln(clock / 1800), fitted by recursive least squares with forgetting and a ridge-style prior (P0). With a few visited clock levels it
extrapolates the curve of a DIFFERENT workload (e.g. a flatter, lower-knee roofline), which is what the unseen-workload scene S5 and the real held-out workload need."""
import numpy as np


class TokenTimeModel:
    def __init__(self, P, forget=0.98, prior_var=1.0):
        self.P, self.lam = P, forget
        self.theta = np.zeros(3)
        self.Pm = np.eye(3) * prior_var

    @staticmethod
    def _phi(f):
        u = np.log(f / 1800.0)
        return np.array([1.0, u, u * u])

    def prior_ms(self, f):
        return 1000.0 / self.P.tok_s(f)

    def predict(self, f):
        return float(self.prior_ms(f) * np.exp(self._phi(f) @ self.theta))

    def update(self, f, tok_ms):
        if not tok_ms > 0:
            return
        phi, y = self._phi(f), float(np.log(tok_ms / self.prior_ms(f)))
        k = self.Pm @ phi / (self.lam + phi @ self.Pm @ phi)
        self.theta = self.theta + k * (y - phi @ self.theta)
        self.Pm = (self.Pm - np.outer(k, phi @ self.Pm)) / self.lam

"""Per-row predictive distributions for the eight CBB prop families."""
from players import distributions as D
from players.features import STATS, COMBOS, mean_for
from players.fit import rho_of

FAMILIES = ("POINTS", "REBOUNDS", "ASSISTS", "THREES", "PRA", "PR", "PA", "RA")


def predictive(row, params, *, combo="moment", copula_draws=20000, seed=519):
    """Return {family: {"mean","alpha","pmf"}} under fitted params.

    combo: "moment" (correlated NB moment match, default, preregistered),
    "independent" (rho=0 ablation) or "copula" (Gaussian copula MC).
    """
    out = {}
    mus = {s: mean_for(row, s, params) for s in STATS}
    al = {s: params["stats"][s]["alpha"] for s in STATS}
    for s in STATS:
        out[s] = {"mean": mus[s], "alpha": al[s], "pmf": D.nb_pmf(mus[s], al[s])}
    for fam, parts in COMBOS.items():
        m = [mus[p] for p in parts]
        a = [al[p] for p in parts]
        if combo == "copula":
            R = [[1.0 if i == j else rho_of(params, parts[i], parts[j]) for j in range(len(parts))]
                 for i in range(len(parts))]
            pmf = D.combo_pmf_copula(m, a, R, draws=copula_draws, seed=seed)
        else:
            rho = {} if combo == "independent" else {
                (i, j): rho_of(params, parts[i], parts[j])
                for i in range(len(parts)) for j in range(i + 1, len(parts))}
            pmf = D.combo_pmf_moment(m, a, rho)
        out[fam] = {"mean": sum(m), "pmf": pmf}
    return out

# Replay canonical bars fixture

This fixture is used by the determinism test (Track X v6) to pin replay
output. It is regenerated deterministically by
`make_features_dict(["AAPL","MSFT","SPY"], n=80, base=400.0, seed=42, trend="up")`
in `backend.organism.replay_simulator`. We intentionally do NOT commit a
`.parquet` / `.csv` snapshot because the synthetic generator is itself the
source of truth and is committed to the codebase. Any future replay test
that needs a frozen bar set should call `make_features_dict(seed=42, ...)`.

If we later want a "golden" snapshot for byte-equal comparison, save the
output of `make_features_dict` once with `pd.to_parquet` and check it in
here. Until then the synthetic generator + fixed seed is the fixture.

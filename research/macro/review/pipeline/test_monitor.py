"""Meaningful boundary tests for stale, missing and misaligned economic data."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import monitor as m

class MonitorTests(unittest.TestCase):
    def test_calendar_gap_does_not_become_13_month_growth(self):
        dates=pd.date_range("2024-01-01",periods=33,freq="MS")
        s=pd.Series(np.arange(100.,133.),index=dates).drop(pd.Timestamp("2025-10-01"))
        actual=m.calendar_yoy(s)
        self.assertAlmostEqual(actual.loc["2026-08"],100*(131/119-1))
        self.assertTrue(pd.isna(actual.loc["2025-10"]))

    def test_missing_year_ago_cannot_reuse_neighbour(self):
        s=pd.Series(range(100,125),index=pd.date_range("2024-01-01",periods=25,freq="MS")).drop(pd.Timestamp("2024-01-01"))
        self.assertTrue(pd.isna(m.calendar_yoy(s).loc["2025-01"]))

    def test_duplicate_and_unsorted_dates_rejected(self):
        for text in ["date,x\n2020-01-01,1\n2020-01-01,2", "date,x\n2020-02-01,2\n2020-01-01,1"]:
            with self.assertRaises(ValueError):m.parse_csv(text,"X")

    def test_html_response_is_not_valid_csv(self):
        with self.assertRaises(ValueError):m.parse_csv("<html>Blocked</html>","X")

    def test_staleness_uses_observation_period_end(self):
        s=pd.Series([100.,102.],index=pd.to_datetime(["2026-07-01","2026-08-01"]))
        self.assertEqual(m.source_health(s,"CPIAUCSL",pd.Timestamp("2026-09-18"))["age_days"],18)
        with self.assertRaises(ValueError):m.source_health(s,"CPIAUCSL",pd.Timestamp("2026-10-26"))

    def test_current_monthly_release_does_not_expire_before_next_is_due(self):
        s=pd.Series([100.,102.],index=pd.to_datetime(["2026-07-01","2026-08-01"]))
        health=m.source_health(s,"CPIAUCSL",pd.Timestamp("2026-09-30"))
        self.assertEqual(health["next_observation_due_by"],"2026-10-25")
        self.assertEqual(health["max_age_days"],55)
        self.assertIsNone(health["published_at"])

    def test_quarterly_release_deadline_accounts_for_next_quarter(self):
        s=pd.Series([100.,102.],index=pd.to_datetime(["2026-01-01","2026-04-01"]))
        health=m.source_health(s,"CPATAX",pd.Timestamp("2026-10-15"))
        self.assertEqual(health["next_observation_due_by"],"2027-01-08")
        with self.assertRaises(ValueError):m.source_health(s,"CPATAX",pd.Timestamp("2027-01-09"))

    def test_mislabeled_source_is_rejected(self):
        with self.assertRaises(ValueError):m.parse_csv("observation_date,UNRATE\n2026-07-01,4\n2026-08-01,4.1","CPIAUCSL")

    def test_malformed_latest_value_does_not_silently_reuse_previous(self):
        with self.assertRaises(ValueError):m.parse_csv("observation_date,BAA10Y\n2026-09-16,1.5\n2026-09-17,1.4\n2026-09-18,blocked","BAA10Y")

    def test_incomplete_period_not_accepted(self):
        s=pd.Series([100.,102.],index=pd.to_datetime(["2026-07-01","2026-08-01"]))
        with self.assertRaises(ValueError):m.source_health(s,"CPIAUCSL",pd.Timestamp("2026-08-15"))

    def test_output_cannot_escape_review(self):
        with self.assertRaises(ValueError):m.safe_path(m.REVIEW.parent/"oops.json")

    def test_missing_week_invalidates_claims_window(self):
        idx=pd.date_range("2024-01-06",periods=80,freq="W-SAT")
        s=pd.Series(np.arange(100.,180.),index=idx)
        self.assertTrue(pd.notna(m.weekly_claims(s).iloc[-1]))
        self.assertTrue(pd.isna(m.weekly_claims(s.drop(idx[-2])).iloc[-1]))

    def test_partial_month_excluded_from_credit_change(self):
        s=pd.Series([1.,1.2,1.4,1.6,2.5],index=pd.to_datetime(["2026-05-29","2026-06-30","2026-07-31","2026-08-31","2026-09-17"]))
        actual=m.derive({"BAA10Y":s},"2026-09-18")["credit_change"]
        self.assertEqual(str(actual.index[-1]),"2026-08")
        self.assertAlmostEqual(actual.iloc[-1],.6)

    def test_future_native_observation_excluded(self):
        s=pd.Series([1.,2.,3.],index=pd.to_datetime(["2026-09-17","2026-09-18","2026-09-19"]))
        self.assertEqual(m.derive({"BAA10Y":s},"2026-09-18")["credit_level"].iloc[-1],2.)

    def test_nonfinite_derived_value_cannot_look_below_threshold(self):
        item=next(r for r in m.read_spec() if r["id"]=="sahm")
        s=pd.Series([.1,np.inf],index=pd.to_datetime(["2026-07-01","2026-08-01"]))
        row=m.evaluate([item],{"sahm":s},{},{})[0]
        self.assertEqual(row["status"],"unavailable")
        self.assertIsNone(row["value"])
        json.dumps(row,allow_nan=False)

    def test_compound_inflation_needs_both_conditions(self):
        item=next(r for r in m.read_spec() if r["id"]=="inflation_acceleration")
        idx=pd.period_range("2026-07",periods=2,freq="M")
        data={"inflation_acceleration":pd.Series([2.1,2.2],index=idx),"inflation":pd.Series([3.1,3.2],index=idx)}
        self.assertEqual(m.evaluate([item],data,{},{} )[0]["status"],"below")
        data["inflation"].iloc[-1]=4
        self.assertEqual(m.evaluate([item],data,{},{} )[0]["status"],"crossed")
        data["inflation"].iloc[-1]=np.inf
        self.assertEqual(m.evaluate([item],data,{},{} )[0]["status"],"unavailable")

    def test_nfci_zero_does_not_cross_strict_threshold(self):
        item=next(r for r in m.read_spec() if r["id"]=="nfci")
        series=pd.Series([-0.1,0.],index=pd.to_datetime(["2026-09-04","2026-09-11"]))
        self.assertEqual(m.evaluate([item],{"nfci":series},{},{})[0]["status"],"below")

    def test_failed_refresh_preserves_last_good_and_writes_attempt(self):
        with tempfile.TemporaryDirectory(dir=m.REVIEW/"artifacts") as path:
            out=Path(path); original={"mode":"snapshot","spec_version":m.VERSION,"as_of":"2026-09-18","indicators":[]}
            (out/"latest.json").write_text(json.dumps(original))
            with patch.object(m,"load_sources",return_value=({}, {}, {"ICSA":"offline"}, {}, "2026-09-19T00:00:00Z")), contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                status=m.main(["--mode","snapshot","--as-of","2026-09-18","--output",path])
            self.assertEqual(status,2)
            self.assertEqual(json.loads((out/"latest.json").read_text()),original)
            self.assertEqual(json.loads((out/"attempt.json").read_text())["status"],"failed")

    def test_supplied_capture_inflation_recomputed(self):
        series,_,errors,_,_=m.load_sources("snapshot",pd.Timestamp("2026-09-18"))
        self.assertFalse(errors)
        data=m.derive(series,"2026-09-18")
        self.assertAlmostEqual(data["inflation"].iloc[-1],3.35301632,places=4)
        self.assertEqual(len(m.evaluate(m.read_spec(),data,{},{})),12)

    def test_source_loader_exception_still_records_failed_attempt(self):
        with tempfile.TemporaryDirectory(dir=m.REVIEW/"artifacts") as path:
            with patch.object(m,"load_sources",side_effect=ValueError("corrupt supplied bundle")), contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                status=m.main(["--mode","snapshot","--as-of","2026-09-18","--output",path])
            self.assertEqual(status,2)
            payload=json.loads((Path(path)/"attempt.json").read_text())
            self.assertEqual(payload["status"],"failed")
            self.assertIn("source_load",payload["errors"])

    def test_all_eight_historical_formulas_match_sealed_study(self):
        series,_,errors,_,_=m.load_sources("snapshot",pd.Timestamp("2026-09-18"))
        self.assertFalse(errors)
        derived=m.derive(series,"2026-09-18")
        reference=pd.read_csv(m.REVIEW/"phase_b_events/monthly_indicator_values.csv",index_col=0)
        reference.index=pd.PeriodIndex(reference.index,freq="M")
        mapping={"claims_rise":("claims_rise_20pct",0),"sahm":("sahm_050",1),"credit_level":("baa_level_300",0),"credit_change":("baa_widening_100",0),"nfci":("nfci_positive",1),"curve":("curve_inverted",1),"inflation":("inflation_400",1),"inflation_acceleration":("cpi_yoy_change_12m",1)}
        for key,(column,lag) in mapping.items():
            s=derived[key];s=s if isinstance(s.index,pd.PeriodIndex) else m.monthly(s)
            pair=pd.concat([s.shift(lag).rename("pipeline"),reference[column].rename("study")],axis=1).dropna()
            self.assertGreater(len(pair),400,key)
            self.assertLess(float((pair.pipeline-pair.study).abs().max()),1e-10,key)

if __name__=="__main__":unittest.main(verbosity=2)

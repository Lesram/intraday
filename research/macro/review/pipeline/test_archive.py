import unittest
import pandas as pd
from score_archive import score

def reading(date,status,mode="live",version="1"):
    return {"mode":mode,"status":"validated","spec_version":version,"as_of":date,"generated_at":date+"T12:00:00Z","indicators":[{"id":"claims_rise","tier":1,"status":status}]}

class ArchiveTests(unittest.TestCase):
    def test_initial_high_reading_cannot_prove_crossing(self):
        self.assertEqual(score([reading("2026-01-01","crossed")],None),[])

    def test_snapshot_does_not_count_as_prospective(self):
        self.assertEqual(score([reading("2026-01-01","below","snapshot"),reading("2026-02-01","crossed","snapshot")],None),[])

    def test_incomplete_horizon_remains_pending(self):
        reads=[reading("2026-01-01","below"),reading("2026-02-01","crossed")]
        labels=pd.Series([1]*12,index=pd.period_range("2026-02",periods=12,freq="M"))
        self.assertEqual(score(reads,labels)[0]["status"],"pending")

    def test_complete_no_event_is_false_alarm(self):
        reads=[reading("2026-01-01","below"),reading("2026-02-01","crossed")]
        labels=pd.Series([0]*13,index=pd.period_range("2026-02",periods=13,freq="M"))
        self.assertEqual(score(reads,labels,asof="2027-03-01")[0]["status"],"false_alarm")

    def test_no_repeated_alarms_while_threshold_stays_high(self):
        reads=[reading("2026-01-01","below"),reading("2026-02-01","crossed"),reading("2026-03-01","crossed")]
        self.assertEqual(len(score(reads,None)),1)

    def test_open_signal_month_is_not_a_monthly_alarm(self):
        reads=[reading("2026-01-01","below"),reading("2026-02-01","crossed")]
        self.assertEqual(score(reads,None,asof="2026-02-15"),[])

    def test_intramonth_reversal_does_not_inherit_monthly_hit_rate(self):
        reads=[reading("2026-01-20","below"),reading("2026-02-05","crossed"),reading("2026-02-25","below")]
        self.assertEqual(score(reads,None,asof="2026-03-01"),[])

    def test_missing_month_resets_crossing_baseline(self):
        reads=[reading("2026-01-01","below"),reading("2026-03-01","crossed")]
        self.assertEqual(score(reads,None,asof="2026-04-01"),[])

    def test_unavailable_month_resets_crossing_baseline(self):
        reads=[reading("2026-01-01","below"),reading("2026-02-01","unavailable"),reading("2026-03-01","crossed")]
        self.assertEqual(score(reads,None,asof="2026-04-01"),[])

    def test_failed_final_monthly_attempt_resets_crossing_baseline(self):
        failure=reading("2026-02-28","below");failure["status"]="failed"
        reads=[reading("2026-01-01","below"),reading("2026-02-01","below"),failure,reading("2026-03-01","crossed")]
        self.assertEqual(score(reads,None,asof="2026-04-01"),[])

    def test_horizon_month_must_finish_even_if_labels_exist(self):
        reads=[reading("2026-01-01","below"),reading("2026-02-01","crossed")]
        labels=pd.Series([0]*13,index=pd.period_range("2026-02",periods=13,freq="M"))
        self.assertEqual(score(reads,labels,asof="2027-02-15")[0]["status"],"pending")

    def test_actual_acquisition_month_prevents_backdated_alarm(self):
        old=reading("2026-01-01","below");old["generated_at"]="2026-01-31T23:00:00Z"
        new=reading("2026-01-31","crossed");new["generated_at"]="2026-02-01T01:00:00Z"
        row=score([old,new],None,asof="2026-03-01")[0]
        self.assertEqual(row["signal_month"],"2026-02")
        self.assertEqual(row["alarm_asof"],"2026-02-01")

    def test_invalid_outcome_label_rejected(self):
        with self.assertRaises(ValueError):score([],pd.Series([.5],index=pd.period_range("2026-01",periods=1,freq="M")))

    def test_no_acquisition_timestamp_cannot_create_prospective_history(self):
        one=reading("2026-01-01","below");two=reading("2026-02-01","crossed")
        del one["generated_at"];del two["generated_at"]
        self.assertEqual(score([one,two],None,asof="2026-03-01"),[])

if __name__=="__main__":unittest.main(verbosity=2)

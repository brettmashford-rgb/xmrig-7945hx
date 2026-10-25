"""Saved status schema inspection must exclude credentials and other methods. ISC."""
import json
import unittest
from tools.inspect_report_info import describe,report_records


class ReportInfoTests(unittest.TestCase):
    def test_numeric_schema_retained_strings_and_nested_credentials_redacted(self):
        value={'hashrate':79000000000000,'rate_text':'7.9e13','worker':'private-worker',
               'wallet':'private-wallet','nested':json.dumps({'token':'private-token','speed':123})}
        result=describe(value);raw=json.dumps(result)
        for secret in('private-worker','private-wallet','private-token'):self.assertNotIn(secret,raw)
        self.assertEqual(result['hashrate'],79000000000000)
        self.assertEqual(result['rate_text'],{'type':'numeric-string','value':'7.9e13'})
        self.assertEqual(result['nested']['value']['speed'],123)

    def test_only_outbound_report_info_is_selected(self):
        records=[{'direction':'out','json':{'method':'login','params':['secret']}},
                 {'direction':'out','json':{'method':'submit','params':['secret']}},
                 {'direction':'in','json':{'method':'report_info'}},
                 {'direction':'out','json':{'method':'report_info','params':[12]}}]
        document={'schema':'pearlhash-decoded-capture-1','records':records}
        self.assertEqual(report_records(document),[records[-1]])
        self.assertEqual(report_records({'schema':'wrong','records':records}),[])


if __name__=='__main__':unittest.main()

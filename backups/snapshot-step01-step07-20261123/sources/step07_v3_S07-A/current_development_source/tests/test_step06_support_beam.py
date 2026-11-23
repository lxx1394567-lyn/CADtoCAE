import unittest
from types import SimpleNamespace as NS
from cadtocae.support_beam_connector import script_source


def runtime():
    ns={'__name__':'test'}
    exec(script_source({},'unused.json'),ns)
    return ns


class SupportBeamTests(unittest.TestCase):
    def test_names_do_not_overlap_except_section(self):
        ns=runtime()
        for group in ('P01','P02','P03','P04'):
            old=ns['b1_names'](group);new=ns['sb_names'](group)
            self.assertEqual(set(old.values())&set(new.values()),{'STEP06_CONNECTOR_SECTION_PURLIN_BOLT'})
            self.assertEqual(new['rp_support'],'STEP06_RP_'+group+'_SUPPORT_BEAM')
            self.assertEqual(new['rp_purlin'],'STEP06_RP_'+group+'_BEAM')

    def test_beam_duplicate_and_overlap_rejected(self):
        ns=runtime()
        for indices in ([[1,2],[2,1]],[[1,2],[2,3]],[[]]):
            with self.assertRaisesRegex(ValueError,'BEAM_HOLE_REGION_DUPLICATE'):
                ns['sb_unique']([[NS(index=i) for i in group] for group in indices])

    def test_four_regions_have_distinct_keys(self):
        ns=runtime();regions=[[NS(index=i*4+j) for j in range(4)] for i in range(4)]
        self.assertEqual(len(ns['sb_unique'](regions)),4)

    def test_no_existing_executor_global_mutation(self):
        ns=runtime();old=ns['execute_connector_b1'].__globals__['b1_names']
        # Failed invocation still must not rebind the original namespace.
        with self.assertRaises(ImportError):ns['sb_execute_one']({},None,None)
        self.assertIs(ns['execute_connector_b1'].__globals__['b1_names'],old)

    def test_python2_grammar(self):
        from lib2to3.refactor import RefactoringTool
        RefactoringTool([]).refactor_string(script_source({},'report.json'),'support_beam.py')


if __name__=='__main__':unittest.main()

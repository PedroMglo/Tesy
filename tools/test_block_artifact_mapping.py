import unittest
from run_bounded import mapped_libraries_match

class ArtifactMap(unittest.TestCase):
    def test_inference_still_requires_nonempty_exact_library_identity(self):
        self.assertFalse(mapped_libraries_match({},{}))
        self.assertFalse(mapped_libraries_match({'libllama':'pin'},None))
        self.assertTrue(mapped_libraries_match({'libllama':'pin'},{'libllama':'pin'}))
        self.assertFalse(mapped_libraries_match({'libllama':'pin'},{'libllama':'wrong'}))
    def test_explicit_artifact_requires_observed_empty_not_missing_map(self):
        c={'schema':'bounded-artifact-only-v1','kind':'PINNED_HEAD_CONVERSION_OR_VALUE_AUDIT','full_model_forward':False,'expected_backend_libraries':{}}
        self.assertTrue(mapped_libraries_match({}, {}, c))
        self.assertFalse(mapped_libraries_match({},None,c))
        self.assertFalse(mapped_libraries_match({}, {'libllama':'pin'},c))
        self.assertFalse(mapped_libraries_match({'libllama':'pin'},{'libllama':'pin'},c))
        for bad in ({},{**c,'full_model_forward':True},{**c,'expected_backend_libraries':{'libllama':'pin'}}):
            with self.assertRaises(ValueError):mapped_libraries_match({}, {}, bad)

    def test_bounded_lossless_characterization_requires_observed_empty_inference_map(self):
        c={'schema':'bounded-artifact-only-v1','kind':'BOUNDED_LOSSLESS_COMPONENT_CHARACTERIZATION','full_model_forward':False,'expected_backend_libraries':{}}
        self.assertTrue(mapped_libraries_match({}, {}, c))
        self.assertFalse(mapped_libraries_match({}, None, c))
        self.assertFalse(mapped_libraries_match({}, {'libllama':'pin'}, c))
        for bad in ({**c,'kind':'ARBITRARY_CODEC'},{**c,'full_model_forward':True},{**c,'extra':'unchecked'}):
            with self.assertRaises(ValueError):mapped_libraries_match({}, {}, bad)

    def test_bounded_auxiliary_fit_requires_observed_empty_inference_map(self):
        c={'schema':'bounded-artifact-only-v1','kind':'BOUNDED_AUXILIARY_CPU_FIT','full_model_forward':False,'expected_backend_libraries':{}}
        self.assertTrue(mapped_libraries_match({}, {}, c))
        self.assertFalse(mapped_libraries_match({}, None, c))
        self.assertFalse(mapped_libraries_match({}, {'libllama':'pin'}, c))
        for bad in ({**c,'kind':'ARBITRARY_PYTHON'},{**c,'full_model_forward':True},{**c,'extra':'unchecked'}):
            with self.assertRaises(ValueError):mapped_libraries_match({}, {}, bad)

if __name__=='__main__':unittest.main()

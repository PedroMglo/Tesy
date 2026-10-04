import tempfile
import unittest
from pathlib import Path
import gguf
from block_eagle3_convert import copy_tokenizer


class OriginalTokenizerMetadata(unittest.TestCase):
    def write_source(self, path):
        w = gguf.GGUFWriter(path, 'gpt-oss')
        w.add_tokenizer_model('gpt2')
        w.add_tokenizer_pre('gpt-4o')
        w.add_token_list(['a', '\x00', 'Ġ'])
        w.add_token_types([1, 3, 1])
        w.add_token_merges(['a b', 'Ġ a'])
        w.add_eos_token_id(1)
        w.add_chat_template('{{ messages }}')
        w.write_header_to_file()
        w.write_kv_data_to_file()
        w.write_tensors_to_file()
        w.close()

    def test_roundtrip_preserves_strings_ids_merges_types_and_template(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'source.gguf', Path(d) / 'head.gguf'
            self.write_source(source)
            r = gguf.GGUFReader(source)
            w = gguf.GGUFWriter(dest, 'eagle3')
            original = copy_tokenizer(r, w, expected_vocab=3)
            w.write_header_to_file()
            w.write_kv_data_to_file()
            w.write_tensors_to_file()
            w.close()
            other = gguf.GGUFReader(dest)
            self.assertEqual(copy_tokenizer(other, gguf.GGUFWriter(None, 'eagle3'),
                                            expected_vocab=3), original)
            for key, field in r.fields.items():
                if key.startswith('tokenizer.'):
                    self.assertEqual(other.fields[key].types, field.types)
                    self.assertEqual(other.fields[key].contents(), field.contents())

    def test_missing_fields_or_cardinality_fail_before_tensor_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'source.gguf'
            self.write_source(source)
            r = gguf.GGUFReader(source)
            with self.assertRaises(ValueError):
                copy_tokenizer(r, gguf.GGUFWriter(None, 'eagle3'))
            del r.fields['tokenizer.ggml.token_type']
            with self.assertRaises(ValueError):
                copy_tokenizer(r, gguf.GGUFWriter(None, 'eagle3'), expected_vocab=3)


if __name__ == '__main__':
    unittest.main()

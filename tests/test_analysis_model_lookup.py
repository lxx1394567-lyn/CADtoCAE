"""Repository contract tests; these do not substitute for Abaqus Python 2."""
import contextlib
import io
from types import SimpleNamespace
import unittest

from cadtocae.analysis_runtime import _resolve_existing_model, resolve_repository_item, _s5_repository_key


class Repository:
    def __init__(self, keys):
        self.names = keys
        self.model = object()

    def keys(self):
        return self.names[:]

    def __contains__(self, key):
        raise AssertionError("Repository membership must not be used")

    def __getitem__(self, key):
        if not any(key is actual for actual in self.names):
            raise AssertionError("Must index with the original Repository key")
        return self.model


class ModelLookupTests(unittest.TestCase):
    def test_all_repository_contracts(self):
        for label in ("Model", "Part", "Instance", "Set", "Surface", "Section", "Feature",
                      "Assembly Set", "Assembly Surface"):
            for expected, keys, error in (
                    ("Exact", ["Exact"], None),
                    (u"Exact", [b"Exact"], None),
                    ("P_SP_SC_ANG28_INCLINED_BEAM", [b"P_SP_SC_ANG28_INCLINED_BEAM"], None),
                    ("Missing", [], "not found"),
                    ("Exact", ["Exact_OTHER", "exact", "Exact "], "not found"),
                    ("Exact", ["Exact", b"Exact"], "Multiple normalized")):
                with self.subTest(label=label, expected=expected, keys=keys):
                    repo = Repository(keys)
                    with contextlib.redirect_stdout(io.StringIO()):
                        if error:
                            with self.assertRaisesRegex(ValueError, error):
                                resolve_repository_item(repo, expected, label)
                        else:
                            self.assertIs(_s5_repository_key(repo, expected, label), keys[0])
                            self.assertIs(resolve_repository_item(repo, expected, label), repo.model)

    def test_optional_absence_does_not_hide_ambiguity(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(_s5_repository_key(Repository([]), "Set", "Set", allow_missing=True))
            with self.assertRaisesRegex(ValueError, "Multiple normalized"):
                _s5_repository_key(Repository(["Set", b"Set"]), "Set", "Set", allow_missing=True)

    def resolve(self, expected, keys):
        repository = Repository(keys)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = _resolve_existing_model(SimpleNamespace(models=repository), expected)
        self.assertIs(result, repository.model)
        self.assertIn("expected model type:", output.getvalue())
        self.assertIn("expected == key:", output.getvalue())

    def test_str_keys(self):
        self.resolve("Model", ["Model"])

    def test_unicode_expected_byte_key(self):
        self.resolve(u"Model", [b"Model"])

    def test_ascii_project_exact(self):
        self.resolve("SP_SC_ANG28_1042110101170S-T0204",
                     [b"SP_SC_ANG28_1042110101170S-T0204"])

    def test_hidden_characters_rejected(self):
        for suffix in (" ", "\n", "\u200b", "\ufeff"):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "not found"):
                self.resolve("Model" + suffix, ["Model"])

    def test_similar_projects_rejected(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.resolve("SP_SC_ANG28", ["SP_DC_ANG28", "SP_SC_ANG28_OTHER"])

    def test_missing_diagnostics(self):
        with self.assertRaisesRegex(ValueError, "Expected repr:") as raised:
            self.resolve("Missing", ["Other"])
        self.assertIn("Available key repr:", str(raised.exception))
        self.assertIn("Other", str(raised.exception))

    def test_multiple_normalized_matches(self):
        with self.assertRaisesRegex(ValueError, "Multiple normalized Model matches"):
            self.resolve("Model", ["Model", b"Model"])

    def test_utf8_bytes_and_invalid_encoding(self):
        self.resolve("\u6a21\u578b", ["\u6a21\u578b".encode("utf-8")])
        with self.assertRaises(UnicodeDecodeError):
            self.resolve("Model", [b"\xff"])

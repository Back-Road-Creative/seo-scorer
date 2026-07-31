"""The store's optional dependency fails loudly, and only the store's.

``filelock`` is behind the ``store`` extra, so a bare install must still
import the scoring half of the package. If someone reaches for the store
without the extra, the error has to name the fix.
"""

import builtins
import importlib
import subprocess
import sys
import textwrap

import pytest

_BLOCK_FILELOCK = """
import sys


class BlockFilelock:
    def find_spec(self, name, path=None, target=None):
        if name == "filelock" or name.startswith("filelock."):
            raise ImportError("No module named 'filelock'")
        return None


sys.meta_path.insert(0, BlockFilelock())
"""


def _run_without_filelock(body: str) -> subprocess.CompletedProcess:
    """Run ``body`` in a subprocess where importing filelock fails."""
    return subprocess.run(
        [sys.executable, "-c", _BLOCK_FILELOCK + textwrap.dedent(body)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_scoring_half_works_with_filelock_unavailable():
    result = _run_without_filelock(
        """
        from seo_scorer import (
            PlatformValidator,
            SEOScorer,
            SEOMetadata,
            YouTubeAdapter,
        )

        assert "filelock" not in sys.modules
        score = SEOScorer().seo_structure_score("x" * 50, "x" * 400, ["x"] * 12)
        assert score == 1.0, score
        print("OK", score)
        """
    )

    assert result.returncode == 0, result.stderr
    assert "OK 1.0" in result.stdout


def test_importing_the_store_without_filelock_says_how_to_fix_it():
    result = _run_without_filelock(
        """
        try:
            import seo_scorer.store
        except ImportError as exc:
            print("MESSAGE:", exc)
        else:
            raise AssertionError("expected ImportError")
        """
    )

    assert result.returncode == 0, result.stderr
    assert "filelock" in result.stdout
    assert "seo-scorer[store]" in result.stdout


def test_the_import_error_is_raised_in_process_too(monkeypatch):
    """Same guard, exercised in-process so coverage tools see it."""
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "filelock" or name.startswith("filelock."):
            raise ImportError("No module named 'filelock'")
        return real_import(name, *args, **kwargs)

    # Load it first, so monkeypatch restores a working module afterwards.
    importlib.import_module("seo_scorer.store")
    monkeypatch.delitem(sys.modules, "seo_scorer.store")
    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(ImportError, match=r"seo-scorer\[store\]"):
        importlib.import_module("seo_scorer.store")


def test_the_store_still_imports_after_the_blocking_tests():
    """Guards against a blocking test leaving a broken module behind."""
    module = importlib.import_module("seo_scorer.store")

    assert module.SEOEventStore is not None

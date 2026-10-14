import sys
import threading
import trace
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def run_tests():
    suite = unittest.defaultTestLoader.discover(str(PROJECT / 'tests'), top_level_dir=str(PROJECT))
    return unittest.TextTestRunner(verbosity=1).run(suite)


def main():
    collector = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    previous_trace = getattr(threading, 'gettrace', lambda: None)()
    threading.settrace(collector.globaltrace)
    try:
        result = collector.runfunc(run_tests)
    finally:
        threading.settrace(previous_trace)
    counts = {
        (str(Path(filename).resolve()), line): hits
        for (filename, line), hits in collector.results().counts.items()
        if PROJECT / 'hibernate_sql' in Path(filename).resolve().parents
        or Path(filename).resolve() in {PROJECT / 'app.py', PROJECT / 'converter.py'}
    }
    report = trace.CoverageResults(counts=counts)
    report.write_results(show_missing=True, summary=True, coverdir=str(PROJECT / 'coverage'))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())

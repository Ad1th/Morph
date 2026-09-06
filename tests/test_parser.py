from morph.telemetry.parser import (
    extract_error_message,
    extract_error_type,
    extract_stack_trace,
)

PY_TRACEBACK = '''Traceback (most recent call last):
  File "/tmp/x.py", line 3, in <module>
    raise ValueError("boom")
ValueError: boom
'''

CHAINED = '''Traceback (most recent call last):
  File "a.py", line 1, in <module>
    do()
KeyError: 'k'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "a.py", line 3, in <module>
    raise RuntimeError("wrapped")
RuntimeError: wrapped
'''


def test_python_traceback_type_and_message():
    assert extract_error_type(PY_TRACEBACK) == "ValueError"
    assert extract_error_message(PY_TRACEBACK) == "boom"


def test_stack_trace_captured():
    trace = extract_stack_trace(PY_TRACEBACK)
    assert trace is not None
    assert trace.startswith("Traceback (most recent call last):")
    assert trace.rstrip().endswith("ValueError: boom")


def test_chained_traceback_resolves_to_last_exception():
    assert extract_error_type(CHAINED) == "RuntimeError"
    assert extract_error_message(CHAINED) == "wrapped"


def test_bare_type_colon_message():
    assert extract_error_type("TimeoutExpired: call timed out") == "TimeoutExpired"
    assert extract_error_message("TimeoutExpired: call timed out") == "call timed out"


def test_custom_exception_name():
    s = "worker crashed\nLockLostException: lease expired after 30s\n"
    assert extract_error_type(s) == "LockLostException"
    assert extract_error_message(s) == "lease expired after 30s"


def test_errno_style_message():
    s = "ConnectionRefusedError: [Errno 111] Connection refused"
    assert extract_error_type(s) == "ConnectionRefusedError"
    assert extract_error_message(s) == "[Errno 111] Connection refused"


def test_bare_type_without_message():
    assert extract_error_type("AssertionError") == "AssertionError"
    assert extract_error_message("AssertionError") is None


def test_dotted_type_stripped_to_class():
    s = "mypkg.errors.ValidationError: bad input"
    assert extract_error_type(s) == "ValidationError"
    assert extract_error_message(s) == "bad input"


def test_falls_back_to_stdout():
    assert extract_error_type("", "RuntimeError: from stdout") == "RuntimeError"


def test_no_error_returns_none():
    assert extract_error_type("", "") is None
    assert extract_error_type("just a normal log line\nanother line\n") is None
    assert extract_error_message("nothing to see here") is None
    assert extract_stack_trace("plain text, no traceback") is None


def test_keyboard_interrupt_recognised():
    assert extract_error_type("KeyboardInterrupt") == "KeyboardInterrupt"


def test_java_stack_trace():
    s = (
        'Exception in thread "main" java.lang.IllegalStateException: nope\n'
        "\tat com.example.App.run(App.java:42)\n"
        "\tat com.example.App.main(App.java:10)\n"
    )
    assert extract_error_type(s) == "IllegalStateException"
    assert extract_error_message(s) == "nope"
    trace = extract_stack_trace(s)
    assert trace is not None and "at com.example.App.run(App.java:42)" in trace

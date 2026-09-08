from pathlib import Path

from codeatlas.parsers.javascript import parse_javascript
from codeatlas.parsers.python import parse_python

FIXTURES = Path(__file__).parent / "fixtures" / "sample"


def test_python_locations_parameters_and_nested_scope():
    result = parse_python((FIXTURES / "auth.py").read_text())
    symbols = {symbol.name: symbol for symbol in result.symbols}
    assert set(symbols) == {"AuthService", "login", "normalize", "logout"}
    assert symbols["login"].kind == "method"
    assert symbols["login"].parameters == ["self", "email", "remember"]
    assert symbols["login"].start_line == 5
    assert symbols["login"].end_line == 8
    assert symbols["login"].parent_id == symbols["AuthService"].id
    assert symbols["normalize"].kind == "function"
    assert symbols["normalize"].parent_id == symbols["login"].id
    assert symbols["logout"].parameters == ["user_id", "**options"]
    assert result.imports == ["typing"]


def test_typescript_classes_arrows_interfaces_and_types():
    result = parse_javascript((FIXTURES / "client.ts").read_text(), typescript=True)
    symbols = {symbol.name: symbol for symbol in result.symbols}
    assert set(symbols) == {"User", "Client", "login", "normalize", "UserId"}
    assert symbols["login"].parent_id == symbols["Client"].id
    assert symbols["login"].parameters == ["email: string", "remember = false"]
    assert symbols["normalize"].parameters == ["value: string"]
    assert symbols["login"].start_line == 7
    assert symbols["User"].kind == "interface"
    assert symbols["UserId"].kind == "type"
    assert result.imports == ["./http"]
    assert result.warning is None


def test_jsx_and_single_argument_arrow():
    result = parse_javascript((FIXTURES / "view.jsx").read_text())
    assert [s.name for s in result.symbols] == ["View", "identity"]
    assert result.symbols[1].parameters == ["value"]
    assert result.warning is None


def test_tsx():
    result = parse_javascript("export const View = () => <div/>;", typescript=True, tsx=True)
    assert result.symbols[0].name == "View"
    assert result.warning is None


def test_malformed_source_reports_partial_failure():
    assert parse_python("def broken(:").warning
    assert parse_javascript("function broken( {").warning


def test_source_is_never_executed(tmp_path):
    marker = tmp_path / "executed"
    result = parse_python(f"open({str(marker)!r}, 'w').write('danger')\ndef safe(): pass")
    assert result.symbols[0].name == "safe"
    assert not marker.exists()

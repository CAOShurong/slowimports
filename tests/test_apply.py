from slowimports.apply import apply_source, plan_apply
from slowimports.analyze import analyze_source


def test_moves_function_only_import():
    src = "import csv\n\ndef read(path):\n    return csv.reader(path)\n"
    out = apply_source(src)
    assert "import csv" not in out.split("def")[0]
    assert "    import csv\n" in out
    compile(out, "<apply>", "exec")


def test_inserts_into_each_using_function():
    src = (
        "import json\n"
        "def a():\n"
        "    return json.dumps({})\n"
        "def b():\n"
        "    return json.loads('{}')\n"
    )
    out = apply_source(src)
    assert out.count("import json") == 2
    assert "def a():\n    import json\n" in out
    assert "def b():\n    import json\n" in out


def test_leaves_import_time_use_alone():
    src = "import json\nX = json.dumps({})\ndef f():\n    return json\n"
    assert apply_source(src) == src


def test_skips_multi_name_import_line():
    src = "import csv, json\n\ndef f():\n    return csv.reader, json.dumps\n"
    bindings = analyze_source(src)
    assert plan_apply(src, bindings) == []
    assert apply_source(src) == src


def test_after_docstring():
    src = (
        "import csv\n"
        "def read(path):\n"
        '    """Load rows."""\n'
        "    return csv.reader(path)\n"
    )
    out = apply_source(src)
    assert '    """Load rows."""\n    import csv\n' in out


def test_from_import():
    src = "from decimal import Decimal\n\ndef money(x):\n    return Decimal(str(x))\n"
    out = apply_source(src)
    assert "from decimal import Decimal" not in out.split("def")[0]
    assert "    from decimal import Decimal\n" in out

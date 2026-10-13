from recentctl.quick import QuickItem, reason, select
from recentctl.rules import Rules


def items():
    return [
        QuickItem("Desktop", r"C:\Users\alice\Desktop", pinned=True),
        QuickItem("batch", r"\\nas\transfer\Private\batch", pinned=False),
        QuickItem("Private", r"\\nas\transfer\Private", pinned=True),
        QuickItem("docs", r"D:\Work\docs", pinned=False),
    ]


def test_patterns_select_frequent_and_report_pinned():
    picked, skipped = select(items(), [r"*\transfer\private*"], None, include_pinned=False)
    assert [i.name for i, _ in picked] == ["batch"]
    assert [i.name for i in skipped] == ["Private"]


def test_include_pinned_unpins_too():
    picked, skipped = select(items(), [r"*\transfer\private*"], None, include_pinned=True)
    assert [i.name for i, _ in picked] == ["batch", "Private"] and skipped == []


def test_rules_private_and_keep_but_no_age():
    r = Rules(private=[r"*\Work\*", r"*\transfer\*"], keep=[r"*\batch"])
    picked, _ = select(items(), [], r, include_pinned=False)
    assert [(i.name, w) for i, w in picked] == [("docs", r"private: *\Work\*")]
    assert reason(items()[1], [], r) is None  # kept

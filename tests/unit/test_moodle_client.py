"""Moodle client behaviour via FakeMoodleClient (no live server)."""


def test_create_and_get_page(moodle):
    created = moodle.create_page(1, "Notes", "<p>i</p>", "<p>body</p>")
    fetched = moodle.get_page(created["cmid"])
    assert fetched["pagecontent"] == "<p>body</p>"


def test_copy_module(moodle):
    original = next(m for s in moodle.course for m in s["modules"] if m["modname"] == "label")
    copied = moodle.copy_module(original["id"], beforemod=0)
    assert copied["cmid"] != original["id"]


def test_invalid_section_raises(moodle):
    try:
        moodle.create_label(99, "<p>x</p>")
        assert False, "expected ValueError"
    except ValueError:
        pass

from agent.summaries import course_summary


def test_course_summary_empty():
    assert course_summary(None) == []
    assert course_summary([]) == []


def test_course_summary_shape(fake_client):
    summary = course_summary(fake_client.course)

    assert isinstance(summary, list)
    assert len(summary) == 2

    general, week1 = summary
    assert general["sectionnum"] == 0
    assert general["name"] == "General"
    assert general["modules"] == [
        {"cmid": 100, "modname": "label", "name": "Welcome label", "visible": 1}
    ]

    assert week1["sectionnum"] == 1
    assert {m["cmid"] for m in week1["modules"]} == {101, 102}


def test_course_summary_omits_full_html_bodies(fake_client):
    """Summary must not include intro/labelcontent/pagecontent etc."""
    summary = course_summary(fake_client.course)
    flat = str(summary)
    assert "labelcontent" not in flat
    assert "pagecontent" not in flat
    assert "syllabus body" not in flat

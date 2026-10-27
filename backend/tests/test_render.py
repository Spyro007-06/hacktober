import unicodedata

import pytest
from jinja2 import UndefinedError

from backend.services.render import TEMPLATE_BY_ROUTE, check_templates, make_env, render_html

ENV = make_env()


def ctx(**over):
    base = dict(
        route="local_body", draft_id="d_test", created_on="2026-10-26",
        decision={"reason_en": "Because rule.", "reason_ta": "விதி காரணமாக."},
        department={"name": "[DEMO] Dept", "address": "DEMO PLACEHOLDER"},
        department_verified=False,
        demo_notice={"en": "DEMO DATA: placeholders.", "ta": "டெமோ தரவு: மாதிரி."},
        complainant={"name": "R. Priya", "address": "14 Gandhi Street", "phone": "98xxxxxx10"},
        category="streetlight", summary_en="The light is dead.", summary_ta="விளக்கு எரியவில்லை.",
        location_text="Gandhi Street", duration="3 months", photo_findings=[], requested_info=[],
        portal_fields={}, portal_fields_verified=False, evidence_photos=[],
        next_steps={"en": "Submit it.", "ta": "சமர்ப்பிக்கவும்."},
    )
    base.update(over)
    return base


def render(route="local_body", **over):
    return render_html(ENV, route, ctx(route=route, **over))


@pytest.mark.parametrize("route,marker", [
    ("local_body", "புகார் கடிதம்"), ("cm_helpline", "புகார் கடிதம்"), ("rti", "தகவல் கோரிக்கை"),
])
def test_every_route_renders_a_complete_bilingual_document(route, marker):
    html = render(route)
    assert html.lstrip().lower().startswith("<!doctype html>") and "</html>" in html
    assert marker in html
    assert "The light is dead." in html and "விளக்கு எரியவில்லை." in html
    assert "14 Gandhi Street" in html and "R. Priya" in html


def test_template_mapping_matches_the_prd_route_split():
    assert TEMPLATE_BY_ROUTE == {"local_body": "grievance.html",
                                 "cm_helpline": "grievance.html", "rti": "rti.html"}
    check_templates(ENV)


def test_tamil_text_survives_rendering_unchanged():
    tamil = unicodedata.normalize("NFC", "காந்தி தெருவில் மூன்று மாதங்களாக எரியவில்லை.")
    assert tamil in render(summary_ta=tamil)


def test_autoescape_neutralises_markup_in_user_text():
    html = render(summary_en="<script>alert(1)</script>", location_text='"><img src=x onerror=1>')
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x" not in html


def test_undefined_variable_fails_loudly_instead_of_rendering_blank():
    context = ctx()
    del context["summary_en"]
    with pytest.raises(UndefinedError):
        render_html(ENV, "local_body", context)


def test_demo_banner_shown_only_for_unverified_departments():
    assert "DEMO DATA" in render(department_verified=False)
    assert "DEMO DATA" not in render(department_verified=True)
    assert "டெமோ தரவு" in render("rti", department_verified=False)


def test_missing_optional_values_leave_no_blank_or_placeholder_in_the_letter():
    html = render(location_text=None, duration="", complainant={"name": "A", "address": "B", "phone": None},
                  department={"name": "The Commissioner", "address": "Main Road"}, department_verified=True)
    assert "Phone:" not in html and "தொலைபேசி:" not in html  # no empty phone line
    assert "at my locality" in html and "எங்கள் பகுதி" in html  # the subject still reads correctly
    body = html.split("<body>")[1]  # the stylesheet legitimately contains brackets
    assert "None" not in body and "[" not in body


def test_letter_has_the_standard_petition_parts_in_both_languages():
    html = render()
    for part in ("From", "To", "Subject:", "Respected Sir / Madam,", "Thanking you,", "Yours faithfully,",
                 "அனுப்புநர்", "பெறுநர்", "பொருள்:", "ஐயா / அம்மையீர்,", "இப்படிக்கு,"):
        assert part in html
    assert "Request to repair the non-functioning streetlight at Gandhi Street" in html
    assert "26-10-2026" in html  # dd-mm-yyyy


def test_portal_table_and_unverified_label_note():
    pf = {"Grievance details": "text", "Communication address": "addr"}
    html = render("cm_helpline", portal_fields=pf, portal_fields_verified=False)
    assert "Grievance details" in html and "unconfirmed placeholders" in html
    assert "unconfirmed placeholders" not in render("cm_helpline", portal_fields=pf, portal_fields_verified=True)
    assert "Portal form fields" not in render("cm_helpline", portal_fields={})


def test_rti_lists_requested_information():
    html = render("rti", requested_info=["Repair budget? / பழுதுபார்ப்பு நிதி?", "Contractor name"])
    assert "following information" in html and "தகவல் அறியும் உரிமைச் சட்டம், 2005" in html
    assert "Repair budget?" in html and "பழுதுபார்ப்பு நிதி?" in html
    assert html.count("Contractor name") == 2  # a question without a Tamil half appears in both letters
    assert "No specific information has been entered" in render("rti", requested_info=[])


def test_photo_observations_labelled_as_automated_and_unverified():
    html = render(photo_findings=["unlit pole"])
    assert "unlit pole" in html and "automated, unverified" in html
    assert "Photo observations" not in render(photo_findings=[])


def test_templates_contain_no_section_numbers_fees_or_deadlines():
    for route in ("local_body", "cm_helpline", "rti"):
        html = render(route, requested_info=["x"])
        for forbidden in ("Section ", "30 days", "within 30", "Rs.", "fee of", "fee is"):
            assert forbidden not in html


def test_only_the_rti_letter_names_the_rti_act():
    # An RTI application must say it is made under the Act; no other letter cites any law.
    assert "Right to Information Act, 2005" in render("rti")
    for route in ("local_body", "cm_helpline"):
        assert "Act" not in render(route)


def test_missing_template_directory_fails_fast(tmp_path):
    with pytest.raises(Exception):
        check_templates(make_env(tmp_path))


def test_rti_subject_names_the_works_not_a_defect():
    html = render("rti", category="road", location_text="Anna Nagar ward")
    assert "regarding road repair works at Anna Nagar ward" in html and "damaged road" not in html

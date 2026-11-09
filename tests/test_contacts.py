from src.contacts import email_reply


def test_cs_department_gets_cs_emails_not_is():
    reply = email_reply("وش ايميل علوم الحاسب")
    assert "cs.office@imamu.edu.sa" in reply
    assert "cs.acadv@imamu.edu.sa" in reply
    assert "is.office" not in reply.lower()


def test_is_projects_committee():
    reply = email_reply("ايميل لجنة مشاريع التخرج نظم")
    assert "IS.GP.m@imamu.edu.sa" in reply and "IS.GP.f@imamu.edu.sa" in reply


def test_cs_projects_committee_is_not_given_the_is_email():
    reply = email_reply("ايميل لجنة مشاريع التخرج علوم الحاسب")
    assert "IS.GP" not in reply
    assert "ما لقيت" in reply and "cs.office@imamu.edu.sa" in reply


def test_projects_committee_without_department_names_the_department():
    reply = email_reply("ايميل لجنة المشاريع")
    assert "نظم المعلومات" in reply and "علوم الحاسب" in reply  # the "not published" note


def test_doctor_by_name():
    assert "lahazzaa@imamu.edu.sa" in email_reply("ايميل د. لميس الهزاع")
    assert "warodhan@imamu.edu.sa" in email_reply("ايميل دكتور الروضان")


def test_college_deanship():
    assert "ccis.dean@imamu.edu.sa" in email_reply("ايميل عميد الكلية")
    assert "ccis.dean@imamu.edu.sa" in email_reply("ايميل كلية علوم الحاسب والمعلومات")


def test_social_counselling_is_not_academic_advising():
    reply = email_reply("ايميل الارشاد النفسي")
    assert "ccis.spg.z.n@imamu.edu.sa" in reply and "acadv" not in reply


def test_university_deanships():
    for q in ("ايميل عمادة القبول والتسجيل", "ايميل القبول والتسجيل", "ايميل التسجيل علوم الحاسب"):
        reply = email_reply(q)
        assert "admission@imamu.edu.sa" in reply and "ccis.dean" not in reply, q
    reply = email_reply("ايميل عمادة شؤون الطلاب")
    assert "crm.imamu.edu.sa" in reply and "ccis.dean" not in reply
    for q in ("ايميل عمادة التعلم الالكتروني", "ايميل عمادة تقنية المعلومات", "ايميل الدعم الفني بلاك بورد"):
        reply = email_reply(q)
        assert "crm.imamu.edu.sa" in reply and "it.office" not in reply, q


def test_contact_questions_without_the_word_email():
    for q in ("عماده القبول والتسجيل", "كيف اتواصل مع عمادة القبول والتسجيل",
              "رقم عمادة القبول والتسجيل", "ابي اتواصل مع شؤون الطلاب"):
        reply = email_reply(q)
        assert reply and ("admission@imamu.edu.sa" in reply or "crm.imamu.edu.sa" in reply), q
    assert "fialmuqhim@imamu.edu.sa" in email_reply("كيف اتواصل مع رئيس قسم علوم الحاسب")


def test_admission_content_questions_are_not_contact_questions():
    assert email_reply("متى يبدأ التسجيل") is None
    assert email_reply("وش شروط القبول في علوم الحاسب") is None
    assert email_reply("عمادة القبول والتسجيل وش شروط التحويل بين الكليات") is None


def test_non_email_questions_fall_through():
    assert email_reply("متى يبدأ الحذف") is None
    assert email_reply("وش ايميلي الجامعي") is None


def test_department_heads_use_the_newest_source():
    assert "رئيس" not in email_reply("ايميل د. لميس الهزاع")
    reply = email_reply("ايميل الدكتور فهد المقحم")
    assert "fialmuqhim@imamu.edu.sa" in reply and "رئيس قسم علوم الحاسب" in reply
    assert "نوف" in email_reply("ايميل رئيس قسم تقنية المعلومات")

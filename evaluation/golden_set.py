"""
Golden questions for the RAG evaluation.

Each reference answer is copied from the official FAQ of the Deanship of
Admission and Registration (docs/imamu_web/faqs/الأسئلة_الشائعة_عمادة_القبول_والتسجيل.md),
so RAGAS compares the chatbot against the university's own wording, not ours.
"""

GOLDEN = [
    {
        "id": "TC-06",
        "topic": "Academic warning",
        "question": "متى يحصل الطالب على الإنذار الأكاديمي؟",
        "reference": "يحصل الطالب على إنذار أكاديمي إذا قل معدله التراكمي عن 2 من 5 في جميع الكليات باستثناء كلية الهندسة (2.75).",
    },
    {
        "id": "TC-07",
        "topic": "Semester withdrawal (اعتذار) limit",
        "question": "كم مرة يحق للطالب الاعتذار عن الفصل الدراسي؟",
        "reference": "لا يحق للطالب الاعتذار عن الدراسة أكثر من ستة فصول دراسية.",
    },
    {
        "id": "TC-08",
        "topic": "Study postponement (تأجيل) limit",
        "question": "كم مرة يحق للطالب تأجيل الدراسة؟",
        "reference": "لا يحق للطالب تأجيل الدراسة أكثر من ثلاث مرات.",
    },
    {
        "id": "TC-09",
        "topic": "Course withdrawal (انسحاب) limit",
        "question": "كم مقرر يحق للطالب الانسحاب منه خلال الفصل الدراسي؟",
        "reference": "يحق للطالب الانسحاب من مقرر أو مقررين فقط خلال الفصل الدراسي.",
    },
    {
        "id": "TC-10",
        "topic": "Enrollment cancellation (طي القيد)",
        "question": "متى يطوى قيد الطالب من الجامعة؟",
        "reference": "يطوى قيد الطالب إذا انقطع عن الدراسة خمسة عشر يوماً متواصلة أو ثلاثين يوماً منفصلة خلال الفصل الدراسي الواحد دون أن يتقدم بطلب تأجيل أو اعتذار عن الدراسة.",
    },
    {
        "id": "TC-11",
        "topic": "Exam deprivation (حرمان) without excuse",
        "question": "متى يحرم الطالب من دخول الاختبار النهائي بدون عذر؟",
        "reference": "يحرم الطالب من الاستمرار في الدراسة ودخول الاختبار النهائي بدون عذر إذا قلت نسبة حضوره عن 80% من الوحدات الدراسية.",
    },
    {
        "id": "TC-12",
        "topic": "Academic dismissal",
        "question": "متى يفصل الطالب من الجامعة؟",
        "reference": "يفصل الطالب من الجامعة إذا حصل على ثلاثة إنذارات متتالية لانخفاض معدله التراكمي، أو إذا لم ينه متطلبات التخرج خلال مدة أقصاها نصف المدة المقررة لتخرجه علاوة على مدة البرنامج.",
    },
    {
        "id": "TC-13",
        "topic": "First-class honours",
        "question": "متى يحصل الطالب على مرتبة الشرف الأولى؟",
        "reference": "تمنح مرتبة الشرف الأولى للطالب الحاصل على معدل تراكمي من 4.75 إلى 5 عند التخرج.",
    },
    {
        "id": "TC-14",
        "topic": "Minimum study load",
        "question": "ما هو الحد الأدنى للعبء الدراسي؟",
        "reference": "الحد الأدنى من العبء الدراسي هو 12 ساعة دراسية.",
    },
]

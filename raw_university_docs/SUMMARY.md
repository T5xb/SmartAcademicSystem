# raw_university_docs: crawl summary

Focused crawl of the public IMSIU site (scripts/crawl_university.py --focus), 2026-10-26.
Scope: College of Computer and Information Sciences (CCIS), Deanship of Admission and Registration,
academic calendar, study plans and course descriptions, FAQs, and student regulations
(public text of each in-force regulation on the Nizam platform, imamu.edu.sa/laws).

Files kept: 378 (after SHA-256 dedup and removal of 432 off-scope files,
e.g. other colleges' plans, bulk per-major registration PDFs, room schedules, staff/org pages).

| Category | Total | Pages (.md) | Documents |
|---|---|---|---|
| academic_calendar | 1 | 0 | 1 |
| admission_registration | 79 | 42 | 37 |
| course_catalogs | 223 | 0 | 223 |
| faqs | 3 | 3 | 0 |
| forms | 6 | 0 | 6 |
| graduate_studies | 3 | 0 | 3 |
| other | 5 | 2 | 3 |
| regulations | 34 | 14 | 20 |
| student_affairs | 4 | 3 | 1 |
| study_plans | 20 | 4 | 16 |

## Scanned PDFs with no text layer (need scripts/ocr_pdf.py)

- course_catalogs/للتحميل__CS1110.pdf (2 pages)
- course_catalogs/للتحميل__CS1140.pdf (2 pages)
- course_catalogs/للتحميل__CS1100.pdf (2 pages)
- course_catalogs/للتحميل__CS1141.pdf (2 pages)
- course_catalogs/للتحميل__CS1242.pdf (2 pages)
- course_catalogs/للتحميل__CS1222.pdf (2 pages)
- course_catalogs/للتحميل__CS114.pdf (2 pages)
- course_catalogs/للتحميل__CS150.pdf (2 pages)
- course_catalogs/للتحميل__CS125.pdf (2 pages)
- course_catalogs/للتحميل__CS151.pdf (2 pages)
- course_catalogs/للتحميل__CS252.pdf (2 pages)
- course_catalogs/للتحميل__CS222.pdf (2 pages)
- course_catalogs/للتحميل__CS330.pdf (2 pages)
- regulations/إرشادات للطلاب حول أنظمة الدراسة والاختبارات في الجامعة__1.pdf (2 pages)
- regulations/لائحة الدراسة والاختبارات للمرحلة الجامعية والقواعد التنفيذية للجامعة__8.pdf (35 pages)
- regulations/دليل الارشاد الاكاديمي​__Academic Advising Guide.pdf (24 pages)
- regulations/لائحة الدراسات والاختبارات للمرحلة الجامعية__لائحة الدراسات والاختبارات للم.pdf (38 pages)
- regulations/لائحة تأديب الطالب__لائحة تأديب الطالب.pdf (39 pages)
- admission_registration/إرشاد الطالب حول أنظمة الدراسة والاختبارات في الجامعة__Regulatory_rules_1444.pdf (35 pages)
- academic_calendar/التقويم الجامعي - Calendar_1448.pdf__Calendar_1448.pdf (2 pages)
- admission_registration/طلاب__M0712_2.pdf (39 pages)
- admission_registration/طلاب__M0711_2.pdf (39 pages)

## Notes

- robots.txt was obeyed (e.g. */Pages/default.aspx on imamu.edu.sa was skipped); 1 request/second.
- Login portals (SIS, advising systems, etc.) were not visited.
- Regulation PDF files on the Nizam platform require a login; the public text of each regulation is
  saved as .md in regulations/ instead. Several key regulations are also public PDFs on the
  Admission deanship and CCIS sites (study & exam regulations, discipline, grievance).
- The crawl was stopped early (≈140 pages) on purpose when only bulk per-major announcement PDFs remained.
- Details of every fetch: _crawl_log.jsonl.

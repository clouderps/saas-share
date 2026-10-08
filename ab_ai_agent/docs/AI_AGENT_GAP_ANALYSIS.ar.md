<div dir="rtl">

# وكيل غيمة الذكي مقابل ذكاء Odoo — تحليل الفجوات وخطة التنفيذ

_2026-10-08 · النسخة التفاعلية (عربي/إنجليزي): https://claude.ai/artifact/TtbrXyhKwxmyF1paHhLEuD_

> إصدار Odoo 19 Community لا يتضمن وكيل ذكاء اصطناعي؛ المرجع هو مصدر Odoo 20.0 Enterprise لوحدات `ai*` (مرخّص OEEL — دُرس السلوك فقط دون نسخ أي كود). منصّتنا مبنية على Odoo 18.

يعتمد Odoo 20 Enterprise (OEEL، دُرِس من حيث السلوك فقط) على إطار وكلاء واحد: إجراءات الخادم كأدوات، وجلسات دائمة، ومهارات تُحمَّل عند الطلب، ومصادر معرفة لكل وكيل مع الاستشهادات، والذكاء الاصطناعي في المحرر والمُنشئ والحقول وإجراءات الخادم والأتمتة وMCP، عبر نحو 53 وحدة ai تُثبَّت تلقائياً (ai_agentic اختيارية). وتتفوّق غيمة (Odoo 18) في القياس متعدد المستأجرين، وحرية اختيار المزوّد، والتخزين المؤقت للتعليمات (prompt caching)، وتحليلات مجموعة الكتل (block kit)، ودعم العربية، والصوت، ومسح المستندات، وأوامر الشرطة المائلة، والإعداد القائم على التأكيد أولاً.

كشفت مراجعة الشيفرة عيوباً بأولوية P0 يجب معالجتها قبل أي ميزات جديدة:
- يستطيع المساعد الافتراضي تأكيد أدوات الكتابة الخاصة بروبوت المحادثة بنفسه، ومنها post_invoice (G45)؛
- زر «تأكيد» يتجاوز مفتاح الإيقاف وفحوص الباقة والمجموعات، وشرائح التأكيد في روبوت المحادثة غير مرتبطة بمقترحها (G02)؛
- أداة data_analysis تنفّذ SQL خاماً دون تقييد بالنطاق (G01)؛
- جميع نماذج Claude التي نقدّمها متقاعدة (G08)؛
- الذكاء الاصطناعي الأصلي في محرر Odoo والمُنشئ يرسل نصوص المستأجر إلى Odoo (G24)؛
- رفض البوابة يرتدّ إلى مفاتيح المستأجر (G07، G44).

الخطة: المراحل 1–4، نحو 26–32 أسبوعاً بمطوّرَين اثنين: التثبيت؛ مساواة نواة الوكيل؛ المعرفة والواجهات؛ حقول الذكاء الاصطناعي وإجراءات الخادم والوكلاء المجدولون وMCP للقراءة فقط. وتبقى المحادثة المباشرة (Livechat) وجسور CRM/الموارد البشرية وOAuth لـ MCP في قائمة الانتظار.

## بطاقة التقييم (0–5)

| المحور | غيمة | Odoo | تعليق |
|---|---|---|---|
| نموذج الوكيل وإعداده | 3.5 | 4.5 | لدينا: شخصيات ai.agent، والمواضيع/الأدوات/المهارات، ومُنشئ بلا شيفرة، وuse_all_capabilities، وسقف لعدد الوكلاء حسب الباقة. ويضيف Odoo مهارات تُحمَّل عند الطلب، وتفويضاً لوكلاء فرعيين، ومهارة Self Update (مقصورة على نماذج ai.*)، وقواعد ai.composer التي تربط كل واجهة بوكيل. |
| مزوّدو LLM والبوابة وضبط التكلفة | 3 | 3 | لدينا: اختيار المزوّد، وبوابة مركزية، وباقات، وميزانيات، ودليل أسعار بالريال، ومطابقة. Odoo: عبر IAP فقط (Odoo يختار النموذج ويحاسب بالرصيد)، دون ميزانيات لكل مستخدم. خُفِّضت درجتنا من 3.5 لأن جميع معرّفات Claude التي نقدّمها متقاعدة (المزوّد يفشل اليوم)، إضافة إلى أخطاء التكلفة، وقائمة الميزات المغلقة، وارتداد وضع 'auto' إلى مفاتيح المستأجر بعد رفض البوابة. |
| استدعاء الأدوات والإجراءات على السجلات | 3.5 | 4.5 | لدينا: CRUD عامّ وquery_data، وopen_list/pivot/graph مع النطاقات والتجميع والمقاييس، وnavigate، وrecord_action، وcreate_record مع معالجة ضريبة القيمة المضافة، وdate_reference (مكافئ لـ compute_date في Odoo). Odoo: أي إجراء خادم كأداة مُتحقَّق منها بالمخطط، و24 أسلوب _ai_tool_* مدمجاً تشمل الإنشاء/التحديث الجماعي وقراءة الملفات (read_binary_content)، وأدوات متصفح تعدّل العرض المفتوح في مكانه. |
| الإنسان في الحلقة والأمان | 2.5 | 4 | تصميمنا أكثر صرامة (لا موافقة تلقائية، والمحاسبة مسودات فقط)، لكن اليوم يستطيع المساعد تأكيد أدوات الكتابة الخاصة بروبوت المحادثة بنفسه ومنها post_invoice (G45)، وزر «تأكيد» يتجاوز البوابات وشرائح التأكيد غير مرتبطة (G02)، وdata_analysis ينفّذ SQL غير مقيّد (G01)، ويمكن للضيف الحصول على ردّ من الروبوت مدعوم بصلاحيات المستخدم الأعلى (G03). تبقى الدرجة 2.5 حتى تُطلق إصلاحات الدفعة 1a من المرحلة 1. ثغرة Odoo نفسه: ‎_ai_tool_run ينفّذ شيفرة إجراء الخادم عبر ‎_run_action_code_multi، فلا تُفحص group_ids الخاصة بالإجراء في هذا المسار. |
| مصادر المعرفة (RAG) والتضمينات | 2.5 | 4.5 | لدينا: ملخّص المعرفة، وai.chat.fact (pgvector وتطابق ثلاثي الأحرف)، وkb_search (مطابقة كلمات بسيطة) على 10 حزم معرفة منسّقة بالعربية والإنجليزية، ومقتطف الموقع؛ semantic_index موجود لكن لا يستخدمه أي نموذج؛ والاستشهادات مجرد هيكل أوّلي. Odoo: مصادر لكل وكيل (ملفات، روابط، Knowledge، Documents)، وتقسيم إلى أجزاء، وتضمين دفعي، واستشهادات مفلترة حسب الصلاحية. |
| الذاكرة والجلسات | 2.5 | 4 | لدينا: الجلسات موجودة فقط عبر ab_ai_chatbot؛ والسجل هو آخر 6 رسائل كنص عادي؛ بلا تلخيص؛ وبلا سياسة احتفاظ. Odoo: يخزّن ai.session وai.session.event كل خطوة بشكل دائم، مع قنوات Discuss، وعناوين تلقائية للمحادثات، وتنظيف تلقائي. |
| واجهات المستخدم (المحادثة، الكونسول، المُنشئ، أزرار التعليمات) | 3.5 | 4.5 | لدينا: الكونسول، ولوحة سجل المحادثات (chatter)، والزر العائم، ومؤشر الذكاء الاصطناعي، إضافة إلى واجهات لا يملكها Odoo: واجهة API أصلية للذكاء الاصطناعي على الجوال (6 نقاط JWT تستخدمها تطبيقات Flutter) وبوابة مسح المستندات. Odoo: الذكاء الاصطناعي في محرر html، ومُنشئ البريد، وعارض الملفات، وشريط النظام، وCtrl+K، مع أزرار تعليمات على السجلات. الذكاء الاصطناعي الأصلي في محرر Odoo 18 CE ومُنشئه موجود لدى مستأجرينا لكنه يُوجَّه إلى خوادم Odoo (G24). |
| عرض الإجابات والتحليلات | 4.5 | 3 | مجموعة الكتل لدينا (شبكة مؤشرات الأداء، ومخططات Chart.js، والجداول، والتنبيهات) إضافة إلى query_data مع المقارنة بالفترة السابقة. Odoo يجيب بفتح عروض pivot أو graph ويربط السجلات في الإجابات؛ أما صفوف جداولنا فغير قابلة للنقر بعد (G48). |
| الصوت | 4 | 3.5 | لدينا: وضع بدون استخدام اليدين، وتأكيد صوتي، وتحويل النص إلى كلام بالعربية، مع القياس. Odoo: تحويل الكلام إلى نص في المُنشئ، وإملاء مباشر في المحرر، ونسخ تسجيلات المكالمات، وهو ما نفتقده. |
| المستندات / استخراج OCR | 4 | 3.5 | يقرأ ab_scan_docs المستندات بالرؤية الحاسوبية إلى مسودات من 7 أنواع خلف بوابات الطيار الآلي، مع بوابة كاملة. Odoo يفرز مجلدات Documents، ويعرض إنشاء فواتير الموردين كأداة، ويتيح للمستخدمين المحادثة حول أي ملف (read_binary_content، 'Summarize this file')، وهو ما لا نستطيعه (G46). خطأ مسار البوابة يخفض درجتنا. |
| حقول الذكاء الاصطناعي | 0 | 4 | غير موجودة في منظومتنا. |
| الذكاء الاصطناعي في الأتمتة وإجراءات الخادم | 1 | 4.5 | لدينا: مهام مجدولة ثابتة فقط (التقرير اليومي، الملخّص). Odoo: نوع إجراء خادم 'AI'، و'Update with AI' (evaluation_type 'ai_computed')، ووكلاء تُطلقهم base.automation وفق جداول زمنية مع صندوق وارد للتشغيلات. |
| MCP / التشغيل البيني | 1.5 | 4 | لدينا: REST مع OpenAPI عبر ab_api_base. Odoo: خادم MCP مع OAuth 2.1، وتسجيل ديناميكي للعملاء، ونطاق 'mcp' لمفاتيح API، وأداة سياق أوّلي. |
| الإعداد بالذكاء الاصطناعي | 3.5 | 1.5 | لدينا: يغيّر ab_ai_agent_config مجموعة مُعتمدة من إعدادات الأعمال (مثل تعدد العملات) بعد «تأكيد» فقط. مهارة Self Update في Odoo مقصورة على نماذج ai.* (‎_check_tool_scope) وقائمة الحظر AI_MODELS_BLOCKLIST لا تغطي إلا نماذج قليلة. |
| حسب التطبيق: المحاسبة | 3 | 3.5 | لدينا: أوامر مسودات فواتير العملاء والموردين والقيود اليومية، وأدوات مالية، ورؤى التقارير (معطّلة عبر البوابة). أداة post_invoice في روبوت المحادثة تكسر قاعدة المسودات فقط (G45)، والتقارير نفسها مُدقَّقة جزئياً. Odoo: أدوات تقود التقارير المحاسبية، إضافة إلى وكلاء تدقيق. |
| حسب التطبيق: المبيعات/CRM، المشتريات، المخزون، نقاط البيع | 3.5 | 2 | لدينا: أدوات تحليلية، و/create quote و/create rfq، وأدوات المخزون، وأدوات نقاط البيع والمطبخ (بعضها معطّل بسبب قائمة الميزات المغلقة). Odoo: أزرار تعليمات في الغالب، إضافة إلى أداة تنشئ عملاء محتملين من المحادثة المباشرة. |
| حسب التطبيق: الموارد البشرية، المشاريع، الدعم الفني، التسويق، الموقع | 1.5 | 3.5 | لدينا: /create employee، وab_error_help (أخطاء عبر التطبيقات، 478 للموارد البشرية)، وأدوات موارد بشرية معطّلة فعلياً بسبب بوابة البيانات الشخصية. Odoo: رسائل رفض توظيف يصوغها الذكاء الاصطناعي، ومساعد سجلات الدوام، والبحث عن تذاكر مشابهة، ومُنشئ حملات، ومنشورات تواصل اجتماعي ووكيل لصندوق وارد التواصل الاجتماعي، ومولّد صفحات موقع. |
| تعدد اللغات / العربية | 4.5 | 3 | تطبيع النص العربي في التوجيه والتخزين المؤقت والبحث في القوائم؛ وإزالة العلامة التجارية بالعربية ضمن ضوابط البوابة؛ وصياغة أعمال سعودية؛ وتحويل النص إلى كلام بالعربية؛ وملفات ar.po. Odoo يكتفي بتوجيه النموذج للرد بلغة المستخدم. |
| المراقبة والتقييمات والاختبارات | 3.5 | 3.5 | لدينا: تدقيق التشغيل مع تصنيف التأصيل وزمن الاستجابة والتقييم؛ ونحو 453 اختبار Python (182 للوكيل، 98 لروبوت المحادثة، 98 للأوامر، 32 للمسح، 18 للعميل، 13 للبوابة، 12 أخرى)، لكن لا شيء لـ ab_ai_base وab_ai_ui والفوترة المركزية أو أي JS؛ وأداة التقييم تقيس بيئة تشغيل متقاعدة. Odoo: اختبارات وحدة وOAuth قوية وخطوات وكيل مرئية، لكن بلا تحليلات للتشغيلات. |
| الأداء | 3 | 3.5 | لدينا: تخزين مؤقت للإجابات، وتخزين مؤقت للتعليمات، وتوجيه للأدوات؛ لكن التشغيل متزامن، والسجل نص واحد متنامٍ، وسياق السجل يقرأ كل الحقول. Odoo: حلقة غير متزامنة، وجلب RAG في الجولة الأولى فقط، واقتطاع السجلات قبل إرسالها إلى النموذج. |
| اعتبارات SaaS متعددة المستأجرين | 4 | 2 | لدينا: رموز المستأجرين، وentity_ref محمي من العبث، وسقوف الباقات، والدفع عند التهيئة. Odoo قاعدة بيانات واحدة مع IAP. تنخفض درجتنا بسبب حارس المستأجر الذي يمنع ab_ai_base (مؤكَّد من الشيفرة) وبسبب O1 (لم يُجرَ بعد أي تشغيل بمزوّد حقيقي عبر البوابة). |

## مطابقة المفاهيم

| المفهوم في Odoo | المقابل لدينا | ملاحظة |
|---|---|---|
| **ai.agent (شخصية مدعومة بسجل شريك)**<br>`ai/models/ai_agent.py (AIAgent, _get_instructions, _build_rag_context)` | **شخصية ai.agent (دون سجل شريك)؛ وشريك روبوت Discuss موجود في ab_ai_chatbot**<br>`saas-share/ab_ai_agent/models/ai_agent.py; saas-client/ab_ai_chatbot/models/discuss_channel.py` | نضيف سقوف الباقات وسقف تكلفة لكل تشغيل وuse_all_capabilities؛ ويضيف Odoo الحقل allowed_agent_ids للتفويض ومصادر لكل وكيل. المسارات: مراجع Odoo نسبية إلى odoo-20.0/odoo/addons/، ومراجعنا نسبية إلى clouderps-apps/ (و odoo-18/ هو نواة Odoo 18 لدينا). |
| **ai.skill (يُعلَن الوصف؛ وتُحمَّل التعليمات والأدوات عند الطلب عبر load_skills)**<br>`ai/models/ai_skill.py; ai/models/ai_tool.py#_ai_tool_load_skills` | **ai.agent.topic (تعليمات + tool_ids، وauto_attach)، مع توجيه بالكلمات المفتاحية**<br>`saas-share/ab_ai_agent/models/ai_agent_topic.py; services/runtime.py#_route_tools` | تعارض في التسمية: ai.agent.skill لدينا قالب تعليمات (context_model، surfaces، requires_record_context)، أقرب إلى ai.prompt.button في Odoo. مواضيعنا تُحمَّل دائماً، لا عند الطلب. |
| **أدوات ir.actions.server بخاصية use_in_ai مع ai_tool_schema**<br>`ai/models/ir_actions_server.py#_ai_tool_run,_check_ai_tool_schema; ai/utils/tools_schema/validators.py` | **ai.agent.tool + السجل ‎_REGISTRY على مستوى الوحدة؛ dispatch_kind python\|server_action**<br>`saas-share/ab_ai_agent/models/ai_agent_tool.py#is_invocable_by; services/tool_dispatcher.py#dispatch,_dispatch_server_action` | فحوص المجموعات موجودة لدينا أصلاً (run() في Odoo 18 يفرض groups_id؛ وdispatch يفحص group_ids للأداة). الناقص: التحقق من الوسائط عند الإرسال، والتأكيد أولاً للحالات التي تكتب، وسياق السجل النشط، والبيانات الأولية والاختبارات (G16). |
| **الأدوات المدمجة في ai.tool ‏(search, read_group, get_fields, get_models, compute_date, get_menus, get_menu_details, open_menu_list/kanban/pivot/graph, run_view_action, compute_report_measures, read_binary_content, prepare_record_previews, update_records, create_records)**<br>`ai/models/ai_tool.py (24 _ai_tool_* methods, incl. _ai_tool_compute_date, _ai_tool_read_binary_content, _ai_tool_prepare_record_previews, _ai_tool_update_records); ai/data/ir_actions_server_data.xml` | **search/read_group/get_fields ← find_records وcount_records وread_record وquery_data وexplain_screen؛ compute_date ← date_reference؛ get_menus/get_menu_details ← find_menu وlist_my_apps؛ run_view_action/open_menu_* ← open_action وnavigate وopen_list/open_pivot/open_graph؛ compute_report_measures ← أقرب مقابل query_data؛ read_binary_content ← لا يوجد (G46)؛ prepare_record_previews ← لا يوجد (G48)؛ update_records/create_records ← update_record/act_on_record لسجل واحد (G47)**<br>`saas-share/ab_ai_agent/services/generic_data.py; services/query_data.py; services/tool_dispatcher.py (date_reference, find_menu, list_my_apps, open_action, open_list/pivot/graph); services/agent_actions.py#update_record,act_on_record` | المبدأ نفسه: الأدوات تعمل بصلاحيات المستخدم وتُرفض النماذج المحظورة. أدواتنا تُرجع مغلّفات عرض (مخططات، بطاقات مؤشرات أداء). |
| **ai.session + ai.session.event (آلة حالات دائمة)**<br>`ai/models/ai_session.py (loop_state, _handle_tool_calls, _resume_pending_interaction)` | **ai.agent.run (سجل تدقيق لكل تشغيل) + ai.chat.conversation/message (وحدة المستأجر) + ai.agent.pending.action**<br>`saas-share/ab_ai_agent/models/ai_agent_run.py; saas-client/ab_ai_chatbot/models/ai_chat.py` | ينتهي التشغيل لدينا عند اقتراح عملية كتابة؛ ويُنفَّذ «التأكيد» خارج الحلقة ولا يرى النموذج النتيجة. كما أن ab_ai_chatbot ما زال يحمل بيئة تشغيل قديمة (G49). |
| **waiting_confirmation + resume_token / auto_confirm**<br>`ai/utils/ai_utils.py#make_confirmation_request_preview; ai/controllers/thread.py#resume_pending_interaction` | **ai.agent.pending.action (مفتاح عشوائي، صلاحية 15 دقيقة، متكرر التنفيذ بأمان؛ الحقلان tool_code وagent_run_id موجودان، وagent_id غير موجود)**<br>`saas-share/ab_ai_agent/models/ai_agent_pending_action.py#propose,resolve` | لا نوفّر عمداً خيار «الموافقة دائماً». لكن أدوات الكتابة القديمة في روبوت المحادثة تتجاوز هذا النموذج وتسلّم مفتاح التأكيد إلى LLM ‏(G45)، وresolve() يتجاوز البوابات (G02). |
| **ask_user_question (سؤال اختيار يوقف التشغيل مؤقتاً)**<br>`ai/models/ai_tool.py#_ai_tool_ask_user_question` | **نص need_info من create_record؛ وأسئلة الالتباس في ab_ai_command؛ وSuggestionChips**<br>`saas-share/ab_ai_agent/services/agent_actions.py#_required_missing; saas-share/ab_ai_command/services/resolvers.py` | لا توجد لدينا أداة اختيار منظّمة (G12). |
| **أدوات العميل (do_action, show_view, adjust_view/adjust_search) + معلومات العرض الحالي**<br>`ai/models/ai_tool.py#_ai_tool_adjust_search; ai/static/src/core/web/search_model_patch.js; ai/static/src/core/web/with_search_patch.js` | **navigate + open_list/open_pivot/open_graph + aiNavigator.sanitizeDirective + AiCursor؛ وai.screen.context (يرسل النطاق والتجميعات والفلاتر، ويُتحقَّق منها على الخادم)**<br>`saas-share/ab_ai_agent/services/navigate.py; services/tool_dispatcher.py#_builtin_open_list,_builtin_open_pivot,_builtin_open_graph; static/src/services/screen_context_service.js; models/ai_screen_context.py#_domain_ok` | نفتح بالفعل عروضاً مفلترة ومجمّعة وعروض pivot بالمقاييس المختارة. الناقص: تعديل العرض المفتوح في مكانه، والتحقق من حقول نطاقات النموذج في open_* ‏(G17). |
| **ai.composer (مفتاح واجهة مرتبط بوكيل) + ai.prompt.button**<br>`ai/models/ai_composer.py; ai/models/ai_prompt_button.py` | **surface_ids في ai.agent + ai.agent.skill (context_model، surfaces) + نقاط بدء مبنية من قوائم المستخدم**<br>`saas-share/ab_ai_agent/models/ai_agent_skill.py; static/src/web/chatter_patch.js` | لا تُعرض بعد شرائح خاصة بكل نموذج (G23). واجهات المحرر والمُنشئ موجودة أصلاً في Odoo 18 CE لكنها تُوجَّه إلى Odoo IAP ‏(G24). |
| **ai.agent.source + ai.embedding + ai.embedding.mixin (pgvector 1536، HNSW)**<br>`ai/models/ai_agent_source.py; ai/models/ai_embedding.py; ai/orm/field_vector.py` | **ai.semantic.index (768 بُعداً، HNSW أو بديل JSON) + ai.chat.fact + ai.agent.knowledge.digest + kb_search على حزم ab_knowledge_base_***<br>`saas-share/ab_ai_base/models/semantic_index.py; saas-client/ab_ai_chatbot/models/chat_fact.py; saas-share/ab_ai_agent/models/ai_agent_knowledge_digest.py; saas-theme/ab_knowledge_base_ai/models/kb_tools.py` | لا مصادر لكل وكيل ولا خط إدخال للبيانات. الاستشهادات موجودة كهيكل أوّلي فقط (services/citation.py). |
| **ناقل IAP ‏odoo_ai ‏(call_odoo_ai) + وسم الاستخدام**<br>`ai/utils/ai_utils.py#call_odoo_ai_transport` | **ab_ai_gateway (مركزي) + ai.client.config.call_ai في ab_ai_client + llm_adapter (البوابة ← المباشر ← المحاكاة)**<br>`saas-ai/ab_ai_gateway/models/ai_gateway_service.py; saas-client/ab_ai_client/models/ai_client_config.py; saas-share/ab_ai_agent/services/llm_adapter.py#call_llm` | أسماء الميزات لدينا Selection مغلقة، بخلاف نص الاستخدام الحر في Odoo ‏(G05). وفي الوضع الافتراضي 'auto' يرتدّ رفض البوابة إلى مفتاح المستأجر الخاص (G07). |
| **رصيد IAP**<br>`ai/data/iap_service_data.xml` | **ai.plan / ai.plan.subscription / ai.tenant.budget / ai.usage.local.budget / ai.usage.price.book (+ ai.token.pricing المركزي)**<br>`saas-ai/ab_ai_plan/models/ai_plan_subscription.py; saas-share/ab_ai_agent/models/ai_usage_local_budget.py; saas-share/ab_ai_agent/models/ai_usage_price_book.py` | منظومتنا أغنى (حدود لكل شركة ومستخدم ووكيل وواجهة، وفوترة بالريال، وتجاوز الحد) لكن فيها أخطاء دقة وجدولا أسعار (G06، G08). |
| **رسائل أجزاء محايدة تجاه المزوّد (TextPart، ToolCallPart، ToolResultPart)**<br>`ai/utils/types.py` | **سجل نصي واحد متنامٍ، مع مخططات أدوات أصلية لكل مزوّد**<br>`saas-share/ab_ai_agent/services/runtime.py#run; saas-share/ab_ai_base/models/ai_service.py#_tools_for_openai,_tools_for_anthropic,_tools_for_gemini` | الفرق المعماري الرئيسي في حلقة الوكيل (G10). |
| **تعليمات متعددة الطبقات + <odoo_current_context> مُلحق بدور المستخدم**<br>`ai/models/ai_agent.py#_get_instructions; ai/models/ai_session.py#_get_context_input` | **‎_compose_system_prompt: بادئة ثابتة، ثم CACHE_BREAK، ثم الجزء المتغيّر**<br>`saas-share/ab_ai_agent/services/runtime.py#_compose_system_prompt` | الفكرة نفسها. نضيف تخزيناً مؤقتاً صريحاً لدى المزوّد، لكنه معطّل في التثبيتات الجديدة (G09). |
| **أداة web_search + استشهادات [WEB_SOURCE:uuid]**<br>`ai/models/ai_tool.py#_ai_tool_web_search; ai/utils/ai_citation.py` | **العلم allow_web_grounding (هيكل أوّلي)**<br>`saas-share/ab_ai_agent/models/ai_agent.py` | غير موجود (G18). |
| **ai_fields (تعليمات على مستوى الحقل، تعبئة بمهمة مجدولة، زر عند الطلب)**<br>`ai_fields/models/models.py#_fill_ai_field,get_ai_field_value; ai_fields/models/ir_model_fields.py#_cron_fill_ai_fields; ai_fields/data/ir_cron_data.xml` | **لا يوجد**<br>`-` | غير موجود (G30). |
| **حالة 'ai' في ir.actions.server + 'Update with AI' ‏(evaluation_type 'ai_computed')**<br>`ai/models/ir_actions_server.py#_ai_action_run; ai_server_actions/models/ir_actions_server.py` | **لا يوجد**<br>`-` | غير موجود (G31). |
| **base.automation.ai_agent_id + جداول ai.automation.trigger + صندوق وارد التشغيلات**<br>`ai_agentic/models/base_automation.py; ai_agentic/models/ai_automation_trigger.py; ai_agentic/models/ir_actions_server.py#_ai_action_run_agent` | **مهام مجدولة ثابتة: التقرير اليومي ai.report، وملخّص المعرفة**<br>`saas-client/ab_ai_client/models/report_generator.py; saas-share/ab_ai_agent/data/ir_cron_data.xml` | لا نستطيع تشغيل وكلاء يعرّفهم المستخدم بمحفّزات أو جداول زمنية (G32). ai_agentic اختيارية وليست تلقائية التثبيت. |
| **مهارة Self Update في ai_agentic (الوكيل يعدّل إعدادات ai.* الخاصة به)**<br>`ai_agentic/data/ai_skill_data.xml; ai_agentic/models/ai_tool.py#_check_tool_scope; ai/utils/ai_utils.py#AI_MODELS_BLOCKLIST` | **ab_ai_agent_config: تغييرات بالتأكيد أولاً على مجموعة مُعتمدة من إعدادات الأعمال**<br>`saas-share/ab_ai_agent_config/__manifest__.py` | نطاق مختلف: وكيل Odoo يعدّل نفسه؛ ووكيلنا يعدّل إعدادات ERP للشركة بعد «تأكيد» فقط. وليس آمناً للأتمتة إطلاقاً. |
| **ai_mcp (خادم ‎/mcp + OAuth 2.1 + نطاق 'mcp' لمفاتيح API + أداة السياق الأوّلي)**<br>`ai_mcp/controllers/mcp_controller.py; ai_mcp/controllers/oauth_server_controller.py; ai_mcp/models/ai_mcp_request_dispatcher.py; ai_mcp/models/ai_tool.py#_ai_tool_mcp_retrieve_initial_context; ai_mcp/models/res_users_description.py` | **ab_api_base (نطاقات JWT، ‏@api_route، ‏OpenAPI/Swagger)**<br>`saas-share/ab_api_base/controllers/api.py#_auth_token,register_scope_validator` | ab_api_base هو الأساس الصحيح. أما auth='bearer' في Odoo 18 فلا يملك معامل نطاق (odoo-18/odoo/addons/base/models/ir_http.py:204). |
| **ai_livechat (الوكيل كمشغّل محادثة مباشرة، forward_operator) + ai_social (وكيل على الرسائل الخاصة في التواصل الاجتماعي مع تحويل لموظف وشروط تفعيل) + بطاقات المعاينة**<br>`ai_livechat/models/im_livechat_channel_rule.py; ai_livechat/controllers/main.py#forward_operator; ai_social/models/ai_agent.py#_ai_tool_social_livechat_add_human; ai_social/models/im_livechat_channel.py; ai_website_livechat/models/ai_preview_card_mixin.py` | **روبوت مبيعات ghaima.sa (مركزي) + أداة التضمين**<br>`saas-ai/ab_ghaima_website_chatbot/controllers/main.py; saas-ai/ab_ghaima_ai_embed/controllers/widget.py` | روبوت الموقع يتصل بالمزوّد مباشرة (حدود معدّل لكل عامل فقط)؛ ودورات أداة التضمين تُسجَّل وتخضع للضوابط عبر البوابة لكن بلا ميزانية. لا يملك أيٌّ منهما بيانات ERP ولا تحويلاً لموظف. وواتساب صادر فقط (G26). |
| **ChatGPTPlugin في محرر html / mail_composer_chatgpt / كتل ‎/prompt**<br>`ai/static/src/editor/plugins/chatgpt_plugin.js; ai/static/src/mail_composer_chatgpt.js; ai/models/mail_render_mixin.py` | **نوافذ ChatGPT والترجمة والبدائل الأصلية في Odoo 18 CE وأداة mail_composer_chatgpt، إضافة إلى استدعاء OLG في معالج إعداد الموقع — وكلها موجّهة إلى نقطة OLG التابعة لـ Odoo IAP**<br>`odoo-18/addons/html_editor/controllers/main.py#generate_text; odoo-18/addons/mail/static/src/core/web/mail_composer_chatgpt.js; odoo-18/addons/website/models/website.py#_OLG_api_rpc` | نصوص المستأجر وdatabase.uuid تغادر منصتنا دون قياس وتحت علامة Odoo التجارية. يُحتوى ذلك عبر ICP من اليوم الأول؛ ثم يمنح وراثة generate_text واحدة ذكاءً اصطناعياً مقيساً في المحرر والمُنشئ (G24). |
| **ir.attachment._ai_read + read_binary_content + تعليمات عارض الملفات**<br>`ai/models/ir_attachment.py#_ai_read; ai/models/ai_tool.py#_ai_tool_read_binary_content; ai/data/ai_composer_data.xml` | **لا يوجد: إرفاق الملفات في المحادثة يرسلها فقط إلى مستخرج مسح المستندات**<br>`saas-client/ab_ai_chatbot/static/src/js/ai_agent_chat_attach_patch.js; saas-share/ab_ai_agent/controllers/agent_chat.py` | غير موجود (G46). |
| **نسخ mail.call.artifact / ملخصات voip_ai / الإملاء المباشر**<br>`ai/models/mail_call_artifact.py; voip_ai/models/voip_call.py#_generate_call_summary; ai/static/src/core/realtime_client.js` | **الصوت المباشر: ‎/ai_agent/voice/transcribe و‎/speak، ووضع بدون استخدام اليدين، والتأكيد الصوتي**<br>`saas-share/ab_ai_agent/controllers/voice.py; static/src/voice/voice.js` | نتفوّق في الصوت التحاوري؛ لكن لا نملك نسخ التسجيلات (G28). |
| **الفرز التلقائي في ai_documents + أدوات فواتير الموردين في ai_documents_account**<br>`ai_documents/models/documents_document.py#_ai_setup_sort_actions; ai_documents/models/ir_actions_server.py` | **استخراج ab_scan_docs بالرؤية الحاسوبية + الطيار الآلي + البوابة**<br>`saas-client/ab_scan_docs/models/scanned_document.py#_run_autopilot; models/scan_ai_config.py#call_ai; controllers/portal_document.py` | نتفوّق في الاستخراج. الفرز التلقائي للمجلدات لا ينطبق (إصدار Community لا يملك تطبيق Documents). |
| **أدوات التقارير في ai_account_reports + وكلاء التدقيق**<br>`ai_account_reports/models/ai_tool.py#_ai_tool_accounting_report_get_values; ai_account_reports/data/ai_audit_agents.xml` | **get_ai_insights في ab_account_reports_ai (طلقة واحدة، على ab_ai_client القديم)**<br>`saas-accounting/ab_account_reports_ai/models/ab_account_report_ai.py` | نحتاج أدوات تقارير يستدعيها الوكيل، مقصورة على التقارير المُدقَّقة (G34). |
| **خاصية ‎_explanation للنموذج / explanation في ir.actions (أوصاف مكتوبة لـ LLM)**<br>`ai/models/ai_tool.py#_ai_tool_get_models; ai/models/ai_agent.py#_get_available_menus` | **ملخّص المعرفة + مسرد find_menu (عربي←إنجليزي) + explain_screen**<br>`saas-share/ab_ai_agent/services/tool_dispatcher.py#_MENU_GLOSSARY,_builtin_explain_screen` | واجهة API في نواة Odoo 20؛ وعلى Odoo 18 نعيد بناءها كبيانات. |

## مصفوفة الفجوات

| الرمز | القدرة | الحالة | الأولوية | الأثر | الجهد |
|---|---|---|---|---|---|
| G01 | أدوات البيانات تحترم قيود الشركة والفرع والصلاحيات | partial | P0 | high | M |
| G02 | «التأكيد» يعيد فحص كل البوابات؛ والتأكيدات مرتبطة بمقترحها | partial | P0 | high | M |
| G03 | هوية صحيحة على واجهات الروبوت والواجهات العامة والمشتركة | partial | P0 | high | M |
| G04 | الحفاظ على سرية بيانات التكلفة والأسرار | partial | P0 | high | S |
| G05 | أسماء ميزات مفتوحة لنسب الاستخدام | partial | P0 | high | S |
| G06 | قياس دقيق، وسقوف تكلفة، وفوترة التجاوز | partial | P0 | high | M |
| G07 | قياس وحوكمة كل استدعاء ذكاء اصطناعي، بما فيها الواجهات العامة | partial | P1 | high | M |
| G08 | معرّفات مزوّد صالحة، ومرونة، وكتالوج نماذج واحد، ومخرجات منظّمة | partial | P0 | high | M |
| G09 | تفعيل التخزين المؤقت للتعليمات افتراضياً | ours_ahead | P0 | medium | S |
| G10 | سجل رسائل محايد تجاه المزوّد (messages[] مع أجزاء tool_call/tool_result) | partial | P1 | high | L |
| G11 | تشغيلات دائمة تصمد أمام إعادة التشغيل وتُستأنف بعد التوقف | partial | P2 | medium | L |
| G12 | أسئلة توضيحية منظّمة (اختيارات، اختيار متعدد، نص حر) | partial | P1 | medium | S |
| G13 | مواضيع تُحمَّل عند الطلب لإبقاء التعليمات وقائمة الأدوات صغيرة | partial | P2 | medium | M |
| G14 | التفويض بين عدة وكلاء | missing | P3 | low | M |
| G15 | وكلاء يحدّثون إعداداتهم بأنفسهم | partial | P3 | low | M |
| G16 | إجراءات الخادم كأدوات، مع التحقق من الوسائط مقابل مخططها | partial | P1 | medium | M |
| G17 | تشكيل العرض الحالي للمستخدم (الفلاتر، التجميعات، المقاييس) | partial | P1 | medium | M |
| G18 | التأصيل بالبحث على الويب مع الاستشهادات | missing | P2 | medium | M |
| G19 | توليد الصور وتحريرها | missing | P3 | low | M |
| G20 | مصادر معرفة لكل وكيل: الإدخال، والتضمينات، والاسترجاع، والاستشهادات | partial | P1 | high | L |
| G21 | جلسات مخزّنة في النواة، مع سجل منظّم وتلخيص | partial | P1 | high | M |
| G22 | الاحتفاظ بالتشغيلات وسجلات الاستخدام | missing | P0 | medium | S |
| G23 | شرائح تعليمات لكل نموذج وحزم تعليمات لكل تطبيق | partial | P1 | medium | M |
| G24 | الذكاء الاصطناعي في المحرر ومُنشئ البريد (صياغة، إعادة كتابة، ترجمة) عبر بوابتنا | partial | P0 | high | M |
| G25 | 'اسأل الذكاء الاصطناعي' في لوحة الأوامر وشريط النظام | partial | P2 | low | S |
| G26 | وكيل ذكاء اصطناعي على قنوات المحادثة المباشرة والموقع وصندوق وارد التواصل الاجتماعي، مع التحويل لموظف | partial | P2 | medium | L |
| G27 | مُنشئ مواقع بالذكاء الاصطناعي (توليد الصفحات، هوية العلامة، تحسين محركات البحث، نماذج الويب) | missing | P3 | low | XL |
| G28 | نسخ التسجيلات والإملاء (نتفوّق في الصوت المباشر) | ours_ahead | P3 | low | M |
| G29 | استخراج المستندات عبر مسار سياسات موحّد | ours_ahead | P0 | high | S |
| G30 | حقول تُملأ بتعليمات الذكاء الاصطناعي | missing | P2 | medium | L |
| G31 | نوع إجراء خادم بالذكاء الاصطناعي و'التحديث بالذكاء الاصطناعي' | missing | P2 | medium | M |
| G32 | وكلاء تُطلقهم الأحداث أو الجداول الزمنية، مع صندوق وارد للتشغيلات | missing | P2 | high | L |
| G33 | خادم MCP لعملاء الذكاء الاصطناعي الخارجيين | missing | P2 | medium | L |
| G34 | أدوات وكيل للتقارير المحاسبية، ورؤى تقارير تعمل فعلاً | partial | P1 | high | M |
| G35 | التقاط العملاء المحتملين وتلخيصهم؛ وصياغة رسائل المبيعات | partial | P2 | medium | M |
| G36 | أدوات مساعد الموارد البشرية وصياغة رسائلها | partial | P2 | medium | M |
| G37 | مساعد سجلات الدوام وتعليمات المشاريع | partial | P3 | low | M |
| G38 | تذاكر مشابهة ومسودات ردود | missing | P3 | low | M |
| G39 | صياغة الحملات والبريد الجماعي ومحتوى التواصل الاجتماعي | missing | P3 | low | L |
| G40 | أدوات تشغيلية للمشتريات والمخزون ونقاط البيع (نحن متقدمون) | ours_ahead | P3 | medium | S |
| G41 | سلوك يعطي العربية الأولوية (نحن متقدمون) | ours_ahead | P2 | medium | S |
| G42 | تغطية اختبارية وتقييمات لبيئة التشغيل الإنتاجية | partial | P1 | high | M |
| G43 | سياق مقتصد في كل خطوة | partial | P1 | medium | S |
| G44 | موثوقية تهيئة المستأجرين لمنظومة الذكاء الاصطناعي | partial | P0 | high | S |
| G45 | كل عملية كتابة تتطلب نقرة بشرية (لا تأكيد ذاتي من النموذج) | partial | P0 | high | S |
| G46 | المحادثة حول الملفات ومرفقات السجلات | missing | P1 | high | M |
| G47 | الإنشاء والتحديث الجماعي بتأكيد واحد | partial | P2 | medium | M |
| G48 | سجلات قابلة للنقر في الإجابات | missing | P2 | medium | S |
| G49 | بيئة تشغيل واحدة؛ ولا حالة عامة تُبدَّل لكل طلب | partial | P1 | medium | M |
| G50 | تكاملات كل تطبيق في جسور تُثبَّت تلقائياً | partial | P1 | medium | M |

## تفاصيل الفجوات

### G01 — أدوات البيانات تحترم قيود الشركة والفرع والصلاحيات

`partial` · `P0` · الأمان

**Odoo:** تعمل جميع أدوات البيانات في بيئة دون sudo عبر ORM (‏_ai_tool_search و‎_ai_tool_read_group يستخدمان has_access مع قواعد السجلات). تُرفض نماذج ir.* وقائمة AI_MODELS_BLOCKLIST. تُحلَّل النطاقات بـ literal_eval وتُحدّ بـ 5000 حرف.

**غيمة:** يعمل query_data بصلاحيات المستخدم عبر Model._read_group، الذي يعيد ab.branch.mixin تعريف ‎_search فيه، فهو مقيّد بالفرع أصلاً (query_data.py:117; odoo-18/odoo/models.py:2006; ab_branch_base/models/branch_mixin.py:40-60). العيوب: ‎_builtin_data_analysis ينفّذ SQL خاماً على pos_order وsale_order وaccount_move دون أي فلتر للشركة أو الفرع أو ACL أو قواعد السجلات (tool_dispatcher.py:840-905)؛ كما يجمّع الأيام على طوابع UTC (خطأ بالنسبة لـ Asia/Riyadh)، ويجمع amount_total عبر العملات تحت عملة الشركة، ويُرجع str(e) إلى النموذج. جداول الحقائق في ab_ai_chatbot ‏(fact_query) عروض مادية تتجاوز قواعد السجلات. query_data يتخطى generic_data.model_blocked. يبني semantic_search النطاق extra_domain تحت sudo، لكن النتائج تُعاد فلترتها بصلاحيات المستخدم (tool_dispatcher.py:1369)، فالخطر هو الاستدلال غير المباشر لا تسريب السجلات. ويقرأ ‎_record_context_block سجل المحادثات عبر record.sudo().message_ids ‏(runtime.py:1322).

**التوصية:** أعد بناء data_analysis على Model._read_group بصلاحيات المستخدم، مع تمرير المنطقة الزمنية للمستخدم في السياق وتجميع الإجماليات حسب العملة (أو تحويلها إلى عملة الشركة)؛ أرجِع خطأً عاماً وسجّل الاستثناء؛ وأبقِ المغلّف الحتمي. استدعِ model_blocked في query_data. تحقّق من حقول extra_domain في semantic_search بصلاحيات المستخدم. اقرأ سجل المحادثات بصلاحيات المستخدم. لا حاجة إلى جسر فروع لـ query_data. ولـ fact_query فقط أضف ab_ai_chatbot_branch ‏(saas-branches، تثبيت تلقائي مع ab_branch_base + ab_ai_chatbot)، أو أعد بناء جداول الحقائق على ‎_read_group واستغنِ عن الجسر. الاختبارات: query_data وdata_analysis مقيّدان بالفرع لمستخدم مقيّد بفرع؛ طلب الساعة 23:30 بتوقيت الرياض يقع في اليوم الصحيح؛ شركة بعملتين تعرض الإجماليات لكل عملة.

`ai/models/ai_tool.py#_ai_tool_read_group,_check_agent_model_access,_parse_domain` `ai/utils/ai_utils.py#AI_MODELS_BLOCKLIST` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_data_analysis,_DA_METRICS,_builtin_semantic_search` `saas-share/ab_ai_agent/services/query_data.py#query_data` `saas-share/ab_ai_agent/services/runtime.py#_record_context_block` `saas-client/ab_ai_chatbot/services/fact_query.py` `saas-branches/ab_branch_base/models/branch_mixin.py`

### G02 — «التأكيد» يعيد فحص كل البوابات؛ والتأكيدات مرتبطة بمقترحها

`partial` · `P0` · الإنسان في الحلقة

**Odoo:** يوقف التأكيدُ دفعةَ أدوات الجلسة مؤقتاً. وعند الاستئناف يُتحقَّق من resume_token بـ compare_digest ويستمر استدعاء الأداة نفسه، مع حصر الأدوات في مهارات الوكيل، وsu=False، ونقطة حفظ (savepoint). (ثغرة Odoo نفسه: ‎_ai_tool_run ينفّذ شيفرة إجراء الخادم عبر ‎_run_action_code_multi، فلا تُفحص group_ids للإجراء في هذا المسار.)

**غيمة:** يستدعي ai.agent.pending.action.resolve() دالة الأداة مباشرة مع agent=None، متجاوزاً actions_enabled وسياسة الباقة وgroup_ids للأداة وallow_write_actions. الحقلان tool_code وagent_run_id موجودان أصلاً في الإجراء المعلّق (ai_agent_pending_action.py:40, :45)، أما agent_id فلا، ولا يمرّر أيُّ مستدعٍ لـ propose() قيمة agent_run ‏(agent_actions.py:232; tool_dispatcher.py:1185, :1271). مسار تأكيد ثانٍ غير مُدقَّق: execute_action في ab_ai_chatbot ‏(ai_chat.py:596-660) يعيد استدعاء أداة مع confirm=True باستخدام tool_name والوسائط المرسلة من العميل؛ ويتحقق ‎_replay_or_execute فقط من أن المفتاح بحالة 'proposed' (بحث sudo على الأداة + المفتاح، chat_action_log.py:56-62)، لا من المستخدم أو المحادثة أو الهدف أو الوسائط، ودون صلاحية زمنية، فيمكن تنفيذ مقترح للسجل A على السجل B. ويمكن لـ screen_button وact_on_record الضغط على زر 'Post' في account.move لأي مستخدم فوترة. وأدوات حضور الموارد البشرية (requires_pii=True) تُعرض على الوكيل الافتراضي (allow_pii=False) وتُرفض دائماً. أما مسار التأكيد الذاتي الذي يقوده النموذج فهو G45.

**التوصية:** أضف agent_id فقط، ومرّر agent وagent_run من كل موضع يستدعي propose(). امنح dispatch() معاملاً بالكلمة فقط confirmed: bool خارج الوسائط (dispatch يحذف مفاتيح _ai_*، tool_dispatcher.py:90) يمرّر _ai_confirmed=True إلى الأداة. يبحث resolve() عن ai.agent.tool بواسطة tool_code، ويجلب agent_id، ويستدعي dispatch()، فيُعاد فحص is_invocable_by وبوابات البيانات الشخصية والكتابة وactions_enabled وسياسة الباقة لحظة النقر. وجّه شرائح التأكيد في روبوت المحادثة عبر ‎/ai_agent/action/confirm واحذف execute_action؛ وحتى ذلك الحين اربط سجل التنفيذ بـ create_uid == env.uid وبالمحادثة، وقارن تجزئة الهدف والوسائط، واجعل صلاحيته 15 دقيقة. أضف سجلاً للأساليب المحمية (action_post في account.move/account.payment، وdone في hr.payslip) لا يجوز لأي مسار وكيل استدعاؤها. فلتر أدوات requires_pii في ‎_resolve_tools عندما لا يسمح الوكيل بالبيانات الشخصية، واجعل أدوات حضور الموارد البشرية التي تعرض الأسماء فقط requires_pii=False (مع بقاء قيد دور الموارد البشرية). أضف اختبارات لعدم تطابق الهدف، ومستخدم آخر، وانتهاء الصلاحية.

`ai/models/ai_session.py#_resume_pending_interaction,_handle_tool_calls` `ai/controllers/thread.py#resume_pending_interaction` `ai/models/ir_actions_server.py#_ai_tool_run` `saas-share/ab_ai_agent/models/ai_agent_pending_action.py#propose,resolve` `saas-share/ab_ai_agent/services/tool_dispatcher.py#dispatch,_builtin_screen_button,_builtin_record_action` `saas-share/ab_ai_agent/services/runtime.py#_resolve_tools` `saas-client/ab_ai_chatbot/models/ai_chat.py#execute_action` `saas-client/ab_ai_chatbot/models/chat_action_log.py` `saas-client/ab_ai_chatbot/services/tools/actions.py#_replay_or_execute`

### G03 — هوية صحيحة على واجهات الروبوت والواجهات العامة والمشتركة

`partial` · `P0` · الأمان

**Odoo:** يعيد خطاف الويب (webhook) بناء البيئة بهوية المستخدم الأصلي مع su=False ويعيد التحقق من صلاحية الوصول للشركة. البحث عن القناة دون sudo؛ وdiscuss.channel.ai_agent_id بصلاحية groups=NO_ACCESS؛ والضيوف يحصلون على سياق ضيف صريح؛ والمعاينات مفلترة بـ user_has_access.

**غيمة:** يعمل روبوت Discuss على محادثة sudo، وعندما لا يكون للكاتب res.users (ضيف أو شريك خارجي) يعمل على بيئة SUPERUSER، ثم ينشر str(e) في القناة (تم التحقق، discuss_channel.py ~L190-220). روابط ‎/ai_chat/shared/<token> لا تنتهي صلاحيتها أبداً. يعرض chatbot.js في ghaima.sa مخرجات النموذج عبر innerHTML. ولا يتحقق ‎/entity/express/status/<id> من is_express، فيمكن الاستعلام عن حالة أي مستأجر. ويمكن لـ conversation_lookup إظهار display_name لسجل لا يستطيع المستخدم قراءته.

**التوصية:** الدفعة 1a: لا تشغّل الروبوت أبداً دون سائل داخلي (ردّ برسالة تسجيل دخول مترجمة)، ولا على بيئة SUPERUSER إطلاقاً؛ سجّل الاستثناءات وردّ برسالة عامة. الدفعة 1b: الحقل share_expires_at (افتراضياً 7 أيام) وإلغاء الروابط عند الحذف؛ اعرض ردود روبوت المحادثة عبر textContent مع markdown آمن؛ تحقّق من is_express واستخدم رمز حالة موقّعاً؛ واستدعِ check_access('read') قبل find_or_create_for_record.

`ai/controllers/thread.py#completion_result_ready,_validate_session_request_company_access` `ai/models/ai_session.py#_get_request_context_snapshot` `ai/models/discuss_channel.py` `saas-client/ab_ai_chatbot/models/discuss_channel.py#_ai_bot_do_reply` `saas-client/ab_ai_chatbot/controllers/chat_controller.py` `saas-ai/ab_ghaima_website_chatbot/static/src/js/chatbot.js` `saas-ai/ab_ai_express_signup/controllers/express.py` `saas-share/ab_ai_agent/controllers/agent_chat.py#conversation_lookup`

### G04 — الحفاظ على سرية بيانات التكلفة والأسرار

`partial` · `P0` · الأمان

**Odoo:** الجلسات والأحداث والتضمينات مقروءة للمسؤولين فقط. حقل سر خطاف الويب بصلاحية NO_ACCESS. والاستخدام يُقاس على خادم Odoo ولا يُعرض للمستخدمين.

**غيمة:** يُرجع ‎/ai_agent/usage/live إنفاق الشركة (مقروءاً بـ sudo) لأي مستخدم داخلي، ويمكن لأي مستخدم مسجّل الانضمام إلى قناة الناقل النصية ai.usage.live.<company_id> لأي شركة. وكل مغلّف يحمل usage.cost_usd. وتضع رؤية Gemini ‏(ai_service.py:1010) والتضمين (:1286) المعامل ‎?key= في الرابط؛ وتسجّل الرؤية الاستثناء ثم تعيد إطلاق نصه كـ UserError ‏(:1048-1050)، فقد يظهر المفتاح على شاشة المستخدم النهائي لا في السجلات فقط. أما محادثة النص والكلام فتستخدم أصلاً الترويسة x-goog-api-key ‏(:739, :1176, :1238)، والبوابة تحجب الأسرار أصلاً (_scrub_secrets، gateway_api.py:312، منذ 2026-06-22). والحقل ai.client.config.entity_token قابل للقراءة عبر RPC من قِبل group_ai_report_user.

**التوصية:** اقصر usage_live على مدير الذكاء الاصطناعي أو مستخدمي النظام؛ أرسل العدّاد المباشر على قناة سجل res.company يُتحقَّق منها مقابل المجموعات في إعادة تعريف ‎_build_bus_channel_list؛ واحذف التكلفة من المغلّفات لغير المسؤولين. انقل استدعاءَي Gemini إلى الترويسة x-goog-api-key؛ ولا تضع نص الاستثناء في UserError أبداً؛ وانقل ‎_scrub_secrets إلى ab_ai_base وأضف مرشّح سجلات يحجب key=. اضبط groups='base.group_system' على entity_token. معيار القبول: البحث بـ grep لا يجد '?key=' في ab_ai_base، وخطأ HTTP مفتعل لا يُظهر المفتاح في السجل أو الواجهة.

`ai/security/ir.access.csv` `ai/models/ai_session.py (request_webhook_secret groups NO_ACCESS)` `saas-share/ab_ai_agent/controllers/agent_chat.py#usage_live` `saas-share/ab_ai_agent/services/meter.py#emit_live` `saas-share/ab_ai_base/models/ai_service.py#_call_gemini_vision,_call_gemini_embed` `saas-ai/ab_ai_gateway/controllers/gateway_api.py (_scrub_secrets)` `saas-client/ab_ai_client/models/ai_client_config.py (entity_token)`

### G05 — أسماء ميزات مفتوحة لنسب الاستخدام

`partial` · `P0` · البوابة

**Odoo:** يرسل العميل نص استخدام حراً ('agent:<xmlid>'، 'ai_field'، 'web_search'، channel_name). يتم النسب والفوترة على الخادم، ولا تُفرض أي قائمة مغلقة على العميل.

**غيمة:** الحقل ai.usage.log.feature من نوع Selection مغلق، وقوائم allowed_features في الباقات مغلقة أيضاً. يرسل المستأجرون business_query وpos_suggestions وkitchen_prediction وkitchen_performance وanomaly_detection وdashboard_insights وaccounting_report_insight. فيُطلق تسجيل السجل ValueError، بعد أن يكون المزوّد قد احتسب التكلفة عند عدم وجود باقة. والنتيجة أن الذكاء الاصطناعي على الجوال ورؤى لوحات المعلومات ورؤى التقارير المحاسبية لا تعمل إطلاقاً عبر البوابة.

**التوصية:** حوّل feature إلى Char وأضف نموذج ربط (الميزة ← الفئة: chat، analytics، documents، voice، compose، automation، mcp، custom). تُقيَّد الباقات على مستوى الفئات؛ والأسماء غير المعروفة تقع في 'custom'. اكتب سجل الاستخدام بحالة 'pending' قبل استدعاء المزوّد وحدّثه بعده. أضف اختبار بوابة لكل نص ميزة يرسله المستأجرون. انشر المركز قبل المستأجرين.

`ai/models/ai_agent.py#_get_usage_string` `ai/utils/types.py (CompletionOptions.usage)` `saas-ai/ab_ai_gateway/models/ai_usage_log.py` `saas-ai/ab_ai_plan/models/ai_plan.py#get_allowed_features_list` `ghaima-api/ab_mobile_ai_api/controllers/ai_query.py` `saas-dashboard/ab_dynamic_dashboard/models/dashboard_ai_bridge.py` `saas-accounting/ab_account_reports_ai/models/ab_account_report_ai.py`

### G06 — قياس دقيق، وسقوف تكلفة، وفوترة التجاوز

`partial` · `P0` · ضبط التكلفة

**Odoo:** يُحتسب رصيد IAP لكل استدعاء على خادم Odoo، فلا يجري العميل أي حسابات تكلفة.

**غيمة:** تُضاف الرموز المخزّنة مؤقتاً إلى total_tokens مرة أخرى وتُحتسب مرتين في ai.usage.price.book.estimate_cost. المسار المباشر لا يضبط usage['cost_usd'] أبداً، فلا يعمل ai.agent.max_cost_usd ويبقى run.cost_usd صفراً. النماذج التي ليس لها صف سعر (gpt-3.5-turbo، gpt-4، claude-3-sonnet/haiku، gemini-flash-latest) تكلّف 0 دولار، فلا تمتلئ الميزانيات أبداً. ‎_cron_generate_overage_invoices بلا سجل ir.cron. وجسر الرصيد يكتب صفَّي rate_limited لكل استدعاء محظور ويطبع '$' للريال.

**التوصية:** وحّد بيانات الاستخدام مرة واحدة في ab_ai_base إلى (input_uncached، cached، output) واستخدم دالة تكلفة واحدة للبوابة والمسار المباشر. في المسار المباشر احسب التكلفة محلياً من دليل الأسعار المتزامن ليعمل سقف كل تشغيل. عند فرض ميزانية وعدم وجود صف سعر للنموذج، احظر الاستدعاء. أضف المهمة المجدولة الناقصة للتجاوز، واحذف سجل حد المعدّل المكرر، واستخدم رمز عملة الباقة، وأضف اختبارات في ab_ai_plan.

`ai/utils/ai_utils.py#call_odoo_ai (credits via iap)` `ai/data/iap_service_data.xml` `saas-share/ab_ai_agent/models/ai_usage_price_book.py#estimate_cost` `saas-share/ab_ai_agent/services/meter.py#record` `saas-share/ab_ai_agent/services/runtime.py (cum_cost)` `saas-ai/ab_ai_gateway/models/ai_token_pricing.py` `saas-ai/ab_ai_plan/models/ai_plan_subscription.py#_cron_generate_overage_invoices` `saas-ai/ab_ai_plan_credit_bridge/models/ai_gateway_service.py`

### G07 — قياس وحوكمة كل استدعاء ذكاء اصطناعي، بما فيها الواجهات العامة

`partial` · `P1` · البوابة

**Odoo:** هناك ناقل واحد (IAP). الخادم يختار النموذج، والعميل يرسل وسم الاستخدام والأعلام فقط، وكل استدعاء يستهلك رصيداً.

**غيمة:** دورات أداة التضمين تمر عبر ai.gateway.service.process_request (ضوابط + ai.usage.log) بالمعرّف entity_ref ‏'embed:<id>' والميزة 'website_chatbot' ‏(widget.py:340-370)، لكن لا توجد باقة أو ميزانية لـ embed:*، والسجلات مدموجة مع روبوت الموقع. روبوت ghaima.sa يستدعي ab_ai_base مباشرة دون سجل استخدام أو ضوابط أو ميزانية؛ لديه حد معدّل لكل IP ‏(20/دقيقة) وحدود للرسائل والحجم، محفوظة في الذاكرة لكل عامل (main.py:36-85)، والعميل يتحكم في السجل. ‎/api/v1/ai/embed بلا حصة أو حد معدّل أو سجل. التسجيل السريع يستخدم entity_ref مشتركاً دون قياس. يقبل resolve_model_for قيمة model_override للمستأجر دون شرط. ويُتجاهل max_tokens وtemperature ‏(O2). وفي وضع llm_mode الافتراضي 'auto' يرتدّ llm_adapter إلى مفتاح المزوّد الخاص بالمستأجر بعد رفض البوابة (الحصة، الباقة) متى وُجد ai.provider.config نشط (llm_adapter.py:203-215)، فثغرة التجاوز F9 مفتوحة في الوكيل أيضاً لا في scan_docs فقط. ولا يملك call_llm معامل feature؛ إذ تأتي الميزة من واجهة الوكيل ('chat' دون وكيل).

**التوصية:** أولاً، سياسة التوجيه (تُطلق مع G44 في المرحلة 1): في llm_adapter يكون رفض البوابة نهائياً ما لم يوجد اشتراك صريح عبر ICP، ولا يرتدّ إلا عند أخطاء النقل، ويدفع التهيئةُ llm_mode='gateway' إلى المستأجرين المرتبطين؛ وأضف المعامل feature= إلى call_llm. ثم (المرحلة 2): صفوف ميزانية للمنصة بسقوف يومية صارمة بالدولار لـ embed:* وexpress_signup وwebsite_chatbot، مع ميزة مستقلة للتضمين؛ ووجّه روبوت الموقع عبر process_request مع سجل محفوظ على الخادم؛ وقِس ‎/embed؛ وقيّد model_override بفئات النماذج المسموحة في الباقة؛ ومرّر max_tokens وtemperature.

`ai/utils/ai_utils.py#call_odoo_ai_transport` `ai/models/ai_session.py#_get_model_round_options` `saas-share/ab_ai_agent/services/llm_adapter.py#call_llm,_feature_for` `saas-ai/ab_ghaima_ai_embed/controllers/widget.py` `saas-ai/ab_ai_gateway/controllers/gateway_api.py (/embed)` `saas-ai/ab_ghaima_website_chatbot/controllers/main.py` `saas-ai/ab_ai_gateway/models/ai_prompt_template.py#resolve_model_for` `saas-client/ab_scan_docs/models/scan_ai_config.py#call_ai`

### G08 — معرّفات مزوّد صالحة، ومرونة، وكتالوج نماذج واحد، ومخرجات منظّمة

`partial` · `P0` · مزوّدو LLM

**Odoo:** معالجة المزوّدين مركزية على خادم الذكاء الاصطناعي لدى Odoo. يُمرَّر provider_data (مثل تواقيع التفكير) دون تعديل. ومهمة مجدولة (_cron_update_deprecated_embedding_models) تنقل النماذج المهملة. وتوفّر CompletionOptions.schema مخرجات بمخطط JSON.

**غيمة:** كل نموذج Claude يقدّمه ab_ai_base، بما فيه الافتراضي claude-3-5-sonnet-20241022، متقاعد اعتباراً من 2026-10-08 (ai_config.py:105-112؛ والمعرّفات نفسها في token_pricing_data.xml ضمن ab_ai_gateway)، فمزوّد Claude يفشل في كل استدعاء اليوم. كما يرسل ‎_call_claude دائماً temperature، وهو ما ترفضه نماذج Claude الحالية (أي قيمة على Opus 5.5؛ والقيمة الافتراضية فقط على Sonnet وHaiku 5.5). لا إعادة محاولة ولا تراجع تدريجي عند 429/5xx. ويفرض ‎_call_gemini القيمة thinkingBudget=0 لكل نماذج gemini-2.5*، بما فيها مسار الرؤية (ai_service.py:722, :1018)؛ ولم يُتحقَّق مما إذا كان gemini-2.5-pro يقبل ذلك. ولا يُستخدم fallback_provider_id إلا في المركز. لا يوجد معامل لمخطط الاستجابة. والمسار المباشر يتجاهل temperature وmodel_class الخاصين بالوكيل. وأسعار النماذج موزّعة على جدولين: ai.usage.price.book (لدى المستأجر، يُزامَن ليلياً من المركز، ويملك أصلاً model_class وeffective_from/to) وai.token.pricing (مركزي).

**التوصية:** إصلاح عاجل في المرحلة 1: استبدل خيارات Claude وصفوف أسعاره بالمعرّفات الحالية (claude-opus-5-5، claude-sonnet-5-5، claude-haiku-5-5؛ تحقّق منها في وثائق Anthropic عند التنفيذ)، وأوقف إرسال temperature إلى Claude، وانقل قيم ai.provider.config.claude_model المخزّنة. المرحلة 2: إعادة محاولة مع تذبذب عشوائي (429/500/502/503/529، مع احترام Retry-After، ومحاولتان كحد أقصى)؛ أضف deprecated_on وreplacement_model إلى ai.usage.price.book وادمج ai.token.pricing فيه (أو اشتق أحدهما من الآخر) لتقرأ البوابة والمسار المباشر جدولاً واحداً — دون نموذج كتالوج جديد؛ ومهمة مجدولة لفحص الصحة وإعادة الربط على صفوف دليل الأسعار؛ وإعداد تفكير لكل نموذج؛ وresponse_schema لكل مزوّد (json_schema في OpenAI، وresponseSchema في Gemini، وأداة إجبارية في Anthropic)؛ ومرّر temperature (حيث يقبلها النموذج) وmax_tokens وmodel_class في المسار المباشر.

`ai/utils/types.py (CompletionOptions.schema)` `ai/models/ai_embedding.py#_cron_update_deprecated_embedding_models` `ai/utils/ai_fields_tools.py#get_ai_value` `saas-share/ab_ai_base/models/ai_service.py#call,_call_openai,_call_gemini,_call_claude` `saas-share/ab_ai_base/models/ai_config.py (claude_model)` `saas-share/ab_ai_agent/models/ai_usage_price_book.py#_cron_sync_pricebook` `saas-ai/ab_ai_gateway/models/ai_token_pricing.py` `saas-ai/ab_ai_gateway/data/token_pricing_data.xml`

### G09 — تفعيل التخزين المؤقت للتعليمات افتراضياً

`ours_ahead` · `P0` · الأداء / التكلفة

**Odoo:** لم يُعثر على تخزين مؤقت من جهة العميل. التعليمات ثابتة والسياق المتغيّر يُلحق بدور المستخدم، وهو ما يناسب التخزين المؤقت.

**غيمة:** تصميمنا أفضل من Odoo في التخزين المؤقت: بادئة ثابتة، وCACHE_BREAK، وcache_control في Anthropic، وتخزين ضمني في OpenAI وGemini. لكن ab_ai_base.provider_cache_enabled افتراضيه False ولا يضبطه إلا ترحيل 18.0.1.15.0، فتدمج التثبيتات الجديدة تعليمات النظام في رسالة المستخدم. ويُفلتر الملخّص حسب مجموعة المستخدم قبل نقطة الفصل، فتختلف البادئة المخزّنة لكل تركيبة مجموعات.

**التوصية:** اضبط provider_cache_enabled=True عبر بيانات noupdate واعرضه في الإعدادات. انقل أقسام الملخّص المفلترة حسب المجموعة إلى ما بعد CACHE_BREAK، أو خزّن ملخّصاً لكل مجموعة. أضف اختبار تثبيت جديد يتأكد من استخدام دور النظام ومن أن cached_tokens > 0 في الاستدعاء الثاني.

`ai/models/ai_agent.py#_get_instructions` `ai/models/ai_session.py#_get_context_input` `saas-share/ab_ai_agent/services/runtime.py#_compose_system_prompt` `saas-share/ab_ai_base/models/ai_service.py#_provider_cache_enabled` `saas-share/ab_ai_agent/migrations/18.0.1.15.0/post-migrate.py`

### G10 — سجل رسائل محايد تجاه المزوّد (messages[] مع أجزاء tool_call/tool_result)

`partial` · `P1` · حلقة الوكيل

**Odoo:** أجزاء TypedDict ‏(TextPart، InlineDataPart، ToolCallPart، ToolResultPart) تُخزَّن كبيانات وصفية في ai.session.event، مع تمرير provider_data. يعمل RAG في الجولة الأولى فقط. وتمر نتائج الأدوات عبر format_tool_result.

**غيمة:** يبني runtime.run نص تعليمات مستخدم واحداً متنامياً ويُلحق 'Tool result for X: …' مقتطعاً إلى 4000 حرف. وكل خطوة تعيد إرسال تعليمات النظام كاملة مع ذلك النص. ولا تُستخدم كتل tool_result الأصلية للمزوّد (كما يذكر تعليق الشيفرة). وإعادة المحاولات عند MALFORMED_FUNCTION_CALL في Gemini تلتفّ على هذه المشكلة.

**التوصية:** أضف قائمة رسائل (الدور + الأجزاء) إلى ab_ai_base مع محوّل تسلسلي لكل مزوّد: دور tool في OpenAI، وكتل tool_use/tool_result في Anthropic (نقطة تخزين مؤقت عند آخر نتيجة أداة)، وfunctionCall/functionResponse في Gemini. يضيف المركز 'messages_v1' إلى GATEWAY_CAPABILITIES ويقبل messages[] على ‎/analyze و‎/stream؛ ويرسل المستأجر messages[] فقط عندما يكون config.has_capability('messages_v1') صحيحاً وإلا يبقي السجل النصي. أبقِ المسار النصي خلف علم ICP كبديل احتياطي. يُنفَّذ بعد اختبارات عقود المزوّدين وG08.

`ai/utils/types.py` `ai/models/ai_session.py#AiSessionEvent,_submit_agent_request` `saas-share/ab_ai_agent/services/runtime.py#run,_parse_response` `saas-share/ab_ai_base/models/ai_service.py#_tools_for_openai,_tools_for_anthropic,_tools_for_gemini,_parse_anthropic_tool_uses` `saas-ai/ab_ai_gateway/models/ai_gateway_service.py#_clean_tool_schemas,GATEWAY_CAPABILITIES` `saas-client/ab_ai_client/models/ai_client_config.py#has_capability`

### G11 — تشغيلات دائمة تصمد أمام إعادة التشغيل وتُستأنف بعد التوقف

`partial` · `P2` · حلقة الوكيل

**Odoo:** يُحمى ai.session.loop_state ‏(waiting_model/confirmation/answer/client_result/external_result/child) بقيود SQL CHECK. تُرسل الطلبات بعد الالتزام وتُستأنف عبر خطاف ويب موثّق بـ HMAC، مع max_successive_calls=30 وmax_tool_calls_per_call=20. ولا يملك Odoo مراقباً لخطاف ويب مفقود.

**غيمة:** حلقة ReAct متزامنة تعمل داخل عامل HTTP واحد (6 خطوات افتراضياً، حتى 20)، مع إرسال التقدّم على الناقل. اقتراح عملية كتابة ينهي التشغيل؛ وبعد «التأكيد» لا يرى النموذج النتيجة أبداً ولا يستطيع متابعة سلسلة مثل 'أنشئ ثم أرسل بريداً'.

**التوصية:** لا تتبنَّ نموذج خطاف الويب في Odoo، لأننا نستدعي المزوّدين بأنفسنا. احفظ حالة التشغيل (رسائل G10) في ai.agent.run. شغّل المهام الطويلة أو الآلية في الخلفية (ir.cron _trigger، أو خيط عامل بمؤشر جديد كما يفعل باعث البث حالياً) وبُثّ التقدّم عبر الناقل. بعد «التأكيد» ألحِق tool_result واستأنف التشغيل نفسه. أضف مهمة مجدولة رقابية تُفشل التشغيلات العالقة لأكثر من N دقيقة.

`ai/models/ai_session.py#_save_and_submit_request,_continue_agent_loop,_advance_tool_batch` `saas-share/ab_ai_agent/services/runtime.py#run` `saas-share/ab_ai_agent/controllers/agent_chat.py#_make_stream_emitter,action_confirm`

### G12 — أسئلة توضيحية منظّمة (اختيارات، اختيار متعدد، نص حر)

`partial` · `P1` · الإنسان في الحلقة

**Odoo:** تعرض ai_tool_ask_user_question من 2 إلى 4 خيارات مع multi_select وallow_free_text، وتضبط waiting_answer وتُرجع 'USER ANSWER:' إلى النموذج. ويُفرض استخدامها عند بلوغ حد الجولات.

**غيمة:** يُرجع create_record قيمة need_info كقائمة نصية بالحقول الناقصة. ويسأل ab_ai_command عن الالتباس نصياً (MAX_ALTERNATIVES=5). وSuggestionChips موجودة لكنها غير مرتبطة بسؤال معلّق.

**التوصية:** أضف أداة نواة ask_user تُرجع كتلة عرض 'question'. وتنشر شرائحها الإجابة مع question_id كدورة تالية. استخدمها لالتباس المحلِّلات وللحقول الناقصة في create_record، وافرضها عند بلوغ max_hops.

`ai/models/ai_tool.py#_ai_tool_ask_user_question` `ai/static/src/discuss/ai_user_input_request.js` `saas-share/ab_ai_agent/services/agent_actions.py#_required_missing,create_record` `saas-share/ab_ai_command/services/resolvers.py` `saas-share/ab_ai_ui/static/src/ai_response/ai_response.js`

### G13 — مواضيع تُحمَّل عند الطلب لإبقاء التعليمات وقائمة الأدوات صغيرة

`partial` · `P2` · نموذج الوكيل

**Odoo:** تُدرج أسماء المهارات وأوصافها في available_skills. وتضيف ai_tool_load_skills التعليمات والأدوات إلى حالة الجلسة عند الطلب. المهارات من نوع تنفيذي أو إرشادي؛ ولا يمكن تعديل المهارات الأصلية.

**غيمة:** تُرفق المواضيع كاملة في كل تشغيل. ويختار ‎_route_tools مجموعات الأدوات بكلمات مفتاحية عربية وإنجليزية. وتُقلَّص أدوات المُنشئ بالكلمات المفتاحية بعد 8.

**التوصية:** اعرض اسم الموضوع ووصفاً من سطر واحد في البادئة المخزّنة. أضف أداة load_topic تضيف تعليمات الموضوع وأدواته لبقية المحادثة، وأبقِ التوجيه بالكلمات المفتاحية كتلميح جلب مسبق. أعد التسمية داخلياً لتجنّب التعارض مع ai.agent.skill لدينا (قالب تعليمات).

`ai/models/ai_skill.py` `ai/models/ai_tool.py#_ai_tool_load_skills` `ai/utils/ai_utils.py#enable_skills` `saas-share/ab_ai_agent/services/runtime.py#_route_tools,_TOOL_GROUPS` `saas-share/ab_ai_agent/models/ai_agent_topic.py`

### G14 — التفويض بين عدة وكلاء

`missing` · `P3` · نموذج الوكيل

**Odoo:** يفعّل allowed_agent_ids للوكيل أداتَي start_session وcontinue_session. تعمل الجلسات الفرعية بالتوازي، وعمق التداخل أقل من 4، ويدمج ‎_merge_child_result الإجابات والمرفقات.

**غيمة:** يختار المستخدمون شخصية؛ ولا يوجد تفويض.

**التوصية:** يؤجَّل. وإن لزم لاحقاً، أضف أداة ask_agent تستدعي runtime.run مع الوكيل المستهدف بهوية المستخدم نفسه، بعمق ≤2 وميزانية تكلفة مشتركة مع الأصل.

`ai/models/ai_tool.py#_ai_tool_start_session,_ai_tool_continue_session` `ai/models/ai_session.py#_merge_child_result` `saas-share/ab_ai_agent/controllers/agent_chat.py#list_agents` `saas-ai/ab_manager_agents/data/manager_agent.xml`

### G15 — وكلاء يحدّثون إعداداتهم بأنفسهم

`partial` · `P3` · نموذج الوكيل

**Odoo:** تُجري مهارة 'Self Update' في ai_agentic كتابات مؤكَّدة على system_prompt وskill_ids للوكيل، وتنشئ مهارات إرشادية مخصّصة، ويمكنها ربط الوكيل كمُنشئ افتراضي. ويقصر ‎_check_tool_scope هذه الكتابات على نماذج ai.*.

**غيمة:** مُنشئ الكونسول يقوده البشر (يقدّم builder_suggest اقتراحات بالعربية والإنجليزية). ولدى ab_ai_chatbot الأداتان remember_note وremember_fact لذاكرة المستخدم. ويغيّر ab_ai_agent_config إعدادات الأعمال (لا إعداد الوكيل) بعد «تأكيد».

**التوصية:** يؤجَّل. لاحقاً يمكن لأداة remember_procedure مقصورة على المسؤولين إنشاء موضوع is_custom عبر إجراء معلّق.

`ai_agentic/data/ai_skill_data.xml (ai_skill_self_update)` `ai_agentic/models/ai_tool.py#_check_tool_scope` `saas-share/ab_ai_agent/models/ai_agent_builder.py` `saas-client/ab_ai_chatbot/services/tools/memory.py` `saas-share/ab_ai_agent_config`

### G16 — إجراءات الخادم كأدوات، مع التحقق من الوسائط مقابل مخططها

`partial` · `P1` · الأدوات

**Odoo:** يصبح سجل ir.actions.server أداةً بوجود use_in_ai وai_tool_name فريد وai_tool_schema (يُفحص بـ validate_schema). تُتحقَّق وسائط LLM مقابل المخطط قبل التشغيل، في بيئة دون sudo، وتُرجع الشيفرة نتيجتها عبر ai['result'].

**غيمة:** ‏‎_dispatch_server_action موجود ويظهر في نموذج الأداة، لكن لا شيء يزوّده ببيانات أولية أو يختبره، ويستدعي action.run() مع ai_tool_arguments فقط في السياق (دون سجل نشط). فحوص المجموعات موجودة أصلاً: ‏ir.actions.server.run() في Odoo 18 يفرض groups_id ‏(odoo-18/odoo/addons/base/models/ir_actions.py:964-966) وdispatch() يفحص group_ids للأداة عبر is_invocable_by ‏(tool_dispatcher.py:68-70; ai_agent_tool.py:189-196). ولا يُفحص المخطط إلا عند حفظ الأداة؛ ولا يتحقق dispatch() من وسائط النموذج، رغم أن توثيق الوحدة يقول ذلك. وjsonschema غير مُعلن لصورة المستأجر (غائب عن dockerfile/requirements-odoo.txt وrequirements-extra.txt)؛ وهو موجود في saas-venv فقط كاعتمادية لـ openapi-spec-validator.

**التوصية:** تحقّق من الوسائط في dispatch() وأرجِع أخطاء {ok: False} يستطيع النموذج التصرف بناءً عليها. أضف jsonschema إلى dockerfile/requirements-extra.txt وإلى external_dependencies في ab_ai_agent، أو وفّر مدقّقاً مبسّطاً لمجموعة JSON-Schema الفرعية التي نستخدمها. اجعل التأكيد أولاً دائماً لحالات إجراءات الخادم التي تكتب. مرّر السجل النشط (active_model/active_id) عندما تستهدف الأداة سجلاً. أضف مفتاح 'استخدام في ذكاء غيمة' بتسميات عربية، واختبارات.

`ai/models/ir_actions_server.py#_ai_tool_run,_check_ai_tool_schema` `ai/utils/tools_schema/validators.py` `saas-share/ab_ai_agent/services/tool_dispatcher.py#dispatch,_dispatch_server_action` `saas-share/ab_ai_agent/models/ai_agent_tool.py#as_llm_schema,is_invocable_by` `dockerfile/requirements-extra.txt`

### G17 — تشكيل العرض الحالي للمستخدم (الفلاتر، التجميعات، المقاييس)

`partial` · `P1` · الأدوات

**Odoo:** أدوات من جهة المتصفح: do_action وshow_view وadjust_view. وتطبّق ai_tool_adjust_search نطاقاً وفلاتر وتجميعاً عبر SearchModel.applyAISearch، وتضبط الرقع مقاييس pivot وgraph. ويرسل WithSearch.getCurrentViewInfo النطاق والفلاتر الحالية في كل دورة.

**غيمة:** يرسل واصف الشاشة أصلاً نطاق البحث والتجميعات والفلاتر، ويُتحقَّق منها على الخادم (ai_screen_context.py:103-113، و_domain_ok في :166؛ screen_context_service.js:156-157). وتفتح open_list وopen_pivot وopen_graph أصلاً عروضاً مفلترة أو مجمّعة بالمقاييس المختارة (tool_dispatcher.py:236-330). الفجوات: (1) أدوات open_* تكتفي بـ literal_eval لنطاق النموذج دون التحقق من الحقول؛ (2) لا يستطيع الوكيل تعديل العرض المفتوح في مكانه.

**التوصية:** (1) مرّر نطاقات open_* وتجميعاتها ومقاييسها عبر ai.screen.context._domain_ok وfields_get بصلاحيات المستخدم. (2) أضف توجيه 'adjust' اختيارياً للتعديل في المكان يطبّقه العميل على SearchModel الحالي (تحقّق من واجهة SearchModel في Odoo 18 أولاً)، مع تعقيمه كما في navigate.

`ai/models/ai_tool.py#_ai_tool_adjust_search,_ai_tool_open_menu_list` `ai/static/src/core/web/search_model_patch.js` `ai/static/src/core/web/with_search_patch.js` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_open_list,_builtin_open_pivot,_builtin_open_graph` `saas-share/ab_ai_agent/models/ai_screen_context.py#_domain_ok` `saas-share/ab_ai_agent/static/src/services/screen_context_service.js` `saas-share/ab_ai_agent/static/src/services/ai_navigator_service.js#sanitizeDirective`

### G18 — التأصيل بالبحث على الويب مع الاستشهادات

`missing` · `P2` · الأدوات / RAG

**Odoo:** تُجري ‎_ai_tool_web_search استدعاءً متداخلاً مؤصَّلاً (أنماط fact وsummary وdeep). تُخزَّن المصادر تحت معرّفات uuid وتُعرض من استشهادات [WEB_SOURCE:uuid]. يمكن تفعيلها لكل جلسة وتُعطَّل عند حصر الإجابات في المصادر. ولا تزور أبداً روابط يقدّمها المستخدم.

**غيمة:** هيكل أوّلي فقط: العلم allow_web_grounding وعمود العدّاد web_grounding_calls.

**التوصية:** نفّذها على البوابة المركزية كميزة 'web_search'، باستخدام أداة التأصيل أو البحث لدى المزوّد (تحقّق من أسماء الواجهات الحالية)، لتبقى المفاتيح مركزية ويُقيَّد الاستخدام بالباقة. أضف أداة web_search لدى المستأجر، وكتلة SourceList في ab_ai_ui، وسياسة إجابة بالعربية. لا تجلب أبداً روابط يقدّمها المستخدم.

`ai/models/ai_tool.py#_ai_tool_web_search` `ai/utils/ai_citation.py#apply_web_citations` `saas-share/ab_ai_agent/models/ai_agent.py (allow_web_grounding)` `saas-share/ab_ai_agent/models/ai_usage_local_log.py (web_grounding_calls)`

### G19 — توليد الصور وتحريرها

`missing` · `P3` · الأدوات

**Odoo:** تأخذ ai_tool_generate_image نسبة أبعاد وصوراً مرجعية وتنشئ مرفقات متتبَّعة للتنظيف. تُستخدم في نافذة الوسائط وأغلفة Knowledge والمنتجات ومنشورات التواصل الاجتماعي.

**غيمة:** لا يوجد.

**التوصية:** يؤجَّل. لاحقاً أضف ميزة البوابة 'image' ورقعة لنافذة الوسائط في ab_ai_composer، أساساً لصور قوائم المطاعم والمنتجات.

`ai/models/ai_tool.py#_generate_image_attachments` `ai/models/ai_attachment_vacuum.py` `-`

### G20 — مصادر معرفة لكل وكيل: الإدخال، والتضمينات، والاسترجاع، والاستشهادات

`partial` · `P1` · RAG / المعرفة

**Odoo:** يغطي ai.agent.source الملفات والروابط ومقالات Knowledge وDocuments (شجرة، حالة، is_active). يقسّم ai.embedding.mixin النص عبر chunk_text (~2000 حرف). ومهمة مجدولة مُحفَّزة تضمّن على دفعات (100 صف / ~10 آلاف رمز) وتزيل التكرار بالمجموع الاختباري. المتجهات pgvector(1536) مع فهرس HNSW. تُضاف أفضل 5 أجزاء في الجولة الأولى. ويحصر restrict_to_sources الإجابات. وتُفلتر استشهادات [SOURCE:id] بـ user_has_access. ويحافظ التنظيف التلقائي ومهمة النماذج المهملة على الفهرس.

**غيمة:** ‏semantic_index في ab_ai_base ‏(provision، embed_records، search؛ HNSW أو بديل JSON؛ Gemini بـ 768 بُعداً)، لكن لا يجهّزه أي نموذج. يُجري ai.chat.fact بحثاً هجيناً بـ pgvector والتطابق الثلاثي. والملخّص الليلي يقدّم البنية فقط. وkb_search وkb_read يطابقان الكلمات ببساطة (kb_tools.py:26, :42) على 10 حزم ab_knowledge_base_* منسّقة (~93 سجلاً بالعربية والإنجليزية). والاستشهادات هيكل أوّلي لأن source_lookup لا يُمرَّر أبداً. وحارس الروابط في ghaima_base لا يسمح إلا بـ ghaima.sa ‏(ghaima_base.py:58) ويحلّ DNS بمعزل عن requests.get اللاحق (:120-136)، فلا يصلح لخدمة روابط العملاء.

**التوصية:** وحدة جديدة ab_ai_knowledge ‏(saas-share) تضم ai.agent.source وai.agent.chunk على semantic_index. أنواع المصادر بالترتيب: مقالات قاعدة المعرفة أولاً (تضمين حزم ab_knowledge_base_* عبر الفهرس الهجين، مع ab_knowledge_base_ai كجسر)، ثم المرفقات (index_content؛ نص PDF عبر pdfminer.six)، ثم الروابط عبر حارس جديد قابل للتهيئة في ab_ai_base: ‏https فقط، والمنفذ 443، دون بيانات مستخدم في الرابط، وعنوان IP قابل للتوجيه عالمياً، والاتصال بالعنوان الذي حُلّ مسبقاً، دون إعادة توجيه، مع حدود للحجم ونوع المحتوى؛ وللمسؤولين فقط. ويبقي ghaima_base قائمة السماح الثابتة لمقتطف الموقع المقفل. ضمّن عبر ‎/embed المقيس في البوابة (G07). استرجع بصلاحيات المستخدم مع فلترة حسب الوصول لكل مصدر. أضف restrict_to_sources وتبويب «المعرفة» واربط citation.apply_numeric_citations. معيار القبول: الاستدعاء العربي recall@5 على مجموعة أسئلة من قاعدة المعرفة.

`ai/models/ai_agent_source.py` `ai/models/ai_embedding.py#_get_similar_chunks,_cron_generate_embedding` `ai/models/ai_embedding_mixin.py` `ai/models/ai_agent.py#_build_rag_context,_get_llm_response_with_sources` `ai_knowledge/models/ai_agent_source.py` `saas-share/ab_ai_base/models/semantic_index.py#provision,embed_records,search` `saas-share/ab_ai_base/services/embeddings.py` `saas-client/ab_ai_chatbot/models/chat_fact.py` `saas-share/ab_ai_agent/services/citation.py` `saas-share/ab_ai_agent/services/ghaima_base.py#_check_url,_fetch_text` `saas-theme/ab_knowledge_base_ai/models/kb_tools.py`

### G21 — جلسات مخزّنة في النواة، مع سجل منظّم وتلخيص

`partial` · `P1` · الذاكرة / الجلسات

**Odoo:** يخزّن ai.session وai.session.event كل جولة بصيغة الأجزاء، مرتبطة بقناة Discuss من نوع ai_chat. يقترح Odoo محادثة سابقة للسجل والواجهة نفسيهما، ويضع عناوين تلقائية للمحادثات، ولديه تبويب AI في قائمة المراسلة، وينظّف المحادثات الخاملة منذ 30 يوماً.

**غيمة:** المحادثات موجودة فقط عند تثبيت saas-client/ab_ai_chatbot (بالتحقق من السلوك)؛ وإلا فالمحادثة بلا حالة. السجل هو آخر 6 رسائل كنص عادي (≤3000 حرف)، ولا يُلخَّص أبداً في مسار الوكيل. وذاكرة المستخدم اختيارية (≤1500 حرف).

**التوصية:** أضف ai.agent.session وai.agent.session.message إلى ab_ai_agent، مع تخزين envelope_json وحقل JSON للأجزاء قابل للفراغ حتى لا ينتظر G10. انقل ai.chat.conversation في ab_ai_chatbot ليحتفظ بالواجهات ويفوّض التخزين. لخّص السجل بفئة نموذج منخفضة التكلفة متى تجاوز ميزانية الرموز. واربط الجلسات بالسجلات.

`ai/models/ai_session.py` `ai/models/discuss_channel.py` `ai/controllers/messaging_menu.py` `saas-share/ab_ai_agent/controllers/agent_chat.py#conversation_*` `saas-client/ab_ai_chatbot/models/ai_chat.py#_send_via_agent_runtime,find_or_create_for_record` `saas-share/ab_ai_agent/services/runtime.py#_user_memory_block`

### G22 — الاحتفاظ بالتشغيلات وسجلات الاستخدام

`missing` · `P0` · الخصوصية / البيانات

**Odoo:** يحذف التنظيف التلقائي محادثات الذكاء الاصطناعي الخاملة منذ 30 يوماً أو الفارغة منذ يوم واحد؛ وينظّف ‎_gc_sources_targets وتنظيف المرفقات الباقي. وبيانات الجلسات مقروءة للمسؤولين فقط.

**غيمة:** صفوف ai.agent.run (حتى 60 ألف حرف من تعليمات النظام، و30 ألفاً من السياق، و50 ألفاً من JSON الأدوات مع بيانات العملاء) وai.usage.local.log تُحفظ إلى الأبد. أما الإجراءات المعلّقة فتُنظَّف بعد 90 يوماً، وهذا جيد.

**التوصية:** أضف ‎@api.autovacuum يفرّغ system_prompt وretrieved_context وtool_calls_json بعد N يوماً (ICP، افتراضياً 30) ويحذف التشغيلات بعد 180 يوماً، مع الإبقاء على الإحصاءات المجمّعة. احذف سجلات الاستخدام الأقدم من M يوماً بعد مطابقتها وتجميعها. ووثّق ذلك كموقف الاحتفاظ وفق نظام حماية البيانات الشخصية (PDPL).

`ai/models/discuss_channel.py (autovacuum)` `ai/models/ai_agent_source.py#_gc_sources_targets` `saas-share/ab_ai_agent/models/ai_agent_run.py` `saas-share/ab_ai_agent/models/ai_usage_local_log.py` `saas-share/ab_ai_agent/models/ai_agent_pending_action.py#_gc_old_proposals`

### G23 — شرائح تعليمات لكل نموذج وحزم تعليمات لكل تطبيق

`partial` · `P1` · واجهات المستخدم

**Odoo:** يحمل ai.prompt.button تعليمات QWeb تُعرض مع السجل ويُظهر 3 منها عشوائياً، مع إخفاء تعليمات سجل المحادثات على النماذج التي لا تدعمه. حزم بيانات فقط لكل تطبيق: ai_sale وai_sale_margin وai_sale_stock وai_purchase وai_stock وai_project وai_calendar (التحضير للاجتماعات) وai_account ('Show me the current cash flow status')، إضافة إلى تعليمات عامة لسجل المحادثات (ai_prompt_summarize_chatter، ai_prompt_write_followup_chatter/_composer).

**غيمة:** يملك ai.agent.skill أصلاً context_model وsurfaces (بما فيها سجل المحادثات) وrequires_record_context ‏(ai_agent_skill.py:62-80)، ويستخدمها المُنشئ والكونسول ومتحكم المحادثة؛ والقوالب تستخدم عناصر نائبة بـ str.format_map. بطاقات المهارات ونقاط البدء في الكونسول مستمدة من قوائم المستخدم وأوامره. الناقص: شرائح لكل نموذج في لوحة سجل المحادثات، وحزم لكل تطبيق، وتعليمات التقويم وتلخيص سجل المحادثات والمتابعة.

**التوصية:** فلتر شرائح سجل المحادثات والمساعد العائم على context_model الموجود مع surfaces؛ وإن لزم دعم نماذج متعددة، حوّل context_model إلى Many2many في خطوة واحدة بدلاً من إضافة حقل موازٍ. أطلق حزم بيانات فقط تُثبَّت تلقائياً بتعليمات عربية: ab_ai_agent_sale و_purchase و_stock و_account و_pos و_project و_calendar (الاجتماعات، الحجوزات، المواعيد) و_hr ‏(saas-share). وأضف مهارتين عامتين: 'لخّص سجل المحادثات' و'صُغ متابعة'.

`ai/models/ai_prompt_button.py#_render_prompt` `ai_sale/data/ai_prompt_button_data.xml` `ai_account/data/ai_prompt_button_data.xml` `ai_calendar/data/ai_prompt_button_data.xml` `ai/data/ai_composer_data.xml` `saas-share/ab_ai_agent/models/ai_agent_skill.py#render_prompt` `saas-share/ab_ai_agent/models/ai_agent_builder.py` `saas-share/ab_ai_agent/static/src/web/chatter_patch.js` `saas-share/ab_ai_agent/static/src/components/ai_agent_chat/ai_agent_chat.js`

### G24 — الذكاء الاصطناعي في المحرر ومُنشئ البريد (صياغة، إعادة كتابة، ترجمة) عبر بوابتنا

`partial` · `P0` · واجهات المستخدم

**Odoo:** تغطي مفاتيح واجهة ai.composer كلاً من html_field_record وmail_composer وhtml_field_text_select وغيرها. يفتح ChatGPTPlugin محادثة ذكاء اصطناعي على حقل أو تحديد، مع 'Use this' و'Send as Message' و'Log as Note'. وتُستخدم أداة mail_composer_chatgpt في معالج إرسال الفاتورة ورسائل رفض التوظيف والتوقيع. وتُقيَّم كتل ‎/prompt في قوالب البريد عند عرض الرسالة.

**غيمة:** جزئي: الواجهة الأصلية موجودة لكنها موجّهة إلى Odoo IAP. نوافذ ChatGPT والترجمة والبدائل في Odoo 18 CE تستدعي أسلوب متحكم واحداً يخدم ‎/html_editor/generate_text و‎/web_editor/generate_text، ويرسل التعليمات وdatabase.uuid إلى web_editor.olg_api_endpoint المحدد في ICP ‏(html_editor/controllers/main.py:543-549). وأداة mail_composer_chatgpt على نصوص mail.compose.message وmail.scheduled.message تفتح النافذة نفسها (mail_compose_message_views.xml:84; mail_scheduled_message_views.xml:37). وبشكل منفصل، يستدعي معالج إعداد الموقع website._OLG_api_rpc('/api/olg/1/generate_placeholder') مع database.uuid والقطاع واللغة (website.py:48, :480-482, :862). ولا شيء في saas-*/ghaima-api يعيد تعريف أيٍّ من المسارين، فالحركة غير مقيسة وتحمل علامة Odoo التجارية وتغادر منصتنا. ولا صياغة مدركة للسجل.

**التوصية:** المرحلة 1 (ساعات): ادفع web_editor.olg_api_endpoint وwebsite.olg_api_endpoint إلى نقطة معطّلة أو مركزية لكل مستأجر عبر لوحة التحكم (cockpit)، واضبطهما عند التهيئة. المرحلة 3: ترث ab_ai_composer ‏(saas-share) أسلوب generate_text — إعادة تعريف واحدة تغطي المسارين ونافذتَي الترجمة والبدائل — وتوجّهه عبر llm_adapter بالميزة 'compose' بلغة المستخدم؛ وأزل العلامة التجارية من تسميات النافذة. ثم أضف سياق السجل إلى مُنشئ البريد الأصلي وإجراء صياغة في account.move.send.wizard (النص widget=html_mail، account_move_send_wizard.xml:50)؛ ولا إرسال تلقائي أبداً. معيار القبول يحاكي iap_jsonrpc وwebsite._OLG_api_rpc معاً، أو يستثني معالج الإعداد صراحةً.

`ai/static/src/editor/plugins/chatgpt_plugin.js` `ai/static/src/mail_composer_chatgpt.js` `ai/models/mail_render_mixin.py#_render_template` `ai_account/wizard/account_move_send_wizard.xml` `hr_recruitment_ai/wizard/applicant_refuse_reason_views.xml` `odoo-18/addons/html_editor/controllers/main.py#generate_text` `odoo-18/addons/html_editor/static/src/main/chatgpt/` `odoo-18/addons/mail/static/src/core/web/mail_composer_chatgpt.js` `odoo-18/addons/website/models/website.py#_OLG_api_rpc` `odoo-18/addons/account/wizard/account_move_send_wizard.xml`

### G25 — 'اسأل الذكاء الاصطناعي' في لوحة الأوامر وشريط النظام

`partial` · `P2` · واجهات المستخدم

**Odoo:** زر ذكاء اصطناعي في شريط النظام (يفتح مُنشئ سجل المحادثات في عرض النموذج). ويرتدّ Ctrl+K إلى 'Ask AI' عند عدم وجود تطابق، و'@' يبحث في الوكلاء.

**غيمة:** زر عائم (ab_ai_chatbot)، وإجراء عميل للكونسول، وزر في سجل المحادثات. لا شيء في لوحة الأوامر.

**التوصية:** سجّل command_provider في ab_ai_agent يعرض 'اسأل ذكاء غيمة: <الاستعلام>' كخيار احتياطي ويسرد أوامر الشرطة المائلة من ab_ai_command، بالعربية والإنجليزية.

`ai/static/src/core/web/command_palette.js` `ai/static/src/web/systray_action.js` `ai_agentic/static/src/command_palette.js` `odoo-18/addons/web/static/src/core/commands/default_providers.js (command_provider registry)` `saas-client/ab_ai_chatbot/static/src/assistant/assistant.js` `saas-share/ab_ai_command/static/src/command_palette.js`

### G26 — وكيل ذكاء اصطناعي على قنوات المحادثة المباشرة والموقع وصندوق وارد التواصل الاجتماعي، مع التحويل لموظف

`partial` · `P2` · واجهات المستخدم

**Odoo:** يضبط ai_livechat الحقل ai_agent_id على قواعد قنوات im_livechat، ويضيف تعليمات مسبقة للمحادثة المباشرة ومسار forward_operator للتحويل لموظف. ويضيف ai_crm_livechat أداة إنشاء عملاء محتملين. ويعرض ai_website_livechat بطاقات معاينة. ويشغّل ai_social وكيلاً على الرسائل الخاصة في التواصل الاجتماعي مع أداة تحويل لموظف وثلاثة شروط تفعيل: دائماً، فقط عند عدم توفر موظف، فقط عند توفر موظف.

**غيمة:** روبوت مبيعات ghaima.sa المركزي يستدعي المزوّد مباشرة (دون سجل استخدام أو ضوابط أو ميزانية)، ويعرض الردود عبر innerHTML ‏(G03)، ويترك للعميل التحكم في السجل؛ ولديه حدود معدّل لكل IP وحدود للرسائل محفوظة لكل عامل. ودورات أداة التضمين مسجّلة وتخضع للضوابط عبر process_request لكن بلا ميزانية أو باقة (G07). لا يملك أيٌّ منهما بيانات ERP أو تحويلاً لموظف. ولا يملك المستأجرون ذكاءً اصطناعياً للمحادثة المباشرة أو الموقع أو صندوق وارد التواصل الاجتماعي؛ وواتساب صادر فقط (saas-hr/ab_whatsapp_notify).

**التوصية:** قائمة الانتظار بعد المرحلة 4. وحدة جديدة مستقلة عن القناة ab_ai_livechat في saas-share (قابلة للتثبيت على المركز والمستأجرين): وكيل لكل قناة بشروط تفعيل (دائماً، عند عدم توفر موظف متصل، عند توفر موظف متصل)، ومجموعة أدوات آمنة للعموم (المنتجات والقائمة المنشورة، وساعات العمل، والحجوزات)، وأداة تحويل لموظف، ونصوص المحادثات، وميزانية. الجسور: ab_ai_livechat_crm (مسودات عملاء محتملين)، وab_ai_livechat_website_sale (بطاقات المنتجات)، ولاحقاً محوّل واتساب وارد، وهو الأهم لاستفسارات المطاعم وحجوزاتها. وأعد بناء روبوت ghaima.sa عليها.

`ai_livechat/models/im_livechat_channel_rule.py` `ai_livechat/controllers/main.py#forward_operator` `ai_crm/data/ir_actions_server_tools.xml` `ai_website_livechat/models/ai_preview_card_mixin.py` `ai_social/models/ai_agent.py#_ai_tool_social_livechat_add_human` `ai_social/models/im_livechat_channel.py` `saas-ai/ab_ghaima_website_chatbot/controllers/main.py` `saas-ai/ab_ghaima_ai_embed/controllers/widget.py` `saas-hr/ab_whatsapp_notify` `odoo-18/addons/im_livechat`

### G27 — مُنشئ مواقع بالذكاء الاصطناعي (توليد الصفحات، هوية العلامة، تحسين محركات البحث، نماذج الويب)

`missing` · `P3` · حسب التطبيق: الموقع

**Odoo:** يقدّم ai_website وكلاء Website Page Generator وBuilder وReviewer، وهوية علامة تجارية، ومُنشئاً مساعداً لتحسين محركات البحث، وأدوات نماذج ويب، ومقاطع، وبحثاً عن الصور، واستخلاص الصفحات. ويضيف ai_website_sale محتوى المنتجات.

**غيمة:** لا شيء لمواقع المستأجرين.

**التوصية:** يؤجَّل. ابدأ بصياغة بيانات SEO الوصفية وأوصاف المنتجات عبر ab_ai_composer.

`ai_website/models/ai_website_service_brand_kit.py` `ai_website/models/ai_tool_webform.py` `ai_website/data/website_ai_agent.xml` `saas-erp/ghaima/ab_ghaima_website_theme`

### G28 — نسخ التسجيلات والإملاء (نتفوّق في الصوت المباشر)

`ours_ahead` · `P3` · الصوت

**Odoo:** تحويل الصوت إلى نص في المُنشئ (/ai/transcription). وإملاء مباشر في المحرر عبر رمز مؤقت لـ OpenAI realtime. ونسخ تسجيلات المكالمات (mail.call.artifact مع حجز وقارن-وبدّل). وملخصات مكالمات voip_ai.

**غيمة:** تحويل الكلام إلى نص والنص إلى كلام في المتصفح أو الخادم، ووضع بدون استخدام اليدين، وتأكيد وإلغاء صوتي، وتحويل Gemini للنص إلى كلام بالعربية، وقياس بالثواني، وتقييد بالباقة. لا إملاء في الحقول ولا نسخ أو تلخيص للتسجيلات.

**التوصية:** لاحقاً أضف زر إملاء في ab_ai_composer يعيد استخدام ServerStt، و'ملاحظة اجتماع من تسجيل صوتي' (رفع، نسخ عبر البوابة، تلخيص، اقتراح ملاحظة في سجل المحادثات).

`ai/controllers/ai.py#transcribe` `ai/models/mail_call_artifact.py#action_transcribe_gevent` `voip_ai/models/voip_call.py` `saas-share/ab_ai_agent/static/src/voice/voice.js` `saas-share/ab_ai_agent/controllers/voice.py`

### G29 — استخراج المستندات عبر مسار سياسات موحّد

`ours_ahead` · `P0` · المستندات / OCR

**Odoo:** يفرز ai_documents المجلدات بالتعليمات (أدوات النقل والوسم وإعادة التسمية، وحد 5 صفحات لملفات PDF، ومهمة مجدولة دفعية لأسماء البريد المستعارة). ويحوّل ai_documents_account إنشاء فواتير الموردين إلى أدوات. ويرسل ir.attachment._ai_read ملفات PDF مضمّنة ويصغّر الصور إلى 1024 بكسل كحد أقصى.

**غيمة:** يستخدم ab_scan_docs الرؤية الحاسوبية لإنشاء فواتير العملاء والموردين والإشعارات الدائنة وأوامر البيع والشراء وعمليات النقل والمدفوعات، مع بوابات للطيار الآلي (الثقة، الإجماليات، التكرار، النوع) و32 اختباراً؛ ونحن متقدمون هنا. الأخطاء: يستدعي call_ai الدالة get_config() خارج كتلة try، فالمستأجرون بلا صف بوابة نشط (FAYIAPROD) لا يصلون أبداً إلى البديل المباشر؛ وبعد رفض الحصة يرتدّ إلى مفتاح المستأجر الخاص (وكذلك يفعل llm_adapter في وضع 'auto'، ‏G07)؛ ويتجاهل llm_mode وقاطع الدائرة. ومن بين وحدات الذكاء الاصطناعي لا يعتمد إلا على ab_ai_ui، لا على ab_ai_agent. والقيمة autopilot_terminal='post' تتيح للأتمتة ترحيل الفواتير، وهو اشتراك اختياري للمسؤول يتعارض مع قاعدة المسودات فقط. ويُجمَع correction_log ‏(scanned_document.py:438، ويُكتب عند ~:1434) لكنه يُعرض فقط ولا يُستفاد منه.

**التوصية:** اعتمد سياسة توجيه llm_adapter من G07 (الرفض نهائي، ولا ارتداد إلا عند الانقطاع)، ثم وجّه scan_docs عبر call_llm(feature='scan_docs')، إما بإضافة اعتمادية على ab_ai_agent أو بنقل دالة الحلّ إلى ab_ai_base أو ab_ai_client. لا تسمح بقيمة 'post' للطيار الآلي إلا إذا ضبطها مدير حسابات، مع تسجيلها. استخدم correction_log كأمثلة تعلّم قليلة لكل مورد. واعرض أداة وكيل scan_document تُرجع إجراءً معلّقاً.

`ai_documents/models/ir_actions_server.py#_ai_action_run` `ai/models/ir_attachment.py#_ai_read` `saas-client/ab_scan_docs/models/scan_ai_config.py#call_ai,autopilot_terminal` `saas-client/ab_scan_docs/models/scanned_document.py#_run_autopilot,_autopilot_finalize,correction_log` `saas-client/ab_scan_docs/__manifest__.py`

### G30 — حقول تُملأ بتعليمات الذكاء الاصطناعي

`missing` · `P2` · حقول الذكاء الاصطناعي

**Odoo:** يمكن ضبط تعليمات ai= على حقل Python أو على ir.model.fields أو على تعريف خاصية. ومهمة مجدولة يومية (ir.model.fields._cron_fill_ai_fields) تملأ قيم char وtext وHTML الفارغة؛ ويملأ إنشاء الحقل آخر 50 سجلاً؛ وتُخزَّن الإخفاقات كقيم فارغة. ولكل نوع حقل زر عند الطلب (get_ai_field_value) يُرجع مخرجات منظّمة مع قيم معدّدة لـ selection وm2o وm2m، مع تفعيل البحث على الويب. ويضيف web_studio_ai_fields ذلك إلى Studio.

**غيمة:** لا يوجد.

**التوصية:** وحدة جديدة ab_ai_fields ‏(saas-share): الحقلان ai_prompt وai_enabled على ir.model.fields، وأداة حقل OWL 'املأ بالذكاء الاصطناعي' تقترح قيمة يقبلها المستخدم (تُكتب بصلاحياته). ومهمة مجدولة دفعية تملأ القيم الفارغة ضمن ai.usage.local.budget وسقف لكل تشغيل. تعتمد على المخرجات المنظّمة (G08). وتعليمات عربية.

`ai_fields/models/models.py#_fill_ai_field,get_ai_field_value` `ai_fields/models/ir_model_fields.py#_cron_fill_ai_fields` `ai/utils/ai_fields_tools.py#get_ai_value,parse_ai_response` `-`

### G31 — نوع إجراء خادم بالذكاء الاصطناعي و'التحديث بالذكاء الاصطناعي'

`missing` · `P2` · الأتمتة

**Odoo:** حالة 'ai' في ir.actions.server: تعليمات HTML مع رموز ‎/field، وai_tool_ids على النموذج نفسه، وAI_ACTIONS_PROMPT (غير تحاوري، يتجاهل التعليمات الموجودة في المستندات). تُسجَّل استدعاءات الأدوات في سجل المحادثات (ai.ai_log_action) مع الوكيل كمؤلف للتتبع. ويضيف ai_server_actions القيمة evaluation_type 'ai_computed' ‏('Update with AI') إلى object_write.

**غيمة:** لا يوجد. ملاحظة للتصميم: المهمة المجدولة في base.automation ليس لها user_id، فتعمل بهوية __system__ ‏(base_automation_data.xml:4-6; ir_cron.py:358, :414)، وuid بقيمة SUPERUSER_ID يعني su=True ‏(odoo-18/odoo/api.py:572-573).

**التوصية:** وحدة جديدة ab_ai_server_actions ‏(saas-share؛ تعتمد على base_automation وab_ai_agent): أضف حالة عبر selection_add مع مستخدم مالك صريح (res.users، وليس المستخدم الأعلى أبداً). شغّل runtime.run دون واجهة مع env(user=owner, su=False)، وارفض التشغيل عندما يكون env.su أو uid == SUPERUSER_ID. استخدم قائمة سماح صريحة للأدوات، وفقط الأدوات الموسومة automation_safe (لا ترحيل ولا تأكيد للمحاسبة أبداً). سجّل كل تشغيل في سجل المحادثات مرتبطاً بـ ai.agent.run. وأضف تقييماً بنمط 'ai_computed' على object_write باستخدام ab_ai_fields.

`ai/models/ir_actions_server.py#_ai_action_run,AI_ACTIONS_PROMPT` `ai_server_actions/models/ir_actions_server.py#_run_action_object_write` `odoo-18/addons/base_automation/data/base_automation_data.xml` `odoo-18/odoo/addons/base/models/ir_cron.py`

### G32 — وكلاء تُطلقهم الأحداث أو الجداول الزمنية، مع صندوق وارد للتشغيلات

`missing` · `P2` · الأتمتة

**Odoo:** ‏base.automation.ai_agent_id مع تعليمات HTML ينشئ إجراء ذكاء اصطناعي فرعياً. ويعيد ai.automation.trigger استخدام محفّز التاريخ لتشغيل الجداول، ويتقدّم التاريخ التالي حتى عند فشل التشغيل. لكل تشغيل قناته الخاصة مع auto_confirm وصندوق وارد 'Automation' للمسؤول، إضافة إلى 'Run now'. ويمكن للوكلاء إنشاء أتمتتهم الخاصة عبر أداة مؤكَّدة. وai_agentic اختيارية.

**غيمة:** مهام مجدولة ثابتة فقط (التقرير اليومي ai.report، والملخّص). Manager Bot بلا جدول زمني. والمستدعون المجدولون يرسلون الميزة 'custom'.

**التوصية:** وحدة جديدة ab_ai_agent_automation ‏(saas-share). يحمل ai.agent.automation الوكيل، والمحفّز (جدول زمني، إنشاء، تعديل، تاريخ)، والنموذج، والنطاق، والتعليمات، والمستخدم المالك، وطريقة التسليم (ملاحظة في سجل المحادثات، صندوق وارد، بريد). يعمل بهوية المالك مع su=False، وليس المستخدم الأعلى أبداً، ضمن ميزانية لكل قاعدة، ويقدّم التشغيل التالي حتى عند الفشل. تتحول عمليات الكتابة إلى إجراءات معلّقة للمالك؛ ولا شيء يُعتمد تلقائياً. وأضف تبويب «الأتمتة» في الكونسول مع «تشغيل الآن».

`ai_agentic/models/base_automation.py#_is_schedule_automation,action_ai_run_now` `ai_agentic/models/ai_automation_trigger.py#_advance_next_trigger_date` `ai_agentic/models/ir_actions_server.py#_ai_action_run_agent` `saas-client/ab_ai_client/models/report_generator.py#cron_generate_reports` `saas-ai/ab_manager_agents/data/manager_skills.xml`

### G33 — خادم MCP لعملاء الذكاء الاصطناعي الخارجيين

`missing` · `P2` · التشغيل البيني

**Odoo:** ‏ai_mcp: ‏POST /mcp ‏(auth='bearer'، bearer_scope='mcp') يعالج initialize وping وtools/list وtools/call. وuse_in_mcp على إجراءات الخادم؛ و5 أدوات للقراءة فقط افتراضياً. وأداة سياق أوّلي تحقن المنطقة الزمنية والمستخدم والشركة النشطة، لأن عميل MCP لا يملك عميل ويب. وتكتسب مفاتيح API نطاق 'mcp'. وخادم OAuth 2.1 كامل: ‏PKCE S256، وتسجيل ديناميكي للعملاء، وقائمة سماح للعملاء، وشاشة موافقة، وإلغاء.

**غيمة:** يملك ab_api_base رموز وصول JWT، وregister_scope_validator، و‎@api_route، وOpenAPI/Swagger على ‎/api/v1/docs. ولدى ab_mobile_ai_api نمط محدِّد للمعدّل. لا يوجد MCP. ولا يملك ‎_auth_method_bearer في Odoo 18 معامل نطاق (يفحص دائماً المفتاح العام 'rpc').

**التوصية:** وحدة جديدة ab_ai_mcp ‏(saas-share؛ تعتمد على ab_ai_agent وab_api_base): نقطة JSON-RPC خلف مدقّق نطاق 'mcp' تعرض سجلات ai.agent.tool الموسومة mcp_enabled (للقراءة فقط افتراضياً) عبر tool_dispatcher.dispatch بهوية مستخدم الرمز. أضف أداة سياق أوّلي (المنطقة الزمنية، الشركة، ملاحظة UTC)، وحد معدّل لكل رمز على نمط rate_limiter، وسجلات استخدام تحت الفئة 'mcp' (استدعاءات الأدوات تصل إلى قاعدة البيانات حتى دون استدعاء LLM). وتُرجع أدوات الكتابة رابط إجراء معلّق للتأكيد داخل غيمة. اشتراك اختياري لكل شركة مع سجل تدقيق. وينتقل OAuth 2.1 والتسجيل الديناميكي للعملاء إلى قائمة الانتظار.

`ai_mcp/controllers/mcp_controller.py#handle_mcp_request` `ai_mcp/models/ai_mcp_request_dispatcher.py#_mcp_tools_list,_mcp_tools_call` `ai_mcp/models/ai_tool.py#_ai_tool_mcp_retrieve_initial_context` `ai_mcp/models/res_users_description.py` `ai_mcp/controllers/oauth_server_controller.py` `saas-share/ab_api_base/controllers/api.py#_auth_token,register_scope_validator,api_route` `ghaima-api/ab_mobile_ai_api/controllers/rate_limiter.py` `odoo-18/odoo/addons/base/models/ir_http.py#_auth_method_bearer`

### G34 — أدوات وكيل للتقارير المحاسبية، ورؤى تقارير تعمل فعلاً

`partial` · `P1` · حسب التطبيق: المحاسبة

**Odoo:** أدوات ai_account_reports: ‏accounting_report_list وdescribe وselect وget_values وexpand_line وopen، مع قيم مقسّمة إلى صفحات وإعدادات تقارير محفوظة في حالة الجلسة. مهارة 'Accounting Report Analysis'. ووكيلا Auditor وAudit Reviewer مع ملفات عمل التدقيق وفحوص الدورات. ويضيف ai_account تعليمات للتدفق النقدي وصياغة بالذكاء الاصطناعي في account.move.send.wizard.

**غيمة:** ‏ab_account_reports_ai.get_ai_insights طلقة واحدة على ≤40 سطراً، ويعتمد على ab_ai_client القديم ويفشل عبر البوابة بسبب اسم ميزته. والتقارير نفسها غير موثوقة جزئياً: وجد تدقيق التقارير المحاسبية 22 سليماً و19 خاطئاً و7 معطّلة و3 فارغة من أصل 51، ولم تُطلق إلا إصلاحات مرحلته الأولى. أيضاً: ‎/create invoice و‎/create bill وcreate_journal_entry (مسودة) وDRAFT_GUARD، وأدوات مالية في روبوت المحادثة (ar_aging، pl_trend، pl_summary، cash_position، tax_summary، cashflow_*)، وسياق هيئة الزكاة والضريبة والجمارك (ZATCA) والمملكة في التعليمات الأساسية.

**التوصية:** جسر جديد يُثبَّت تلقائياً ab_ai_agent_account_reports ‏(saas-accounting؛ ab_account_reports + ab_ai_agent): ‏report_list وget_values وexpand_line وopen على ab.account.report بصلاحيات المستخدم، مقصورة على التقارير المُدقَّقة فقط (قائمة الدخل، الميزانية العمومية، ميزان المراجعة، ضريبة القيمة المضافة) حتى تكتمل مراحل التدقيق 2–4، مع الإبقاء على استبعاد is_year_end_closing؛ وموضوع 'اشرح قائمة الدخل / الميزانية العمومية / ضريبة القيمة المضافة' بالعربية. أعد بناء ab_account_reports_ai على ab_ai_agent وادمجه في الجسر. معيار القبول: تساوي get_values واجهة التقرير للخيارات نفسها على نسخة من FAYIAPROD. ويأتي وكيل قائمة مراجعة التدقيق لاحقاً.

`ai_account_reports/models/ai_tool.py#_ai_tool_accounting_report_get_values,_ai_tool_accounting_report_expand_line` `ai_account_reports/data/ai_skill_data.xml` `ai_account_reports/data/ai_audit_agents.xml` `saas-accounting/ab_account_reports_ai/models/ab_account_report_ai.py#get_ai_insights` `saas-share/ab_ai_command_account_entry/services/journal_entry.py` `saas-client/ab_ai_chatbot/services/tools/finance.py`

### G35 — التقاط العملاء المحتملين وتلخيصهم؛ وصياغة رسائل المبيعات

`partial` · `P2` · حسب التطبيق: CRM / المبيعات

**Odoo:** ‏ai_crm: ‏ai_tool_create_livechat_lead مع اكتشاف المعاملات. وai_crm_livechat. وحزم تعليمات المبيعات (مخططات حسب الدولة والمندوب والفئة). وai_product لأوصاف المنتجات وصورها.

**غيمة:** أمر ‎/create quote؛ وأدوات تحليل المبيعات (sales_totals، top_products، top_customers، sales_by_branch، sales_trend_monthly)؛ وأداتا confirm_sale_order وcancel_sale_order القديمتان (غير آمنتين، انظر G45). ومهارة 'Create a Quote' في Manager Bot توجّه النموذج خطأً لاستدعاء confirm_sale_order. لا تكامل مع CRM. ونتفوّق في تحليلات المبيعات.

**التوصية:** أصلح مهارة Manager Bot لتستخدم run_command create_quote الآن (مع G45). قائمة الانتظار: ab_ai_command_crm ‏(‎/create lead، مواصفة على crm.lead) وab_ai_agent_crm (ملخص العميل المحتمل والخطوة التالية؛ إنشاء عميل محتمل من المحادثة أو البريد كإجراء معلّق).

`ai_crm/models/crm_lead.py#_ai_create_lead,_ai_get_lead_create_available_params` `ai_sale/data/ai_prompt_button_data.xml` `saas-share/ab_ai_command_sale/models/sale_order.py` `saas-client/ab_ai_chatbot/services/tools/sales.py` `saas-ai/ab_manager_agents/data/manager_skills.xml`

### G36 — أدوات مساعد الموارد البشرية وصياغة رسائلها

`partial` · `P2` · حسب التطبيق: الموارد البشرية

**Odoo:** يصوغ hr_recruitment_ai رسائل الرفض بالذكاء الاصطناعي (mail_composer_chatgpt على applicant.get.refuse.reason). ويصوغ sign_ai رسائل طلبات التوقيع. لا ذكاء اصطناعي آخر للموارد البشرية.

**غيمة:** ‏‎/create employee (حقول الهوية فقط، دون الراتب). وأدوات حضور الموارد البشرية المعطّلة على الوكيل الافتراضي (بوابة البيانات الشخصية، انظر G02). وab_error_help يشرح الأخطاء عبر التطبيقات (478 للموارد البشرية) مع روابط لقاعدة المعرفة. وواجهة API للموارد البشرية على الجوال. ومنظومة الموارد البشرية السعودية في saas-hr.

**التوصية:** قائمة الانتظار. إما ab_ai_agent_hr في saas-share بجوار ab_ai_command_hr (تثبيت تلقائي مع hr + ab_ai_agent)، أو ab_hr_ai داخل saas-hr اتباعاً لقاعدة تسمية ab_hr_*؛ وفي الحالتين دون فروع، ودون أي اعتماد على النسخ المكررة القديمة الـ 18 من ab_hr_*. وإن وُضعت في saas-hr فيجب أن ينجح verify_no_conflict.py وverify_branch_free.py. النطاق: رصيد الإجازات والحضور بصلاحيات المستخدم، وإجابات عن نظام العمل السعودي والسياسات مؤصَّلة بمصادر G20، وشروح مسيرات الرواتب كمسودات فقط. وتأتي رسائل رفض التوظيف عبر ab_ai_composer.

`hr_recruitment_ai/wizard/applicant_refuse_reason_views.xml` `sign_ai/static/src/sign_ai_button.js` `saas-share/ab_ai_command_hr/models/hr_employee.py` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_hr_*` `saas-share/ab_error_help/__manifest__.py`

### G37 — مساعد سجلات الدوام وتعليمات المشاريع

`partial` · `P3` · حسب التطبيق: المشاريع

**Odoo:** أزرار تعليمات ai_project. وai_timesheet_grid: مساعد سجلات الدوام (get_assistant_data، timesheets_assistant_model.js) على شبكة سجلات الدوام في Enterprise.

**غيمة:** أداة create_task القديمة في روبوت المحادثة فقط (انظر G45).

**التوصية:** يؤجَّل. لاحقاً أضف أمر ‎/log time (مزيج ab_ai_command على account.analytic.line، مسودات) وملخصات المهام.

`ai_timesheet_grid/models/account_analytic_line.py#get_assistant_data` `ai_project/data/ai_prompt_button_data.xml` `saas-client/ab_ai_chatbot/services/tools/actions.py (create_task)`

### G38 — تذاكر مشابهة ومسودات ردود

`missing` · `P3` · حسب التطبيق: الدعم الفني

**Odoo:** ‏ai_helpdesk: ‏use_ai ووكيل ذكاء اصطناعي لكل فريق؛ وتضمينات التذاكر مع عتبة تشابه ونطاق زمني؛ ومُنشئ ردود مُغذّى بسجل التذكرة.

**غيمة:** ‏ab_ghaima_support المركزي (التذاكر واتفاقيات مستوى الخدمة) بلا ذكاء اصطناعي. والمستأجرون يعملون على Community دون دعم فني.

**التوصية:** يؤجَّل. لاحقاً أضف ab_ghaima_support_ai (مركزي): تذاكر مشابهة عبر semantic_index، ومسودات ردود بالعربية، واقتراحات من قاعدة المعرفة.

`ai_helpdesk/models/helpdesk_ticket.py#_get_similar_tickets,_get_embedding_content` `ai_helpdesk/models/ai_composer.py#_get_initial_context` `saas-erp/ghaima/ab_ghaima_support`

### G39 — صياغة الحملات والبريد الجماعي ومحتوى التواصل الاجتماعي

`missing` · `P3` · حسب التطبيق: التسويق

**Odoo:** وكيل Campaign Builder ومهاراته في ai_marketing_automation (الفرز، حذف الخطوات)، ورقعة المُنشئ في ai_mass_mailing، ومنشورات ai_social وصوره، وتعيين معاملات الانبعاثات في ai_esg. (وكيل صندوق وارد ai_social نمط قنوات، مغطى في G26.)

**غيمة:** لا يوجد.

**التوصية:** يؤجَّل. لاحقاً أضف ab_ai_agent_mass_mailing: عناوين ونصوص بالعربية عبر ab_ai_composer، وأفكار عروض ترويجية للمطاعم من بيانات نقاط البيع.

`ai_marketing_automation/data/ai_agent.xml` `ai_mass_mailing/static/src/builder/mass_mailing_builder_patch.js` `ai_social/data/ai_composer_data.xml` `odoo-18/addons/mass_mailing`

### G40 — أدوات تشغيلية للمشتريات والمخزون ونقاط البيع (نحن متقدمون)

`ours_ahead` · `P3` · حسب التطبيق: المشتريات / المخزون / نقاط البيع

**Odoo:** أزرار تعليمات فقط (ai_purchase، ai_stock، ai_sale_stock). لا ذكاء اصطناعي لنقاط البيع.

**غيمة:** ‏‎/create rfq؛ وأدوات المخزون (low_stock_products، out_of_stock_products، reorder_rules، inventory_summary، product_stock_status)؛ وأدوات نقاط البيع (pos_session_status، top_cashiers)؛ ومسح أوامر الشراء وعمليات النقل؛ وتنبؤات المطبخ والحالات الشاذة على الجوال، المعطّلة حالياً بسبب G05.

**التوصية:** بعد G05، أضف مواضيع للمطاعم (هندسة القائمة، الهدر، ساعات الذروة) إلى حزم تعليمات ab_ai_agent_pos و_stock.

`ai_purchase/data/ai_prompt_button_data.xml` `ai_stock/data/ai_prompt_button_data.xml` `saas-share/ab_ai_command_purchase/models/purchase_order.py` `saas-client/ab_ai_chatbot/services/tools/inventory.py` `saas-client/ab_ai_chatbot/services/tools/pos.py` `ghaima-api/ab_mobile_ai_api/controllers/ai_kitchen.py`

### G41 — سلوك يعطي العربية الأولوية (نحن متقدمون)

`ours_ahead` · `P2` · تعدد اللغات / العربية

**Odoo:** أوصاف الأدوات والمهارات قابلة للترجمة والبروتوكول يطلب الرد بلغة المستخدم. ولم يُعثر على تطبيع خاص بالعربية.

**غيمة:** ‏ar.po عبر الوحدات؛ وتوحيد الحروف العربية في التوجيه ومفتاح التخزين المؤقت والبحث في القوائم؛ ومسرد قوائم عربي←إنجليزي؛ وإزالة العلامة التجارية بالعربية في ضوابط البوابة (أودو، اوضو، اوديو، اودو ← غيمة، ai_guardrails.py:104-108)؛ وصياغة سعودية؛ وتحويل النص إلى كلام بالعربية. المشكلات المتبقية: عبارات شرطية عربية/إنجليزية مكتوبة مباشرة في Python (نقاط البدء، التأكيدات)؛ وإخفاء البيانات الشخصية كلّي أو لا شيء لكل باقة (allow_pii، ai_plan.py:53؛ والبوابة تتخطى الحجب عند ضبطه، ai_gateway_service.py:177-183)، فعند تعطيله تُحذف أرقام ضريبة القيمة المضافة والسجل التجاري والهاتف التي يحتاجها الوكيل؛ وتعليمات التسجيل السريع تذكر 'Odoo 18'.

**التوصية:** انقل العبارات الشرطية إلى ‎_() مع مدخلات في ar.po. استبدل plan.allow_pii الكلّي بإخفاء انتقائي: أبقِ أرقام ضريبة القيمة المضافة والسجل التجاري والهاتف التي يحتاجها العمل، واستمر في إخفاء أرقام البطاقات والآيبان والهوية الوطنية. أضف إعداداً لكل مستخدم للأرقام الهندية أو اللاتينية. وأصلح تعليمات التسجيل.

`ai/utils/agent_instructions_prompts.py (GLOBAL_PROTOCOL_TEMPLATE)` `saas-share/ab_ai_agent/services/runtime.py#_fold,_confirmation_text` `saas-ai/ab_ai_gateway/models/ai_guardrails.py#_BRAND_REPLACEMENTS,apply_pre_call` `saas-ai/ab_ai_plan/models/ai_plan.py (allow_pii)` `saas-ai/ab_ai_gateway/models/ai_gateway_service.py` `saas-ai/ab_ai_express_signup/models/ai_onboarding_service.py`

### G42 — تغطية اختبارية وتقييمات لبيئة التشغيل الإنتاجية

`partial` · `P1` · المراقبة / الاختبارات

**Odoo:** ‏ai/tests ‏(test_ai_session، test_llm_tool_calling، test_ai_access، test_tool_update_records، test_tool_create_records)، وtest_ai، وtest_ai_fields، واختبارات الحالات الحدّية لـ OAuth في ai_mcp، وجولات اختبار الواجهة.

**غيمة:** نحو 453 اختبار Python: ‏ab_ai_agent ‏182، وab_ai_chatbot ‏98، وab_ai_command ‏98، وab_scan_docs ‏32، وab_ai_client ‏18، وab_ai_gateway ‏13، وab_ai_agent_cache ‏5، وab_ai_command_account_entry ‏4، وab_ai_agent_config ‏3. لا شيء لـ ab_ai_base وab_ai_ui وab_ai_plan وجسر الرصيد وab_ai_entity والتضمين وروبوت الموقع والتسجيل السريع ووكلاء المدير، ولا اختبارات JS في أي وحدة ذكاء اصطناعي. ويؤكد tests/test_actions.py في ab_ai_chatbot أن confirm=True ينفّذ، وهو السلوك الكامن وراء G45. ويقيس تقييم المجموعة الذهبية agent_loop وintent_router المتقاعدين للعناصر غير الخاصة بالمساعد. لا يوجد CI ولم يُجرَ بعد أي تشغيل بمزوّد حقيقي عبر البوابة (O1).

**التوصية:** اختبارات عقود لحمولات المزوّدين ببيانات مسجّلة في ab_ai_base؛ واختبارات hoot لـ AiAgentChat وتعقيم المتنقّل؛ واختبار انحدار لكل عيب P0 (حدّث test_actions.py مع G45). وجّه أداة التقييم إلى runtime.run فقط، مع مجموعة ذهبية من ≥150 عنصراً بالإنجليزية والعربية، واجعل الإصدارات مشروطة بعتبات قابلة للقياس (دقة الأدوات ≥90% بالإنجليزية و≥85% بالعربية، ودون تراجع عن الإصدار السابق، مع الإبلاغ عن زمن الاستجابة p95 والتكلفة لكل تشغيل). شغّل odoo-bin --test-tags والتقييم ليلياً عبر ir.cron على بيئة التجهيز، من خلال البوابة وبمزوّد حقيقي (يغلق O1)، واحفظ النتائج.

`ai/tests/test_llm_tool_calling.py` `ai/tests/test_ai_access.py` `ai_mcp/tests` `saas-share/ab_ai_agent/tests` `saas-client/ab_ai_chatbot/tests/test_actions.py` `saas-client/ab_ai_chatbot/services/eval_runner.py` `saas-client/ab_ai_chatbot/data/golden_set.json` `saas-ai/docs/AI_GATEWAY_TENANT_LINK_ANALYSIS.md`

### G43 — سياق مقتصد في كل خطوة

`partial` · `P1` · الأداء

**Odoo:** يُجلب RAG في الجولة الأولى فقط ويُخزَّن مؤقتاً. ويقتطع تسلسل السجلات الأسماء إلى 60 حرفاً، ويتخطى قوائم x2many التي تتجاوز 50، ويحذف الحقول التي لا يستطيع المستخدم قراءتها. ويُرجع البحث 50 سجلاً افتراضياً، و200 كحد أقصى.

**غيمة:** يقرأ ‎_record_context_block كل الحقول، بما فيها الحقول المحسوبة غير المخزّنة. ويُجري explain_screen الأمر search_count([]) على النموذج كله. وكل خطوة تعيد إرسال التعليمات كاملة. وما يصل إلى 6 استدعاءات للمزوّد تعمل بشكل متزامن في عامل واحد.

**التوصية:** اقصر سياق السجل على حقول عرض النموذج الحالي المخزّنة أو المرتبطة، وحدّ قوائم x2many بـ 20، واقتطع القيم الطويلة. واجعل explain_screen يستخدم عدّاً محدوداً. أما التوفير في كل خطوة فيأتي مع G10.

`ai/models/models.py#_ai_serialize_fields_data,_ai_truncate` `ai/models/ai_session.py (rag_context state)` `saas-share/ab_ai_agent/services/runtime.py#_record_context_block` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_explain_screen`

### G44 — موثوقية تهيئة المستأجرين لمنظومة الذكاء الاصطناعي

`partial` · `P0` · SaaS متعدد المستأجرين

**Odoo:** قاعدة بيانات واحدة. يثبّت ai_auto_install وحدة ai فقط عند توفر pgvector. وحساب IAP واحد لكل قاعدة بيانات.

**غيمة:** مؤكَّد من الشيفرة: يدرج ab_tenant_module_guard الوحدة ab_ai_base في MAIN_SERVER_MODULES ‏(ir_module_module.py:33-36)، ويعلّمها غير قابلة للتثبيت عند update_list ‏(:88-104) ويرفض button_install ‏(:111-119)؛ وتعتمد ab_ai_agent وab_dashboard_ai_insights كلتاهما على ab_ai_base، فلا يستطيع المستأجر الجديد تثبيت منظومة الذكاء الاصطناعي. ومجرد رفع الحظر سيتيح لمسؤولي المستأجرين إضافة مفاتيح مزوّديهم الخاصة، وفي وضع 'auto' الالتفاف على رفض الحصة المركزي (G07). وab_manager_agents وحدة للمستأجر محفوظة في المستودع المركزي وتستدعي env._t غير المعرّفة في Odoo 18، فلا تظهر تعليمات تسجيل الدخول أبداً. وتبقى صفوف مستأجرين قديمة تشير إلى المستأجر نفسه (O10). ولم يُجرَ بعد اختبار بمزوّد حقيقي عبر البوابة (O1). وsaas-ai/ab_ai_daily_report شجرة متبقية من مجلدات فارغة.

**التوصية:** احذف ab_ai_base من MAIN_SERVER_MODULES فقط بالتزامن مع سياسة التوجيه المدفوعة من المركز: عندما يكون المستأجر مرتبطاً بالبوابة، اضبط llm_mode='gateway'، واجعل حقول مفاتيح المزوّد للقراءة فقط أو مخفية، واجعل llm_adapter يرفض الوضع المباشر. معيار القبول: المستأجر المرتبط لا يستطيع إجراء استدعاء مباشر ولا تجاوز رفض الحصة حتى مع إدخال مفتاح، والمستأجر الجديد يثبّت منظومة الذكاء الاصطناعي مع بقاء الحارس فعّالاً. استورد ‎_t في ab_manager_agents وانقلها إلى saas-client بعد التحقق من ربط المجلد (bind-mount). افحص pgvector عند التهيئة وسجّل توفره. احذف المجلدات المتبقية. وشغّل اختبار O1 السريع عبر لوحة التحكم قبل تحويل أي مستأجر إلى وضع البوابة.

`ai_auto_install/__manifest__.py` `ai/__init__.py#pgvector_is_available` `saas-client/ab_tenant_module_guard/models/ir_module_module.py#_tenant_guard_sweep,button_install` `saas-share/ab_ai_agent/__manifest__.py` `saas-dashboard/ab_dashboard_ai_insights/__manifest__.py` `saas-ai/ab_manager_agents/static/src/services/manager_open_on_login.js` `saas-ai/ab_ai_plan/models/odoo_entity.py#_push_ai_gateway_config` `saas-ai/ab_ai_daily_report`

### G45 — كل عملية كتابة تتطلب نقرة بشرية (لا تأكيد ذاتي من النموذج)

`partial` · `P0` · الإنسان في الحلقة

**Odoo:** توقف أدوات الكتابة الجلسة في حالة waiting_confirmation؛ ولا يُستأنف التنفيذ إلا بنقرة المستخدم، مع التحقق عبر resume_token المفحوص بـ compare_digest. ويوفّر Odoo أيضاً auto_confirm، وهو ما لا نوفّره عمداً.

**غيمة:** أدوات الكتابة القديمة في روبوت المحادثة (confirm_sale_order، post_invoice، cancel_sale_order، create_task) موصولة بالوكيل ومرفقة بمساعد غيمة مع is_write_action=True ‏(agent_bridge.py:172-191)؛ وهذا الوكيل لديه allow_write_actions=True وuse_all_capabilities=True ‏(ai_agent_data.xml:28-29). وتُرجع هذه الأدوات الشكل القديم ثنائي المرحلة: يُرجع ‎_preview ‏(actions.py:36-58) المفتاح idempotency_key مع confirm_prompt يطلب من النموذج 'Call <tool> with confirm=true and idempotency_key=…'. ولا تعامل بيئة التشغيل النتيجة كمقترح إلا عند ضبط result['confirmation']['key'] ‏(runtime.py:697-706)، فلا يُنشأ إجراء معلّق ولا شريحة، ويعود المفتاح إلى النموذج. وconfirm وidempotency_key وسيطان عاديان: ‎_wrap لا يحذف إلا المفاتيح المبدوءة بـ '_' ‏(agent_bridge.py:121) وdispatch لا يحذف إلا ‎_ai_* ‏(tool_dispatcher.py:83-90). وactions_enabled وحد 'actions' في الباقة لا يقيّدان إلا ACTION_TOOLS وPROPOSAL_TOOLS ‏(runtime.py:1430-1453)؛ والأدوات خارج ‎_ALL_ROUTED تُعرض دائماً (:1557)؛ وفحص acl_group موجود في call_tool، الذي لا يستدعيه ‎_wrap أبداً (tool_registry.py:127-130). وpost_invoice يستدعي action_post ‏(actions.py:160-190)، كاسراً قاعدة المحاسبة كمسودات فقط. اكتُشف بقراءة الشيفرة؛ ولم يُعَد إنتاجه فعلياً.

**التوصية:** البند الأول في المرحلة 1. عطّل post_invoice في كتالوج الوكيل (يبقى الترحيل إجراءً بشرياً). أعد كتابة confirm_sale_order وcancel_sale_order وcreate_task لتقترح عبر ai.agent.pending.action.propose (مع إرجاع result.confirmation.key)، أو استغنِ عنها لصالح screen_button. في dispatch() احذف confirm وidempotency_key من الوسائط التي يرسلها النموذج. أضف الأدوات المعاد كتابتها إلى PROPOSAL_TOOLS وطبّق actions_enabled وبوابة الباقة على كل أداة is_write_action. اربط acl_group بـ ai.agent.tool.group_ids في sync_agent_tools. حدّث manager_agent.xml:66-67 وai_agent_data.xml:87. معيار القبول: نموذج محاكى يستدعي post_invoice أو confirm_sale_order مع confirm=true والمفتاح المُرجع، في التشغيل نفسه أو الدورة التالية، لا ينفّذ شيئاً؛ ومع actions_enabled=False لا تُعرض أي أداة كتابة.

`ai/models/ai_session.py#_resume_pending_interaction` `ai/controllers/thread.py#resume_pending_interaction` `ai/utils/ai_utils.py#make_confirmation_request_preview` `saas-client/ab_ai_chatbot/services/tools/actions.py#_preview,_replay_or_execute,post_invoice` `saas-client/ab_ai_chatbot/services/agent_bridge.py#_wrap,_is_write_action,sync_agent_tools` `saas-share/ab_ai_agent/services/runtime.py#_proposal_of,_resolve_tools` `saas-share/ab_ai_agent/services/tool_dispatcher.py#dispatch` `saas-share/ab_ai_agent/data/ai_agent_data.xml` `saas-ai/ab_manager_agents/data/manager_agent.xml`

### G46 — المحادثة حول الملفات ومرفقات السجلات

`missing` · `P1` · الأدوات / المستندات

**Odoo:** يقرأ read_binary_content حتى 5 سجلات (MAX_BINARY_CONTENT_RECORDS_TO_READ=5). ويرسل ir.attachment._ai_read ملفات PDF مضمّنة، محدودة بأول وآخر N صفحة (ai_max_pdf_pages)، ويصغّر الصور. ولعارض الملفات 'Summarize this file' و'Explain this file'. وتنتقل مرفقات المحادثة كأجزاء بيانات مضمّنة.

**غيمة:** يرسل إرفاق الملفات في المحادثة كل ملف إلى ‎/scan-docs/upload/submit لاستخراجه إلى حقول شبيهة بالفواتير (ai_agent_chat_attach_patch.js)؛ ولا يقبل ‎/ai_agent/run أي مرفقات (agent_chat.py:412). فلا يمكن تلخيص ملف PDF لعقد أو مناقصة أو سياسة أو السؤال عنه، ولا يستطيع الوكيل قراءة مرفقات السجل الحالي.

**التوصية:** أضف أداة read_attachment إلى نواة ab_ai_agent دون اعتماد على الماسح: تحقّق من صلاحية القراءة على res_model/res_id بهوية المستخدم، وحدّ الصفحات والحجم، واستخدم مسار الرؤية الموجود في ab_ai_base مع ميزة البوابة 'document_qa'. اقبل الرفع في ‎/ai_agent/run ودع المستخدم يختار بين 'اسأل عن هذا الملف' و'امسحه كمستند'. معيار القبول: 'لخّص العقد المرفق' على ملف PDF عربي من 40 صفحة يُجاب من N صفحة على الأكثر؛ ويُرفض مرفق على سجل غير مقروء.

`ai/models/ai_tool.py#_ai_tool_read_binary_content` `ai/models/ir_attachment.py#_ai_read` `ai/data/ai_composer_data.xml (ai_file_viewer_helper, ai_prompt_summarize_file, ai_prompt_explain_file)` `saas-client/ab_ai_chatbot/static/src/js/ai_agent_chat_attach_patch.js` `saas-share/ab_ai_agent/controllers/agent_chat.py#run` `saas-share/ab_ai_base/models/ai_service.py (vision path)`

### G47 — الإنشاء والتحديث الجماعي بتأكيد واحد

`partial` · `P2` · الأدوات

**Odoo:** تأخذ update_records قائمة تحديثات عبر سجلات ونماذج مع شرح ومعاينة؛ وتأخذ create_records قائمة قيم.

**غيمة:** سجل واحد لكل مقترح (update_record، act_on_record). فطلب مثل 'أسند هؤلاء العملاء المحتملين الـ 12 إلى أحمد' يحتاج 12 تأكيداً أو لا يمكن تنفيذه.

**التوصية:** أضف إجراءً معلّقاً دفعياً يحمل كتلة data_table للفروقات. حدّه بـ 50 سجلاً، واشترط تأكيداً واحداً، وتحقّق من صلاحية الكتابة لكل سجل، واستخدم نقطة حفظ لكل سجل مع نتائج لكل سجل. وتبقى قواعد المسودات فقط سارية.

`ai/models/ai_tool.py#_ai_tool_update_records,_ai_tool_create_records` `saas-share/ab_ai_agent/services/agent_actions.py#update_record,act_on_record`

### G48 — سجلات قابلة للنقر في الإجابات

`missing` · `P2` · عرض الإجابات

**Odoo:** تربط الإجابات بالسجلات (prepare_record_previews، ‎_ai_get_preview_metadata)؛ وتعرض المحادثة المباشرة بطاقات معاينة.

**غيمة:** كتلتا data_table وhighlight_list تعرضان سجلات لا يستطيع المستخدم فتحها (لا معالجة للنقر أو href أو res_id)، ما يُضعف مجموعة الكتل في قوائم مثل 'الفواتير المتأخرة'.

**التوصية:** أضف row_ref {model, id} إلى صفوف data_table. تحقّق منه على الخادم بصلاحيات المستخدم (check_access) وافتحه عبر aiNavigator.

`ai/models/ai_tool.py#_ai_tool_prepare_record_previews` `ai_website_livechat/models/ai_preview_card_mixin.py` `saas-share/ab_ai_ui/static/src/blocks/data_table.js` `saas-share/ab_ai_ui/static/src/blocks/data_table.xml`

### G49 — بيئة تشغيل واحدة؛ ولا حالة عامة تُبدَّل لكل طلب

`partial` · `P1` · حلقة الوكيل / الموثوقية

**Odoo:** حلقة وكيل واحدة (ai.session) تخدم كل الواجهات؛ ولم نجد أي ترقيع لمتغيرات الوحدة العامة لكل طلب.

**غيمة:** ما زال ab_ai_chatbot يحمل بيئة التشغيل السابقة للوكيل: ‏agent_loop.py ‏(438 سطراً) وtool_dispatcher.py الخاص به (168) لا يُصل إليهما إلا من التقييمات والاختبارات (eval_runner.py:24)؛ وchat_response_cache.py ‏(437) لا يستورده إلا models/__init__.py؛ وأدوات الكتابة القديمة ثنائية المرحلة باقية (G45). ويبدّل ‎_send_via_agent_runtime الدالة العامة tool_registry.call_tool على مستوى الوحدة لكل طلب ويعيدها في finally ‏(ai_chat.py:563-590). وفي وضع الخيوط أو gevent يمكن للطلبات المتزامنة إرسال أحداث الأدوات إلى قناة ناقل مستخدم آخر، وقد تطمس الاستعادةُ تبديلاً متزامناً.

**التوصية:** بعد G45، احذف الوحدات الميتة وأدوات الكتابة القديمة، ومرّر on_event صراحةً بدلاً من تبديل المتغير العام، ووجّه eval_runner إلى runtime.run ‏(G42). معيار القبول: مستخدمان متزامنان يتلقى كلٌّ منهما أحداث أدواته فقط.

`ai/models/ai_session.py` `saas-client/ab_ai_chatbot/services/agent_loop.py` `saas-client/ab_ai_chatbot/services/tool_dispatcher.py` `saas-client/ab_ai_chatbot/models/chat_response_cache.py` `saas-client/ab_ai_chatbot/models/ai_chat.py#_send_via_agent_runtime` `saas-client/ab_ai_chatbot/services/eval_runner.py`

### G50 — تكاملات كل تطبيق في جسور تُثبَّت تلقائياً

`partial` · `P1` · بنية الوحدات

**Odoo:** تُطلق ميزات الذكاء الاصطناعي لكل تطبيق كوحدات جسر ai_<app>؛ و53 من أصل 56 وحدة ذات صلة بالذكاء الاصطناعي تُثبَّت تلقائياً، فلا تحصل قاعدة البيانات إلا على قطع الذكاء الاصطناعي للتطبيقات الموجودة فيها.

**غيمة:** قاعدة الجسور مكسورة اليوم. يعتمد ab_ai_chatbot اعتماداً صلباً على ab_scan_docs (الذي يجرّ account وsale وpurchase وstock وportal) وعلى ab_ai_client ‏(sale، account). ويعتمد ab_manager_agents اعتماداً صلباً على crm وhr وsale_management وaccount. ويعتمد ab_account_reports_ai على ab_ai_client القديم بدلاً من ab_ai_agent. فعلى المستأجرين الذين يستخدمون الموارد البشرية فقط أو الباقة الأساسية تثبيت المحاسبة والمخزون والمبيعات للحصول على روبوت المحادثة.

**التوصية:** انقل رقعة الإرفاق والكاميرا إلى ab_ai_chatbot_scan_docs ‏(auto_install)؛ وانقل أدوات المالية والمبيعات في روبوت المحادثة إلى جسور لكل تطبيق؛ وقسّم مواضيع المجالات في ab_manager_agents إلى جسور؛ وأعد بناء ab_account_reports_ai على ab_ai_agent (مع دمجه في ab_ai_agent_account_reports). معيار القبول: يُثبَّت ab_ai_chatbot على قاعدة بيانات لا تحتوي إلا hr.

`ai_sale/__manifest__.py` `ai_account/__manifest__.py` `saas-client/ab_ai_chatbot/__manifest__.py` `saas-client/ab_ai_client/__manifest__.py` `saas-client/ab_scan_docs/__manifest__.py` `saas-ai/ab_manager_agents/__manifest__.py` `saas-accounting/ab_account_reports_ai/__manifest__.py`

## نقاط التفوق

- بوابة متعددة المستأجرين (ab_ai_gateway + ab_ai_plan + ab_ai_entity): رموز المستأجرين، وentity_ref محمي من العبث، وسقوف الباقات، وميزانيات بالدولار لكل مستأجر، وحدود المعدّل، وضوابط (منها إزالة العلامة التجارية بالعربية)، ومزوّد احتياطي، ودليل أسعار بالريال يُطابَق مع استخدام المستأجرين. أما Odoo فلا يملك إلا رصيد IAP لقاعدة بيانات واحدة.
- حرية اختيار المزوّد وخيار الاستضافة المحلية: OpenAI وGemini وClaude (تحتاج معرّفاته إلى تحديث G08) وOllama، مع مفاتيح مشفّرة بـ Fernet، ووضع محاكاة، وقاطع دائرة (llm_adapter). أما Odoo فمقيّد بنقطة IAP الخاصة به.
- تخزين مؤقت للتعليمات مصمَّم ضمن بنية التعليمات (بادئة ثابتة + CACHE_BREAK + cache_control في Anthropic)، إضافة إلى تخزين مؤقت للإجابات يطبّع العربية ويعيد تشغيل خطط البيانات بصلاحيات المستخدم. ولم نجد لدى Odoo أي تخزين مؤقت من جهة العميل.
- تُعرض الإجابات كمجموعة كتل (شبكة مؤشرات الأداء، ومخططات Chart.js، والجداول، والتنبيهات، والمصدر) يغذّيها query_data، الذي يقارن بالفترة السابقة ضمن مهلة استعلام قدرها 8 ثوانٍ. أما Odoo فيفتح العروض بدلاً من ذلك.
- التأكيد أولاً لأدوات الإجراءات الأساسية، دون خيار «الموافقة دائماً»: التأكيدات متكررة التنفيذ بأمان وتنتهي بعد 15 دقيقة، وDRAFT_GUARD يبقي المحاسبة كمسودات، وcreate_record يرفض كل ما لا يبقى مسودة، والتأكيد الصوتي يسلك المسار نفسه. وأدوات الكتابة في روبوت المحادثة بانتظار الترحيل (G45).
- وكيل إعداد بالتأكيد أولاً (ab_ai_agent_config): يغيّر مجموعة مُعتمدة من إعدادات الأعمال (مثل تعدد العملات) بعد «تأكيد» فقط. أما مهارة Self Update في Odoo فمقصورة على نماذج ai.* وقائمة حظرها لا تغطي إلا نماذج قليلة.
- أوامر شرطة مائلة حتمية (ab_ai_command، ‏98 اختباراً): محلّل يدرك العربية، ومحلِّلات تسأل عند التباس التطابق، ومسودات فقط، دون رحلة ذهاب وإياب إلى LLM.
- العربية أولاً: تطبيع النص، ومسرد قوائم عربي←إنجليزي، وصياغة أعمال سعودية، وتحويل Gemini للنص إلى كلام بالعربية، وملفات ar.po بالعربية السعودية عبر الوحدات.
- محتوى معرفي منسّق: 10 حزم ab_knowledge_base_* (نحو 93 سجلاً بالعربية والإنجليزية مع لقطات شاشة، وإخفاء الميزات غير المثبّتة) تغذّي kb_search وkb_read وexplain_screen؛ وab_error_help يشرح الأخطاء عبر التطبيقات (478 للموارد البشرية). وهذه هي المجموعة الأولى البديهية لـ RAG.
- صوت تحاوري (وضع بدون استخدام اليدين، وتأكيد وإلغاء صوتي، مع القياس والتقييد بالباقة). أما Odoo فلا يملك إلا الإملاء والنسخ.
- مسح المستندات بالرؤية الحاسوبية إلى 7 أنواع سجلات مع بوابات الثقة والإجمالي والتكرار والنوع (ab_scan_docs، ‏32 اختباراً)، إضافة إلى بوابة: رفع دفعي، والتقاط تلقائي بالكاميرا، وإعادة مطابقة البنود، وطلبات إنشاء منتجات (ab.product.request)، وسجل تصحيحات (20 مساراً تحت ‎/scan-docs/*).
- واجهة API أصلية للذكاء الاصطناعي على الجوال تستخدمها تطبيقات Flutter: ‏6 نقاط JWT ‏(‎/api/v1/ai/query، ‎/suggestions، ‎/dashboard/summary، ‎/dashboard/anomalies، ‎/kitchen/predict، ‎/kitchen/performance)، ومحدِّد معدّل، ووثائق OpenAPI ‏(ghaima-api/ab_mobile_ai_api).
- تسجيل في خدمة SaaS بمساعدة الذكاء الاصطناعي (ab_ai_express_signup).
- تدقيق التشغيلات (ai.agent.run): الرموز، وزمن الاستجابة، وrouted_via، وتصنيف مؤصَّل/جزئي/غير مؤصَّل، وتقييم المستخدم، إضافة إلى سجلات استخدام لكل خطوة وأداة تقييم.
- تنقّل آمن: الخادم يبني كل توجيه تنقّل، ويُتحقَّق من نطاق واصف الشاشة على الخادم، والعميل لا يقبل إلا أشكال السجل أو القائمة أو القائمة الرئيسية، ومؤشر الذكاء الاصطناعي يُظهر وجهته.
- نصائح استباقية بلا تكلفة وموجز يومي، وملخّص معرفة ليلي يبقى ثابتاً بايتاً ببايت لتبقى البادئة المخزّنة صالحة.
- تحليلات نقاط البيع والمطاعم (جداول الحقائق، وأدوات الكاشير والجلسات، ونقاط المطبخ)، وهو ما لا يغطيه ذكاء Odoo الاصطناعي إطلاقاً.
- تعليمات أساسية مقفلة ومقتطف معرفة من الموقع موقّع بـ HMAC ولا يُجلب إلا من نطاقات ghaima.sa المسموح بها.

## التحسينات

### طبقة سياسات واحدة لكل عمليات الكتابة بالذكاء الاصطناعي

تصل عمليات الكتابة إلى السجلات عبر ستة مسارات بقواعد مختلفة: الموزّع، وresolve() عند «التأكيد»، وexecute_action في روبوت المحادثة، وscreen_button، وأدوات الكتابة القديمة في روبوت المحادثة (التي يستطيع النموذج تأكيدها بنفسه)، والطيار الآلي في scan_docs. ويحقق Odoo الاتساق بتشغيل كل أداة داخل دفعة أدوات الجلسة.

اجعل tool_dispatcher.dispatch الطريق الوحيد لتنفيذ أي أداة، بما في ذلك عند «التأكيد» (علم confirmed بالكلمة فقط). انقل كل عمليات الكتابة إلى ai.agent.pending.action؛ واحذف post_invoice وexecute_action. أضف سجلاً للأساليب المحمية (الترحيل، اعتماد مسير الرواتب) لا يجوز لأي مسار وكيل استدعاؤها. امنح كل أداة علم automation_safe للتشغيلات دون واجهة، واربط كل إجراء معلّق بوكيله وتشغيله.

تغطي: G45, G02, G29, G31, G32, G47

### جعل البوابة المدخل المقيس الوحيد

الواجهات العامة والتضمينات ومسح المستندات واستدعاءات OLG الأصلية في محرر Odoo ومعالج الإعداد كلها تتجاوز القياس؛ ووضع 'auto' يتيح لمفاتيح المستأجرين الالتفاف على رفض الحصة؛ وقائمة الميزات المغلقة تعطّل مستدعين مشروعين.

اجعل رفض البوابة نهائياً وادفع llm_mode='gateway' إلى المستأجرين المرتبطين؛ واجعل feature من نوع Char مربوطاً بفئات؛ وامنح الواجهات العامة ميزانيات منصة؛ وقِس ‎/embed؛ وقيّد model_override؛ واحتوِ نقاط OLG ثم أعد تعريفها؛ واستخدم دالة توحيد تكلفة واحدة لكل المسارات.

تغطي: G05, G06, G07, G24, G29, G44

### سجل قائم على الأجزاء ومخرجات منظّمة في ab_ai_base

النص الواحد المتنامي يستهلك الرموز في كل خطوة، ويسبب استدعاءات أدوات مشوّهة، ويمنع التخزين المؤقت متعدد الخطوات. وتحتاج حقول الذكاء الاصطناعي والأتمتة إلى مخرجات بمخطط JSON، ويجب أن تبقى معرّفات النماذج حديثة.

اختبارات عقود المزوّدين أولاً؛ ثم إعادة المحاولة مع التراجع التدريجي، ودعم response_schema، وحقول الإهمال في ai.usage.price.book (جدول أسعار واحد)؛ ثم قائمة رسائل محايدة تجاه المزوّد مع محوّل لكل مزوّد، يقدّمها المركز كقدرة 'messages_v1' ولا يستخدمها المستأجرون إلا عند الإعلان عنها.

تغطي: G08, G10, G43, G30, G42

### جلسات في النواة، مع سياسة احتفاظ

الذاكرة والسجل يعتمدان على وحدة من جهة المستأجر، وسجلات التدقيق تخزّن بيانات العملاء إلى الأبد.

أضف ai.agent.session وai.agent.session.message إلى ab_ai_agent (مع حقل JSON للأجزاء قابل للفراغ حتى لا ينتظر G10)، وانقل ab_ai_chatbot إليهما، وأضف ملخصات متجددة وتنظيفاً تلقائياً للتشغيلات والسجلات.

تغطي: G21, G22, G11

### مصادر معرفة مع استشهادات

لا يمكن اليوم تأصيل الإجابات عن سياسات الشركة أو أدلة المنتجات أو الأنظمة السعودية. وشيفرة الاستشهادات والفهرس الدلالي ومجموعة معرفة منسّقة موجودة لكنها غير موصولة ببعضها.

ابنِ ab_ai_knowledge على ai.semantic.index مع مقالات قاعدة المعرفة كمصدر أول، ثم المرفقات والروابط عبر حارس SSRF جديد قابل للتهيئة في ab_ai_base؛ وضمّن عبر البوابة المقيسة، وفلتر الاسترجاع حسب الصلاحية، واربط استشهادات [SOURCE:id]. ثم أضف البحث على الويب عبر البوابة.

تغطي: G20, G18, G38, G36

### توجيه الذكاء الاصطناعي الأصلي في المحرر والمُنشئ عبر بوابتنا

يعرض Odoo 18 CE الذكاء الاصطناعي أصلاً في كل حقل html وفي مُنشئ البريد، لكنه يرسل نصوص المستأجر وdatabase.uuid إلى Odoo. وأسلوب متحكم موروث واحد يحوّله إلى ذكاء اصطناعي مقيس يدرك العربية في كل مكان.

احتوِ نقطتَي OLG عبر ICP من اليوم الأول. ثم ترث ab_ai_composer أسلوب generate_text (المساران، ونافذتا الترجمة والبدائل)، وتضيف سياق السجل إلى المُنشئ الأصلي وإجراء صياغة في account.move.send.wizard، إضافة إلى مزوّد أوامر Ctrl+K.

تغطي: G24, G25, G28

### قراءة الملفات، والعمل الجماعي، وربط السجلات

لا يستطيع المستخدمون السؤال عن ملف PDF لعقد أو مناقصة، والطلبات الجماعية تحتاج تأكيداً لكل سجل، والسجلات المدرجة في الإجابات لا يمكن فتحها.

أداة read_attachment على مسار الرؤية مع فحص الصلاحيات وحدود الصفحات؛ وإجراء معلّق دفعي مع جدول فروقات ونقطة حفظ لكل سجل؛ وrow_ref على صفوف data_table يُتحقَّق منه بصلاحيات المستخدم ويُفتح عبر aiNavigator.

تغطي: G46, G47, G48

### حزم تعليمات لكل تطبيق كجسور بيانات فقط

معظم قيمة Odoo لكل تطبيق تأتي من حزم تعليمات بيانات فقط. أدواتنا أقوى لكن نقاط الدخول لاكتشافها أقل.

اعرض الشرائح مفلترة على context_model الموجود وsurfaces. أطلق ab_ai_agent_sale و_purchase و_stock و_account و_pos و_project و_calendar و_hr كوحدات بيانات تُثبَّت تلقائياً بتعليمات عربية، إضافة إلى مهارتين عامتين لتلخيص سجل المحادثات والمتابعة. وأطلق ab_ai_agent_account_reports على التقارير المُدقَّقة فقط.

تغطي: G23, G34, G35, G40

### وكلاء دون واجهة يلتزمون بالتأكيد أولاً ولا يعملون أبداً بصلاحيات المستخدم الأعلى

العمل المتكرر في المنشآت الصغيرة والمتوسطة (متابعة المتأخرات، ملاحظة نقدية يومية، تنبيهات المخزون) يحتاج محفّزات وجداول زمنية. يعتمد Odoo استدعاءات الأدوات تلقائياً في هذه التشغيلات، والمهمة المجدولة في base.automation تعمل بهوية مستخدم النظام؛ ويجب ألا نفعل أياً منهما.

ab_ai_fields، ثم ab_ai_server_actions، ثم ab_ai_agent_automation. لكل قاعدة مستخدم مالك؛ والتشغيلات تستخدم env(user=owner, su=False) ضمن ميزانية، وعمليات الكتابة تصبح إجراءات معلّقة في صندوق وارد المالك، والتشغيل المجدول التالي يتقدّم حتى بعد الفشل.

تغطي: G30, G31, G32

### MCP للقراءة فقط على ab_api_base

يسأل العملاء بشكل متزايد ChatGPT وClaude وعملاء مشابهين عن بيانات ERP الخاصة بهم. مصادقة bearer في Odoo 18 بلا نطاقات، لكن مدقّقات نطاق JWT لدينا تملكها.

ab_ai_mcp: ‏tools/list وtools/call على سجلات ai.agent.tool الموسومة لـ MCP، للقراءة فقط افتراضياً، واشتراك اختياري لكل شركة، مع أداة سياق أوّلي، وحد معدّل لكل رمز، وسجلات استخدام تحت 'mcp'، وسجل تدقيق. وينتقل OAuth 2.1 إلى قائمة الانتظار.

تغطي: G33

### حدود وحدات نظيفة

ما زالت بيئة تشغيل قديمة تُشحن مع خطأ تزامن، والاعتماديات الصلبة تفرض المحاسبة والمخزون والمبيعات على مستأجري الموارد البشرية فقط، كاسرةً قاعدة الجسور.

أوقف بيئة تشغيل روبوت المحادثة القديمة والتبديل العام لـ call_tool؛ وقسّم أجزاء المسح والمالية والمبيعات في روبوت المحادثة ومواضيع Manager Bot إلى جسور تُثبَّت تلقائياً؛ وأعد بناء ab_account_reports_ai على ab_ai_agent.

تغطي: G49, G50

### بوابة إصدار بالاختبارات والتقييمات

معظم عيوب P0 تقع في وحدات بلا اختبارات، واختبار قائم يؤكد سلوك التأكيد الذاتي غير الآمن، وأداة التقييم تقيس شيفرة لم تعد مستخدمة.

اختبارات عقود للمزوّدين، واختبارات hoot لواجهة المحادثة، واختبار انحدار لكل إصلاح، ومجموعة ذهبية من ≥150 عنصراً بالعربية والإنجليزية على runtime.run بعتبات دقة، ومهمة مجدولة ليلية على بيئة التجهيز تشغّل الاختبارات والتقييمات عبر البوابة بمزوّد حقيقي (O1).

تغطي: G42, G44

## خطة التنفيذ

### المرحلة 1 — 4 أسابيع (مطوّران)

التثبيت: إغلاق عيوب الأمان والقياس والتهيئة دون إضافة ميزات. الدفعة 1a (الأسبوع 1) إصلاحات عاجلة؛ والدفعة 1b (الأسابيع 2–4) تستكمل الإصلاحات. بافتراض مطوّرَين اثنين. تعريف الإنجاز لكل بند في كل مرحلة: ملف ar.po بالعربية السعودية مُتحقَّق من تحميله في Odoo على قاعدة بيانات جديدة (لا عبر polib فقط)؛ وفحص الاتجاه من اليمين إلى اليسار؛ واختبار الترقية على نسخة من FAYIAPROD أو مستأجر تجريبي، وليس على الإنتاج أبداً؛ ونشر المركز قبل المستأجرين لأي تغيير في عقد البوابة؛ والتزام واحد لكل مستودع مع مدخل في CHANGELOG؛ واختبار انحدار لكل إصلاح.

#### 1a: منع المساعد من تأكيد عمليات الكتابة بنفسه (G45)

الوحدات: `ab_ai_chatbot`, `ab_ai_agent`, `ab_manager_agents`

الخطوات:
1. عطّل post_invoice في كتالوج الوكيل (sync_agent_tools)؛ ويبقى الترحيل إجراءً بشرياً
2. أعد كتابة confirm_sale_order وcancel_sale_order وcreate_task لتقترح عبر ai.agent.pending.action.propose (مع إرجاع result.confirmation.key)، أو استغنِ عنها لصالح screen_button
3. في dispatch() احذف confirm وidempotency_key من الوسائط التي يرسلها النموذج؛ وأضف الأدوات المعاد كتابتها إلى PROPOSAL_TOOLS
4. طبّق actions_enabled وحد 'actions' في الباقة على كل أداة is_write_action في ‎_resolve_tools؛ واربط acl_group بـ ai.agent.tool.group_ids في sync_agent_tools
5. حدّث التعليمات في ai_agent_data.xml:87 وmanager_agent.xml:66-67؛ وعدّل tests/test_actions.py في ab_ai_chatbot الذي يؤكد أن confirm=True ينفّذ

**يكتمل عندما:** تشغيل مُبرمج يستدعي فيه النموذج المحاكى post_invoice أو confirm_sale_order مع confirm=true والمفتاح المُرجع، في التشغيل نفسه أو الدورة التالية، لا ينفّذ شيئاً وتبقى الفاتورة مسودة؛ ومع actions_enabled=False لا تُعرض أي أداة كتابة؛ واختبار grep مع اختبار dispatch يُظهران أن لا مسار وكيل يصل إلى account.move.action_post.

#### 1a: إعادة فحص كل البوابات عند «التأكيد» (G02)

الوحدات: `ab_ai_agent`, `ab_ai_chatbot`

الخطوات:
1. أضف agent_id إلى ai.agent.pending.action (الحقلان tool_code وagent_run_id موجودان أصلاً)؛ ومرّر agent وagent_run من كل موضع يستدعي propose() ‏(agent_actions.py:232; tool_dispatcher.py:1185, :1271)
2. امنح dispatch() معاملاً بالكلمة فقط confirmed: bool خارج الوسائط، يمرّر _ai_confirmed=True إلى الأداة
3. resolve(): ابحث عن ai.agent.tool بواسطة tool_code، واجلب agent_id، واستدعِ dispatch(..., confirmed=True)
4. ربط مؤقت في execute_action ضمن ab_ai_chatbot: ‏create_uid == env.uid، والمحادثة نفسها، وتجزئة الهدف والوسائط، وصلاحية 15 دقيقة

**يكتمل عندما:** الاختبارات: إيقاف actions_enabled بين الاقتراح و«التأكيد» يمنع التنفيذ؛ والمستخدم الذي فقد مجموعة الأداة لا يستطيع التأكيد؛ ومقترح روبوت المحادثة للسجل A لا يُنفَّذ على السجل B أو لمستخدم آخر؛ والمفتاح المنتهي يُرفض.

#### 1a: إعادة بناء data_analysis على ORM (G01)

الوحدات: `ab_ai_agent`

الخطوات:
1. أعد بناء ‎_builtin_data_analysis على Model._read_group بصلاحيات المستخدم (إعدادات query_data المسبقة)، مع الإبقاء على مغلّف kpi_grid والمخطط
2. مرّر المنطقة الزمنية للمستخدم في السياق لتجميع الأيام؛ وجمّع الإجماليات حسب العملة أو حوّلها إلى عملة الشركة
3. أرجِع خطأً عاماً إلى النموذج وسجّل الاستثناء
4. استدعِ generic_data.model_blocked في query_data

**يكتمل عندما:** الاختبارات: مستخدم الشركة B يحصل على إجماليات الشركة B فقط؛ والمستخدم بلا صلاحية قراءة لنقاط البيع أو المحاسبة يحصل على ok=False؛ والمستخدم المقيّد بفرع لا يرى إلا فرعه عبر query_data وdata_analysis؛ وطلب الساعة 23:30 بتوقيت الرياض يقع في اليوم الصحيح؛ والشركة بعملتين تعرض الإجماليات لكل عملة.

#### 1a: إغلاق مسار الروبوت بصلاحيات المستخدم الأعلى وتسريبات المفاتيح والإنفاق (G03, G04)

الوحدات: `ab_ai_chatbot`, `ab_ai_agent`, `ab_ai_base`

الخطوات:
1. روبوت Discuss: عند عدم وجود سائل داخلي، ردّ برسالة تسجيل دخول مترجمة؛ ولا تستخدم بيئة SUPERUSER أبداً؛ وسجّل الاستثناءات وردّ برسالة عامة
2. usage_live: اشترط مدير الذكاء الاصطناعي؛ وانقل العدّاد المباشر إلى قناة سجل res.company يُتحقَّق منها في ‎_build_bus_channel_list؛ واحذف cost_usd من المغلّفات لغير المسؤولين
3. رؤية Gemini والتضمين: أرسل المفتاح في الترويسة x-goog-api-key؛ ولا تضع نص الاستثناء في UserError أبداً؛ وانقل ‎_scrub_secrets إلى ab_ai_base وأضف مرشّح سجلات يحجب key=

**يكتمل عندما:** إشارة الضيف (@mention) لا تحصل على بيانات؛ وغير المدير يحصل على 403 من ‎/ai_agent/usage/live ولا يستطيع الاشتراك في قناة شركة أخرى؛ وgrep لا يجد '?key=' في ab_ai_base؛ وخطأ HTTP مفتعل من Gemini لا يُظهر المفتاح في السجل أو الواجهة.

#### 1a: احتواء خروج بيانات OLG إلى Odoo واستعادة مزوّد Claude (G24, G08)

الوحدات: `ab_ai_plan (دفع إعدادات المستأجر)`, `ab_ai_base`, `ab_ai_gateway`

الخطوات:
1. ادفع web_editor.olg_api_endpoint وwebsite.olg_api_endpoint إلى نقطة معطّلة (أو مركزية) لكل مستأجر عبر لوحة التحكم، واضبطهما عند التهيئة
2. استبدل خيارات Claude وصفوف أسعاره بالمعرّفات الحالية (claude-opus-5-5، claude-sonnet-5-5، claude-haiku-5-5؛ تحقّق منها في وثائق Anthropic عند التنفيذ)
3. أوقف إرسال temperature في ‎_call_claude؛ وانقل قيم ai.provider.config.claude_model المخزّنة

**يكتمل عندما:** مع محاكاة iap_jsonrpc وwebsite._OLG_api_rpc، لا يصل أي استدعاء إلى خادم OLG من المحرر أو المُنشئ أو معالج الإعداد؛ وينجح استدعاء Claude على كل معرّف جديد في الوضعين المباشر والبوابة.

#### 1b: أسماء ميزات مفتوحة وقياس دقيق (G05, G06)

الوحدات: `ab_ai_gateway`, `ab_ai_plan`, `ab_ai_plan_credit_bridge`, `ab_ai_agent`, `ab_ai_base`

الخطوات:
1. حوّل ai.usage.log.feature إلى Char مع ترحيل؛ وأضف ربط ai.feature.bucket وقيّد الباقات على مستوى الفئات ('custom' للأسماء غير المعروفة)
2. اكتب سجل الاستخدام بحالة 'pending' قبل استدعاء المزوّد وأنهِه بعده
3. أضف توحيد بيانات الاستخدام في ab_ai_base ‏(input_uncached، cached، output) واستخدمه في meter.record وestimate_cost والبوابة
4. احسب cost_usd محلياً في المسار المباشر ليُفرض max_cost_usd
5. أضف الصفوف الناقصة في ai.usage.price.book؛ وأغلق بأمان (fail closed) عند فرض ميزانية وعدم وجود سعر للنموذج
6. أضف ir.cron لـ ‎_cron_generate_overage_invoices؛ واحذف سجل حد المعدّل المكرر؛ واستخدم رمز عملة الباقة

**يكتمل عندما:** تنجح اختبارات البوابة لكل ميزة يرسلها المستأجرون (business_query، pos_suggestions، kitchen_prediction، kitchen_performance، anomaly_detection، dashboard_insights، accounting_report_insight)؛ والاستدعاء المخزّن مؤقتاً يُبلغ عن الإجمالي = المدخلات + المخرجات؛ والتشغيل في الوضع المباشر يتوقف عند max_cost_usd؛ والمهمة المجدولة للتجاوز موجودة ومختبرة.

#### 1b: سياسة توجيه واحدة: رفض البوابة نهائي (G07, G29, G44)

الوحدات: `ab_ai_agent`, `ab_ai_base`, `ab_ai_client`, `ab_scan_docs`, `ab_tenant_module_guard`, `ab_ai_plan`, `ab_manager_agents`

الخطوات:
1. llm_adapter: رفض البوابة (الحصة، الباقة) نهائي ما لم يوجد اشتراك صريح عبر ICP؛ ولا ارتداد إلا عند أخطاء النقل
2. تدفع التهيئةُ llm_mode='gateway' إلى المستأجرين المرتبطين؛ وتصبح حقول مفاتيح المزوّد للقراءة فقط أو مخفية لديهم ويرفض llm_adapter الوضع المباشر
3. أضف المعامل feature= إلى call_llm؛ ووجّه scan_docs عبره (أضف اعتمادية ab_ai_agent، أو انقل دالة الحلّ إلى ab_ai_base أو ab_ai_client)؛ وأصلح استدعاء get_config() خارج كتلة try
4. احذف ab_ai_base من MAIN_SERVER_MODULES بالتزامن مع السياسة أعلاه
5. لا تسمح بـ autopilot_terminal='post' إلا إذا ضبطها مدير حسابات، وسجّل كل ترحيل آلي
6. ab_manager_agents: استورد ‎_t؛ وانقلها إلى saas-client بعد التحقق من ربط مجلد الحاوية؛ واحذف مجلدات saas-ai/ab_ai_daily_report الفارغة
7. شغّل اختبار O1 السريع بمزوّد حقيقي عبر لوحة التحكم قبل تحويل أي مستأجر إلى وضع البوابة

**يكتمل عندما:** على نسخة من FAYIAPROD (بلا صف بوابة) تعمل عمليات المسح عبر المزوّد المباشر؛ وعلى مستأجر مرتبط يكون رفض الحصة نهائياً للوكيل وscan_docs حتى مع إدخال مفتاح مزوّد؛ ويثبّت مستأجر تجريبي جديد منظومة الذكاء الاصطناعي مع بقاء الحارس فعّالاً؛ وتظهر تعليمات تسجيل الدخول للمدير.

#### 1b: استكمال التقييد بالنطاق وتحصين الواجهات (G01, G02, G03, G04)

الوحدات: `ab_ai_agent`, `ab_ai_chatbot`, `ab_ai_chatbot_branch (جديدة، saas-branches، تثبيت تلقائي)`, `ab_ghaima_website_chatbot`, `ab_ai_express_signup`, `ab_ai_client`

الخطوات:
1. ab_ai_chatbot_branch: فلاتر الفروع لـ fact_query فقط (أو أعد بناء جداول الحقائق على ‎_read_group واستغنِ عن الجسر)
2. تحقّق من حقول extra_domain في semantic_search بصلاحيات المستخدم؛ واقرأ سجل المحادثات في ‎_record_context_block بصلاحيات المستخدم
3. سجل الأساليب المحمية (action_post في account.move/account.payment، وdone في hr.payslip) محظور في screen_button وact_on_record
4. وجّه شرائح التأكيد في روبوت المحادثة عبر ‎/ai_agent/action/confirm واحذف execute_action
5. فلتر أدوات requires_pii عندما لا يسمح الوكيل بالبيانات الشخصية؛ واجعل أدوات حضور الموارد البشرية التي تعرض الأسماء فقط requires_pii=False
6. share_expires_at (افتراضياً 7 أيام) والإلغاء عند الحذف؛ وchatbot.js يعرض عبر textContent مع markdown آمن؛ وحالة التسجيل السريع تتحقق من is_express برمز موقّع؛ وconversation_lookup يستدعي check_access('read')؛ وentity_token بصلاحية groups='base.group_system'

**يكتمل عندما:** الاختبارات: المستخدم المقيّد بفرع لا يرى إلا فرعه في جداول الحقائق؛ ومستخدم الفوترة لا يستطيع الترحيل عبر screen_button؛ وحمولة XSS في الرد تُعرض كنص؛ ورابط المشاركة المنتهي يُرجع 404؛ ويستطيع الوكيل الافتراضي استخدام hr_leave_pending لمستخدم الموارد البشرية.

يعتمد على: 1a: إعادة فحص كل البوابات عند «التأكيد»

#### 1b: التخزين المؤقت مفعّل افتراضياً، وسياسة الاحتفاظ، وسياق مقتصد (G09, G22, G43)

الوحدات: `ab_ai_base`, `ab_ai_agent`

الخطوات:
1. اضبط ab_ai_base.provider_cache_enabled=True (بيانات noupdate) وأضف مفتاحاً في الإعدادات
2. انقل أقسام الملخّص المفلترة حسب المجموعة إلى ما بعد CACHE_BREAK
3. أضف ‎@api.autovacuum يفرّغ الأعمدة النصية الكبيرة في ai.agent.run بعد N يوماً (ICP، افتراضياً 30) ويحذف الصفوف بعد 180 يوماً؛ واحذف سجلات الاستخدام الأقدم من M يوماً بعد مطابقتها
4. اقصر ‎_record_context_block على حقول عرض النموذج المخزّنة أو المرتبطة، وحدّ x2many بـ 20؛ واجعل العدّ في explain_screen محدوداً

**يكتمل عندما:** اختبار تثبيت جديد: يُستخدم دور النظام والاستدعاء المطابق الثاني يُبلغ عن cached_tokens > 0 (مزوّد محاكى)؛ وبعد التنظيف تصبح التعليمات وJSON الأدوات فارغة في التشغيلات القديمة؛ ويبقى سياق سجل أمر بيع من 300 بند أقل من 6 آلاف حرف.

#### 1b: إيقاف بيئة تشغيل روبوت المحادثة القديمة (G49, G42)

الوحدات: `ab_ai_chatbot`

الخطوات:
1. احذف agent_loop.py، وtool_dispatcher.py الخاص بروبوت المحادثة، وchat_response_cache.py، وأدوات الكتابة القديمة ثنائية المرحلة
2. مرّر on_event صراحةً بدلاً من تبديل tool_registry.call_tool لكل طلب
3. وجّه eval_runner إلى runtime.run

**يكتمل عندما:** طلبان متزامنان من مستخدمَين مختلفَين (اختبار بالخيوط) يتلقى كلٌّ منهما أحداث أدواته فقط على الناقل؛ وتُثبَّت الوحدة وتنجح اختباراتها المتبقية؛ وgrep لا يجد أي استيراد للوحدات المحذوفة.

يعتمد على: 1a: منع المساعد من تأكيد عمليات الكتابة بنفسه

### المرحلة 2 — 8–9 أسابيع (مطوّران)

مساواة نواة الوكيل: اختبارات العقود أولاً، ثم مرونة المزوّدين والسجل القائم على الأجزاء؛ وتجري بالتوازي الجلسات وask_user وتعديل العرض وأدوات إجراءات الخادم وحوكمة المسارات العامة وتنظيم الاعتماديات. تعريف الإنجاز نفسه كما في المرحلة 1.

#### اختبارات عقود المزوّدين وخط أساس التقييم (G42)

الوحدات: `ab_ai_base`, `ab_ai_ui`, `ab_ai_agent`, `ab_ai_plan`, `ab_ai_chatbot`

الخطوات:
1. اختبارات عقود ببيانات مسجّلة لـ 4 مزوّدين × (المحادثة، الأدوات، المخطط، التضمين)
2. اختبارات hoot لعرض AiAgentChat ولـ aiNavigator.sanitizeDirective؛ واختبارات ab_ai_plan لـ check_quota والتجاوز والسياسة
3. مجموعة ذهبية من ≥150 عنصراً بالإنجليزية والعربية، تُقاس على runtime.run فقط
4. مهمة ir.cron ليلية على بيئة التجهيز تشغّل odoo-bin --test-tags والتقييم عبر البوابة بمزوّد حقيقي (يغلق O1) وتحفظ النتائج

**يكتمل عندما:** لدى ab_ai_base وab_ai_plan ‏≥20 اختباراً لكلٍّ منهما؛ ويحفظ التشغيل الليلي دقة الأدوات ونسبة التأصيل وزمن الاستجابة p95 والتكلفة لكل تشغيل، مع الإبلاغ عن الإنجليزية والعربية منفصلتين؛ ويُسجَّل خط أساس قبل بدء العمل على السجل.

#### متطلبات صورة المستأجر وقاعدة البيانات (G16, G20, G46)

الوحدات: `dockerfile (صورة المستأجر)`, `ab_ai_plan (التهيئة)`, `ab_ai_agent`

الخطوات:
1. أضف jsonschema وpdfminer.six إلى dockerfile/requirements-extra.txt وإلى external_dependencies المقابلة (متطلبات Odoo 18 تثبّت PyPDF2 فقط، الذي يستخرج العربية بشكل ضعيف)
2. افحص امتداد pgvector أثناء التهيئة وسجّل توفره لكل مستأجر
3. تحقّق من ربط مجلد الحاوية لكل مستودع تُضاف إليه وحدة (saas-share، saas-client، saas-branches)
4. انشر الصورة المعاد بناؤها عبر لوحة التحكم

**يكتمل عندما:** نقطة فحص على كل مستأجر تُبلغ عن إصدارات jsonschema وpdfminer وpgvector؛ ومسارات الوحدات تُحلّ بعد ‎-u على كل مستأجر.

#### مرونة المزوّدين، وكتالوج دليل الأسعار، والمخرجات المنظّمة (G08)

الوحدات: `ab_ai_base`, `ab_ai_gateway`, `ab_ai_agent`

الخطوات:
1. إعادة محاولة مع تذبذب عشوائي في ab_ai_base ‏(429/500/502/503/529، مع احترام Retry-After، ومحاولتان كحد أقصى)
2. أضف deprecated_on وreplacement_model إلى ai.usage.price.book؛ وادمج ai.token.pricing فيه (أو اشتق أحدهما من الآخر) لتقرأ البوابة والمسار المباشر جدولاً واحداً
3. مهمة مجدولة ليلية لفحص الصحة وإعادة الربط على صفوف دليل الأسعار
4. إعداد تفكير لكل نموذج (تحقّق مما إذا كان gemini-2.5-pro يقبل thinkingBudget=0 في مسارَي النص والرؤية)
5. response_schema لكل مزوّد؛ ومرّر temperature (حيث تُقبل) وmax_tokens وmodel_class في المسار المباشر

**يكتمل عندما:** تغطي اختبارات العقود إعادة المحاولة ومخرجات المخطط وإعداد التفكير لكل مزوّد؛ ويُعاد ربط النموذج الموسوم كمهمل ببديله دون استدعاءات فاشلة؛ ويغيّر response_style للوكيل قيمة temperature في الوضع المباشر على النماذج التي تقبلها.

يعتمد على: اختبارات عقود المزوّدين وخط أساس التقييم, 1b: أسماء ميزات مفتوحة وقياس دقيق

#### سجل رسائل قائم على الأجزاء (G10)

الوحدات: `ab_ai_base`, `ab_ai_agent`, `ab_ai_gateway`, `ab_ai_client`

الخطوات:
1. عرّف بنية الرسالة (الدور + الأجزاء: text، tool_call، tool_result، inline_data، provider_data)
2. محوّلات تسلسلية لـ OpenAI (دور tool)، وAnthropic (‏tool_use/tool_result مع cache_control على الكتلة الأخيرة)، وGemini (‏functionCall/functionResponse)
3. أعد كتابة حلقة الخطوات في بيئة التشغيل لتُلحق الأجزاء؛ وأبقِ المسار النصي خلف علم ICP
4. يضيف المركز 'messages_v1' إلى GATEWAY_CAPABILITIES ويقبل messages[] على ‎/analyze و‎/stream؛ ولا يرسل المستأجرون messages[] إلا عندما يكون config.has_capability('messages_v1') صحيحاً

**يكتمل عندما:** على المجموعة الذهبية: دقة الأدوات ≥90% بالإنجليزية و≥85% بالعربية دون تراجع عن المسار النصي؛ وcached_tokens > 0 في الخطوة الثانية وما بعدها؛ وصفر إعادات محاولة بسبب MALFORMED_FUNCTION_CALL في Gemini؛ والإبلاغ عن زمن الاستجابة p95 والتكلفة لكل تشغيل مقارنة بخط الأساس.

يعتمد على: مرونة المزوّدين، وكتالوج دليل الأسعار، والمخرجات المنظّمة

#### الجلسات في النواة (G21)

الوحدات: `ab_ai_agent`, `ab_ai_chatbot`

الخطوات:
1. أضف ai.agent.session وai.agent.session.message (‏envelope_json مع حقل JSON للأجزاء قابل للفراغ، والوكيل، ومرساة السجل، والشركة) مع قواعد سجلات تقصرها على صفوف المستخدم
2. انقل ai.chat.conversation وai.chat.message؛ ويفوّض ab_ai_chatbot التخزين ويحتفظ بالواجهات
3. لخّص السجل بفئة نموذج منخفضة التكلفة متى تجاوز ميزانية الرموز
4. يتحقق conversation_lookup من صلاحية القراءة أولاً؛ وأضف سياسة احتفاظ للجلسات

**يكتمل عندما:** دون ab_ai_chatbot يحتفظ الكونسول بسجله؛ ومعه تعيد المحادثات المنقولة عرض مخططاتها (تشغيل تجريبي على نسخة من FAYIAPROD)؛ ولا يستطيع المستخدم فتح جلسة لسجل لا يستطيع قراءته.

#### ask_user وتعديل العرض في مكانه (G12, G17)

الوحدات: `ab_ai_agent`, `ab_ai_ui`, `ab_ai_command`

الخطوات:
1. أضف أداة ask_user وكتلة عرض 'question' (اختيارات، اختيار متعدد، نص حر؛ وتُنشر الإجابة كدورة تالية مع question_id)
2. استخدمها لالتباس المحلِّلات ولـ need_info في create_record؛ وافرضها عند max_hops
3. تحقّق من نطاقات open_list/open_pivot/open_graph وتجميعاتها ومقاييسها عبر ai.screen.context._domain_ok وfields_get بصلاحيات المستخدم
4. توجيه 'adjust' اختياري يُطبَّق على SearchModel الحالي (تحقّق من واجهة Odoo 18 أولاً)، مع تعقيمه على العميل
5. تسميات عربية في ar.po

**يكتمل عندما:** 'اعرض الفواتير غير المدفوعة للراجحي مجمّعة حسب الشهر' يضيّق القائمة المفتوحة في مكانها؛ والشريك الملتبس يُظهر شرائح اختيار؛ والحقل الوهمي في نطاق يرسله النموذج يُرفض على الخادم.

#### إجراءات الخادم كأدوات، مع التحقق من الوسائط (G16)

الوحدات: `ab_ai_agent`

الخطوات:
1. تحقّق من وسائط الأدوات في dispatch() ‏(jsonschema أو مدقّق مبسّط) وأرجِع أخطاء ok=False يستطيع النموذج التصرف بناءً عليها
2. اجعل التأكيد أولاً دائماً لحالات إجراءات الخادم التي تكتب؛ ومرّر active_model/active_id عندما تستهدف الأداة سجلاً
3. أضف مفتاح 'استخدام في ذكاء غيمة' (الاسم، الوصف، المخطط) في نموذج ir.actions.server، مترجماً

**يكتمل عندما:** الاختبارات: الوسيط غير الصالح يُرجع خطأ تحقق دون تشغيل؛ وإجراء object_write ينتج إجراءً معلّقاً؛ وإجراء الشيفرة يرى السجل النشط.

يعتمد على: متطلبات صورة المستأجر وقاعدة البيانات

#### حوكمة المسارات العامة (G07)

الوحدات: `ab_ai_gateway`, `ab_ai_plan`, `ab_ghaima_ai_embed`, `ab_ghaima_website_chatbot`, `ab_ai_express_signup`

الخطوات:
1. صفوف ميزانية للمنصة بسقوف يومية صارمة بالدولار لـ embed:* وexpress_signup وwebsite_chatbot؛ وميزة مستقلة للتضمين
2. وجّه روبوت الموقع عبر process_request مع سجل محفوظ على الخادم
3. قِس ‎/embed (الحصة، حد المعدّل، سجل الاستخدام)
4. قيّد model_override بفئات النماذج المسموحة في الباقة؛ ومرّر max_tokens وtemperature

**يكتمل عندما:** كل استدعاء عام يكتب صفاً في ai.usage.log تحت ميزته الخاصة؛ وعند بلوغ السقف تُرجع الأداة رسالة 'مشغول' مترجمة؛ ولا يستطيع مستأجر باقة Starter فرض أقوى نموذج.

يعتمد على: 1b: أسماء ميزات مفتوحة وقياس دقيق

#### تنظيم الاعتماديات: جسور لكل تطبيق (G50)

الوحدات: `ab_ai_chatbot`, `ab_ai_chatbot_scan_docs (جديدة، auto_install)`, `ab_manager_agents`, `ab_account_reports_ai`

الخطوات:
1. انقل رقعة الإرفاق والكاميرا إلى ab_ai_chatbot_scan_docs
2. انقل أدوات المالية والمبيعات في روبوت المحادثة إلى جسور لكل تطبيق
3. قسّم مواضيع المجالات في ab_manager_agents إلى جسور
4. أعد بناء ab_account_reports_ai على ab_ai_agent

**يكتمل عندما:** يُثبَّت ab_ai_chatbot على قاعدة بيانات لا تحتوي إلا hr؛ ولم يعد ab_account_reports_ai يعتمد على ab_ai_client؛ ويترقّى المستأجرون الحاليون دون فقدان بيانات على نسخة من FAYIAPROD.

يعتمد على: 1b: إيقاف بيئة تشغيل روبوت المحادثة القديمة

### المرحلة 3 — 7–8 أسابيع (مطوّران)

المعرفة والواجهات: RAG مع الاستشهادات، والمحادثة حول الملفات، وذكاء اصطناعي في المحرر والمُنشئ موجّه عبر البوابة، وحزم تعليمات لكل تطبيق على التقارير المُدقَّقة، ومقترحات جماعية، وسجلات قابلة للنقر، وبحث على الويب، وتحسينات العربية. تعريف الإنجاز نفسه كما في المرحلة 1.

#### ab_ai_knowledge: مصادر المعرفة والاستشهادات (G20)

الوحدات: `ab_ai_knowledge (جديدة، saas-share)`, `ab_knowledge_base_ai (توسيعها كجسر لمصدر قاعدة المعرفة)`, `ab_ai_base`, `ab_ai_gateway`

الخطوات:
1. أضف ai.agent.source ‏(kb_article، attachment، url؛ شجرة؛ حالة؛ is_active؛ restrict_to_sources على ai.agent) وai.agent.chunk باستخدام ai.semantic.index.provision
2. مقالات قاعدة المعرفة أولاً (حزم ab_knowledge_base_* العشر)، ثم المرفقات (index_content؛ نص PDF عبر pdfminer.six)، ثم الروابط
3. جلب الروابط عبر حارس جديد قابل للتهيئة في ab_ai_base: ‏https فقط، والمنفذ 443، دون بيانات مستخدم، وعنوان IP قابل للتوجيه عالمياً، والاتصال بالعنوان المحلول، دون إعادة توجيه، وحدود للحجم ونوع المحتوى؛ للمسؤولين فقط؛ ويبقي ghaima_base قائمة السماح الثابتة
4. تقسيم بنحو 2000 حرف، وإزالة التكرار بالمجموع الاختباري، وتضمين دفعي عبر ‎/embed المقيس في البوابة بمهمة مجدولة مُحفَّزة
5. استرجاع بصلاحيات المستخدم ببحث هجين (متجهات + pg_trgm)، مفلتر بصلاحية القراءة لكل مصدر، في الجولة الأولى فقط
6. اربط citation.apply_numeric_citations؛ وأضف كتلة SourceList في ab_ai_ui وتبويب «المعرفة» في الكونسول؛ وواجهة عربية

**يكتمل عندما:** الاستدعاء العربي recall@5 ≥0.8 على مجموعة أسئلة من قاعدة المعرفة (يُؤكَّد الهدف بعد أول خط أساس)؛ والإجابات تحمل استشهادات [n] مرتبطة بالمصادر؛ والمستخدم الذي لا يملك صلاحية على مقال مقيّد لا يحصل على أجزاء منه؛ وبديل JSON يعمل دون pgvector؛ وحارس الروابط يرفض عناوين IP الخاصة وإعادة التوجيه والمنافذ غير 443.

يعتمد على: متطلبات صورة المستأجر وقاعدة البيانات, حوكمة المسارات العامة

#### قراءة المرفقات في المحادثة (G46)

الوحدات: `ab_ai_agent`, `ab_ai_base`, `ab_ai_chatbot_scan_docs`

الخطوات:
1. أضف أداة read_attachment إلى نواة ab_ai_agent دون اعتماد على الماسح: تحقّق من صلاحية القراءة على res_model/res_id بهوية المستخدم، وحدود للصفحات والحجم، ومسار الرؤية في ab_ai_base مع ميزة البوابة 'document_qa'
2. اقبل الرفع في ‎/ai_agent/run
3. يعرض الإرفاق في المحادثة خيارَي 'اسأل عن هذا الملف' أو 'امسحه كمستند' (مسار الماسح يقع في جسر المسح)

**يكتمل عندما:** 'لخّص العقد المرفق' على ملف PDF عربي من 40 صفحة يُجاب من N صفحة على الأكثر (ICP)؛ ويُرفض مرفق على سجل لا يستطيع المستخدم قراءته؛ ويظهر الاستخدام تحت 'document_qa'.

يعتمد على: متطلبات صورة المستأجر وقاعدة البيانات

#### ab_ai_composer: الصياغة في المحرر والبريد عبر البوابة (G24, G25)

الوحدات: `ab_ai_composer (جديدة، saas-share)`, `ab_ai_composer_account (جسر جديد، auto_install مع account)`, `ab_ai_agent`

الخطوات:
1. ورّث أسلوب generate_text في html_editor (يغطي ‎/html_editor/generate_text و‎/web_editor/generate_text ونافذتَي الترجمة والبدائل) ووجّهه عبر llm_adapter بالميزة 'compose' بلغة المستخدم؛ وأزل العلامة التجارية من تسميات النافذة
2. أضف سياق السجل (حقول السجل وسجل المحادثات الحديث، مقروءة بصلاحيات المستخدم) إلى مسار mail_composer_chatgpt الأصلي
3. الجسر: إجراء صياغة في account.move.send.wizard (نص html_mail) بلغة الشريك؛ ولا إرسال تلقائي أبداً
4. سجّل command_provider لـ 'اسأل ذكاء غيمة' وأوامر الشرطة المائلة في Ctrl+K

**يكتمل عندما:** مع محاكاة iap_jsonrpc وwebsite._OLG_api_rpc لا يصل أي طلب إلى خادم OLG (معالج إعداد الموقع موجّه أو مستثنى صراحةً)؛ وتظهر استدعاءات المحرر والمُنشئ في ai.usage.local.log تحت 'compose'؛ ومسودة بريد الفاتورة تستخدم لغة الشريك ومبالغ الفاتورة.

يعتمد على: 1a: احتواء خروج بيانات OLG إلى Odoo واستعادة مزوّد Claude, 1b: أسماء ميزات مفتوحة وقياس دقيق

#### حزم تعليمات لكل تطبيق وأدوات التقارير المُدقَّقة (G23, G34, G40)

الوحدات: `ab_ai_agent`, `ab_ai_agent_sale`, `ab_ai_agent_purchase`, `ab_ai_agent_stock`, `ab_ai_agent_pos`, `ab_ai_agent_project`, `ab_ai_agent_calendar`, `ab_ai_agent_hr (saas-share)`, `ab_ai_agent_account_reports (جديدة، saas-accounting)`

الخطوات:
1. اعرض شرائح سجل المحادثات والمساعد العائم مفلترة على context_model الموجود مع surfaces
2. أطلق حزم بيانات فقط تُثبَّت تلقائياً بتعليمات عربية وإنجليزية، إضافة إلى مهارتين عامتين 'لخّص سجل المحادثات' و'صُغ متابعة' ومواضيع للمطاعم (هندسة القائمة، الهدر، ساعات الذروة)
3. ab_ai_agent_account_reports: ‏report_list وget_values وexpand_line وopen على ab.account.report بصلاحيات المستخدم، مقصورة على التقارير المُدقَّقة (قائمة الدخل، الميزانية العمومية، ميزان المراجعة، ضريبة القيمة المضافة)، مع الإبقاء على استبعاد is_year_end_closing
4. ادمج ab_account_reports_ai في الجسر على فئة ميزة صالحة

**يكتمل عندما:** على نسخة من FAYIAPROD تساوي أرقام get_values واجهة التقرير للخيارات نفسها، مع استبعاد قيود إقفال نهاية السنة من قوائم الدخل؛ ولا يُعرض أي تقرير غير مُدقَّق؛ وفي نموذج sale.order لا تظهر إلا المهارات ذات context_model ‏sale.order وواجهة سجل المحادثات، بتسميات عربية؛ و'لماذا انخفض صافي الربح هذا الشهر؟' يستدعي get_values وexpand_line.

يعتمد على: 1b: أسماء ميزات مفتوحة وقياس دقيق, مراحل تدقيق التقارير المحاسبية 2–4 (saas-accounting، خارج هذه الخطة) لأي تقرير خارج قائمة السماح

#### مقترحات جماعية وسجلات قابلة للنقر (G47, G48)

الوحدات: `ab_ai_agent`, `ab_ai_ui`

الخطوات:
1. إجراء معلّق دفعي يحمل data_table للفروقات: حد 50 سجلاً، وتأكيد واحد، وفحص كتابة لكل سجل، ونقطة حفظ لكل سجل، ونتائج لكل سجل؛ وتسري قواعد المسودات فقط
2. row_ref {model, id} على صفوف data_table، يُتحقَّق منه على الخادم بـ check_access ويُفتح عبر aiNavigator

**يكتمل عندما:** 'أسند هؤلاء العملاء المحتملين الـ 12 إلى أحمد' ينتج مقترحاً واحداً وتأكيداً واحداً، ويُبلَّغ عن السجل الذي لا يستطيع المستخدم الكتابة عليه كفاشل بينما تنجح البقية؛ والنقر على صف يفتح السجل؛ وrow_ref مزوّر لسجل غير مقروء يُرفض.

يعتمد على: 1a: إعادة فحص كل البوابات عند «التأكيد»

#### البحث على الويب عبر البوابة (G18)

الوحدات: `ab_ai_gateway`, `ab_ai_plan`, `ab_ai_agent`, `ab_ai_ui`

الخطوات:
1. أضف الميزة 'web_search' في المركز باستخدام أداة التأصيل أو البحث لدى المزوّد (تحقّق من أسماء الواجهات الحالية)؛ مقيّدة بالباقة
2. أضف أداة web_search لدى المستأجر، لا تُعرض إلا عند ضبط agent.allow_web_grounding وعدم حصر الإجابات في المصادر
3. خزّن مصادر الويب بمعرّفات uuid واعرض الاستشهادات في كتلة SourceList؛ ولا تجلب أبداً روابط يقدّمها المستخدم

**يكتمل عندما:** سؤال عن أخبار حديثة للبنك المركزي السعودي أو هيئة الزكاة والضريبة والجمارك يُرجع مصادر مستشهداً بها؛ ويزداد عدّاد web_grounding_calls؛ ولا تُعرض الأداة عندما لا تتضمنها الباقة.

يعتمد على: ab_ai_knowledge: مصادر المعرفة والاستشهادات

#### تحسينات العربية والإخفاء الانتقائي للبيانات الشخصية (G41)

الوحدات: `ab_ai_agent`, `ab_ai_gateway`, `ab_ai_plan`, `ab_ai_express_signup`

الخطوات:
1. انقل العبارات الشرطية العربية/الإنجليزية المكتوبة مباشرة إلى ‎_() وar.po
2. استبدل plan.allow_pii الكلّي بإخفاء انتقائي: أبقِ أرقام ضريبة القيمة المضافة والسجل التجاري والهاتف، واستمر في إخفاء أرقام البطاقات والآيبان والهوية الوطنية
3. أضف تفضيلاً لكل مستخدم لنظام الأرقام؛ وأصلح تعليمات التسجيل التي تذكر 'Odoo 18'

**يكتمل عندما:** اختبارات تبديل اللغة لا تُظهر نقاط بدء أو تأكيدات غير مترجمة؛ ويصل رقم ضريبة القيمة المضافة للمستأجر إلى الوكيل دون حجب بينما تُحجب أرقام البطاقات والآيبان والهوية الوطنية.

### المرحلة 4 — 7–10 أسابيع (مطوّران)

الأتمتة والتشغيل البيني: حقول الذكاء الاصطناعي، وإجراءات الخادم بالذكاء الاصطناعي، والوكلاء المجدولون، وMCP للقراءة فقط. قائمة الانتظار، غير مجدولة: ab_ai_livechat في saas-share (مستقلة عن القناة، مع _crm و_website_sale ومحوّل واتساب وارد)، وab_ai_command_crm وab_ai_agent_crm، وجسر وكيل الموارد البشرية، وOAuth 2.1 لـ MCP، وفجوات P3 المؤجلة. تعريف الإنجاز نفسه كما في المرحلة 1.

#### ab_ai_fields (G30)

الوحدات: `ab_ai_fields (جديدة، saas-share)`, `ab_ai_base`

الخطوات:
1. أضف ai_enabled وai_prompt (مع عناصر نائبة للحقول) على ir.model.fields؛ وابدأ بأنواع char وtext وhtml وselection وmany2one
2. أداة OWL 'املأ بالذكاء الاصطناعي': مخرجات منظّمة مع القيم المسموحة (قيم معدّدة لـ selection وmany2one)؛ يقبلها المستخدم ثم تُكتب بصلاحياته
3. مهمة مجدولة دفعية للقيم الفارغة ضمن ai.usage.local.budget وسقف لكل تشغيل؛ وخزّن الإخفاقات حتى لا يُعاد المحاولة بلا نهاية

**يكتمل عندما:** يُملأ حقل 'الوصف العربي' للمنتج بالنقر ويطابق المخطط؛ وتتوقف المهمة المجدولة عند بلوغ الميزانية؛ وتُرفض قيم selection خارج المجموعة المسموحة.

يعتمد على: مرونة المزوّدين، وكتالوج دليل الأسعار، والمخرجات المنظّمة

#### ab_ai_server_actions (G31)

الوحدات: `ab_ai_server_actions (جديدة، saas-share؛ تعتمد على base_automation وab_ai_agent وab_ai_fields)`

الخطوات:
1. أضف عبر selection_add حالة ذكاء اصطناعي على ir.actions.server مع تعليمات HTML، ومستخدم مالك إلزامي (ليس المستخدم الأعلى)، وقائمة سماح للأدوات على النموذج نفسه
2. شغّل runtime.run دون واجهة مع env(user=owner, su=False) وسياسة غير تحاورية تتجاهل التعليمات الموجودة في المستندات؛ وارفض التشغيل عندما يكون env.su أو uid == SUPERUSER_ID
3. لا يجوز الكتابة إلا للأدوات الموسومة automation_safe؛ ولا ترحيل ولا تأكيد للمحاسبة أبداً
4. سجّل كل تشغيل في سجل المحادثات مرتبطاً بـ ai.agent.run؛ وأضف تقييماً محسوباً بالذكاء الاصطناعي لـ object_write

**يكتمل عندما:** لا يمكن حفظ قاعدة دون مالك؛ والتشغيل الذي تطلقه المهمة المجدولة في base.automation ينفَّذ بهوية المالك لا المستخدم الأعلى؛ وتُرفض الأداة خارج قائمة السماح؛ ويظهر كل تشغيل في سجل المحادثات مع رابط إلى تشغيله.

يعتمد على: ab_ai_fields, إجراءات الخادم كأدوات، مع التحقق من الوسائط

#### ab_ai_agent_automation: وكلاء مجدولون ومُطلقون بالأحداث (G32, G11)

الوحدات: `ab_ai_agent_automation (جديدة، saas-share)`, `ab_ai_agent`

الخطوات:
1. أضف ai.agent.automation (الوكيل؛ المحفّز: جدول زمني أو on_create أو on_write أو تاريخ؛ النموذج؛ النطاق؛ التعليمات؛ المالك؛ التسليم: ملاحظة في سجل المحادثات أو صندوق وارد أو بريد؛ الميزانية)
2. نفّذ في الخلفية بمؤشر جديد وحالة تشغيل محفوظة، بهوية المالك مع su=False؛ وقدّم التشغيل التالي حتى بعد الفشل؛ وأضف مراقباً للتشغيلات العالقة
3. تتحول عمليات الكتابة إلى إجراءات معلّقة في صندوق وارد المالك؛ ولا شيء يُعتمد تلقائياً
4. أضف تبويب «الأتمتة» في الكونسول (قائمة، تفعيل/تعطيل، تشغيل الآن، السجل)؛ واستخدم فئة الميزة 'automation'

**يكتمل عندما:** 'ملخص الفواتير المتأخرة' اليومي في الساعة 08:00 ينشر ملاحظة عربية للمالك؛ والتشغيل الفاشل لا يُعاد في كل دورة للمهمة المجدولة؛ وسقف الميزانية يوقف التكاليف المنفلتة.

يعتمد على: الجلسات في النواة, ab_ai_server_actions

#### ab_ai_mcp (للقراءة فقط) (G33)

الوحدات: `ab_ai_mcp (جديدة، saas-share؛ تعتمد على ab_ai_agent وab_api_base)`

الخطوات:
1. ‏POST /mcp بـ JSON-RPC يعالج initialize وping وtools/list وtools/call، خلف نطاق 'mcp' مسجّل عبر register_scope_validator
2. اعرض سجلات ai.agent.tool الموسومة mcp_enabled (أدوات القراءة افتراضياً) عبر tool_dispatcher.dispatch بهوية مستخدم الرمز
3. أضف أداة سياق أوّلي (المنطقة الزمنية، الشركة، ملاحظة UTC)، وحد معدّل لكل رمز على نمط rate_limiter في ab_mobile_ai_api، وسجلات استخدام تحت الفئة 'mcp'
4. تُرجع أدوات الكتابة رابط إجراء معلّق للتأكيد داخل غيمة؛ واشتراك اختياري لكل شركة مع سجل تدقيق وصلاحية زمنية للرمز

**يكتمل عندما:** يسرد عميل MCP الأداتين find_records وquery_data ويستدعيهما بهوية مستخدم الرمز؛ وتجيب أدوات التاريخ بالمنطقة الزمنية لمستخدم الرمز؛ وتُرجع الدفعة فوق الحد 429؛ ويُرجع رمز شركة معطّلة 403؛ ولا يُنفَّذ استدعاء الكتابة أبداً دون تأكيد داخل التطبيق.

يعتمد على: إجراءات الخادم كأدوات، مع التحقق من الوسائط

## المخاطر

| الخطر | المعالجة |
|---|---|
| الترخيص: وحدات الذكاء الاصطناعي في Odoo 20 مرخّصة بـ OEEL-1. ونسخ التعليمات أو المخططات أو الشيفرة إلى وحداتنا ab_* المرخّصة بـ LGPL سيلوّثها ترخيصياً. | قاعدة الغرفة النظيفة: يوثّق هذا التحليل السلوك فقط. ويجب ألا يفتح المنفّذون ملفات OEEL أثناء كتابة الشيفرة، وتُكتب التعليمات ومخططات الأدوات من الصفر. وتتحقق مراجعة الشيفرة من ذلك. |
| نقل البيانات عبر الحدود وفق نظام حماية البيانات الشخصية (PDPL): كل استدعاء عبر البوابة أو مباشر يرسل بيانات ERP، بما فيها البيانات الشخصية للعملاء عند ضبط allow_pii، إلى OpenAI أو Google أو Anthropic خارج المملكة. | اتفاقية معالجة بيانات مع كل مزوّد؛ وإشعار موافقة ومعالجة بيانات بالعربية لكل مستأجر؛ وخيار لكل باقة للتوجيه عبر Ollama أو نموذج مستضاف في المملكة؛ وحجب البيانات الشخصية مفعّل افتراضياً باستثناء معرّفات الأعمال المعتمدة (G41). |
| معرّفات نماذج المزوّدين تُوقف دون إشعار. وقد حدث ذلك بالفعل: جميع معرّفات Claude التي نقدّمها متقاعدة ومزوّد Claude يفشل اليوم. | إصلاح عاجل في المرحلة 1 إلى المعرّفات الحالية؛ ثم deprecated_on وreplacement_model على ai.usage.price.book، واستدعاء فحص صحة ليلي لكل نموذج مُعدّ، وإعادة ربط تلقائية. |
| دفع llm_mode='gateway' إلى المستأجرين المرتبطين قد يقطع الخدمة عن مستأجرين يعتمدون اليوم على مفاتيحهم الخاصة، أو يوقف الذكاء الاصطناعي أثناء انقطاع المركز. | تبقى أخطاء النقل ترتدّ إلى البديل؛ واشتراك اختياري صريح عبر ICP يتحكم فيه المركز للمستأجرين المسموح لهم باستخدام مفاتيحهم؛ والإعلان قبل الإطلاق؛ والنشر مستأجراً تلو الآخر عبر لوحة التحكم بعد اختبار O1 السريع. |
| إعادة هيكلة السجل القائم على الأجزاء (G10) تمس أربعة محوّلات تسلسلية للمزوّدين وبيئة التشغيل والبوابة، وقد تسبب تراجعاً في استدعاء الأدوات لدى جميع المستأجرين دفعة واحدة. | اختبارات العقود وخط أساس التقييم أولاً؛ ويعلن المركز 'messages_v1' ويبقي المستأجرون المسار النصي خلف علم ICP؛ وعتبات المجموعة الذهبية تشترط الإصدار؛ والنشر مستأجراً تلو الآخر. |
| أدوات الوكيل على التقارير المحاسبية التي وجدها التدقيق خاطئة أو معطّلة ستقدّم إجابات خاطئة بثقة. | قائمة سماح بالتقارير المُدقَّقة فقط (قائمة الدخل، الميزانية العمومية، ميزان المراجعة، ضريبة القيمة المضافة)؛ ومعيار القبول يقارن get_values بواجهة التقرير على نسخة من FAYIAPROD؛ وتوسيع القائمة فقط مع اكتمال مراحل التدقيق 2–4. |
| نقل المحادثات من ab_ai_chatbot إلى النواة (G21) وإيقاف بيئة التشغيل القديمة تغييرات في البيانات والسلوك على مستأجرين فعليين. | سكربت ما قبل الترحيل ينسخ البيانات، وتبقى النماذج القديمة للقراءة فقط لإصدار واحد. تشغيل تجريبي على نسخة من FAYIAPROD والتحقق من إعادة عرض المغلّفات قبل النشر. |
| قد تفتقر بعض عناقيد PostgreSQL لدى المستأجرين إلى امتداد pgvector، ما يبطئ RAG والبحث الدلالي. | الفحص عند التهيئة وتسجيل التوفر. استخدام بديل جيب التمام (cosine) بـ JSON مع حد لحجم المجموعة، وإضافة الامتداد إلى صور المستأجرين، والإبقاء على البحث الهجين بـ pg_trgm لتحسين الاستدعاء بالعربية. |
| الأتمتة دون واجهة وحقول الذكاء الاصطناعي قد ترفع التكاليف بشكل منفلت (حلقات المهام المجدولة، التعبئة الخلفية الكبيرة). | ميزانية لكل قاعدة ولكل تشغيل، إضافة إلى الفحص المسبق عبر ai.usage.local.budget. وتقديم التشغيل التالي حتى بعد الفشل. وحدود دفعات لكل تشغيل مجدول وسقف على مستوى الباقة لفئة 'automation'. |
| حقن التعليمات (prompt injection) عبر مصادر RAG أو المرفقات أو نصوص سجل المحادثات أو مدخلات المحادثة العامة لتوجيه الوكلاء الذين يستخدمون الأدوات. | تغليف نتائج الأدوات والأجزاء المسترجعة ونصوص الملفات في أسوار بيانات. والإبقاء على قوائم سماح للأدوات لكل واجهة (القنوات العامة لا تحصل على أدوات كتابة). وحذف وسائط التأكيد من مدخلات النموذج (G45)، والإبقاء على التأكيد أولاً لكل عملية كتابة، وإضافة مجموعة تقييم للحقن. |
| يرسل MCP بيانات ERP إلى عملاء LLM خارجيين، ما يثير مخاوف تتعلق بنظام حماية البيانات الشخصية وتوطين البيانات في المملكة. | معطّل افتراضياً، واشتراك اختياري لكل شركة، ومجموعة أدوات للقراءة فقط، وسجل تدقيق لكل استدعاء، وحدود معدّل، وصلاحية قصيرة للرمز، وصفحة موافقة للمسؤول بالعربية توضّح وجهة البيانات. |
| إعادة تعريف أسلوب generate_text الأصلي، أو تعطيل نقاط OLG، قد يعطّل ميزات المحرر عند تحديثات Odoo 18. | وراثة أسلوب المتحكم بدلاً من استبدال المسار، والحفاظ على عقد الاستجابة (نص، أو UserError)، وعرض رسالة واضحة عند التعطيل، وإضافة اختبار hoot يقود النافذة الأصلية. |
| تغيير حقل الميزة في البوابة من Selection إلى Char يؤثر على التقارير وتقييد الباقات والملخصات الحالية. | ترحيل القيم كما هي، وإضافة ربط بالفئات مع قيمة افتراضية 'custom'، والإبقاء على قوائم ميزات الباقات كفئات، وتعبئة ai.usage.summary بأثر رجعي. |
| تستمر التشغيلات المتزامنة في إشغال عمّال HTTP حتى يُنجز G11. | الإبقاء على max_hops عند 6، وتحديد أحجام نتائج الأدوات، وتطبيق مهلات الاستعلام في query_data، ونقل الأتمتة إلى التنفيذ في الخلفية أولاً. |

</div>

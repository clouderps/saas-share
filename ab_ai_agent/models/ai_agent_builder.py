# -*- coding: utf-8 -*-
"""Agent Console builder — add tools, skills and topics without code.

* A **tool** is a preset over the generic data tools: one model the user
  picks + one operation (search / count / read / open / create / update)
  + an optional fixed filter and field list. No Python, no server action;
  at run time it goes through the same gates as every tool and runs as
  the person chatting (see services/generic_data.run_preset).
* A **skill** is a prompt template with {placeholders}.
* A **topic** is instructions + a set of tools.

Who can build: the same people who can edit agents (``ai.agent`` write =
AI Designer). Everything runs as the caller, never sudo — the ORM ACL on
ai.agent.tool / .skill / .topic is the real gate, the check here only
gives a clean message. Only builder-made records (``is_custom``) can be
edited or removed here; module-shipped ones are protected.
"""
from __future__ import annotations

import json
import re
import string

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from ..services import generic_data

SKILL_PLACEHOLDERS = ('message', 'model', 'id', 'record_name')

OP_LABELS = {
    'search': ('Find', 'بحث في'),
    'count': ('Count', 'عدد'),
    'read': ('Show details of', 'تفاصيل'),
    'open': ('Open list of', 'فتح قائمة'),
    'create': ('Create', 'إنشاء'),
    'update': ('Update', 'تعديل'),
}
OP_HELP = {
    'search': ('Find {label} records the user can see and list them. Optional extra filter.',
               'يبحث في سجلات {label} التي يستطيع المستخدم رؤيتها ويعرضها. يمكن إضافة فلتر.'),
    'count': ('Count {label} records the user can see. Optional extra filter.',
              'يحسب عدد سجلات {label} التي يستطيع المستخدم رؤيتها.'),
    'read': ('Show the details of one {label} record (by number, name or the one on screen).',
             'يعرض تفاصيل سجل واحد من {label} (بالرقم أو الاسم أو المفتوح على الشاشة).'),
    'open': ('Open the {label} list for the user, optionally filtered.',
             'يفتح قائمة {label} للمستخدم مع فلتر اختياري.'),
    'create': ('Propose a new {label} record; the user confirms before anything is saved.',
               'يقترح إنشاء سجل جديد في {label}؛ لا يُحفظ شيء قبل تأكيد المستخدم.'),
    'update': ('Propose changes to one {label} record; the user confirms before anything is saved.',
               'يقترح تعديل سجل من {label}؛ لا يُحفظ شيء قبل تأكيد المستخدم.'),
}
OP_CATEGORY = {'search': 'retrieval', 'count': 'retrieval', 'read': 'retrieval',
               'open': 'navigation', 'create': 'write', 'update': 'write'}


def _slug(text, fallback):
    s = re.sub(r'[^a-z0-9]+', '_', (text or '').lower()).strip('_')
    return (s or fallback)[:40]


class AIAgentBuilder(models.Model):
    _inherit = 'ai.agent'

    # ── Guards ─────────────────────────────────────────────────

    @api.model
    def _builder_check(self, model_name='ai.agent.tool', op='create'):
        if not self._console_can_edit() or not self.env[model_name].has_access(op):
            raise AccessError(_('Only AI agent designers can add or change tools, skills and topics.'))

    @api.model
    def _builder_custom(self, model_name, rec_id):
        rec = self.env[model_name].browse(int(rec_id or 0)).exists()
        if not rec:
            raise UserError(_('This item no longer exists.'))
        if not rec.is_custom:
            raise UserError(_('Built-in items are protected. Only items added from the console can be changed here.'))
        return rec

    # ── Pickers ────────────────────────────────────────────────

    @api.model
    def builder_models(self, query='', write=False):
        """Installed models the CALLER can read (and the assistant may
        use), for the model picker."""
        self._builder_check()
        dom = [('transient', '=', False)]
        if query:
            dom += ['|', ('model', 'ilike', query), ('name', 'ilike', query)]
        out = []
        # sudo: model *names* only — ir.model is not readable by every
        # internal user. Each hit is then filtered on the caller's own
        # read access to that model, so nothing they cannot open is listed.
        for m in self.env['ir.model'].sudo().search(dom, limit=200, order='name'):
            if m.model not in self.env or generic_data.model_blocked(self.env, m.model, write=write):
                continue
            if not self.env[m.model].has_access('read'):
                continue
            out.append({'model': m.model, 'name': m.name})
            if len(out) >= 30:
                break
        return out

    @api.model
    def builder_fields(self, model):
        self._builder_check()
        if generic_data.model_blocked(self.env, model) or not self.env[model].has_access('read'):
            raise UserError(_('You cannot use this model.'))
        allowed = generic_data.readable_fields(self.env, self.env[model])
        return sorted(({'name': n, 'string': m.get('string') or n, 'type': m.get('type')}
                       for n, m in allowed.items()), key=lambda f: f['string'].lower())

    @api.model
    def builder_suggest(self, model, op):
        """Auto-suggested names + descriptions, English and Arabic."""
        self._builder_check()
        if op not in generic_data.PRESET_OPS or model not in self.env:
            raise UserError(_('Pick a model and an operation.'))
        label_en = self.env[model].with_context(lang='en_US')._description or model
        label_ar = self.env[model].with_context(lang='ar_001')._description or label_en
        en, ar = OP_LABELS[op]
        hen, har = OP_HELP[op]
        return {'name_en': f'{en} {label_en}', 'name_ar': f'{ar} {label_ar}',
                'description_en': hen.format(label=label_en),
                'description_ar': har.format(label=label_ar)}

    # ── Tools ──────────────────────────────────────────────────

    @api.model
    def _builder_names(self, values, sugg):
        """(English source name, Arabic translation) for a new tool. The
        dialog says which language the typed name is in (``name_lang``);
        the other side comes from the suggestion, and an English name the
        designer rewrote gets no mismatched Arabic suggestion."""
        typed = (values.get('name') or '').strip()
        if values.get('name_lang') == 'ar':
            return sugg['name_en'], typed or sugg['name_ar']
        if not typed or typed == sugg['name_en']:
            return sugg['name_en'], sugg['name_ar']
        return typed, ''

    @api.model
    def _builder_tool_vals(self, values, model, op):
        Model = self.env[model]
        allowed = generic_data.readable_fields(self.env, Model)
        try:
            domain = generic_data.safe_domain(values.get('domain') or [], allowed, Model)
            flds = values.get('fields') or []
            if flds:
                flds = generic_data._pick_fields(flds, allowed, Model)
        except ValueError as e:
            raise UserError(str(e))
        preset = {'model': model, 'op': op, 'domain': [list(d) if isinstance(d, tuple) else d
                                                      for d in domain]}
        if flds:
            preset['fields'] = flds
        if values.get('limit'):
            preset['limit'] = max(1, min(generic_data.MAX_ROWS, int(values['limit'])))
        return preset

    @api.model
    def builder_create_tool(self, values):
        self._builder_check('ai.agent.tool')
        values = values or {}
        model, op = values.get('model'), values.get('op')
        if op not in generic_data.PRESET_OPS:
            raise UserError(_('Pick an operation.'))
        write = op in generic_data.WRITE_OPS
        why = generic_data.model_blocked(self.env, model, write=write)
        if why:
            raise UserError(_('The assistant cannot use this model: %s', why))
        Model = self.env[model]
        if not Model.has_access('read') or (write and not Model.has_access(
                'create' if op == 'create' else 'write')):
            raise UserError(_('You do not have access to this model.'))
        sugg = self.builder_suggest(model, op)
        name_en, name_ar = self._builder_names(values, sugg)
        desc_en = (values.get('description') or '').strip() or sugg['description_en']
        desc_ar = (values.get('description_ar') or '').strip() or sugg['description_ar']
        preset = self._builder_tool_vals(values, model, op)
        Tool = self.env['ai.agent.tool']
        base = f"{op}_{model.replace('.', '_')}"[:48]
        code, n = base, 1
        while Tool.with_context(active_test=False).search_count([('code', '=', code)]):
            n += 1
            code = f'{base}_{n}'
        tool = Tool.with_context(lang='en_US').create({
            'name': name_en,
            'code': code,
            'category': OP_CATEGORY[op],
            'description': desc_en,
            'schema': json.dumps(generic_data.preset_schema(op)),
            'dispatch_kind': 'python',
            # Proposal-only at dispatch (create/update go through the
            # confirm-first pending-action flow), so never a write action.
            'is_write_action': False,
            'allow_end_message': op == 'open',
            'preset_json': json.dumps(preset),
            'preset_model': model,
            'preset_op': op,
            'is_custom': True,
        })
        self._builder_set_ar(tool, 'description', desc_ar)
        self._builder_set_ar(tool, 'name', name_ar)
        if values.get('topic_id'):
            topic = self.env['ai.agent.topic'].browse(int(values['topic_id'])).exists()
            if topic:
                topic.tool_ids = [fields.Command.link(tool.id)]
        return {'id': tool.id, 'code': tool.code, 'name': tool.name}

    @api.model
    def builder_update_tool(self, tool_id, values):
        self._builder_check('ai.agent.tool', 'write')
        tool = self._builder_custom('ai.agent.tool', tool_id)
        values = values or {}
        vals = {}
        typed = (values.get('name') or '').strip()
        name_ar = typed if typed and values.get('name_lang') == 'ar' else ''
        if typed and not name_ar:
            vals['name'] = typed
        if 'description' in values and (values['description'] or '').strip():
            vals['description'] = values['description'].strip()
        if 'active' in values:
            vals['active'] = bool(values['active'])
        if 'domain' in values or 'fields' in values or 'limit' in values:
            old = json.loads(tool.preset_json or '{}')
            merged = {'domain': old.get('domain'), 'fields': old.get('fields'),
                      'limit': old.get('limit'), **values}
            vals['preset_json'] = json.dumps(
                self._builder_tool_vals(merged, tool.preset_model, tool.preset_op))
        # Writing the English source can reset other translations; keep
        # the Arabic name/description unless this edit replaces them.
        keep_ar = {f: tool.with_context(lang='ar_001')[f] for f in ('name', 'description')
                   if f in vals and self.env['res.lang']._lang_get('ar_001')
                   and tool.with_context(lang='ar_001')[f] != tool.with_context(lang='en_US')[f]}
        if vals:
            tool.with_context(lang='en_US').write(vals)
        for f, text in keep_ar.items():
            self._builder_set_ar(tool, f, text)
        if (values.get('description_ar') or '').strip():
            self._builder_set_ar(tool, 'description', values['description_ar'].strip())
        if name_ar:
            # Typed in the Arabic UI: it is the Arabic name; the English
            # source name stays as it was.
            self._builder_set_ar(tool, 'name', name_ar)
        return {'id': tool.id}

    # ── Skills ─────────────────────────────────────────────────

    @api.model
    def _builder_check_template(self, template):
        template = (template or '').strip()
        if not template:
            raise UserError(_('The prompt template cannot be empty.'))
        try:
            names = {f for _l, f, _s, _c in string.Formatter().parse(template) if f is not None}
        except ValueError:
            raise UserError(_('The prompt template has an unbalanced { or }. Use {{ and }} for literal braces.'))
        bad = sorted(n for n in names if n.split('.')[0].split('[')[0] not in SKILL_PLACEHOLDERS
                     or n != n.split('.')[0].split('[')[0])
        if bad:
            raise UserError(_('Unknown placeholder(s): %(bad)s. Allowed: %(ok)s',
                              bad=', '.join('{%s}' % b for b in bad),
                              ok=', '.join('{%s}' % p for p in SKILL_PLACEHOLDERS)))
        return template, names

    @api.model
    def builder_create_skill(self, agent_id, values):
        self._builder_check('ai.agent.skill')
        values = values or {}
        name = (values.get('name') or '').strip()
        if not name:
            raise UserError(_('Give the skill a name.'))
        template, names = self._builder_check_template(values.get('template'))
        ctx_model = (values.get('context_model') or '').strip() or False
        if ctx_model and (generic_data.model_blocked(self.env, ctx_model)
                          or not self.env[ctx_model].has_access('read')):
            raise UserError(_('You cannot use this model.'))
        shared = values.get('shared', True)
        agent = self.browse(int(agent_id or 0)).exists()
        if not shared and not agent:
            raise UserError(_('This agent no longer exists.'))
        Skill = self.env['ai.agent.skill']
        base = _slug(name, 'skill')
        code, n = base, 1
        while Skill.with_context(active_test=False).search_count([('code', '=', code)]):
            n += 1
            code = f'{base}_{n}'
        icon = (values.get('icon') or 'fa-magic').strip()
        if not icon.startswith('fa-'):
            icon = f'fa-{icon}'
        skill = Skill.create({
            'name': name,
            'code': code,
            'description': (values.get('description') or '').strip() or False,
            'icon': re.sub(r'[^a-z0-9-]', '', icon) or 'fa-magic',
            'accent': values.get('accent') if values.get('accent') in dict(
                Skill._fields['accent'].selection) else 'blue',
            'user_prompt_template': template,
            'context_model': ctx_model,
            'requires_record_context': bool(values.get('requires_record_context')
                                            or {'id', 'record_name'} & names),
            'surfaces': 'chatter' if values.get('requires_record_context') else 'chat',
            'is_global': bool(shared),
            'agent_id': False if shared else agent.id,
            'is_custom': True,
        })
        return {'id': skill.id, 'code': skill.code, 'name': skill.name}

    @api.model
    def builder_update_skill(self, skill_id, values):
        self._builder_check('ai.agent.skill', 'write')
        skill = self._builder_custom('ai.agent.skill', skill_id)
        values = values or {}
        vals = {}
        if (values.get('name') or '').strip():
            vals['name'] = values['name'].strip()
        if 'template' in values:
            vals['user_prompt_template'], _n = self._builder_check_template(values['template'])
        for key in ('description', 'icon'):
            if key in values:
                vals[key] = (values[key] or '').strip() or False
        if 'active' in values:
            vals['active'] = bool(values['active'])
        if vals:
            skill.write(vals)
        return {'id': skill.id}

    # ── Topics ─────────────────────────────────────────────────

    @api.model
    def _builder_tools(self, ids):
        return self.env['ai.agent.tool'].browse([int(i) for i in ids or []]).exists()

    @api.model
    def builder_create_topic(self, agent_id, values):
        self._builder_check('ai.agent.topic')
        values = values or {}
        name = (values.get('name') or '').strip()
        if not name:
            raise UserError(_('Give the topic a name.'))
        Topic = self.env['ai.agent.topic']
        base = _slug(name, 'topic')
        code, n = base, 1
        while Topic.with_context(active_test=False).search_count([('code', '=', code)]):
            n += 1
            code = f'{base}_{n}'
        topic = Topic.create({
            'name': name,
            'code': code,
            'description': (values.get('description') or '').strip() or False,
            'instructions': (values.get('instructions') or '').strip() or False,
            'tool_ids': [fields.Command.set(self._builder_tools(values.get('tool_ids')).ids)],
            'is_custom': True,
        })
        agent = self.browse(int(agent_id or 0)).exists()
        if agent and not agent.use_all_capabilities:
            agent.topic_ids = [fields.Command.link(topic.id)]
        return {'id': topic.id, 'code': topic.code, 'name': topic.name}

    @api.model
    def builder_update_topic(self, topic_id, values):
        self._builder_check('ai.agent.topic', 'write')
        topic = self._builder_custom('ai.agent.topic', topic_id)
        values = values or {}
        vals = {}
        if (values.get('name') or '').strip():
            vals['name'] = values['name'].strip()
        for key in ('description', 'instructions'):
            if key in values:
                vals[key] = (values[key] or '').strip() or False
        if 'tool_ids' in values:
            vals['tool_ids'] = [fields.Command.set(self._builder_tools(values['tool_ids']).ids)]
        if 'active' in values:
            vals['active'] = bool(values['active'])
        if vals:
            topic.write(vals)
        return {'id': topic.id}

    # ── Delete ─────────────────────────────────────────────────

    BUILDER_KINDS = {'tool': 'ai.agent.tool', 'skill': 'ai.agent.skill', 'topic': 'ai.agent.topic'}

    @api.model
    def builder_delete(self, kind, rec_id):
        model_name = self.BUILDER_KINDS.get(kind)
        if not model_name:
            raise UserError(_('Unknown item type.'))
        self._builder_check(model_name, 'unlink')
        self._builder_custom(model_name, rec_id).unlink()
        return True

    # ── Helpers ────────────────────────────────────────────────

    @api.model
    def _builder_set_ar(self, rec, field, text):
        """Store the Arabic text as the field's ar_001 translation when
        Saudi Arabic is installed (the console's default UI language)."""
        if not text:
            return
        lang = 'ar_001' if self.env['res.lang']._lang_get('ar_001') else None
        if lang:
            rec.with_context(lang=lang).write({field: text})


class AIBuilderProtect(models.AbstractModel):
    """Module-shipped tools / topics / skills cannot be deleted by a
    designer from any screen; administrators (and module uninstall,
    which runs as superuser) still can."""
    _name = 'ai.agent.builder.protect'
    _description = 'Ghaima AI — protect shipped AI records'

    def unlink(self):
        if not (self.env.su or self.env.user.has_group('base.group_system')):
            if self.filtered(lambda r: not r.is_custom):
                raise UserError(_('Built-in items are protected. Archive them instead.'))
        return super().unlink()


class AIAgentToolProtect(models.Model):
    _name = 'ai.agent.tool'
    _inherit = ['ai.agent.tool', 'ai.agent.builder.protect']


class AIAgentTopicProtect(models.Model):
    _name = 'ai.agent.topic'
    _inherit = ['ai.agent.topic', 'ai.agent.builder.protect']


class AIAgentSkillProtect(models.Model):
    _name = 'ai.agent.skill'
    _inherit = ['ai.agent.skill', 'ai.agent.builder.protect']

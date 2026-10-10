# -*- coding: utf-8 -*-
"""Default agent = all capabilities; generic data tools stay inside the
user's rights; the console builder is designer-only and its tools work
end-to-end through the dispatcher."""
import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services import generic_data, runtime, tool_dispatcher


@tagged('post_install', '-at_install')
class TestFullAccessAndBuilder(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.assistant = cls.env.ref('ab_ai_agent.agent_ghaima_assistant')
        cls.company_b = cls.env['res.company'].create({'name': 'AI Other Co'})
        cls.user = cls.env['res.users'].create({
            'name': 'AI Plain', 'login': 'ai_plain_fab',
            'company_id': cls.env.company.id, 'company_ids': [(6, 0, [cls.env.company.id])],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.designer = cls.env['res.users'].create({
            'name': 'AI Designer', 'login': 'ai_designer_fab',
            'company_id': cls.env.company.id, 'company_ids': [(6, 0, [cls.env.company.id])],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('base.group_partner_manager').id,
                                  cls.env.ref('ab_ai_agent.group_ai_agent_designer').id])],
        })
        Partner = cls.env['res.partner']
        cls.co_a = Partner.create({'name': 'Zyx Visible Co', 'is_company': True,
                                   'company_id': cls.env.company.id})
        cls.person_a = Partner.create({'name': 'Zyx Visible Person', 'is_company': False,
                                       'company_id': cls.env.company.id})
        cls.hidden = Partner.create({'name': 'Zyx Hidden Co', 'is_company': True,
                                     'company_id': cls.company_b.id})

    def _uenv(self, user):
        return self.env(user=user.id, context=dict(self.env.context, ai_screen={}))

    # ── (1) default agent: everything, including later additions ──

    def test_default_agent_flags(self):
        self.assertTrue(self.assistant.use_all_capabilities)
        self.assertTrue(self.assistant.allow_write_actions)
        for code in ('find_records', 'count_records', 'read_record'):
            self.assertIn(code, self.assistant._effective_tools().mapped('code'))

    def test_new_tool_topic_skill_reach_default_agent(self):
        tool = self.env['ai.agent.tool'].create({
            'name': 'Later tool', 'code': 'zz_later_tool', 'description': 'x',
            'category': 'retrieval'})
        topic = self.env['ai.agent.topic'].create({'name': 'Later topic', 'code': 'zz_later_topic'})
        other = self.env['ai.agent'].create({'name': 'Other', 'code': 'zz_other_agent',
                                             'system_prompt': 'x'})
        skill = self.env['ai.agent.skill'].create({
            'name': 'Later skill', 'code': 'zz_later_skill', 'agent_id': other.id,
            'user_prompt_template': '{message}'})
        agent = self.assistant.with_user(self.user)
        self.assertIn(tool, agent._effective_tools())
        self.assertIn(topic, agent._effective_topics())
        self.assertIn(skill, agent._effective_skills())
        offered = runtime._resolve_tools(self._uenv(self.user), agent)
        self.assertIn('zz_later_tool', offered.mapped('code'))
        # A plain agent does not get it.
        self.assertNotIn(tool, other._effective_tools())

    def test_group_restricted_tool_still_filtered(self):
        tool = self.env['ai.agent.tool'].create({
            'name': 'Admin only', 'code': 'zz_admin_only', 'description': 'x',
            'group_ids': [(6, 0, [self.env.ref('base.group_system').id])]})
        offered = runtime._resolve_tools(self._uenv(self.user), self.assistant.with_user(self.user))
        self.assertNotIn(tool.code, offered.mapped('code'))

    # ── (2) generic tools: the user's rights, nothing more ──────────

    def test_record_rules_apply(self):
        env = self._uenv(self.user)
        res = generic_data.search_records(env, model='res.partner',
                                          domain=[['name', 'ilike', 'Zyx']], fields=['name'])
        names = {r['name'] for r in res['records']}
        self.assertIn('Zyx Visible Co', names)
        self.assertNotIn('Zyx Hidden Co', names)
        self.assertEqual(generic_data.count_records(env, model='res.partner',
                                                    domain=[['name', 'ilike', 'Zyx Hidden']])['count'], 0)
        got = generic_data.get_record(env, model='res.partner', record=self.hidden.id)
        self.assertIn('error', got)

    def test_model_without_acl_refused(self):
        env = self._uenv(self.user)
        target = next((m for m in ('account.move', 'sale.order', 'purchase.order', 'hr.contract',
                                   'stock.picking') if m in env
                       and not env[m].has_access('read')), None)
        if not target:
            self.skipTest('no business model without read access for a plain user')
        res = generic_data.search_records(env, model=target)
        self.assertEqual(res.get('error'), 'not permitted')

    def test_blocked_models_and_secret_fields(self):
        env = self._uenv(self.user)
        for model in ('ir.config_parameter', 'res.groups', 'ir.cron', 'ai.agent.run'):
            self.assertEqual(generic_data.search_records(env, model=model).get('error'),
                             'not permitted', model)
        # res.users readable, but never its secrets — not as a column, not as a filter.
        self.assertIn('error', generic_data.search_records(env, model='res.users', fields=['password']))
        self.assertIn('error', generic_data.search_records(
            env, model='res.users', domain=[['password', '=', 'x']]))
        # Base settings: admin only.
        self.assertEqual(generic_data.search_records(env, model='res.company').get('error'),
                         'not permitted')
        self.assertNotIn('error', generic_data.search_records(self.env, model='res.company'))
        # No writes to users through the assistant, even for an admin.
        from odoo.addons.ab_ai_agent.services import agent_actions
        res = agent_actions.create_record(self.env, model='res.users', values={'name': 'x'})
        self.assertEqual(res.get('error'), 'not permitted')

    def test_caps(self):
        env = self._uenv(self.user)
        res = generic_data.search_records(env, model='res.partner', limit=1000)
        self.assertLessEqual(res['count'], generic_data.MAX_ROWS)

    # ── (3) builder ──────────────────────────────────────────────────

    def test_builder_requires_designer(self):
        Agent = self.env['ai.agent'].with_user(self.user)
        with self.assertRaises(AccessError):
            Agent.builder_create_tool({'model': 'res.partner', 'op': 'search'})
        with self.assertRaises(AccessError):
            Agent.builder_create_skill(self.assistant.id, {'name': 'x', 'template': '{message}'})
        with self.assertRaises(AccessError):
            Agent.builder_create_topic(self.assistant.id, {'name': 'x'})
        with self.assertRaises(AccessError):
            Agent.builder_models('partner')

    def test_builder_tool_end_to_end(self):
        Agent = self.env['ai.agent'].with_user(self.designer)
        self.assertTrue(any(m['model'] == 'res.partner' for m in Agent.builder_models('res.partner')))
        self.assertFalse(any(m['model'].startswith('ir.') for m in Agent.builder_models('ir.')))
        made = Agent.builder_create_tool({
            'model': 'res.partner', 'op': 'search',
            'domain': [['is_company', '=', True]], 'fields': ['name', 'is_company']})
        tool = self.env['ai.agent.tool'].browse(made['id'])
        self.assertTrue(tool.is_custom)
        self.assertFalse(tool.is_write_action)
        self.assertIn(tool, self.assistant._effective_tools())
        # Runs as the chatting user, through every dispatcher gate.
        env = self._uenv(self.user)
        out = tool_dispatcher.dispatch(env, tool.with_env(env),
                                       {'domain': [['name', 'ilike', 'Zyx']]},
                                       agent=self.assistant.with_env(env))
        self.assertTrue(out['ok'], out)
        names = {r['name'] for r in out['result']['records']}
        self.assertEqual(names, {'Zyx Visible Co'})           # fixed filter + record rule
        # The model cannot widen the fixed filter.
        out = tool_dispatcher.dispatch(env, tool.with_env(env),
                                       {'domain': ['|', ['is_company', '=', False], ['id', '>', 0]]},
                                       agent=self.assistant.with_env(env))
        self.assertTrue(all(r['is_company'] for r in out['result']['records']))

    def test_builder_create_preset_only_proposes(self):
        made = self.env['ai.agent'].with_user(self.designer).builder_create_tool(
            {'model': 'res.partner', 'op': 'create'})
        tool = self.env['ai.agent.tool'].browse(made['id'])
        # A user without create rights on partners is refused outright…
        env = self._uenv(self.user)
        out = tool_dispatcher.dispatch(env, tool.with_env(env), {'values': {'name': 'Zyx Proposed'}},
                                       agent=self.assistant.with_env(env))
        self.assertEqual(out['result'].get('error'), 'not permitted')
        # …one with rights only gets a proposal: nothing is created yet.
        env = self._uenv(self.designer)
        out = tool_dispatcher.dispatch(env, tool.with_env(env), {'values': {'name': 'Zyx Proposed'}},
                                       agent=self.assistant.with_env(env))
        self.assertTrue(out['ok'], out)
        self.assertFalse(self.env['res.partner'].search_count([('name', '=', 'Zyx Proposed')]))
        self.assertTrue(out['result'].get('requires_confirmation')
                        or out['result'].get('need_info'), out['result'])

    def test_builder_blocks_bad_input(self):
        Agent = self.env['ai.agent'].with_user(self.designer)
        with self.assertRaises(UserError):
            Agent.builder_create_tool({'model': 'ir.config_parameter', 'op': 'search'})
        with self.assertRaises(UserError):
            Agent.builder_create_tool({'model': 'res.users', 'op': 'update'})
        with self.assertRaises(UserError):
            Agent.builder_create_tool({'model': 'res.partner', 'op': 'search',
                                       'domain': [['nope_field', '=', 1]]})
        with self.assertRaises(UserError):
            Agent.builder_create_skill(self.assistant.id, {'name': 'S', 'template': 'Hi {secret}'})

    def test_builder_skill_topic_and_protection(self):
        Agent = self.env['ai.agent'].with_user(self.designer)
        sk = Agent.builder_create_skill(self.assistant.id, {
            'name': 'Partner brief', 'template': 'Brief me on {record_name}: {message}',
            'context_model': 'res.partner'})
        skill = self.env['ai.agent.skill'].browse(sk['id'])
        self.assertTrue(skill.is_global and skill.is_custom and skill.requires_record_context)
        self.assertIn(skill, self.assistant._effective_skills())
        tool = self.env.ref('ab_ai_agent.tool_find_records')
        tp = Agent.builder_create_topic(self.assistant.id, {
            'name': 'Partners', 'instructions': 'Use it.', 'tool_ids': [tool.id]})
        topic = self.env['ai.agent.topic'].browse(tp['id'])
        self.assertEqual(topic.tool_ids, tool)
        # Shipped records are protected from designers.
        with self.assertRaises(UserError):
            Agent.builder_update_tool(tool.id, {'name': 'hijack'})
        with self.assertRaises(UserError):
            tool.with_user(self.designer).unlink()
        Agent.builder_delete('topic', topic.id)
        self.assertFalse(topic.exists())
        payload = self.assistant.with_user(self.designer).console_payload()
        self.assertTrue(payload['full_access'])
        self.assertTrue(any(s['id'] == skill.id for s in payload['skills']))

    # ── review fixes ──────────────────────────────────────────────

    def test_dotted_path_cannot_reach_blocked_data(self):
        env = self._uenv(self.user)
        for dom in ([['user_ids.groups_id.name', '=', 'Settings']],
                    [['create_uid.password', '=', 'x']],
                    [['message_ids.body', 'ilike', 'x']],
                    [['name.foo', '=', 'x']]):
            out = generic_data.count_records(env, model='res.partner', domain=dom)
            self.assertIn('error', out, dom)
        # One allowed hop still works.
        out = generic_data.count_records(env, model='res.partner',
                                         domain=[['parent_id.name', 'ilike', 'Zyx']])
        self.assertNotIn('error', out, out)
        # Without a model only plain fields pass.
        with self.assertRaises(ValueError):
            generic_data.safe_domain([['parent_id.name', '=', 'x']], {'parent_id': {}})

    def test_write_presets_obey_gates(self):
        made = self.env['ai.agent'].with_user(self.designer).builder_create_tool(
            {'model': 'res.partner', 'op': 'create'})
        tool = self.env['ai.agent.tool'].browse(made['id'])
        env = self._uenv(self.designer)
        agent = self.assistant.with_env(env)
        self.assertIn(tool.code, runtime._resolve_tools(env, agent).mapped('code'))
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.actions_enabled', 'False')
        self.assertNotIn(tool.code, runtime._resolve_tools(env, agent).mapped('code'))
        out = generic_data.run_preset(env, tool.with_env(env), agent=agent,
                                      values={'name': 'Zyx Gate'})
        self.assertEqual(out.get('error'), 'not permitted')
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.actions_enabled', 'True')
        self.assistant.allow_write_actions = False
        self.assertNotIn(tool.code, runtime._resolve_tools(env, agent).mapped('code'))
        out = generic_data.run_preset(env, tool.with_env(env), agent=agent,
                                      values={'name': 'Zyx Gate'})
        self.assertEqual(out.get('error'), 'not permitted')

    def test_proposal_tools_follow_agent_write_permission(self):
        """screen_button / act_on_record confirm, post or validate records:
        an agent without write permission must not offer them."""
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.actions_enabled', 'True')
        proposal = {'screen_button', 'act_on_record'}
        self.assistant.allow_write_actions = True
        offered = set(runtime._resolve_tools(self.env, self.assistant).mapped('code'))
        if not proposal & offered:
            self.skipTest('proposal tools are not installed on this database')
        self.assistant.allow_write_actions = False
        self.assertFalse(proposal & set(runtime._resolve_tools(self.env, self.assistant).mapped('code')))

    def test_quota_message_names_the_cap(self):
        daily = runtime._quota_envelope('en', Exception('Daily token limit exceeded (5/5)'))['response']
        monthly = runtime._quota_envelope('ar', Exception('Monthly token limit exceeded (5/5)'))['response']
        self.assertIn('midnight', daily)
        self.assertIn('الشهرية', monthly)
        self.assertIn('renews', runtime._quota_envelope('en')['response'])

    def test_edit_keeps_filter_and_arabic_name(self):
        Agent = self.env['ai.agent'].with_user(self.designer)
        made = Agent.builder_create_tool({
            'model': 'res.partner', 'op': 'search', 'name': 'شركات زيكس', 'name_lang': 'ar',
            'domain': [['is_company', '=', True]]})
        tool = self.env['ai.agent.tool'].browse(made['id'])
        # Edit without domain/fields (what the dialog sends when untouched).
        Agent.builder_update_tool(tool.id, {'name': 'Zyx companies', 'name_lang': 'en'})
        preset = json.loads(tool.preset_json)
        self.assertEqual(preset['domain'], [['is_company', '=', True]])
        self.assertEqual(tool.with_context(lang='en_US').name, 'Zyx companies')
        if self.env['res.lang']._lang_get('ar_001'):
            self.assertEqual(tool.with_context(lang='ar_001').name, 'شركات زيكس')
        payload = tool._builder_edit_payload()
        self.assertEqual(payload['preset_domain'], [['is_company', '=', True]])

    def test_arabic_question_routes_builder_tools(self):
        Agent = self.env['ai.agent'].with_user(self.designer)
        made = [Agent.builder_create_tool({'model': 'res.partner', 'op': 'count',
                                           'name': f'Zyx tool {i}'}) for i in range(10)]
        tools = self.env['ai.agent.tool'].browse([m['id'] for m in made])
        if not self.env['res.lang']._lang_get('ar_001'):
            return
        label_ar = self.env['res.partner'].with_context(lang='ar_001')._description
        kept = runtime._route_builder_tools(tools, f' كم عدد {label_ar} ')
        self.assertTrue(kept, label_ar)

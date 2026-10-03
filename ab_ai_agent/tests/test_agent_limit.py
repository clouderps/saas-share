from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAgentLimit(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Agent = self.env['ai.agent']
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.Agent.search([('active', '=', True), ('is_system', '=', False)]).write({'active': False})
        self.system = self.Agent.search([('active', '=', True)])

    def _agent(self, code, **kw):
        return self.Agent.create(dict({'name': code, 'code': code, 'surface_ids': 'chatter'}, **kw))

    def test_no_limit_means_everyone_works(self):
        self.ICP.set_param('ab_ai_agent.max_agents', '0')
        self._agent('x1'); self._agent('x2')
        self.assertIsNone(self.Agent._working_agent_ids())

    def test_limit_blocks_activating_one_too_many(self):
        self.ICP.set_param('ab_ai_agent.max_agents', str(len(self.system) + 1))
        self._agent('ok1')
        with self.assertRaises(ValidationError):
            self._agent('too_many')

    def test_module_data_never_breaks_on_the_limit(self):
        self.ICP.set_param('ab_ai_agent.max_agents', str(len(self.system)))
        extra = self.Agent.with_context(install_mode=True).create(
            {'name': 'shipped', 'code': 'shipped', 'surface_ids': 'chatter'})
        working = self.Agent._working_agent_ids()
        self.assertNotIn(extra.id, working)          # loads, but does not answer
        self.assertTrue(set(self.system.ids) <= working)  # the assistant always works

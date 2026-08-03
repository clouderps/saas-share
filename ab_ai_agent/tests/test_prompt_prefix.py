# -*- coding: utf-8 -*-
"""The system prompt must open with a question-invariant prefix.

A provider prefix cache only matches a byte-identical head. The blocks
that never change — persona, report/chart rendering rules, topic
instructions, the tool protocol — therefore have to come FIRST, ahead of
the live snapshot, the retrieved knowledge and the date.

They used to be interleaved, which meant no two requests shared a prefix
and nothing was cacheable however the flags were set. These tests exist
so that ordering cannot quietly regress: appending a volatile block in
the wrong place is an easy, invisible mistake.
"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services.runtime import _compose_system_prompt


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestPromptPrefix(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['ai.agent'].search(
            [('code', '=', 'ghaima_assistant')], limit=1)

    def _prompt(self, question):
        return _compose_system_prompt(
            self.env, self.agent, locale='en', user_question=question)

    @staticmethod
    def _shared_prefix(a, b):
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return n

    def test_two_questions_share_a_long_prefix(self):
        """The whole point. Two unrelated questions must produce prompts
        that agree for thousands of characters before diverging."""
        a = self._prompt('How many products do we have?')
        b = self._prompt('Where do I create a credit note?')
        shared = self._shared_prefix(a, b)
        self.assertGreater(
            shared, 2000,
            'only %d chars shared — a volatile block has moved into the '
            'prefix and broken prefix caching' % shared)

    def test_the_prefix_is_most_of_the_prompt(self):
        a = self._prompt('sales today')
        b = self._prompt('who is on leave?')
        shared = self._shared_prefix(a, b)
        self.assertGreater(
            shared / max(len(a), 1), 0.30,
            'less than 30%% of the prompt is cacheable (%d of %d chars)'
            % (shared, len(a)))

    def test_invariant_blocks_precede_volatile_ones(self):
        """Order, asserted on markers rather than on exact text so
        wording can change without breaking the test."""
        prompt = self._prompt('anything at all')

        tool_protocol = prompt.find('## Tool')
        snapshot = prompt.find('Live business snapshot')
        today = prompt.find('## Today')

        self.assertNotEqual(tool_protocol, -1, 'tool protocol block missing')
        for name, pos in (('snapshot', snapshot), ('today', today)):
            if pos != -1:
                self.assertLess(
                    tool_protocol, pos,
                    'the tool protocol (invariant, large) must come before '
                    'the %s block (volatile) or it cannot be cached' % name)

    def test_persona_still_opens_the_prompt(self):
        """Reordering must not have displaced the persona from the top —
        it sets the tone for everything after it."""
        prompt = self._prompt('hello')
        self.assertTrue(
            prompt.lstrip().startswith((self.agent.system_prompt or '')[:40].lstrip()),
            'the agent persona must remain the first thing the model reads')

    def test_nothing_was_dropped_in_the_reorder(self):
        """Reordering is not deletion — every block still has to be
        present, otherwise answers silently lose grounding."""
        prompt = self._prompt('how are sales this month?')
        self.assertIn('## Today', prompt)
        self.assertGreater(len(prompt), 1500)

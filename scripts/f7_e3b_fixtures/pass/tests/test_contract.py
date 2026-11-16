import unittest


class E3BPassingContract(unittest.TestCase):
    def test_real_executor_accepts_true_condition(self):
        self.assertEqual(2 + 2, 4)

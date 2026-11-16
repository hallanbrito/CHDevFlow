import unittest


class E3BFailingContract(unittest.TestCase):
    def test_real_executor_refuses_bad_result(self):
        self.assertEqual(2 + 2, 5)

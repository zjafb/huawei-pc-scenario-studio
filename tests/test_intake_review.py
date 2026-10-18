"""Independent ambiguity checks; these are synthetic requests, not real runs."""
import unittest

from app.intake import resolve


class IntakeReviewTests(unittest.TestCase):
    def intake(self, product, free_text="", variant="标准版", os_name="Windows"):
        return resolve(product=product, audience="大学新生", scene="school", platform="moments",
                       variant=variant, os_name=os_name, free_text=free_text)

    def test_wrong_year_is_not_assumed_2024(self):
        self.assertNotEqual("ok", self.intake("MateBook D 14 2023").status)

    def test_model_prefix_does_not_match_different_number(self):
        self.assertNotEqual("ok", self.intake("D140 2024").status)

    def test_both_variants_need_choice(self):
        result = self.intake("D 14 2024 标准版和 SE 版", variant="")
        self.assertNotEqual("ok", result.status)

    def test_both_operating_systems_need_choice(self):
        result = self.intake("D 14 2024 Windows 和 Linux", os_name="")
        self.assertNotEqual("ok", result.status)

    def test_exact_model_configuration_can_proceed(self):
        self.assertEqual("ok", self.intake("MateBook D 14 2024").status)


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.generate_tts import detect_gender, detect_contact_gender, get_dialogue_voices

class TestGenderIdentification(unittest.TestCase):

    def test_detect_gender_female_cues(self):
        self.assertEqual(detect_gender("I (24F) am having trouble with my husband."), "female")
        self.assertEqual(detect_gender("As a 28 year old woman, I refused to pay."), "female")
        self.assertEqual(detect_gender("My fiancé dumped me right before the wedding."), "female")
        self.assertEqual(detect_gender("My boyfriend of 3 years lied to me."), "female")

    def test_detect_gender_male_cues(self):
        self.assertEqual(detect_gender("I (29M) caught my wife lying about money."), "male")
        self.assertEqual(detect_gender("As a guy, I never expected my girlfriend to do this."), "male")
        self.assertEqual(detect_gender("My wife asked for a divorce out of nowhere."), "male")
        self.assertEqual(detect_gender("My fiancée broke off our engagement."), "male")

    def test_detect_contact_gender_male_names_and_roles(self):
        self.assertEqual(detect_contact_gender("Landlord Dave"), "male")
        self.assertEqual(detect_contact_gender("Boss Mike"), "male")
        self.assertEqual(detect_contact_gender("Brother Tom"), "male")
        self.assertEqual(detect_contact_gender("Fiancé Mark"), "male")
        self.assertEqual(detect_contact_gender("Ex-Husband"), "male")
        self.assertEqual(detect_contact_gender("Dad"), "male")

    def test_detect_contact_gender_female_names_and_roles(self):
        self.assertEqual(detect_contact_gender("Bridezilla Sarah"), "female")
        self.assertEqual(detect_contact_gender("Sister Emily"), "female")
        self.assertEqual(detect_contact_gender("Mom"), "female")
        self.assertEqual(detect_contact_gender("Karen Neighbor"), "female")
        self.assertEqual(detect_contact_gender("Ex-Wife"), "female")
        self.assertEqual(detect_contact_gender("Mother-in-law"), "female")

    def test_dialogue_voices_same_gender_male_distinct(self):
        me_edge, contact_edge, me_google, contact_google = get_dialogue_voices("male", "male")
        # Ensure voices are distinct and not identical
        self.assertNotEqual(me_edge, contact_edge)
        self.assertNotEqual(me_google, contact_google)
        self.assertIn("Christopher", me_edge)
        self.assertIn("Guy", contact_edge)

    def test_dialogue_voices_same_gender_female_distinct(self):
        me_edge, contact_edge, me_google, contact_google = get_dialogue_voices("female", "female")
        # Ensure voices are distinct and not identical
        self.assertNotEqual(me_edge, contact_edge)
        self.assertNotEqual(me_google, contact_google)
        self.assertIn("Jenny", me_edge)
        self.assertIn("Aria", contact_edge)

    def test_dialogue_voices_female_to_male(self):
        me_edge, contact_edge, me_google, contact_google = get_dialogue_voices("female", "male")
        self.assertIn("Jenny", me_edge)
        self.assertIn("Guy", contact_edge)

    def test_dialogue_voices_male_to_female(self):
        me_edge, contact_edge, me_google, contact_google = get_dialogue_voices("male", "female")
        self.assertIn("Christopher", me_edge)
        self.assertIn("Jenny", contact_edge)


if __name__ == "__main__":
    unittest.main()

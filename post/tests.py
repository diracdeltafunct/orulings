from django.test import TestCase
from django.contrib.auth.models import User
from post.models import PersonalNote, Post, RuleSection, Tag
from django.utils import timezone
from django.urls import reverse

from post.models import UserProfile

class PostModelTest(TestCase):
    def setUp(self):
        # Create a sample user for testing
        self.user = User.objects.create_user(username='testuser', password='testpassword')

        # Create a sample tag for testing
        self.tag = Tag.objects.create(name='Test Tag')

        # Create a sample post for testing
        self.post = Post.objects.create(
            title='Test Post',
            content='This is a test post content.',
            pub_date=timezone.now(),
            tag=self.tag,
            author=self.user
        )

    def test_post_title(self):
        self.assertEqual(str(self.post), 'Test Post')

    def test_post_content(self):
        self.assertEqual(self.post.content, 'This is a test post content.')

    def test_post_pub_date(self):
        # Ensure pub_date is within a reasonable timeframe
        self.assertLess(self.post.pub_date, timezone.now())

    def test_post_tag(self):
        self.assertEqual(self.post.tag, self.tag)

    def test_post_author(self):
        self.assertEqual(self.post.author, self.user)

    def test_post_str_representation(self):
        expected_str = f'{self.post.title}'
        self.assertEqual(str(self.post), expected_str)


class AccountTests(TestCase):
    def test_signup_creates_contributor_and_profile(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newuser",
                "name": "New User",
                "email": "new@example.com",
                "discord_handle": "newuser123",
                "password1": "A-secure-password-456!",
                "password2": "A-secure-password-456!",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        user = User.objects.get(username="newuser")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.first_name, "New User")
        self.assertEqual(user.profile.discord_handle, "newuser123")

    def test_contributor_cannot_manage_roles(self):
        contributor = User.objects.create_user("contributor", password="password")
        self.client.force_login(contributor)

        response = self.client.get(reverse("manage_users"))

        self.assertEqual(response.status_code, 403)

    def test_staff_can_promote_contributor_to_staff(self):
        staff = User.objects.create_user("staff", password="password", is_staff=True)
        contributor = User.objects.create_user("contributor", password="password")
        self.client.force_login(staff)

        response = self.client.post(
            reverse("update_user_role", args=[contributor.pk]), {"role": "staff"}
        )

        self.assertRedirects(response, reverse("manage_users"))
        contributor.refresh_from_db()
        self.assertTrue(contributor.is_staff)
        self.assertFalse(contributor.is_superuser)

    def test_staff_cannot_assign_admin(self):
        staff = User.objects.create_user("staff", password="password", is_staff=True)
        contributor = User.objects.create_user("contributor", password="password")
        self.client.force_login(staff)

        self.client.post(
            reverse("update_user_role", args=[contributor.pk]), {"role": "admin"}
        )

        contributor.refresh_from_db()
        self.assertFalse(contributor.is_superuser)

    def test_staff_cannot_modify_admin(self):
        staff = User.objects.create_user("staff", password="password", is_staff=True)
        admin_user = User.objects.create_superuser(
            "adminuser", "admin@example.com", "password"
        )
        self.client.force_login(staff)

        self.client.post(
            reverse("update_user_role", args=[admin_user.pk]), {"role": "contributor"}
        )

        admin_user.refresh_from_db()
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_staff)

    def test_admin_can_assign_admin(self):
        admin_user = User.objects.create_superuser(
            "adminuser", "admin@example.com", "password"
        )
        contributor = User.objects.create_user("contributor", password="password")
        self.client.force_login(admin_user)

        self.client.post(
            reverse("update_user_role", args=[contributor.pk]), {"role": "admin"}
        )

        contributor.refresh_from_db()
        self.assertTrue(contributor.is_superuser)
        self.assertTrue(contributor.is_staff)

    def test_profile_update(self):
        user = User.objects.create_user("member", password="password")
        self.client.force_login(user)

        response = self.client.post(
            reverse("profile"),
            {
                "name": "Updated Name",
                "email": "updated@example.com",
                "discord_handle": "updated_handle",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Updated Name")
        self.assertEqual(user.email, "updated@example.com")
        self.assertEqual(UserProfile.objects.get(user=user).discord_handle, "updated_handle")


class PersonalNoteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("noteowner", password="password")
        self.other_user = User.objects.create_user("otheruser", password="password")
        self.rule = RuleSection.objects.create(
            rule_type="CR", section="100", text="A test rule"
        )

    def test_authenticated_user_can_save_sanitized_personal_note(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("save_personal_note"),
            data='{"rule_type":"CR","section":"100","note":"<p>Mine</p><script>bad()</script>"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        note = PersonalNote.objects.get(user=self.user, rule_section=self.rule)
        self.assertEqual(note.content, "<p>Mine</p>bad()")

    def test_personal_notes_are_private_on_rule_page(self):
        PersonalNote.objects.create(
            user=self.user, rule_section=self.rule, content="Owner-only note"
        )
        PersonalNote.objects.create(
            user=self.other_user, rule_section=self.rule, content="Other user's secret"
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("crsection_detail", args=["100"]))

        self.assertContains(response, "Owner-only note")
        self.assertNotContains(response, "Other user's secret")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_saving_empty_note_deletes_it(self):
        PersonalNote.objects.create(
            user=self.user, rule_section=self.rule, content="Delete me"
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("save_personal_note"),
            data='{"rule_type":"CR","section":"100","note":""}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            PersonalNote.objects.filter(user=self.user, rule_section=self.rule).exists()
        )

    def test_anonymous_user_cannot_save_personal_note(self):
        response = self.client.post(
            reverse("save_personal_note"),
            data='{"rule_type":"CR","section":"100","note":"No access"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PersonalNote.objects.exists())

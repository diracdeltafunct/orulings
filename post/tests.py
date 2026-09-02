import json

from django.test import TestCase
from django.contrib.auth.models import User
from post.models import AnnotationProposal, PersonalNote, Post, RuleSection, Tag
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

    def test_personal_note_cannot_exceed_2000_visible_characters(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("save_personal_note"),
            data=json.dumps(
                {"rule_type": "CR", "section": "100", "note": "x" * 2001}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PersonalNote.objects.exists())

    def test_personal_note_allows_2000_visible_characters(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("save_personal_note"),
            data=json.dumps(
                {"rule_type": "CR", "section": "100", "note": "x" * 2000}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PersonalNote.objects.get(user=self.user).content), 2000
        )


class AnnotationApprovalTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user("contributor", password="password")
        self.staff = User.objects.create_user(
            "staff", password="password", is_staff=True
        )
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        self.rule = RuleSection.objects.create(
            rule_type="CR",
            section="200",
            text="Approval test rule",
            annotations="<p>Current annotation</p>",
        )

    def submit_annotation(self, user, content):
        self.client.force_login(user)
        return self.client.post(
            reverse("save_annotation"),
            data=json.dumps(
                {"rule_type": "CR", "section": "200", "annotation": content}
            ),
            content_type="application/json",
        )

    def test_contributor_edit_is_pending_and_not_public(self):
        response = self.submit_annotation(
            self.contributor, "<p>Proposed annotation</p><script>bad()</script>"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["pending"])
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.annotations, "<p>Current annotation</p>")
        proposal = AnnotationProposal.objects.get()
        self.assertEqual(proposal.status, AnnotationProposal.Status.PENDING)
        self.assertEqual(proposal.content, "<p>Proposed annotation</p>bad()")

    def test_staff_edit_is_published_immediately(self):
        response = self.submit_annotation(self.staff, "<p>Staff annotation</p>")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("pending", response.json())
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.annotations, "<p>Staff annotation</p>")
        self.assertFalse(AnnotationProposal.objects.exists())

    def test_only_admin_can_access_review_queue(self):
        for user in (self.contributor, self.staff):
            self.client.force_login(user)
            response = self.client.get(reverse("annotation_review_queue"))
            self.assertEqual(response.status_code, 403)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("annotation_review_queue"))
        self.assertEqual(response.status_code, 200)

    def test_admin_approval_publishes_proposal(self):
        proposal = AnnotationProposal.objects.create(
            rule_section=self.rule,
            submitted_by=self.contributor,
            content="<p>Approved annotation</p>",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("review_annotation_proposal", args=[proposal.pk, "approve"])
        )

        self.assertRedirects(response, reverse("annotation_review_queue"))
        proposal.refresh_from_db()
        self.rule.refresh_from_db()
        self.assertEqual(proposal.status, AnnotationProposal.Status.APPROVED)
        self.assertEqual(proposal.reviewed_by, self.admin)
        self.assertIsNotNone(proposal.reviewed_at)
        self.assertEqual(self.rule.annotations, "<p>Approved annotation</p>")
        self.client.logout()
        public_response = self.client.get(reverse("crsection_detail", args=["200"]))
        self.assertContains(public_response, "Approved annotation")

    def test_admin_rejection_does_not_change_public_annotation(self):
        proposal = AnnotationProposal.objects.create(
            rule_section=self.rule,
            submitted_by=self.contributor,
            content="<p>Rejected annotation</p>",
        )
        self.client.force_login(self.admin)

        self.client.post(
            reverse("review_annotation_proposal", args=[proposal.pk, "reject"])
        )

        proposal.refresh_from_db()
        self.rule.refresh_from_db()
        self.assertEqual(proposal.status, AnnotationProposal.Status.REJECTED)
        self.assertEqual(self.rule.annotations, "<p>Current annotation</p>")


class AttributionTests(TestCase):
    def setUp(self):
        self.rule = RuleSection.objects.create(
            rule_type="TR", section="300", text="Attribution test rule"
        )

    def create_proposal(self, user, status):
        return AnnotationProposal.objects.create(
            rule_section=self.rule,
            submitted_by=user,
            content="A contribution",
            status=status,
        )

    def test_only_users_with_approved_contributions_are_listed(self):
        approved_user = User.objects.create_user(
            "approved", first_name="Approved Person"
        )
        pending_user = User.objects.create_user("pending", first_name="Pending Person")
        rejected_user = User.objects.create_user(
            "rejected", first_name="Rejected Person"
        )
        self.create_proposal(approved_user, AnnotationProposal.Status.APPROVED)
        self.create_proposal(pending_user, AnnotationProposal.Status.PENDING)
        self.create_proposal(rejected_user, AnnotationProposal.Status.REJECTED)

        response = self.client.get(reverse("attribution"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approved Person")
        self.assertNotContains(response, "Pending Person")
        self.assertNotContains(response, "Rejected Person")

    def test_contributor_is_listed_once_with_accepted_count(self):
        user = User.objects.create_user("repeat", first_name="Repeat Contributor")
        self.create_proposal(user, AnnotationProposal.Status.APPROVED)
        self.create_proposal(user, AnnotationProposal.Status.APPROVED)

        response = self.client.get(reverse("attribution"))

        self.assertContains(response, "Repeat Contributor", count=1)
        self.assertContains(response, "2 accepted contributions")

    def test_username_is_used_when_profile_name_is_blank(self):
        user = User.objects.create_user("fallback-user")
        self.create_proposal(user, AnnotationProposal.Status.APPROVED)

        response = self.client.get(reverse("attribution"))

        self.assertContains(response, "fallback-user")


class ContributionGuideTests(TestCase):
    def test_contribution_guide_is_public_and_links_to_signup(self):
        response = self.client.get(reverse("how_to_contribute"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("signup"))
        self.assertContains(response, "Contributor submissions enter an approval queue")
        self.assertContains(response, "Personal notes are private to your account")

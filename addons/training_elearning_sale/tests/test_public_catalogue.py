from odoo.addons.training_elearning.tests.test_activities import LessonCase
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestPublicElearningRegistration(LessonCase, HttpCase):
    def test_public_shop_product_and_cart_leave_learning_private(self):
        if not hasattr(self.env["website"], "sale_product_domain"):
            self.skipTest("Website Sale is optional")
        course = self.course(learning_public_catalogue=True)
        article = self.article(course)
        course.action_learning_publish()
        manager = new_test_user(
            self.env,
            login="fictional_shop_learning_manager",
            groups="training_elearning_sale.group_learning_sales_manager",
        )
        product = self.env["product.template"].with_user(manager).create(
            {
                "name": "Fictional autonomous shop offer",
                "type": "service",
                "list_price": 100,
                "learning_channel_id": course.id,
                "service_tracking": "no",
            }
        )
        url = f"/formations/catalogue/{self.catalog.id}"
        self.authenticate(None, None)
        self.assertNotIn(product.website_url, self.url_open(url).text)
        product.sudo().is_published = True
        website = self.env["website"].search([], order="sequence, id", limit=1)
        other_site = self.env["website"].create(
            {"name": "Other fictional site", "company_id": website.company_id.id, "sequence": website.sequence + 10}
        )
        product.sudo().website_id = other_site.id
        self.assertNotIn(product.website_url, self.url_open(url).text)
        product.sudo().website_id = website.id
        page = self.url_open(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn(product.website_url, page.text)
        self.assertIn("S’inscrire en eLearning", page.text)
        self.assertNotIn("Demander une offre autonome", page.text)
        self.assertNotIn(article.name, page.text)
        self.assertEqual(self.url_open(product.website_url).status_code, 200)
        result = self.url_open(
            "/shop/cart/add",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "product_template_id": product.id,
                    "product_id": product.product_variant_id.id,
                    "quantity": 1,
                },
                "id": 1,
            },
        ).json()
        self.assertNotIn("error", result, result)
        line = self.env["sale.order.line"].search([("product_id", "=", product.product_variant_id.id)])
        self.assertTrue(line)
        self.assertEqual(line.learning_channel_id, course)
        self.assertEqual(line.order_id.state, "draft")
        self.assertFalse(course.sudo().channel_partner_ids)
        self.assertIn(self.url_open(article.website_url).status_code, (403, 404))
        course.write({"learning_public_catalogue": False})
        self.assertEqual(self.url_open(url).status_code, 404)

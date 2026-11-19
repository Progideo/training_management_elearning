"""Project native website shop links for explicitly commercial courses."""

from collections import defaultdict

from odoo import api, models
from odoo.fields import Domain
from odoo.tools import format_amount


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    @api.private
    def _catalogue_shop_offers(self, company):
        offers = super()._catalogue_shop_offers(company)
        # Use the same visibility rules as a visitor, including site and
        # product saleability. The public course flag alone never publishes a product.
        by_channel = defaultdict(list)
        for product in self._catalogue_shop_products(company):
            by_channel[product.learning_channel_id.id].append({"name": product.name, "url": product.website_url})
        return {**offers, **by_channel}

    @api.private
    def _catalogue_shop_products(self, company):
        """Products a visitor of this operator's website may buy for these courses."""
        website = self.env.website
        if not self or not website or website.company_id != company or not hasattr(website, "sale_product_domain"):
            return self.env["product.template"]
        visitor_site = website.with_user(website.user_id)
        return self.env["product.template"].sudo().search(
            Domain(visitor_site.sale_product_domain())
            & Domain("company_id", "=", company.id)
            & Domain("learning_channel_id", "in", self.ids)
            & Domain("active", "=", True),
            order="website_sequence, id",
        )


class TrainingCourse(models.Model):
    _inherit = "training.course"

    @api.private
    def _catalogue_facts(self, company):
        facts = super()._catalogue_facts(company)
        channels = self._catalogue_public_channels(company)
        products = channels._catalogue_shop_products(company)
        for course in self:
            autonomous = facts[course.id].get("autonomous")
            if not autonomous:
                continue
            offers = products.filtered(lambda p, t=course: p.learning_channel_id.training_course_id == t)
            if not offers:
                continue
            # Lowest public price, excluding taxes, in the product currency; « HT » is added by the page.
            prices = []
            for product in offers:
                taxes = product.taxes_id.filtered(lambda tax: tax.company_id == company)
                amount = taxes.compute_all(product.list_price, product.currency_id, 1.0, product=product)[
                    "total_excluded"
                ]
                prices.append((amount, product))
            amount, product = min(prices, key=lambda item: (item[0], item[1].id))
            autonomous.update(
                {
                    "access_months": product.learning_access_months,
                    "price": {"amount": amount, "label": format_amount(self.env, amount, product.currency_id)},
                }
            )
        return facts

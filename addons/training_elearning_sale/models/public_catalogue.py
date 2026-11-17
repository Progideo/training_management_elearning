"""Project native website shop links for explicitly commercial courses."""

from collections import defaultdict

from odoo import api, models
from odoo.fields import Domain


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    @api.private
    def _catalogue_shop_offers(self, company):
        offers = super()._catalogue_shop_offers(company)
        website = self.env.website
        if not self or not website or website.company_id != company or not hasattr(website, "sale_product_domain"):
            return offers
        # Use the same visibility rules as a visitor, including site and
        # product saleability. The public course flag alone never publishes a product.
        visitor_site = website.with_user(website.user_id)
        products = self.env["product.template"].sudo().search(
            Domain(visitor_site.sale_product_domain())
            & Domain("company_id", "=", company.id)
            & Domain("learning_channel_id", "in", self.ids)
            & Domain("active", "=", True),
            order="website_sequence, id",
        )
        by_channel = defaultdict(list)
        for product in products:
            by_channel[product.learning_channel_id.id].append({"name": product.name, "url": product.website_url})
        return {**offers, **by_channel}
